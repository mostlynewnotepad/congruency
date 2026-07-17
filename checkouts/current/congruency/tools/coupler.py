#!/usr/bin/env python3
"""coupler.py — THE COUPLER: the loop between codebean and the coding agent.

WHAT THIS IS. A senior hands the junior ONE function signature; the junior returns ONLY that
function's body; the machine (codebean's model) holds the skeleton and applies the decorators.
The junior is an LLM given TEXT and nothing else — it never sees a filesystem path, a tool, or a
repository. That is not a rule the junior is asked to obey; it is the shape of the prompt, so
"rewrite the whole module", "write to some other file" and "call a tool" are UNREPRESENTABLE
rather than merely discouraged.

WHY (the failure modes this removes, measured on the GLM canaries #414/#416): a worker told
"rewrite this module" returned 1791 lines for a 65-line decoy, wandered into an unrelated module
for ~18 steps, wrote to a plausible-but-wrong nested path, emitted a Bash `command` as a list and
needed ~33 steps against Claude's ~12. A worker handed `def call_tool(name, args):` and asked for
the body cannot do any of those things: the skeleton is not the LLM's to invent.

SCOPE: PYTHON ONLY. codebean is ast-based and cannot lower PHP. (By unique blob the forge is 89%
Python / 6% PHP — 5,119 of 5,736 unique code files.)

────────────────────────────────────────────────────────────────────────────────────────────────
THE SPINE IS REUSED, NOT REBUILT. Everything mechanical comes from
`codebean_mcp/prototype/code_wrapper.py`, imported at runtime (see `load_code_wrapper`):

    lower_functions(src_path) -> [Function]   the MOCK SENIOR: source -> signatures + docstrings
    lower_node(node)          -> Function     the per-node lowering lower_functions itself calls
    _ast_norm(src)            -> str          the SAME identity the ticketer uses
    critic(cand, original)    -> bool         _ast_norm(rendered) == _ast_norm(original)
    judge(cand)               -> (ok, [why])  decorator present, imports, one-def-per-artefact ...
    Candidate / Function / Module             the codebean model (model.py), incl. render()

THE SENIOR IS MECHANICAL, NOT AN LLM. For the refactor/PRESERVE case, `lower_functions` IS a
deterministic senior: it yields every signature and docstring from the original source. No senior
agent is built here, and none is needed.

────────────────────────────────────────────────────────────────────────────────────────────────
THE LOOP, per module:

  1. LOWER      the original -> one `Blank` per top-level function (signature, docstring, and the
                original body kept back as the hidden oracle).
  2. STRUCTURE  FIRST: every signature is laid down via `add_function` BEFORE any body is filled,
                so a body may call any sibling regardless of fill order. No topological sort.
  3. FILL       one function at a time. The junior is handed EXACTLY: its own signature and
                docstring, the sibling signatures (names and args only, no bodies), and the
                module's imports and constants. Nothing else.
  4. GATE       cheapest first: parse -> then `critic` for PRESERVE functions. `critic` is a
                MECHANICAL PROOF of behaviour preservation, not an auditor's prose opinion.

                WHICH WAY THE PROOF RUNS, exactly — because the difference decides how every
                number this tool prints must be read. critic PASSES only if the body is
                _ast_norm-identical to the original, so a PASS *proves* behaviour is preserved:
                comments, formatting and whitespace cannot fool it, and a changed constant or a
                dropped branch cannot survive it. The converse does NOT hold. A FAIL means "not
                the same code", NOT "wrong code": measured on pilot_pure.py, a junior answered
                `fib` with `if n < 2: return n` + a loop over `range(n - 1)` accumulating via its
                sibling `add(a, b)` — a correct Fibonacci that fails critic against an original
                spelled `a, b = (0, 1)` + a loop over `range(n)`. So critic is
                SOUND (no wrong body passes) but not COMPLETE (right bodies fail). That is the
                right bias for a refactor gate, and it is why the benchmark reports `reproduced`
                and `works` as two separate numbers instead of one "score".
  5. RETRY      per FUNCTION, never per module: a gate failure re-prompts that ONE function with
                the exact error (SyntaxError line N / the _ast_norm mismatch). After --attempts
                failures that ONE blank escalates to a stronger model. A bad body costs one
                re-prompt, never a module.

THE DOCSTRING BELONGS TO THE SKELETON. `lower_node` keeps a function's docstring as the first
statement of its *body* (its own docstring explains why: `render()` re-indents the model's `doc`
field blindly and corrupts multi-line docstrings). The docstring is the SENIOR's output — part of
`add_function` — so the machine re-attaches it and the junior returns only the statements after
it. Without this the junior would have to retype the docstring verbatim or fail `_ast_norm`, which
would measure typing, not coding.

THE CRITIC'S FEEDBACK NEVER CONTAINS THE ORIGINAL. A retry tells the junior that its body failed
to parse (its own SyntaxError) or failed the round-trip — never what the original said. If the
gate quoted the original body, the junior could copy it and the benchmark below would be
measuring an echo. `--selftest` asserts this.

────────────────────────────────────────────────────────────────────────────────────────────────
MODES (exactly one is required):

  --selftest                 A throwaway synthetic module, a SCRIPTED junior, no network, no live
                             db, and no writes outside the temp dir. Proves: structure-first; a
                             body that fails parse is re-prompted; a PRESERVE function that
                             differs semantically FAILS critic; one that differs only in
                             whitespace/comments PASSES; escalation fires after N; the junior is
                             never handed a path, a tool, or a sibling's body.

  --preserve --src M.py      Refill every body under the critic and emit the rebuilt module. It is
                             emitted ONLY if EVERY function passed the critic against the
                             original; otherwise nothing is emitted and the failures are named.
                             (Falling back to the original body for a function the junior could
                             not reproduce would make "passes critic" true by construction and
                             therefore worthless.)

  --benchmark --src M.py     THE BLANK-AND-REFILL BENCHMARK — how this tool proves itself. Blank
                             every body, have the junior refill it from signature+docstring, and
                             compare against the original kept back. Ground truth is free and 262
                             forge repos of real code are the corpus, which answers #173
                             ("benchmark on ACTUAL agent tasks, not generic evals") with numbers
                             instead of vibes. Per function it reports:
                               reproduced  `_ast_norm`-equal to the original (it wrote THE code)
                               works       it compiles AND passes code_wrapper's `judge`
                             Read them as two DIFFERENT questions, and neither one alone:
                               * "works" is exactly a compile+rules claim. It does NOT mean the
                                 module's test-suite passes; this tool runs no test-suite and does
                                 not pretend to.
                               * "reproduced" measures IDENTITY, not correctness (see THE GATE
                                 above): a correct body written differently counts as not
                                 reproduced. reproduced is therefore a LOWER bound on how often
                                 the junior was right, and the gap between the two columns is the
                                 rate at which it wrote good code that was not the original's.
                             A function the junior never ANSWERED (a stalled or unreachable
                             engine) is printed as `no answer` and left OUT of both rates, which
                             are taken over the answered functions only. An unanswered blank
                             leaves an empty body that assembles to `pass` — which compiles and
                             passes judge — so scoring it would report a dead backend as a junior
                             that works perfectly. If nothing was answered, nothing is measured
                             and the run exits 1.

ENGINES (--engine, default claude). The junior is text-in/text-out on every one of them:
  claude    `claude -p` with --json-schema (stdout is exactly the JSON object), a replaced system
            prompt, and every tool denied.
  cerebras  the litellm proxy's `worker` alias -> cerebras/zai-glm-4.7 (GLM 4.7), via
            ollama_agent.py's openai flavor.
  ollama    a local model over ollama_agent.py's ollama flavor.
  cerebras/ollama go through ollama_agent.constrained(), so the JSON-Schema + validate + corrective
  -retry channel is shared verbatim rather than re-implemented here. ollama_agent is imported
  LAZILY: --selftest never touches it, and so never needs a network or a registry.

  ESCALATION MAY CROSS ENGINES, and for cerebras it must — see the ESCALATION table for the
  probe. In short: openai_chat always sends one reasoning param, and every proxy alias except GLM
  4.7 either rejects both (gpt-oss-120b: HTTP 400), is not deployed (qwen-3-coder-480b: HTTP 404),
  or IS GLM 4.7 under another name. So `--engine cerebras` escalates ONE failed blank to claude —
  which is also the forge's own documented path for a GLM coder that cannot finish. Pass
  `--escalate-attempts 0` to keep a run inside its engine, or `--escalate-engine` to choose.

USAGE
    python3 coupler.py --selftest
    python3 coupler.py --benchmark --src <module.py> [--limit N] [--engine claude]
    python3 coupler.py --benchmark --src <module.py> --engine cerebras --json
    python3 coupler.py --preserve  --src <module.py> [--limit N] [--out rebuilt.py] [--mature]

MEASURED against the real forge module codebean_mcp/prototype/pilot_pure.py (4 pure, documented
functions: add, slugify, fib, clamp). Every line below is one observed run, so these commands are
known to run rather than merely intended to:
    --benchmark                    reproduced 2/4, works 4/4, first-shot 1/4, 58s
                                   (claude, the default: sonnet escalating to opus)
    --benchmark --engine cerebras  reproduced 2/4, works 4/4, first-shot 2/4, 66s (GLM 4.7)
    --preserve --attempts 6 --escalate-attempts 2
                                   2/4 pass critic; the module is therefore NOT emitted and the
                                   run exits 1, naming slugify and fib (claude, 221s)
    --preserve --limit 1 --mature  1/1 passes critic and the module IS emitted, 3s (claude). The
                                   emitted `add` was checked AST-identical to the original by a
                                   plain `ast.dump(ast.parse(...))` comparison OUTSIDE this tool —
                                   an oracle that is not the code under test.

WHICH FUNCTIONS REPRODUCE IS STRUCTURAL, NOT LUCK, and that is the most useful thing this module
measures. Both engines — Claude and GLM 4.7, independently — reproduced exactly `add` and `clamp`
and failed exactly `slugify` and `fib`. The two failures are not sampling noise; each has a cause
that no number of retries can remove:
  * slugify's original body opens with a function-local `import re`. `re` is NOT among the module's
    imports, so the junior — correctly reasoning that it may not use an unimported name — wrote a
    hand-rolled character loop instead. It cannot infer a private import it was never shown.
  * fib's original is one of several equally idiomatic spellings; the junior wrote another (and
    reached for its sibling `add`, which is structure-first working exactly as intended).
Both answers were CORRECT code. Both fail a gate that demands identity — which is the whole of the
`reproduced` vs `works` distinction above, observed rather than argued: works stayed 4/4 on both
engines while reproduced stayed 2/4.

So read `reproduced` as a LOWER bound on the junior and never as a grade. A module reproduces to
the extent its original is the obvious spelling of its docstring; where the original hides a quirk
the docstring does not imply, PRESERVE will refuse it forever, and refusing is the correct
behaviour — see run 3 above, which named its two failures and emitted nothing. What does NOT move
is the gate: nothing reaches the output that critic has not proven identical to the original.

EXIT CODES: 0 ok / 1 a mode reported failure / 2 a usage or environment error (one line, never a
traceback).
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Tool names the junior must never be handed. Checked case-sensitively against the coupler's OWN
# scaffold text (see audit_prompt) — never against the module's source, which may legitimately
# contain any word at all.
TOOL_NAMES = ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Bash", "Glob", "Grep",
              "Task", "WebFetch", "WebSearch", "TodoWrite")

BODY_SCHEMA = {"type": "object",
               "properties": {"body": {"type": "string"}},
               "required": ["body"],
               "additionalProperties": False}

# What a critic rejection is told back to the junior. Note what it is NOT: it quotes nothing from
# the original — it is this one CONSTANT string, so it cannot leak the answer no matter which
# module is being coupled. It exists because "does not round-trip the original" alone is unusable
# feedback: measured on pilot_pure.py, juniors answered `slugify` with a correct hand-rolled
# character loop and `fib` with a correct `if n < 2: return n` variant. Both are right, and
# both fail a gate that demands identity — so the junior has to be told that identity, not
# equivalence, is the bar. It moves some functions and not others, and it cannot conjure slugify's
# unshown function-local `import re` (see the module docstring); no honest hint can.
CRITIC_HINT = ("Your body must be AST-IDENTICAL to the original implementation, not merely "
               "equivalent to it. Emit the single most direct and idiomatic implementation the "
               "docstring describes — where an obvious one-expression form exists, that one, "
               "rather than a longer restatement of it.")

# The junior's whole system identity: a function-body generator. No repo, no tools, no paths.
JUNIOR_SYSTEM = ("You are a Python function-body generator. You are given one function signature, "
                 "its docstring, the signatures of its siblings, and the module's imports and "
                 "constants. You emit ONLY that one function's body statements, as JSON.")

# The base model each engine's junior runs on. --model overrides it.
ENGINE_MODELS = {
    "claude":   "sonnet",
    "cerebras": "worker",             # litellm alias -> cerebras/zai-glm-4.7 (GLM 4.7)
    "ollama":   "qwen2.5-coder:7b",   # == ollama_agent.ROLE_MODELS["worker"]
}

# Where ONE blank goes when it has failed --attempts times: (engine, model). Escalation may cross
# ENGINES, because "a stronger model" is not always one the current engine serves.
#
# cerebras escalates to claude, and that is measured, not preferred. ollama_agent's openai_chat
# ALWAYS sends exactly one reasoning param (reasoning_params: clear_thinking:false, or
# reasoning_effort:"none" — "Exactly ONE of the two is sent, never both"). Probed against the live
# proxy, every alias it serves other than GLM 4.7 rejects BOTH:
#     cerebras-gpt-oss / dispatch (cerebras/gpt-oss-120b) -> HTTP 400 on either param
#     cerebras-qwen-coder (qwen-3-coder-480b)             -> HTTP 404, not deployed
#     cerebras-glm                                        -> the SAME zai-glm-4.7 as `worker`
#                                                            (litellm_config.yaml), so not stronger
# So the proxy offers this channel no stronger model than the GLM the junior already ran on, and
# escalating within cerebras could only re-run the same model. Escalating to Claude is also the
# forge's own documented path for a GLM coder that cannot finish (litellm_config.yaml's num_retries
# note: transient 429s are retried so they do not "escalate the ticket to Claude prematurely").
# --escalate-engine / --escalate-model override this; --escalate-attempts 0 disables it entirely,
# which is how to keep a cerebras or ollama run from ever reaching claude.
ESCALATION = {
    "claude":   ("claude", "opus"),
    "cerebras": ("claude", "opus"),
    "ollama":   ("ollama", "gemma3:27b"),   # == ollama_agent.ROLE_MODELS["adversary"], a bigger
}                                           # local model of a different family


class CouplerError(RuntimeError):
    """A usage or environment problem, reported as ONE line and exit 2 — never a traceback."""


# ── locating and importing the spine ─────────────────────────────────────────────────────────────
def find_code_wrapper(start=None):
    """Absolute path of codebean_mcp/prototype/code_wrapper.py.

    $CONGRUENCY_CODE_WRAPPER overrides everything. Otherwise every ancestor of this file is tried
    for `codebean_mcp/prototype/code_wrapper.py`. The walk (rather than a fixed ../ hop) is what
    makes this work from BOTH a normal checkout and a pair worktree: codebean_mcp lives beside the
    congruency checkout and is not tracked in it, so a worktree sits one directory deeper than the
    checkout does and a hard-coded relative path would resolve in only one of the two.
    """
    env = os.environ.get("CONGRUENCY_CODE_WRAPPER")
    if env:
        p = Path(env).expanduser()
        if not p.is_file():
            raise CouplerError("$CONGRUENCY_CODE_WRAPPER does not name a file: %s" % p)
        return p.resolve()
    here = Path(start or __file__).resolve()
    for d in [here] + list(here.parents):
        cand = d / "codebean_mcp" / "prototype" / "code_wrapper.py"
        if cand.is_file():
            return cand.resolve()
    raise CouplerError(
        "code_wrapper.py not found: no ancestor of %s contains codebean_mcp/prototype/"
        "code_wrapper.py — set $CONGRUENCY_CODE_WRAPPER to its path" % here)


_CW = None


def load_code_wrapper(path=None):
    """Import code_wrapper as a module object, with its import-time side effects contained.

    Three of them, all real and all suppressed here:
      * it PRINTS "[telemetry] unavailable ..." when jazz_telemetry is absent — captured, so it can
        never corrupt this tool's stdout (--benchmark/--preserve emit machine-readable reports);
      * it does sys.path.insert(0, ~/code/forge/work/jazz_telemetry) — sys.path is restored;
      * importing it (and the model.py it loads by path) would write __pycache__ next to files
        OUTSIDE this tool's control — sys.dont_write_bytecode is set across the import, so
        --selftest's "no writes outside the temp dir" is true rather than merely hoped for.

    The module is registered in sys.modules BEFORE exec_module, which is not optional: code_wrapper
    defines @dataclass classes, and dataclasses resolves a field's type through
    sys.modules[cls.__module__].__dict__. Loading it by path without registering it first makes
    that lookup return None and every @dataclass in the file dies with an AttributeError.
    Cached: the import happens once per process.
    """
    global _CW
    if _CW is not None:
        return _CW
    p = Path(path) if path else find_code_wrapper()
    name = "cw_coupler"
    saved_path, saved_bc = list(sys.path), sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(name, p)
        if spec is None or spec.loader is None:
            raise CouplerError("code_wrapper at %s is not importable as Python" % p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        buf = io.StringIO()
        with redirect_stdout(buf):
            spec.loader.exec_module(mod)
    except CouplerError:
        sys.modules.pop(name, None)
        raise
    except Exception as e:
        sys.modules.pop(name, None)
        raise CouplerError("could not import code_wrapper from %s: %r" % (p, e))
    finally:
        sys.path[:] = saved_path
        sys.dont_write_bytecode = saved_bc
    for need in ("lower_functions", "lower_node", "_ast_norm", "critic", "judge",
                 "Candidate", "Function", "Module"):
        if not hasattr(mod, need):
            raise CouplerError("code_wrapper at %s has no %s — wrong file?" % (p, need))
    _CW = mod
    return mod


def load_ollama_agent():
    """Import the sibling ollama_agent.py (the cerebras/ollama engines). LAZY on purpose: it runs a
    registry gate at import and owns the network config, neither of which --selftest may need."""
    p = HERE / "ollama_agent.py"
    if not p.is_file():
        raise CouplerError("ollama_agent.py not found beside this tool (%s) — "
                           "--engine cerebras/ollama need it; --engine claude does not" % p)
    name = "ollama_agent_coupler"
    saved_bc = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(name, p)
        if spec is None or spec.loader is None:
            raise CouplerError("ollama_agent.py at %s is not importable as Python" % p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod          # before exec_module — see load_code_wrapper
        spec.loader.exec_module(mod)
        return mod
    except CouplerError:
        sys.modules.pop(name, None)
        raise
    except Exception as e:
        sys.modules.pop(name, None)
        raise CouplerError("could not import ollama_agent.py: %r" % e)
    finally:
        sys.dont_write_bytecode = saved_bc


# ── the model: one hole per function ─────────────────────────────────────────────────────────────
@dataclass
class Blank:
    """ONE function-shaped hole: what the senior emits, plus the oracle the junior never sees."""
    name: str
    params: str
    returns: str
    is_async: bool
    decorators: list
    doc: str                 # the docstring statement as ast.unparse emits it — the SKELETON's
    doc_display: str         # the docstring as it reads in the source — the PROMPT's (see below)
    rest_body: str           # the original body WITHOUT the docstring — the junior's target
    original_body: str       # the full original body, docstring included
    original_src: str        # ast.unparse(node): the critic's oracle. HIDDEN from the junior.

    def signature(self):
        """`def name(params) -> returns` — no decorators (the machine applies those), no colon."""
        kw = "async def" if self.is_async else "def"
        sig = "%s %s(%s)" % (kw, self.name, self.params)
        if self.returns:
            sig += " -> %s" % self.returns
        return sig


@dataclass
class Fill:
    """The outcome of one blank: what the junior produced and what the gate made of it."""
    name: str
    ok: bool = False
    body: str = ""
    attempts: int = 0
    escalated: bool = False
    first_shot_ok: bool = False
    answered: bool = False        # the junior returned a body at least once
    reproduced: bool = False      # _ast_norm-equal to the original
    works: bool = False           # compiles AND passes code_wrapper.judge
    gate: str = ""                # which refused it: "parse" | "critic" | "junior" | ""
    reason: str = ""
    prompts: list = field(default_factory=list)


# ── the MOCK SENIOR: lower_functions IS the senior ───────────────────────────────────────────────
def module_header(tree, max_const=800):
    """The module's imports and constants — the only module-wide context the junior is given.

    Imports are every top-level import; constants are every top-level assignment. A constant whose
    source exceeds max_const chars is elided to `NAME = ...` (still valid Python to read): the
    junior needs the NAME to call or reference, never a 20KB table's contents.
    """
    imports, consts = [], []
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            imports.append(ast.unparse(n))
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            src = ast.unparse(n)
            if len(src) > max_const:
                targets = [n.target] if isinstance(n, ast.AnnAssign) else n.targets
                names = ", ".join(ast.unparse(t) for t in targets)
                src = "%s = ...  # value elided (%d chars)" % (names, len(src))
            consts.append(src)
    return "\n".join(imports), "\n".join(consts)


def mock_senior(src_path, cw):
    """The senior, with no LLM in it: `lower_functions` yields every signature + docstring
    mechanically, which for the refactor case IS a senior's entire output.

    Returns (blanks, imports, constants). The blanks carry the original body too — that is the
    benchmark's ground truth and the critic's oracle, and it is never handed to the junior.
    """
    src_text = Path(src_path).read_text(encoding="utf-8")
    try:
        tree = ast.parse(src_text)
    except SyntaxError as e:
        raise CouplerError("%s does not parse as Python: line %s: %s" % (src_path, e.lineno, e.msg))

    lowered = cw.lower_functions(Path(src_path))          # the senior's canonical output
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if [f.name for f in lowered] != [n.name for n in nodes]:
        raise CouplerError("internal: lower_functions disagreed with the parsed tree for %s"
                           % src_path)

    blanks = []
    for fn, node in zip(lowered, nodes):
        doc, doc_display, rest = split_docstring(node, src_text)
        blanks.append(Blank(
            name=fn.name, params=fn.params, returns=fn.returns, is_async=fn.is_async,
            decorators=list(fn.decorators), doc=doc, doc_display=doc_display, rest_body=rest,
            original_body=fn.body, original_src=ast.unparse(node)))
    imports, consts = module_header(tree)
    return blanks, imports, consts


def split_docstring(node, src_text):
    """(doc_for_the_skeleton, doc_for_the_prompt, body_without_the_docstring), all as source text.

    TWO SPELLINGS OF THE SAME DOCSTRING, and the difference is not cosmetic — it is the multi-line
    docstring trap that `lower_functions`' own docstring warns about, reached by a second route:

      * THE SKELETON gets `ast.unparse`'s form, which collapses even a multi-line docstring to ONE
        line with escaped newlines ('a\\n\\n    b\\n    '). model.py's render() indents every body
        line by 4 — and indenting a one-line literal cannot change the string's VALUE, whereas
        indenting a REAL triple-quoted block would push 4 spaces INSIDE the string and change it.
        That is precisely why lower_node keeps docstrings in the body as unparse output, and the
        critic would catch the alternative as a mismatch.
      * THE PROMPT gets the original source segment, so the junior reads the docstring as a human
        wrote it instead of an escaped one-line blob. It never renders, so it cannot corrupt
        anything, and both spellings encode the identical string value — so _ast_norm is untouched
        either way.

    A docstring-only function yields its docstring and an EMPTY rest — an empty hole. It is left
    empty rather than filled with `pass`, because the original has no `pass` and inventing one
    would fail the critic on a function that is already complete.
    """
    body = list(node.body)
    doc = display = ""
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        doc = ast.unparse(body[0])
        # The segment's continuation lines still carry their original indentation, so the prompt
        # indents only its FIRST line and the block reads exactly as it does in the source.
        display = ast.get_source_segment(src_text, body[0]) or doc
        body = body[1:]
    return doc, display, "\n".join(ast.unparse(s) for s in body)


# ── the SKELETON: the codebean MCP surface, over code_wrapper's model ─────────────────────────────
class Skeleton:
    """The codebean surface — new_module / add_function / set_body / render — over the same model
    objects code_wrapper uses (model.py's Function/Module).

    This mirrors the MCP contract (codebean_mcp/codebean_mcp/server.py) with two deliberate
    differences, stated rather than hidden:
      * `add_function` there takes decorators as ONE comma-joined string and splits on "," — which
        would tear `@lru_cache(maxsize=None, typed=True)` in half. Here decorators are the list
        model.Function already holds.
      * that surface cannot express a return annotation or `async def`; model.Function can, and the
        critic demands exactness, so `returns`/`is_async` are carried through.

    `ops` records every call in order, which is how --selftest proves STRUCTURE FIRST: every
    add_function lands before any set_body.
    """

    def __init__(self, cw, name):
        self.cw = cw
        self.module = cw.Module(name)
        self.ops = []

    def new_module(self, name):
        self.module = self.cw.Module(name)
        self.ops.append("new_module:%s" % name)
        return self.module

    def add_function(self, name, params="", body="pass", doc="", decorators=(),
                     returns="", is_async=False):
        self.module.functions[name] = self.cw.Function(
            name=name, params=params, body=body, doc=doc, decorators=list(decorators),
            returns=returns, is_async=is_async)
        self.ops.append("add_function:%s" % name)
        return self.module.functions[name]

    def set_body(self, name, body):
        fn = self.module.functions.get(name)
        if fn is None:
            raise CouplerError("set_body: no function %r in the skeleton" % name)
        fn.body = body
        self.ops.append("set_body:%s" % name)
        return fn

    def render(self, instrument=True):
        return self.module.render(instrument=instrument)

    def structure_first(self):
        """True iff every add_function preceded every set_body."""
        adds = [i for i, o in enumerate(self.ops) if o.startswith("add_function:")]
        sets = [i for i, o in enumerate(self.ops) if o.startswith("set_body:")]
        return (not adds or not sets) or max(adds) < min(sets)


def lay_down_structure(cw, blanks, module_name):
    """STRUCTURE FIRST: EVERY signature via add_function BEFORE any body is filled, so a body may
    call any sibling regardless of fill order and no topological sort is needed. Each function is
    born holding only its docstring (the senior's output); the bodies are the junior's."""
    sk = Skeleton(cw, module_name)
    sk.new_module(module_name)
    for b in blanks:
        sk.add_function(name=b.name, params=b.params, body=b.doc or "pass", doc="",
                        decorators=b.decorators, returns=b.returns, is_async=b.is_async)
    return sk


# ── the junior's context: the ONLY thing it is ever handed ───────────────────────────────────────
@dataclass
class JuniorContext:
    """EXACTLY what the ticket permits the junior to see, and nothing else: its own signature and
    docstring, the sibling signatures (names and args only — no bodies), and the module's imports
    and constants.

    (Signature alone is not enough: a body calls its siblings and uses the module's imports, and a
    junior denied those hallucinates private helpers. This is the minimum viable context and it is
    still text-in/text-out.)
    """
    signature: str
    doc: str
    siblings: list
    imports: str
    constants: str

    def components(self):
        """Every text this context contributes to a prompt. audit_prompt subtracts these to leave
        the coupler's own scaffold."""
        return [self.signature, self.doc, self.imports, self.constants] + list(self.siblings)


def context_for(blank, blanks, imports, constants):
    """The junior's context. `doc_display` — not the skeleton's escaped `doc` — is what the junior
    reads; see split_docstring for why the two spellings exist."""
    sibs = [b.signature() for b in blanks if b.name != blank.name]
    return JuniorContext(signature=blank.signature(), doc=blank.doc_display, siblings=sibs,
                         imports=imports, constants=constants)


def render_junior_prompt(ctx, tried=()):
    """Build the junior's prompt. A PURE function of `ctx` (+ `tried`: the junior's OWN rejected
    answers and the gate's error for each) — there is no path, no tool, no repo and no original
    body in scope here to leak, which is what makes the guarantee structural instead of
    aspirational.

    `tried` is EVERY rejected attempt, not just the last, and the difference is measured. Echoing
    only the most recent answer anchors the model on it: it edits that body and re-submits a near
    duplicate, so eight attempts explore about one idea and escalation inherits the same rut.
    Showing the whole rejected set and demanding a materially different one turns a retry into a
    search over formulations — which is the only thing that can find the original's spelling when
    several are equally idiomatic. It leaks nothing: every line of it is the junior's own output.

    NOTE for anyone editing the scaffold below: it must not contain a tool's name. `audit_prompt`
    checks the scaffold against TOOL_NAMES case-sensitively, so "Emit the body" is fine and
    "Write the body" is a self-inflicted violation. That is deliberate — the check has to be able
    to fail.
    """
    p = ["Fill in ONE Python function body.", ""]
    if ctx.imports:
        p += ["--- the module's imports ---", ctx.imports, ""]
    if ctx.constants:
        p += ["--- the module's constants ---", ctx.constants, ""]
    if ctx.siblings:
        p += ["--- sibling signatures (names and args only; you may call these) ---"]
        p += ctx.siblings
        p += [""]
    p += ["--- your function ---", ctx.signature + ":"]
    if ctx.doc:
        p += ["    " + ctx.doc]        # first line only — see split_docstring
    p += [""]
    if tried:
        p += ["--- every answer you have already given for this function was REJECTED ---"]
        for i, (body, err) in enumerate(tried):
            p += ["attempt %d emitted:" % (i + 1), body, "and was rejected: %s" % err, ""]
        p += ["Do not emit any of those again, nor a re-spelling of one. Emit a materially "
              "DIFFERENT implementation.", ""]
    p += ["Emit JSON: an object whose \"body\" key holds ONLY the statements of this function's "
          "body — no def line, no signature, no docstring (it is already supplied above), no "
          "fences, no commentary. Indent as if at the top level of the body: the machine indents "
          "it into the function and applies the decorators."]
    return "\n".join(p)


def forbidden_paths(src):
    """The path strings `audit_prompt` must not find in the coupler's OWN scaffold.

    A candidate is kept only if it is path-SHAPED: it contains a directory separator, or it names a
    `.py` file. Dropping the rest is not a weakening of the check — it is what makes the check
    possible at all.

    `--src gpl_stamp.py` — the natural spelling from the `tools/` directory the corpus modules live
    in, and the one this tool's own docstring and `--help` print — has
    `Path("gpl_stamp.py").parent == Path(".")`. A bare `'.'` is a substring of the scaffold's own
    fixed prose ("Fill in ONE Python function body."), so checking it made the audit fire on the
    coupler's constant text and killed every `--benchmark`/`--preserve` run with a relative `--src`
    at exit 2, before the junior was ever called. The same trap is latent for any relative parent
    that is an ordinary word: `--src sub/mod.py` would otherwise check the token `'sub'` against
    English prose. A word is not evidence of a path.

    Nothing real is lost. The scaffold is a CONSTANT with no path interpolated into it; the audit
    exists to catch a future edit that interpolates one, and any such edit would carry a path's full
    spelling — the module's own filename, its absolute path, its absolute parent, or the cwd. All of
    those are still checked. `--selftest` asserts both halves: a planted path is still caught, and a
    bare relative `--src` audits clean.
    """
    src = Path(src)
    seps = [s for s in (os.sep, os.altsep) if s]
    out = []
    for c in (str(src), str(src.resolve()), str(src.parent), str(src.resolve().parent),
              os.getcwd()):
        if c in out or c in ("", os.curdir, os.pardir) or c in seps:
            continue
        if any(s in c for s in seps) or c.endswith(".py"):
            out.append(c)
    return out


def audit_prompt(prompt, ctx, forbidden=(), bodies=(), own=()):
    """Prove the junior was handed nothing it must not have. Returns a list of violation strings.

    The check is SUBTRACTIVE, and that is the point: every component text of `ctx` is removed from
    the prompt, and what remains is the coupler's OWN scaffold. Only the scaffold is searched for
    tool names and for `forbidden` tokens (the module's path, the cwd — see `forbidden_paths`,
    which is what a caller should build this list with). This distinguishes the two cases a naive
    grep conflates:
      * the coupler handing the junior a path or a tool                 -> a violation;
      * a module's own docstring or constant happening to contain a path (`DEFAULT = Path.home() /
        "x/y.py"`) -> NOT a violation. That text is the senior's output, mechanically lowered from
        the source; the coupler did not hand the junior a filesystem, it handed it the module's
        own constants, which the ticket explicitly permits.

    `own` — the junior's OWN rejected answers, quoted back on a retry — is subtracted before
    anything is judged, and that is not a loophole: a junior cannot leak to itself. It matters
    because a CORRECT junior's answer IS the original body, so without this the leak check below
    would fire on the junior's own words the moment a correct body was re-prompted for any reason.

    `bodies` are then checked against what remains: no body — no sibling's, and not this function's
    own original — may reach the junior from the COUPLER, ever.
    """
    base = prompt
    for o in own:
        if o:
            base = base.replace(o, "")
    scaffold = base
    for c in ctx.components():
        if c:
            scaffold = scaffold.replace(c, "")
            scaffold = scaffold.replace(textwrap.indent(c, "    "), "")
    out = []
    for t in TOOL_NAMES:
        if t in scaffold:
            out.append("the coupler's scaffold names a tool: %r" % t)
    for f in forbidden:
        if f and f in scaffold:
            out.append("the coupler's scaffold names a path: %r" % f)
    for b in bodies:
        if b and b.strip() and b in base:
            out.append("a function body reached the prompt: %r" % b[:60])
    return out


# ── the junior: text in, body text out ───────────────────────────────────────────────────────────
def strip_fences(text):
    """Drop a ```python ... ``` wrapper if the junior added one despite being asked not to.

    The junior is told to emit no fences and the JSON channel gives it no reason to, but a model
    that wraps its answer anyway has still ANSWERED — that is a formatting quirk, and spending a
    retry on it (or failing the function) would be the tool's fault, not the junior's.
    """
    t = (text or "").strip("\n")
    lines = t.splitlines()
    if not (lines and lines[0].lstrip().startswith("```")):
        return t
    lines = lines[1:]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].lstrip().startswith("```"):
        lines.pop()
    return "\n".join(lines)


class ClaudeJunior:
    """`claude -p`, with --json-schema so stdout is EXACTLY the object (prose suppressed), the
    system prompt REPLACED (so no repo/agent identity leaks in) and every tool denied. The junior
    is a text-in/text-out function; it is handed no cwd it could act on and no tool to act with."""

    def __init__(self, timeout=300):
        self.timeout = timeout

    def __call__(self, prompt, model=None):
        cmd = ["claude", "-p", prompt,
               "--json-schema", json.dumps(BODY_SCHEMA),
               "--system-prompt", JUNIOR_SYSTEM,
               "--disallowedTools", ",".join(TOOL_NAMES)]
        if model:
            cmd += ["--model", model]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
        except FileNotFoundError:
            raise CouplerError("the `claude` binary is not on PATH — --engine claude needs it")
        except subprocess.TimeoutExpired:
            raise CouplerError("the junior exceeded its %ss budget (raise --timeout)" % self.timeout)
        if r.returncode != 0:
            raise CouplerError("claude exited %s: %s"
                               % (r.returncode, (r.stderr or r.stdout).strip()[-300:]))
        out = (r.stdout or "").strip()
        try:
            obj = json.loads(out[out.index("{"):out.rindex("}") + 1])
        except (ValueError, IndexError):
            raise CouplerError("the junior emitted no JSON object: %r" % out[:200])
        if not isinstance(obj.get("body"), str):
            raise CouplerError("the junior's reply has no string \"body\": %r" % out[:200])
        return obj["body"]


class ProxyJunior:
    """The cerebras (GLM 4.7) and ollama juniors, through ollama_agent.constrained() — so the
    JSON-Schema + validate + corrective-retry channel (#175/R4) is REUSED verbatim rather than
    re-implemented. That retry is a TRANSPORT retry (the reply was not schema-shaped); it is not
    the gate's retry, which is about the body being wrong."""

    # GLM 4.7 reasons before it answers, and that reasoning is spent from the SAME max_tokens
    # budget as the reply. Measured here on the live proxy at 4096: the model spent the whole
    # budget thinking, returned finish_reason=length with EMPTY content, and the attempt was lost
    # having produced nothing. A function body is short; the budget therefore has to cover the
    # thinking, not the body. 16384 is generous for both and stays well under GLM 4.7's real
    # 40000 ceiling (ollama_agent.GLM_MAX_TOKENS, which clamp_max_tokens enforces anyway).
    MAX_TOKENS = 16384

    def __init__(self, flavor, timeout=300, retries=2):
        self.flavor = flavor
        self.timeout = timeout
        self.retries = retries
        self.oa = load_ollama_agent()

    def __call__(self, prompt, model=None):
        msgs = [{"role": "system", "content": JUNIOR_SYSTEM},
                {"role": "user", "content": prompt}]
        try:
            obj = self.oa.constrained(model, msgs, BODY_SCHEMA, self.retries,
                                      time.time() + self.timeout, label="body",
                                      flavor=self.flavor, num_predict=2048,
                                      max_tokens=self.MAX_TOKENS)
        except Exception as e:
            raise CouplerError("the %s junior failed: %r" % (self.flavor, e))
        body = obj.get("body")
        if not isinstance(body, str):
            raise CouplerError("the %s junior's reply has no string \"body\"" % self.flavor)
        return body


class ScriptedJunior:
    """--selftest's junior: a dict {function name: [reply, reply, ...]}, popped per attempt. No
    network, no model, no db — the loop under test is the coupler's, not a model's."""

    def __init__(self, script, default=None):
        self.script = {k: list(v) for k, v in script.items()}
        self.default = default
        self.seen = []          # (name-ish, prompt, model) per call — the selftest's evidence

    def __call__(self, prompt, model=None):
        """A reply that is an Exception is RAISED rather than returned — that is how the selftest
        stages a junior which never answers."""
        name = None
        for k in self.script:
            if ("def %s(" % k) in prompt and "--- your function ---" in prompt:
                # the function under fill is the one after the "your function" header
                tail = prompt.split("--- your function ---", 1)[1]
                if ("def %s(" % k) in tail:
                    name = k
                    break
        self.seen.append((name, prompt, model))
        replies = self.script.get(name)
        if not replies:
            if self.default is None:
                raise CouplerError("scripted junior: nothing left for %r" % name)
            return self.default
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


def make_junior(engine, timeout):
    if engine == "claude":
        return ClaudeJunior(timeout=timeout)
    if engine == "cerebras":
        return ProxyJunior("openai", timeout=timeout)
    if engine == "ollama":
        return ProxyJunior("ollama", timeout=timeout)
    raise CouplerError("unknown engine %r (choose claude, cerebras or ollama)" % engine)


# ── assembly and the gate ────────────────────────────────────────────────────────────────────────
def candidate_function(cw, blank, body):
    return cw.Function(name=blank.name, params=blank.params, body=body or "pass", doc="",
                       decorators=list(blank.decorators), returns=blank.returns,
                       is_async=blank.is_async)


def assemble(cw, blank, junior_body):
    """The machine's job: docstring (the skeleton's) + the junior's statements.

    The junior's text is normalised first — fences dropped, and dedented if that is what makes it
    sit at body level. Both spellings are tried against the REAL rendering (the junior's `return`
    is a SyntaxError at module level but fine inside the def, so the body can only be judged in
    place); if neither parses, the dedented one is kept so the gate reports the honest error.
    """
    t = strip_fences(junior_body)
    variants = []
    for v in (textwrap.dedent(t), t):
        if v not in variants:
            variants.append(v)
    chosen = variants[0]
    for v in variants:
        if _renders(cw, blank, v):
            chosen = v
            break
    parts = []
    if blank.doc:
        parts.append(blank.doc)
    if chosen.strip():
        parts.append(chosen.strip("\n"))
    if not parts:
        parts.append("pass")
    return "\n".join(parts)


def _renders(cw, blank, body):
    if not body.strip():
        return True
    try:
        ast.parse(candidate_function(cw, blank, body).render(instrument=False))
        return True
    except SyntaxError:
        return False


def gate(cw, blank, body, preserve=True):
    """The gate, cheapest first. Returns (ok, which, reason).

    1. PARSE   — does the assembled function compile at all? (cheap, and catches most junk)
    2. CRITIC  — for a PRESERVE function, code_wrapper.critic: _ast_norm(rendered) ==
                 _ast_norm(original). A MECHANICAL PROOF of behaviour preservation, not an
                 auditor's prose opinion: formatting, comments and whitespace cannot fool it, and
                 a changed constant or a dropped branch cannot pass it.
    The reason strings carry the junior's OWN error (SyntaxError line N) or the critic's verdict —
    never the original source. See the module docstring.
    """
    fn = candidate_function(cw, blank, body)
    rendered = fn.render(instrument=False)
    try:
        ast.parse(rendered)
    except SyntaxError as e:
        return False, "parse", "SyntaxError line %s: %s" % (e.lineno, e.msg)
    if preserve:
        cand = cw.Candidate(blank.name, fn, "junior")
        if not cw.critic(cand, blank.original_src):
            return False, "critic", cand.reason or "does not round-trip the original"
    return True, "", ""


def measure(cw, blank, body):
    """(reproduced, works) for the benchmark, both mechanical.

    reproduced: _ast_norm-equal to the original — the junior wrote THE code, not merely code.
    works:      the artefact compiles AND passes code_wrapper.judge (R1..R5: one def per artefact,
                born instrumented, addressable name, compiles, no module-scope side effects).
                This is a compile+rules claim. It is NOT a test-suite result.
    """
    fn = candidate_function(cw, blank, body)
    try:
        reproduced = cw._ast_norm(fn.render(instrument=False)) == cw._ast_norm(blank.original_src)
    except SyntaxError:
        return False, False
    try:
        obeyed, _ = cw.judge(cw.Candidate(blank.name, fn, "junior"))
    except SyntaxError:
        obeyed = False
    return reproduced, bool(obeyed)


# ── the loop: one function at a time, retry and escalate per BLANK ───────────────────────────────
def fill_blank(cw, sk, blank, blanks, imports, constants, junior, *, preserve=True,
               attempts=3, escalate_attempts=1, model=None, escalate_model=None,
               escalate_junior=None, forbidden=(), log=None):
    """Fill ONE blank: prompt -> gate -> re-prompt that ONE function -> escalate that ONE blank.

    The retry is per FUNCTION and never per module: a bad body costs one re-prompt. After
    `attempts` failures on the base model this ONE blank — not the module — escalates for
    `escalate_attempts` more tries. `escalate_junior` may be a DIFFERENT engine's junior (see
    ESCALATION); it defaults to this one, so escalation is then only a change of model.
    """
    ctx = context_for(blank, blanks, imports, constants)
    # every body in the module, including this one's: none may ever appear in a prompt
    bodies = [b.rest_body for b in blanks]
    res = Fill(name=blank.name)
    tried = []                       # (the junior's own rejected body, why the gate refused it)
    ej = escalate_junior or junior
    plan = ([(junior, model, False)] * attempts
            + [(ej, escalate_model, True)] * escalate_attempts)

    for i, (use_junior, use_model, is_esc) in enumerate(plan):
        prompt = render_junior_prompt(ctx, tried=tried)
        bad = audit_prompt(prompt, ctx, forbidden=forbidden, bodies=bodies,
                           own=[b for b, _ in tried])
        if bad:
            # fail CLOSED: the junior's isolation is the whole point of this tool
            raise CouplerError("prompt audit failed for %s: %s" % (blank.name, "; ".join(bad)))
        res.prompts.append(prompt)
        res.attempts = i + 1
        res.escalated = res.escalated or is_esc
        if log:
            log("   %s %s%s (attempt %d/%d)" % ("↑" if is_esc else "·", blank.name,
                                                " [escalated]" if is_esc else "", i + 1, len(plan)))
        try:
            raw = use_junior(prompt, model=use_model)
        except CouplerError as e:
            # The junior never ANSWERED (it stalled, the transport failed, the reply was not
            # JSON). That is not a bad body, so it costs this attempt and nothing more: a module
            # is not abandoned because one call to one model timed out.
            #
            # The failure is deliberately NOT fed back as prompt feedback, for two reasons: there
            # is no body to correct, and a transport error carries the engine's own stderr, which
            # can name a path — which the audit would (rightly) refuse. The same prompt is simply
            # tried again.
            res.gate, res.reason = "junior", str(e)
            if log:
                log("   ! %s: %s" % (blank.name, e))
            continue
        res.answered = True
        body = assemble(cw, blank, raw)
        ok, which, reason = gate(cw, blank, body, preserve=preserve)
        res.body, res.gate, res.reason = body, which, reason
        if ok:
            res.ok = True
            res.first_shot_ok = (i == 0)
            break
        # A critic rejection carries the constant CRITIC_HINT; a parse rejection does not need it
        # (the junior's own SyntaxError says everything). Neither quotes the original.
        error = (reason + " — " + CRITIC_HINT) if which == "critic" else reason
        tried.append((strip_fences(raw), error))

    # A function the junior never ANSWERED is not measured. Scoring it would be a lie in the
    # tool's favour AND against it: an unanswered blank leaves an empty body, which assembles to
    # `pass`, which compiles and passes judge — so a dead backend would otherwise print
    # "works: yes" for every function in the module while no model had run at all.
    if res.answered:
        res.reproduced, res.works = measure(cw, blank, res.body)
    sk.set_body(blank.name, res.body if res.ok else (blank.doc or "pass"))
    return res


def couple(src, junior, *, preserve=True, attempts=3, escalate_attempts=1, model=None,
           escalate_model=None, escalate_junior=None, limit=0, log=None, cw=None):
    """Lower -> lay every signature down -> fill one body at a time. Returns (skeleton, fills)."""
    cw = cw or load_code_wrapper()
    src = Path(src)
    if not src.is_file():
        raise CouplerError("no such module: %s" % src)
    blanks, imports, constants = mock_senior(src, cw)
    if not blanks:
        raise CouplerError("%s has no top-level functions to couple" % src)
    if limit:
        blanks = blanks[:limit]
    sk = lay_down_structure(cw, blanks, src.stem)          # STRUCTURE FIRST — all of it, first
    forbidden = forbidden_paths(src)
    fills = []
    for b in blanks:
        fills.append(fill_blank(cw, sk, b, blanks, imports, constants, junior, preserve=preserve,
                                attempts=attempts, escalate_attempts=escalate_attempts,
                                model=model, escalate_model=escalate_model,
                                escalate_junior=escalate_junior,
                                forbidden=forbidden, log=log))
    return sk, fills


# ── modes ────────────────────────────────────────────────────────────────────────────────────────
def plan_engines(a):
    """(junior, model, escalate_junior, escalate_model, escalate_engine) from the CLI.

    The escalation junior is built ONLY when escalation is actually enabled, so
    `--escalate-attempts 0` on a host with no `claude` binary (or no proxy) never constructs an
    engine it will not use.
    """
    model = a.model or ENGINE_MODELS[a.engine]
    esc_engine, esc_default = ESCALATION[a.engine]
    esc_engine = a.escalate_engine or esc_engine
    esc_model = a.escalate_model or (esc_default if esc_engine == ESCALATION[a.engine][0]
                                     else ENGINE_MODELS[esc_engine])
    junior = make_junior(a.engine, a.timeout)
    esc_junior = None
    if a.escalate_attempts:
        esc_junior = junior if esc_engine == a.engine else make_junior(esc_engine, a.timeout)
    return junior, model, esc_junior, esc_model, esc_engine


def _esc_label(engine, esc_engine, esc_model):
    return esc_model if esc_engine == engine else "%s/%s" % (esc_engine, esc_model)


def run_preserve(a):
    cw = load_code_wrapper()
    junior, model, esc_junior, esc_model, esc_engine = plan_engines(a)
    esc = _esc_label(a.engine, esc_engine, esc_model)
    t0 = time.time()
    sk, fills = couple(a.src, junior, preserve=True, attempts=a.attempts,
                       escalate_attempts=a.escalate_attempts, model=model,
                       escalate_model=esc_model, escalate_junior=esc_junior,
                       limit=a.limit, log=(None if a.json else _log), cw=cw)
    ok = [f for f in fills if f.ok]
    bad = [f for f in fills if not f.ok]
    report = {"mode": "preserve", "src": str(a.src), "engine": a.engine, "model": model,
              "escalate_model": esc, "functions": len(fills), "passed": len(ok),
              "failed": len(bad), "seconds": round(time.time() - t0, 1),
              "structure_first": sk.structure_first(),
              "results": [{"name": f.name, "critic": f.ok, "attempts": f.attempts,
                           "escalated": f.escalated, "gate": f.gate, "reason": f.reason}
                          for f in fills]}
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        print("\n=== PRESERVE %s (engine=%s, model=%s, escalate=%s) ===" % (a.src, a.engine, model, esc))
        for f in fills:
            print("  %-6s %-28s attempts=%d%s%s"
                  % ("PASS" if f.ok else "FAIL", f.name, f.attempts,
                     " escalated" if f.escalated else "",
                     "" if f.ok else "  [%s] %s" % (f.gate, f.reason)))
        print("\n%d/%d functions pass critic against the original (%.0fs)"
              % (len(ok), len(fills), time.time() - t0))
    if bad:
        _log("\nNOT emitting the module: %d function(s) did not pass the critic (%s)."
             % (len(bad), ", ".join(f.name for f in bad)))
        _log("A body the junior could not reproduce is not silently replaced by the original — "
             "that would make \"passes critic\" true by construction.")
        return 1
    out = sk.render(instrument=not a.mature)
    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
        _log("\nwrote %s (%d bytes, %s)" % (a.out, len(out), "mature" if a.mature else "instrumented"))
    elif not a.json:
        print("\n=== rebuilt module (%s) ===" % ("mature" if a.mature else "born instrumented"))
        print(out)
    return 0


def run_benchmark(a):
    cw = load_code_wrapper()
    junior, model, esc_junior, esc_model, esc_engine = plan_engines(a)
    esc = _esc_label(a.engine, esc_engine, esc_model)
    t0 = time.time()
    # The benchmark BLANKS every body and has the junior refill it. The gate still runs (that is
    # the loop under test), and the original is kept back as ground truth — never shown.
    sk, fills = couple(a.src, junior, preserve=True, attempts=a.attempts,
                       escalate_attempts=a.escalate_attempts, model=model,
                       escalate_model=esc_model, escalate_junior=esc_junior,
                       limit=a.limit, log=(None if a.json else _log), cw=cw)
    n = len(fills)
    scored = [f for f in fills if f.answered]
    mute = [f for f in fills if not f.answered]
    ns = len(scored)
    rep = sum(f.reproduced for f in scored)
    wrk = sum(f.works for f in scored)
    first = sum(f.first_shot_ok for f in scored)
    # The rates are over the functions the junior ANSWERED. A function whose engine never replied
    # measures nothing about a model, so counting it as a miss would report a broken backend as a
    # bad junior; it is reported on its own line instead, and never silently dropped.
    report = {"mode": "benchmark", "src": str(a.src), "engine": a.engine, "model": model,
              "escalate_model": esc, "functions": n, "answered": ns, "unanswered": len(mute),
              "reproduced": rep, "works": wrk, "first_shot": first,
              "reproduced_rate": round(rep / ns, 3) if ns else None,
              "works_rate": round(wrk / ns, 3) if ns else None,
              "seconds": round(time.time() - t0, 1),
              "results": [{"name": f.name, "answered": f.answered,
                           "reproduced": f.reproduced if f.answered else None,
                           "works": f.works if f.answered else None,
                           "attempts": f.attempts, "escalated": f.escalated,
                           "gate": f.gate, "reason": f.reason} for f in fills]}
    if a.json:
        print(json.dumps(report, indent=2))
        return 0 if ns else 1
    print("\n=== BLANK-AND-REFILL BENCHMARK: %s ===" % a.src)
    print("engine=%s model=%s escalate=%s attempts=%d(+%d escalated)"
          % (a.engine, model, esc, a.attempts, a.escalate_attempts))
    print("\n  %-30s %-11s %-9s %s" % ("function", "reproduced", "works", "attempts"))
    print("  " + "-" * 64)
    for f in fills:
        if f.answered:
            r, w = ("yes" if f.reproduced else "no"), ("yes" if f.works else "no")
        else:
            r = w = "no answer"
        print("  %-30s %-11s %-9s %d%s"
              % (f.name[:30], r, w, f.attempts, " (escalated)" if f.escalated else ""))
    print("  " + "-" * 64)
    if not ns:
        print("  the junior answered for NO function — nothing was measured.")
        print("  last error: %s" % (fills[-1].reason or "(none)"))
        return 1
    print("  reproduced %d/%d (%.0f%%)   works %d/%d (%.0f%%)   first-shot %d/%d   %.0fs"
          % (rep, ns, 100.0 * rep / ns, wrk, ns, 100.0 * wrk / ns, first, ns, time.time() - t0))
    if mute:
        print("  %d of %d function(s) got NO answer from the junior and are NOT scored above "
              "(rates are over the %d answered): %s"
              % (len(mute), n, ns, ", ".join(f.name for f in mute)))
        print("  that is an engine/transport failure, not a model result — e.g. %s"
              % (mute[0].reason or "(no reason recorded)")[:110])
    print("\n  reproduced = _ast_norm-equal to the original body: it wrote THE code. This measures")
    print("               IDENTITY, not correctness — a right body written differently counts as")
    print("               'no', so this is a LOWER bound on how often the junior was right.")
    print("  works      = the artefact compiles AND passes code_wrapper.judge (R1..R5).")
    print("               A compile+rules claim, NOT a test-suite result: none is run.")
    return 0


# ── --selftest ───────────────────────────────────────────────────────────────────────────────────
SELFTEST_SRC = '''"""A throwaway synthetic module. Nothing here is imported or installed."""
import math

SCALE = 3


def area(r):
    """Return the area of a circle of radius r."""
    return math.pi * r * r


def scaled_area(r):
    """Return the area of a circle of radius r, multiplied by SCALE."""
    marker_zz9 = SCALE
    return area(r) * marker_zz9


def describe(r):
    """Describe the circle of radius r.

    This docstring spans several lines on purpose: a multi-line docstring is the
    one that render() corrupts if it is re-indented, so the round trip has to
    survive it.
    """
    return 'r=%s area=%s' % (r, area(r))


def stub(r):
    """Document a circle of radius r and do nothing else: this body is only a docstring."""
'''

_CHECKS = []


def _check(name, ok, detail=""):
    _CHECKS.append((name, bool(ok), detail))
    print("  %-4s %-42s %s" % ("PASS" if ok else "FAIL", name, detail))
    return bool(ok)


def _snapshot(dirs):
    """RECURSIVE, and keyed on (size, mtime) rather than names.

    Both properties are load-bearing, and a weaker snapshot passes while the tool misbehaves:
      * a top-level listing cannot see a new .pyc appear INSIDE an already-existing __pycache__/;
      * a name-only listing cannot see an existing .pyc be REWRITTEN in place.
    """
    snap = {}
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            snap[str(d)] = None
            continue
        ents = {}
        for p in sorted(d.rglob("*")):
            try:
                st = p.stat()
            except OSError:
                continue
            ents[str(p.relative_to(d))] = (p.is_dir(), st.st_size, st.st_mtime_ns)
        snap[str(d)] = ents
    return snap


def _diff_snapshots(before, after):
    out = []
    for d, b in before.items():
        a = after.get(d)
        if b == a:
            continue
        if b is None or a is None:
            out.append("%s appeared/vanished" % d)
            continue
        for k in sorted(set(b) | set(a)):
            if b.get(k) != a.get(k):
                out.append("%s/%s %s" % (d, k, "created" if k not in b else
                                         ("removed" if k not in a else "modified")))
    return out


def selftest(a):
    """Every claim this tool makes, proven on a synthetic module with a scripted junior.

    No network, no live db, and no writes outside the temp dir — including no __pycache__ beside
    the imported code_wrapper (load_code_wrapper sets sys.dont_write_bytecode), which is exactly
    the kind of write a "creates no files" claim quietly breaks on.
    """
    print("=== coupler --selftest ===")
    # Snapshot BEFORE the first import, which is the whole trick: importing code_wrapper is itself
    # a candidate write (a .pyc beside it). Snapshot after it and that write is baselined in as
    # "pre-existing", and the check goes green while the file is being created. find_code_wrapper
    # only LOCATES the file — it imports nothing.
    cw_dir = find_code_wrapper().parent
    watched = [HERE, cw_dir, cw_dir.parent / "codebean_mcp"]
    before = _snapshot(watched)
    cw = load_code_wrapper()

    with tempfile.TemporaryDirectory(prefix="coupler-selftest-") as td:
        td = Path(td)
        src = td / "synthetic.py"
        src.write_text(SELFTEST_SRC, encoding="utf-8")
        blanks, imports, constants = mock_senior(src, cw)
        by = {b.name: b for b in blanks}

        # ── the senior ──────────────────────────────────────────────────────────────────────────
        _check("senior lowers every function",
               [b.name for b in blanks] == ["area", "scaled_area", "describe", "stub"],
               str([b.name for b in blanks]))
        _check("senior keeps the docstring out of the hole",
               "Return the area" in by["area"].doc and "math.pi" not in by["area"].doc,
               "doc is the skeleton's, body is the junior's")
        _check("the skeleton's docstring is one escaped line (render indents it safely)",
               "\n" not in by["describe"].doc and "\\n" in by["describe"].doc,
               "multi-line docstring collapsed by ast.unparse")
        _check("the junior reads the docstring as written, not escaped",
               by["describe"].doc_display.startswith('"""Describe the circle')
               and "\n" in by["describe"].doc_display)
        _check("senior keeps the original body back as the oracle",
               "math.pi * r * r" in by["area"].original_src)
        _check("module header carries imports and constants",
               "import math" in imports and "SCALE = 3" in constants)

        # ── 1. STRUCTURE FIRST ──────────────────────────────────────────────────────────────────
        good = {"area": ["return math.pi * r * r"],
                "scaled_area": ["marker_zz9 = SCALE\nreturn area(r) * marker_zz9"],
                "describe": ["return 'r=%s area=%s' % (r, area(r))"],
                "stub": [""]}
        sk, fills = couple(src, ScriptedJunior(good), preserve=True, attempts=2,
                           escalate_attempts=1, model="base", escalate_model="strong", cw=cw)
        adds = [o for o in sk.ops if o.startswith("add_function:")]
        sets = [o for o in sk.ops if o.startswith("set_body:")]
        _check("structure first: every signature before any body",
               sk.structure_first() and len(adds) == 4 and len(sets) == 4,
               " ".join(sk.ops))
        _check("a multi-line docstring survives the round trip (critic proves it)",
               [f.ok and f.reproduced for f in fills if f.name == "describe"] == [True])
        _check("a correct junior passes the critic on every function",
               all(f.ok and f.reproduced for f in fills))
        _check("a correct junior is never escalated and needs one attempt",
               all(f.attempts == 1 and not f.escalated for f in fills))

        # ── 2. the junior's isolation ───────────────────────────────────────────────────────────
        prompt = fills[0].prompts[0]
        ctx0 = context_for(by["area"], blanks, imports, constants)
        forbidden = [str(src), str(td), os.getcwd()]
        viol = audit_prompt(prompt, ctx0, forbidden=forbidden,
                            bodies=[b.rest_body for b in blanks])
        _check("prompt audit: no path, no tool, no body", viol == [], "; ".join(viol) or "clean")
        _check("the junior is handed no path", str(src) not in prompt and str(td) not in prompt)
        _check("the junior is handed no tool name",
               not any(t in prompt for t in TOOL_NAMES))
        _check("a sibling's body never reaches the prompt", "marker_zz9" not in prompt)
        _check("the function's own original body never reaches the prompt",
               "math.pi * r * r" not in prompt)
        _check("the junior IS handed its signature, docstring, siblings, imports and constants",
               "def area(r)" in prompt and "Return the area" in prompt
               and "def scaled_area(r)" in prompt and "import math" in prompt
               and "SCALE = 3" in prompt)
        _check("the prompt is a pure function of the context",
               prompt == render_junior_prompt(ctx0))

        # The audit must be able to FAIL, or it proves nothing. Both halves are planted here, into
        # the SCAFFOLD (not the context), which is the only place either would be a real leak.
        _check("the audit CATCHES a path planted in the scaffold",
               ("the coupler's scaffold names a path: %r" % str(src))
               in audit_prompt(prompt + "\nsee " + str(src), ctx0, forbidden=forbidden))
        _check("the audit CATCHES a tool name planted in the scaffold",
               "the coupler's scaffold names a tool: 'Bash'"
               in audit_prompt(prompt + "\nuse the Bash tool", ctx0, forbidden=forbidden))
        _check("the audit CATCHES a body planted in the scaffold",
               audit_prompt(prompt + "\nreturn math.pi * r * r", ctx0, forbidden=forbidden,
                            bodies=[b.rest_body for b in blanks]) != [])

        # ── 2b. a RELATIVE --src is audited on paths, not on English ────────────────────────────
        # `Path("synthetic.py").parent` is "." — and "." occurs in the scaffold's own fixed prose
        # ("Fill in ONE Python function body."). Checking that token made the audit fire on the
        # coupler's own constant text, so every --benchmark/--preserve with a relative --src died
        # at exit 2 before the junior was ever called. See forbidden_paths.
        rel = forbidden_paths("synthetic.py")
        _check("forbidden_paths drops the degenerate '.' parent of a bare --src",
               "." not in rel and "" not in rel, str(rel))
        _check("forbidden_paths keeps every real spelling of a bare --src",
               "synthetic.py" in rel and str(Path("synthetic.py").resolve()) in rel
               and os.getcwd() in rel, "filename, absolute path, absolute parent, cwd")
        _check("a bare relative --src audits CLEAN against the scaffold",
               audit_prompt(prompt, ctx0, forbidden=rel) == [],
               "; ".join(audit_prompt(prompt, ctx0, forbidden=rel)) or "no violation")
        # and the end-to-end proof of the same thing: the documented `--src M.py` form, run with
        # the cwd holding the module, must couple rather than exit 2.
        cwd0 = os.getcwd()
        try:
            os.chdir(td)
            _, frel = couple("synthetic.py", ScriptedJunior(good), preserve=True, attempts=2,
                             escalate_attempts=1, model="base", escalate_model="strong", cw=cw)
        finally:
            os.chdir(cwd0)
        _check("`--src M.py` (relative, as --help prints it) runs the whole loop",
               all(f.ok for f in frel) and len(frel) == 4,
               "%d/%d filled with no prompt-audit abort" % (sum(f.ok for f in frel), len(frel)))

        # ── 3. a body that fails parse is re-prompted ───────────────────────────────────────────
        j = ScriptedJunior({"area": ["return (", "return math.pi * r * r"],
                            "scaled_area": ["marker_zz9 = SCALE\nreturn area(r) * marker_zz9"],
                            "describe": ["return 'r=%s area=%s' % (r, area(r))"],
                            "stub": [""]})
        _, f2 = couple(src, j, preserve=True, attempts=3, escalate_attempts=1,
                       model="base", escalate_model="strong", cw=cw)
        fa = f2[0]
        _check("a body that fails parse is re-prompted (not abandoned)",
               fa.attempts == 2 and fa.ok, "attempts=%d ok=%s" % (fa.attempts, fa.ok))
        retry = fa.prompts[1]
        _check("the re-prompt quotes the junior's own rejected attempt back to it",
               "return (" in retry and "attempt 1 emitted:" in retry)
        _check("the re-prompt carries the exact error (SyntaxError line N)",
               "SyntaxError line" in retry, retry.split("the gate said: ")[-1].splitlines()[0]
               if "the gate said: " in retry else "(missing)")
        _check("the re-prompt does not leak the original body",
               "math.pi * r * r" not in retry)
        _check("the re-prompt is still path-free and tool-free",
               audit_prompt(retry, ctx0, forbidden=forbidden) == [])

        # ── 3b. a junior that never ANSWERS costs one attempt, not the module ───────────────────
        stalled = ScriptedJunior({"area": [CouplerError("stalled: no answer"),
                                           "return math.pi * r * r"],
                                  "scaled_area": ["marker_zz9 = SCALE\n"
                                                  "return area(r) * marker_zz9"],
                                  "describe": ["return 'r=%s area=%s' % (r, area(r))"],
                                  "stub": [""]})
        _, f2b = couple(src, stalled, preserve=True, attempts=3, escalate_attempts=1,
                        model="base", escalate_model="strong", cw=cw)
        _check("a junior that never answers costs ONE attempt, not the module",
               f2b[0].attempts == 2 and f2b[0].ok and all(f.ok for f in f2b),
               "the other %d functions still filled" % (len(f2b) - 1))

        # A dead engine must never be scored as a model result: an unanswered blank leaves an
        # empty body, which assembles to `pass` — which compiles and passes judge.
        dead = ScriptedJunior({"area": [CouplerError("backend refused the connection")]},
                              default=None)
        _, f2c = couple(src, dead, preserve=True, attempts=2, escalate_attempts=0,
                        model="base", escalate_model="strong", limit=1, cw=cw)
        _check("a function the junior never answered is NOT scored as working",
               (not f2c[0].answered) and (not f2c[0].works) and (not f2c[0].reproduced)
               and f2c[0].gate == "junior",
               "answered=%s works=%s — a dead backend is not a benchmark result"
               % (f2c[0].answered, f2c[0].works))

        # ── 4. the critic is two-sided ──────────────────────────────────────────────────────────
        ok_sem, which_sem, why_sem = gate(cw, by["area"], assemble(cw, by["area"], "return 0"))
        _check("a PRESERVE function that differs semantically FAILS critic",
               (not ok_sem) and which_sem == "critic", why_sem)
        fenced = "```python\nreturn math.pi * r * r\n```"
        _check("a junior that wraps its body in fences anyway still passes",
               gate(cw, by["area"], assemble(cw, by["area"], fenced))[0],
               "a formatting quirk costs no attempt")
        indented = "    return math.pi * r * r"     # emitted as if already inside the def
        _check("a junior that indents its body to def level still passes",
               gate(cw, by["area"], assemble(cw, by["area"], indented))[0])

        wsp = "# a comment the original never had\n\n\nreturn   math.pi * r   *   r\n\n"
        ok_wsp, which_wsp, why_wsp = gate(cw, by["area"], assemble(cw, by["area"], wsp))
        _check("one that differs only in whitespace/comments PASSES critic",
               ok_wsp, why_wsp or "_ast_norm-equal")
        ok_drop, which_drop, _ = gate(cw, by["scaled_area"],
                                      assemble(cw, by["scaled_area"], "return area(r) * SCALE"))
        _check("an equivalent-looking body that is not the original FAILS critic",
               (not ok_drop) and which_drop == "critic", "critic proves, it does not opine")

        # the gate is cheapest-first: a body that cannot parse is refused by parse, not the critic
        ok_p, which_p, _ = gate(cw, by["area"], assemble(cw, by["area"], "return ("))
        _check("the gate is cheapest first: parse refuses before critic",
               (not ok_p) and which_p == "parse")

        # a docstring-only function is a function whose hole is genuinely EMPTY
        _check("a docstring-only function's hole is empty (nothing to fill)",
               by["stub"].rest_body == "", repr(by["stub"].rest_body))
        _check("a junior returning nothing reproduces a docstring-only function",
               gate(cw, by["stub"], assemble(cw, by["stub"], ""))[0])
        _check("an invented `pass` FAILS critic on a docstring-only function",
               not gate(cw, by["stub"], assemble(cw, by["stub"], "pass"))[0],
               "the machine adds no statement the original lacks")

        # ── 5. escalation fires after N ─────────────────────────────────────────────────────────
        always_bad = ScriptedJunior({"area": ["return 0"], "scaled_area": ["return 0"],
                                     "describe": ["return 0"], "stub": ["return 0"]})
        _, f3 = couple(src, always_bad, preserve=True, attempts=2, escalate_attempts=1,
                       model="base", escalate_model="strong", cw=cw)
        fb = f3[0]
        models = [m for (_n, _p, m) in always_bad.seen]
        _check("escalation fires after N failures, on that ONE blank",
               fb.escalated and fb.attempts == 3 and not fb.ok,
               "attempts=%d escalated=%s" % (fb.attempts, fb.escalated))
        _check("the first N attempts use the base model, the escalation a stronger one",
               models[:2] == ["base", "base"] and models[2] == "strong", str(models[:3]))
        _check("a failed blank leaves the skeleton's docstring, not a wrong body",
               not fb.ok and fb.gate == "critic")

        # escalation may hand the blank to a DIFFERENT engine's junior (cerebras -> claude)
        base_j = ScriptedJunior({"area": ["return 0"]})
        esc_j = ScriptedJunior({"area": ["return math.pi * r * r"]})
        _, f3b = couple(src, base_j, preserve=True, attempts=2, escalate_attempts=1,
                        model="base", escalate_model="strong", escalate_junior=esc_j,
                        limit=1, cw=cw)
        _check("escalation can cross ENGINES, not just models",
               f3b[0].ok and f3b[0].escalated and f3b[0].attempts == 3
               and len(base_j.seen) == 2 and len(esc_j.seen) == 1,
               "base junior got %d attempts, the escalation junior got %d"
               % (len(base_j.seen), len(esc_j.seen)))
        # These are the CRITIC's re-prompts (the run above fails critic, not parse), so they cover
        # the feedback path the parse-retry check above cannot reach.
        _check("a critic re-prompt names the critic's verdict",
               any("round-trip" in p for p in fb.prompts[1:]),
               "the exact _ast_norm mismatch, re-prompted per function")
        _check("a critic re-prompt says identity, not equivalence, is the bar",
               any("AST-IDENTICAL" in p for p in fb.prompts[1:]),
               "a constant hint — it quotes nothing from the original")
        # the rejected set ACCUMULATES, so the junior searches instead of re-editing one idea
        _check("every rejected attempt is carried forward, not just the last",
               "attempt 1 emitted:" in fb.prompts[2] and "attempt 2 emitted:" in fb.prompts[2]
               and "materially DIFFERENT" in fb.prompts[2],
               "attempt 3's prompt names both earlier attempts")
        _check("NO prompt of a whole critic-failing run leaks the original body",
               all("math.pi * r * r" not in p for f in f3 for p in f.prompts),
               "ground truth stays hidden or the benchmark measures an echo")

        # ── 6. measurement ──────────────────────────────────────────────────────────────────────
        rep_ok, works_ok = measure(cw, by["area"], assemble(cw, by["area"], "return math.pi * r * r"))
        rep_no, works_no2 = measure(cw, by["area"], assemble(cw, by["area"], "return 0"))
        _check("benchmark: a faithful refill measures reproduced AND works", rep_ok and works_ok)
        _check("benchmark: a wrong refill measures not-reproduced but may still work",
               (not rep_no) and works_no2, "reproduced and works are independent")

        # ── 7. no writes outside the temp dir ───────────────────────────────────────────────────
        after = _snapshot(watched)
        drift = _diff_snapshots(before, after)
        _check("no writes outside the temp dir (no __pycache__, no artefacts)",
               not drift, "; ".join(drift[:3]) or "%d dirs unchanged, recursively" % len(watched))

    ok = all(c[1] for c in _CHECKS)
    n_ok = sum(1 for c in _CHECKS if c[1])
    print("\n%s — %d/%d checks" % ("ALL CHECKS PASS" if ok else "CHECKS FAILED", n_ok, len(_CHECKS)))
    return 0 if ok else 1


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="coupler.py",
        description="The COUPLER: the senior emits signatures, the junior fills ONE body at a "
                    "time, the critic gates AST-equivalence. Python only.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="modes:\n"
               "  --selftest                  scripted junior, temp dir, no network\n"
               "  --benchmark --src M.py      blank every body, refill, score reproduced/works\n"
               "  --preserve  --src M.py      refill under the critic and emit the module\n")
    m = p.add_argument_group("mode (exactly one)")
    m.add_argument("--selftest", action="store_true", help="prove the loop on a synthetic module")
    m.add_argument("--benchmark", action="store_true", help="the blank-and-refill benchmark")
    m.add_argument("--preserve", action="store_true", help="refill a module under the critic")
    p.add_argument("--src", type=Path, help="the module to couple (--benchmark / --preserve)")
    p.add_argument("--engine", default="claude", choices=sorted(ENGINE_MODELS),
                   help="which junior (default: claude)")
    p.add_argument("--model", help="override the junior's base model for the engine")
    p.add_argument("--escalate-engine", choices=sorted(ENGINE_MODELS),
                   help="override the engine ONE blank escalates to (default: claude for "
                        "claude/cerebras, ollama for ollama — the proxy serves no model stronger "
                        "than its GLM through this channel)")
    p.add_argument("--escalate-model", help="override the model ONE blank escalates to")
    p.add_argument("--attempts", type=int, default=3,
                   help="attempts per function on the base model before escalating (default 3)")
    p.add_argument("--escalate-attempts", type=int, default=1,
                   help="attempts on the stronger model after that; 0 disables escalation "
                        "(default 1)")
    p.add_argument("--limit", type=int, default=0, help="only the first N functions")
    p.add_argument("--timeout", type=int, default=300, help="seconds per junior call (default 300)")
    p.add_argument("--out", type=Path, help="--preserve: write the rebuilt module here")
    p.add_argument("--mature", action="store_true",
                   help="--preserve: emit the frozen decorator-free form (default: born "
                        "instrumented)")
    p.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    a = p.parse_args(argv)

    modes = [a.selftest, a.benchmark, a.preserve]
    if sum(bool(x) for x in modes) != 1:
        p.error("choose exactly one of --selftest, --benchmark, --preserve")
    if (a.benchmark or a.preserve) and not a.src:
        p.error("--src is required with --benchmark and --preserve")
    if a.attempts < 1:
        p.error("--attempts must be at least 1")
    if a.escalate_attempts < 0:
        p.error("--escalate-attempts cannot be negative")

    try:
        if a.selftest:
            return selftest(a)
        if a.benchmark:
            return run_benchmark(a)
        return run_preserve(a)
    except CouplerError as e:
        print("coupler: %s" % e, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("coupler: interrupted", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
