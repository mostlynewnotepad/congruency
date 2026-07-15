#!/usr/bin/env python3
"""local_graph.py — the ticket-authorization lifecycle as a LangGraph StateGraph, with a
checkpointer, conditional edges (pass/fail/dry), and an interrupt node for wallet-signed approval.

    BRAKE -> PAIR -> WORK -> VALIDATE -> SETTLE -> HARVEST

Each node is a thin wrapper over code that already exists and is already tested: the nodes call
pair_loop.py's `Forge` (the git layer) and its governed REST routes verbatim. This module adds three
things pair_loop does not have and nothing else:

  1. a CHECKPOINTER  — the in-flight cursor (which round, which node, which worktree) is persisted
                       after every super-step, so a run KILLED mid-flight RESUMES exactly where it
                       stopped instead of restarting at round 1.
  2. CONDITIONAL EDGES — pass / fail / dry routing out of `decide` (see "The dry edge" below).
  3. an INTERRUPT node — `approval_gate` pauses the graph before the irreversible merge and demands
                       a WALLET-SIGNED approval to proceed (see "The approval gate" below).

THE GRAPH (nodes as built in build_graph(); -> plain edge, => conditional edge):

    START -> brake => clear ....... open_worktree -> spawn_pair -> run_worker -> commit
                   => halt ........ halted -> END                                  |
                                                                                   v
              decide <- run_auditor <------------------------------------------------
                |
                => fail (rounds left) ... respawn -> spawn_pair   (a FRESH worker, findings carried)
                => exhausted ............ gave_up ......... \
                => dry .................. dry ............... > harvest_fail -> END
                => pass ................. approval_gate      /
                                             |  (INTERRUPT: pauses for a wallet signature)
                                             => rejected .... held ... /
                                             => approved .... merge
                                                               => refused . merge_refused -> harvest_fail
                                                               => ok ...... settle -> reap -> harvest_pass -> END

    The ticket's brake -> pair -> work -> validate -> settle -> harvest reads down this graph as
    brake -> spawn_pair -> run_worker -> run_auditor -> (merge, settle, reap) -> harvest_*.

DEFINITIONS (this file assumes no prior context):
  ticket       a row in `tickets` that AUTHORIZES an agent to act; work on nothing else.
  kind         the ticket's classification (`build`, `documentation`, ...). `build` is a PAIR kind:
               a worker (`coder`) produces, an adversary (`tester`) judges (migration
               0029_ticket_authorization.sql:34-45).
  brake        the check performed BEFORE anything acts: `ticket.stops` counts active (unreleased)
               stop tickets aimed at this ticket or any ancestor; > 0 means the ticket authorizes
               nothing right now (route: migrations/0030_pair_loop_routes.sql:21-26).
  worktree     a second working directory driven by the same .git, so the ticket's branch is checked
               out somewhere else on disk and the base tree is never touched.
  the ledger   the append-only `ticket_events` table, written only through governed REST routes.
               Never rewritten (triggers `tg_ticket_events_no_update` / `_no_delete`, migration
               0029_ticket_authorization.sql:142-145).
  checkpoint   a snapshot of the graph's state + the next node, written to THIS module's own sqlite
               file after every node. Volatile scratch, not a ledger. See "Checkpoint vs ledger".
  super-step   one node execution; the checkpointer writes one checkpoint per super-step.
  thread_id    the checkpointer's key for one run. Here it is always `ticket-<id>`: one ticket, one
               resumable thread.

CHECKPOINT VS LEDGER — they COMPLEMENT, they do not duplicate (the rule this module obeys):
  The append-only ledger is the durable SOURCE OF TRUTH for SETTLED FACTS (branch opened, deliverable
  committed, verdict, merged, DONE, work UID, lesson). The checkpoint holds ONLY the VOLATILE CURSOR
  (current node, round counter, worktree path, last verdict, accumulated findings). Deleting the
  checkpoint file loses no history — a run simply cannot auto-resume, exactly as pair_loop cannot
  today.
  The rule this module enforces, stated exactly: NO node lets the checkpoint DECIDE a settled fact.
  Every authority is re-derived from the durable stores at the moment it is needed — `decide`
  re-reads `ahead` from git (`Forge.ahead_of`) on every single pass rather than trusting the cursor;
  `merge` believes only `Forge.merge_to_base`'s verified post-state (HEAD moved AND a real merge
  commit exists), never a checkpointed flag or git's exit code; and `process_status DONE` still goes
  through the governed route, still gated by `tg_tickets_pair_completion`
  (0029_ticket_authorization.sql:133-141), which refuses DONE unless two DISTINCT agents hold two
  DISTINCT roles. Facts the checkpoint does carry forward (the merge sha `settle` puts in its
  work.record note, say) were established by git at the instant they were written and stay true in
  git — the checkpoint TRANSPORTS them, it never AUTHORIZES them. So a checkpoint that disagrees with
  git or the ledger cannot settle anything: git and the ledger win, and a stale cursor at worst
  re-runs an idempotent node.

THE ENGINE — read this before assuming which library runs (the docstring is a claim; this one is
checkable with `--engine`):
  The graph is DEFINED ONCE against the LangGraph API (`StateGraph`, `add_node`, `add_edge`,
  `add_conditional_edges`, `compile(checkpointer=...)`, `invoke(..., config={"configurable":
  {"thread_id": ...}})`, `interrupt()`, `Command(resume=...)`, `START`, `END`).
  * If `langgraph` (+ `langgraph-checkpoint-sqlite`) IS importable, that definition is compiled and
    run by REAL LangGraph with its real `SqliteSaver`. Nothing here shadows it.
  * If it is NOT importable, the SAME definition is compiled and run by the embedded, API-compatible
    engine in this file (`_EmbeddedStateGraph` + `_EmbeddedSqliteSaver`), which implements the exact
    subset used above with the same semantics (checkpoint per super-step; `invoke(None, cfg)`
    resumes; `interrupt()` pauses and re-executes its node from the start on resume).
  The fallback is not a preference, it is this repository's recorded constraint. DEPENDENCIES.md
  records the reference host's Python as carrying "no third-party packages, no `pip install`", and
  its stated discipline is "never ship a runtime-dependency change without recording it here" — which
  this ticket's mandate (create/overwrite ONLY this file, touch nothing else) does not permit. And in
  fact `langgraph` is not installed here and cannot be: `pip install` refuses under PEP 668
  (externally-managed environment). Verify both for yourself:
      python3 -c "import langgraph"          # ModuleNotFoundError
      python3 -m pip install langgraph       # error: externally-managed-environment
  A hard `import langgraph` would therefore make this tool crash on every invocation, on the very
  environment DEPENDENCIES.md records. `--engine` prints which engine is live.

  WHAT IS AND IS NOT PROVEN HERE (so this docstring promises nothing it has not earned): the
  EMBEDDED engine is what runs in this environment and what `--selftest` drives — every check it
  prints, including a real SIGKILL and resume. The LangGraph branch hands the identical definition to
  the real library and is written against its documented API (`StateGraph`/`add_conditional_edges`/
  `compile(checkpointer=...)`/`SqliteSaver.from_conn_string`/`interrupt`/`Command`, sources in
  docs/research/langgraph_lifecycle_state_machine.md §7), but it is NOT exercised here, because the
  library cannot be installed here. Install `langgraph` + `langgraph-checkpoint-sqlite` and
  `--engine` reports "langgraph" with the graph definition unchanged; re-run `--selftest` there to
  exercise that branch.

THE DRY EDGE — `decide` routes pass / fail / dry:
  pass   the adversary passed AND the branch has commits the base lacks -> approval_gate.
  fail   the adversary failed -> respawn a FRESH worker if rounds remain, else gave_up.
  dry    the adversary passed BUT `git rev-list <base>..ticket/<id>` is EMPTY — the round produced
         nothing to land (the worker reproduced what base already had byte-for-byte, so
         commit_deliverable made no commit), or a prior run already merged it. Nothing is merged,
         nothing is recorded, the branch and worktree persist, the ticket stays open. This is
         pair_loop's empty-branch refusal (module docstring policy 3, pair_loop.py:48-54) promoted to
         an explicit edge so it is decided BEFORE the merge is attempted rather than discovered
         inside it. `Forge.merge_to_base` remains the authority on every other refusal (conflict, a
         drifted base tree) and is never second-guessed.

THE APPROVAL GATE — the interrupt node, placed between a passing verdict and the irreversible merge:
  `approval_gate` calls `interrupt(payload)`, which PAUSES the graph and persists the checkpoint; the
  process may then exit entirely. An approver later reads the pending payload and resumes with
  `Command(resume={"approve": true, "wallet": "<id>", "signature": "<hex>"})`.
  The signature is HMAC-SHA256 over the CANONICAL payload (`json.dumps(payload, sort_keys=True,
  separators=(",", ":"))`) keyed by CONGRUENCY_WALLET_KEY (read from the environment or
  `.secrets/ats.env`, the same source pair_loop reads CONGRUENCY_API_KEY from, pair_loop.py:141-150).
  HMAC keyed by a held secret is the stdlib-only stand-in for a wallet's asymmetric signature; this
  node is the single seam where a real signer (EIP-191 / a hardware wallet) drops in — replace
  `wallet_verify` and nothing else changes.
  The gate FAILS CLOSED. It routes to `merge` only when `approve` is true AND the signature verifies
  against the exact payload the approver was shown. No key configured, a missing signature, a
  signature over a DIFFERENT payload, or `approve: false` all route to `held`: nothing is merged, the
  branch and worktree persist, the ticket stays open. Because a node re-executes from its start on
  resume, `approval_gate` performs NO side effect before its `interrupt()` call.

Usage (every form except --selftest/--engine needs CONGRUENCY_API_KEY, from the env or
.secrets/ats.env, and a reachable congruency server):
    python3 local_graph.py --ticket 251 --deliverable docs/X.md    # drive the ticket through the graph
    python3 local_graph.py --ticket 251 --deliverable docs/X.md --resume         # resume after a kill
    python3 local_graph.py --ticket 251 --status                   # show the checkpoint cursor
    python3 local_graph.py --ticket 251 --approve                  # sign the pending gate + merge
    python3 local_graph.py --ticket 251 --reject                   # refuse it; nothing merges
    python3 local_graph.py --selftest                              # prove the graph; no db, no agents
    python3 local_graph.py --engine                                # report the live engine, then exit
    ... [--rounds 2] [--timeout 480] [--base main] [--checkpoints PATH] [--keep-worktree]

--selftest builds THROWAWAY git repos in a temp dir and drives real graphs through them with the
governed routes and agent spawns replaced by recorded fakes. It proves the ticket's acceptance the
only way it can be proven: a child process is really SIGKILLed mid-run (signal 9 cannot be caught,
so nothing could have flushed on the way out), and a NEW process resumes from the checkpoint file and
settles. It never touches this repo, the db, the network, or the real checkpoint file, and spawns no
agents.

Exit codes (they mirror pair_loop's, with two added for the gate it does not have):
    0  settled — the branch merged into the base and the ticket is DONE (--selftest: all checks passed)
    1  rounds exhausted — the adversary never passed; branch + worktree kept, ticket stays open
       (--selftest: at least one check FAILED)
    2  unexpected — a Variant-A bug report was filed to the registry's bug_reports sink
    3  halted — an active stop ticket aims at this ticket or an ancestor; nothing was done
    4  refused — passed review but nothing landed: a merge conflict, a drifted base tree (#213), or a
       DRY round with no commits the base lacks. Branch + worktree persist; the ticket stays open.
    5  paused at the approval gate — awaiting a wallet-signed approval. NOT a failure: the checkpoint
       holds the run; --approve or --reject continues it.
    6  held — the approval was rejected or its signature did not verify. Nothing merged.
"""
import argparse
import contextlib
import hashlib
import hmac
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pair_loop  # noqa: E402  — the Forge, the governed routes and the prompts are REUSED, never forked
from pair_loop import ROOT, Unexpected  # noqa: E402

try:                        # TypedDict lives in typing on 3.8+; kept optional so the tool never dies on it
    from typing import TypedDict
except ImportError:         # pragma: no cover
    TypedDict = dict


# ══ the engine ═══════════════════════════════════════════════════════════════════════════════════
# Real LangGraph if it is installed; otherwise the embedded, API-compatible engine defined below.
# The graph DEFINITION (build_graph) is written once and does not know which of the two it got.

class _Interrupt(Exception):
    """Raised by the embedded `interrupt()` to pause the graph. Carries the approver's payload."""

    def __init__(self, payload):
        super().__init__("graph interrupted")
        self.payload = payload


class _EmbeddedCommand:
    """The embedded `Command(resume=...)`: hand a value back to the `interrupt()` that paused."""

    def __init__(self, resume=None):
        self.resume = resume


class _ResumeBox:
    """Holds the value a resuming `interrupt()` should return, for exactly one node execution.

    Process-global, which is sound because the embedded engine runs ONE graph per process — the same
    one-process-per-ticket model pair_loop uses (parallel tickets are parallel PROCESSES, each with
    its own branch, worktree and thread_id). Do not drive two embedded graphs from two threads of one
    process; nothing here needs to, and this box would be the race.
    """

    def __init__(self):
        self.has, self.value = False, None


_RESUME = _ResumeBox()


def _embedded_interrupt(payload):
    """Pause the graph and surface `payload`; on resume, return the value passed to Command(resume=).

    Mirrors LangGraph's dynamic interrupt: the node re-executes from its start on resume, and THIS
    call returns the resumed value instead of raising.
    """
    if _RESUME.has:
        _RESUME.has, v = False, _RESUME.value
        return v
    raise _Interrupt(payload)


class _EmbeddedSqliteSaver:
    """A checkpointer: one row per super-step in ITS OWN sqlite file.

    Never the governed `congruency.sqlite` — a checkpoint is volatile scratch and must not share a
    file with the append-only source of truth. Each `put` COMMITS before returning, which is what
    makes a SIGKILL survivable: whatever the resume reads was durable before the process died.
    """

    def __init__(self, con):
        self.con = con
        self.con.execute("CREATE TABLE IF NOT EXISTS checkpoints ("
                         "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                         "  thread_id TEXT NOT NULL,"
                         "  ts REAL NOT NULL,"
                         "  state TEXT NOT NULL,"
                         "  next TEXT NOT NULL,"
                         "  interrupt TEXT)")
        self.con.execute("CREATE INDEX IF NOT EXISTS ix_ckpt_thread ON checkpoints (thread_id, id)")
        self.con.commit()

    @classmethod
    @contextlib.contextmanager
    def from_conn_string(cls, path):
        """Context manager, matching langgraph.checkpoint.sqlite.SqliteSaver.from_conn_string."""
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
        con = sqlite3.connect(path)
        try:
            yield cls(con)
        finally:
            con.close()

    def put(self, thread_id, state, nxt, interrupt_payload=None):
        self.con.execute("INSERT INTO checkpoints (thread_id, ts, state, next, interrupt) VALUES (?,?,?,?,?)",
                         (thread_id, time.time(), json.dumps(state, default=str), nxt,
                          json.dumps(interrupt_payload) if interrupt_payload is not None else None))
        self.con.commit()   # durable BEFORE we return — the whole point

    def latest(self, thread_id):
        r = self.con.execute("SELECT state, next, interrupt FROM checkpoints WHERE thread_id = ? "
                             "ORDER BY id DESC LIMIT 1", (thread_id,)).fetchone()
        if not r:
            return None
        return {"state": json.loads(r[0]), "next": r[1],
                "interrupt": json.loads(r[2]) if r[2] else None}

    def history(self, thread_id):
        return [{"ts": ts, "next": nxt} for ts, nxt in
                self.con.execute("SELECT ts, next FROM checkpoints WHERE thread_id = ? ORDER BY id",
                                 (thread_id,)).fetchall()]


class _Snapshot:
    """What `get_state` returns: the checkpointed values, the next node, any pending interrupt.

    `.values` / `.next` carry the same meaning as LangGraph's StateSnapshot fields.
    """

    def __init__(self, values, nxt, interrupt_payload):
        self.values, self.next, self.interrupt = values, nxt, interrupt_payload


class _EmbeddedCompiled:
    """A compiled graph: run it with `invoke(input, config)`; resume with `invoke(None, config)`."""

    def __init__(self, nodes, edges, conds, entry, checkpointer):
        self.nodes, self.edges, self.conds = nodes, edges, conds
        self.entry, self.checkpointer = entry, checkpointer

    def _thread(self, config):
        try:
            return config["configurable"]["thread_id"]
        except (TypeError, KeyError):
            raise Unexpected('config must be {"configurable": {"thread_id": "<id>"}}')

    def _next_of(self, cur, state):
        if cur in self.conds:
            router, mapping = self.conds[cur]
            key = router(state)
            if key not in mapping:
                raise Unexpected("router for node %r returned %r, which is not one of %s"
                                 % (cur, key, sorted(mapping)))
            return mapping[key]
        if cur in self.edges:
            return self.edges[cur]
        raise Unexpected("node %r has no outgoing edge and is not END — the graph is malformed" % cur)

    def get_state(self, config):
        snap = self.checkpointer.latest(self._thread(config))
        return _Snapshot(snap["state"], snap["next"], snap["interrupt"]) if snap else _Snapshot({}, None, None)

    def invoke(self, inp, config=None):
        thread = self._thread(config)
        resume_value, has_resume = None, False
        if isinstance(inp, _EmbeddedCommand):
            resume_value, has_resume, inp = inp.resume, True, None
        if inp is None:                                   # ── resume from the checkpoint ──
            snap = self.checkpointer.latest(thread)
            if not snap:
                raise Unexpected("no checkpoint for thread %r — there is nothing to resume; run it "
                                 "without --resume first" % thread)
            if snap["next"] == END:
                return snap["state"]                      # already finished; resuming is a no-op
            state, cur = dict(snap["state"]), snap["next"]
        else:                                             # ── a fresh run ──
            state, cur = dict(inp), self.entry
            self.checkpointer.put(thread, state, cur)     # checkpoint BEFORE the first node runs
        while cur != END:
            _RESUME.has, _RESUME.value = has_resume, resume_value
            has_resume = False                            # only the node we resume INTO consumes it
            try:
                upd = self.nodes[cur](state)
            except _Interrupt as e:
                self.checkpointer.put(thread, state, cur, e.payload)   # pause here; re-run this node on resume
                out = dict(state)
                out["__interrupt__"] = [e.payload]
                return out
            finally:
                _RESUME.has, _RESUME.value = False, None
            if upd:
                state.update(upd)                         # last-value-wins channels (LangGraph's default)
            nxt = self._next_of(cur, state)
            self.checkpointer.put(thread, state, nxt)     # one checkpoint per super-step
            cur = nxt
        return state


class _EmbeddedStateGraph:
    """The embedded `StateGraph`: the subset of the builder API this module uses."""

    def __init__(self, state_schema=None):
        self.state_schema = state_schema        # accepted for API parity; channels are last-value-wins
        self.nodes, self.edges, self.conds, self.entry = {}, {}, {}, None

    def add_node(self, name, fn):
        self.nodes[name] = fn

    def add_edge(self, src, dst):
        if src == START:
            self.entry = dst
        else:
            self.edges[src] = dst

    def add_conditional_edges(self, src, router, mapping):
        self.conds[src] = (router, mapping)

    def compile(self, checkpointer=None):
        if checkpointer is None:
            raise Unexpected("this graph requires a checkpointer (the interrupt node has nothing to "
                             "resume from without one)")
        if not self.entry:
            raise Unexpected("the graph has no START edge")
        return _EmbeddedCompiled(self.nodes, self.edges, self.conds, self.entry, checkpointer)


try:
    from langgraph.graph import StateGraph, START, END          # noqa: F401
    from langgraph.types import interrupt, Command              # noqa: F401
    from langgraph.checkpoint.sqlite import SqliteSaver         # noqa: F401
    ENGINE = "langgraph"
except ImportError:
    START, END = "__start__", "__end__"
    StateGraph, SqliteSaver = _EmbeddedStateGraph, _EmbeddedSqliteSaver
    interrupt, Command = _embedded_interrupt, _EmbeddedCommand
    ENGINE = "embedded"


# ══ the state: the VOLATILE CURSOR ONLY (no settled fact is authoritative here) ═══════════════════
class LifecycleState(TypedDict, total=False):
    tid: int                 # the ticket this run is authorized by
    kind: str                # its kind (a pair kind: build / bug / documentation / bet)
    title: str
    body: str
    deliverable: str         # repo-relative path the worker must produce
    base: str                # branch ticket/<id> forked from and merges back into
    branch: str
    worktree: str
    rounds: int              # max worker rounds before giving up
    round: int               # THE cursor pair_loop loses on a kill
    worker: str
    auditor: str
    forge: str               # the forge agent id (holds the git pen)
    w_role: str
    a_role: str
    stops: int
    verdict: str
    findings: list           # the current round's findings, injected into the next worker's prompt
    history: list            # [{"round": n, "findings": [...]}] — harvest's input
    committed: bool
    sha: str
    strays: list
    ahead: int               # re-derived from git in `decide`, never trusted from the checkpoint
    timeout: int             # seconds per agent spawn
    keep_worktree: bool
    approved: bool
    approval_note: str
    note: str                # the worker's one-line note on what it produced
    ref: str
    merge_sha: str
    reason: str
    outcome: str             # set ONLY by a terminal node; maps to the exit code
    reaped: bool


OUTCOME_EXIT = {"settled": 0, "gave_up": 1, "halted": 3, "refused": 4, "paused": 5, "held": 6}


# ══ the wallet ════════════════════════════════════════════════════════════════════════════════════
def wallet_canonical(payload):
    """The exact bytes a wallet signs: the payload, canonically serialized.

    Sorted keys + no whitespace, so the approver and the verifier agree byte-for-byte regardless of
    dict ordering. Sign what you see: the signature covers the WHOLE approval payload (ticket,
    branch, base, verdict, ahead, sha), so a signature is not transferable to a different merge.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def wallet_sign(payload, key):
    return hmac.new(key.encode(), wallet_canonical(payload).encode(), hashlib.sha256).hexdigest()


def wallet_verify(payload, signature, key):
    """True only if `signature` is a valid HMAC-SHA256 over THIS payload under `key`. Fails closed.

    The seam a real wallet replaces: swap this for an asymmetric verify (recover the signer from an
    EIP-191 signature and check it against an allow-list) and the graph is unchanged.
    """
    if not key or not signature:
        return False
    return hmac.compare_digest(wallet_sign(payload, key), str(signature))


def wallet_key():
    """The wallet secret, from the same place pair_loop reads its api key (pair_loop.py:141-150)."""
    return pair_loop._secret("CONGRUENCY_WALLET_KEY")


# ══ dependencies: the seam the selftest replaces (real routes/spawns vs recorded fakes) ═══════════
class Deps:
    """Everything the nodes reach the outside world through.

    The real wiring is pair_loop's, verbatim — `Forge` for git, `rest`/`rows` for the governed REST
    surface, `spawn_claude` for agents, `harvest` for the lesson. --selftest swaps in fakes so the
    graph can be driven with no db, no network and no agents; the graph itself never changes.

    `spawn(role, prompt, tools, timeout, cwd, rnd)` takes the round explicitly: the round is the
    graph's cursor, and a resumed process must serve the round the CHECKPOINT says it is on, not one
    it counted for itself (a fresh process has counted nothing).
    """

    def __init__(self, forge, rest, rows, spawn, harvest, forge_agent, wkey=None, on_node=None):
        self.forge, self.rest, self.rows = forge, rest, rows
        self.spawn, self.harvest, self.forge_agent = spawn, harvest, forge_agent
        self.wallet_key = wkey
        self.on_node = on_node or (lambda name: None)


def real_deps(base_root=None):
    def spawn(role, prompt, tools, timeout, cwd, rnd):
        return pair_loop.spawn_claude(prompt, tools, timeout, cwd)
    return Deps(pair_loop.forge_for(base_root), pair_loop.rest, pair_loop.rows, spawn,
                pair_loop.harvest, pair_loop.forge_agent, wallet_key())


# ══ the nodes — each a thin wrapper over pair_loop's existing, tested code ════════════════════════
def n_brake(state, deps):
    """BRAKE: an active stop aimed at this ticket or any ancestor halts the run before anything acts."""
    st = deps.rows("ticket.stops", {"ticket_id": state["tid"]})
    return {"stops": int(st[0]["active_stops"]) if st else 0}


def r_brake(state):
    return "halt" if int(state.get("stops", 0)) > 0 else "clear"


def n_open_worktree(state, deps):
    """Open branch ticket/<id> in its own worktree. Idempotent: a resumed run reuses both.

    The forge agent (the ticket's git steward, which holds the git pen) is registered HERE, not
    before the graph starts: the brake must halt a stopped ticket "before anything acts", and
    `agent.register` is an act. This mirrors pair_loop, which brakes at :1002-1006 and only calls
    forge_agent at :1011. Registration is idempotent, so re-running this node on a resume is safe.
    """
    fid = deps.forge_agent(state["tid"])
    wt = deps.forge.open_worktree(state["tid"], state["base"])
    deps.rest("ticket.progress", {
        "ticket_id": state["tid"], "agent_id": fid,
        "note": "branch %s %s off %s; worktree %s" % (
            wt["branch"], "opened" if wt["created"] else "reopened (resumed)", state["base"],
            os.path.relpath(wt["path"], deps.forge.root))})
    return {"branch": wt["branch"], "worktree": wt["path"], "forge": fid}


def _prompt_ctx(state, deps):
    focus = pair_loop.FOCUS.get(state["kind"], pair_loop.FOCUS["documentation"])
    pb = os.path.join(state["worktree"], "docs/PLAYBOOK.md")
    pb_line = ("\nBefore starting, read docs/PLAYBOOK.md — the AUDITED playbook of lessons harvested "
               "from prior tickets. Apply what applies.\n") if os.path.isfile(pb) else ""
    ctx = dict(tid=state["tid"], kind=state["kind"], title=state["title"], body=state["body"],
               deliverable=state["deliverable"], playbook=pb_line, branch=state["branch"],
               workspace=pair_loop.WORKSPACE % {"branch": state["branch"]},
               worker_focus=focus["worker_focus"], audit_focus=focus["audit_focus"])
    return ctx, focus


def n_spawn_pair(state, deps):
    """PAIR: register a FRESH worker + adversary for this round and authorize both on the ticket.

    A fresh spawn IS the memory clear. The old agents' trails stay on the record forever.
    """
    ctx, _ = _prompt_ctx(state, deps)
    worker = "%s-t%dr%d" % (state["w_role"], state["tid"], state["round"])
    auditor = "%s-t%dr%d" % (state["a_role"], state["tid"], state["round"])
    for agent, role, tmpl in ((worker, state["w_role"], pair_loop.WORKER_PROMPT),
                              (auditor, state["a_role"], pair_loop.AUDITOR_PROMPT)):
        fx = ("\nPrior adversary findings to address:\n- " + "\n- ".join(state.get("findings") or []) + "\n"
              if (state.get("findings") and role == state["w_role"]) else "")
        deps.rest("agent.register", {"agent_id": agent, "parent": "local_graph",
                                     "prompt": tmpl % {**ctx, "agent": agent, "role": role, "findings": fx},
                                     "tools": json.dumps(["claude -p"])})
        deps.rest("ticket.assign", {"ticket_id": state["tid"], "agent_id": agent, "role": role})
    deps.rest("process_status", {"id": state["tid"], "status": "ACTIVE"})
    return {"worker": worker, "auditor": auditor}


def n_run_worker(state, deps):
    """WORK: the worker produces the deliverable IN the worktree. It holds no git pen."""
    ctx, focus = _prompt_ctx(state, deps)
    fx = ("\nPrior adversary findings to address:\n- " + "\n- ".join(state.get("findings") or []) + "\n"
          if state.get("findings") else "")
    prompt = pair_loop.WORKER_PROMPT % {**ctx, "agent": state["worker"], "role": state["w_role"], "findings": fx}
    res = deps.spawn("worker", prompt, focus["worker_tools"], state.get("timeout", 480),
                     state["worktree"], state["round"])
    if not res.get("done"):
        raise Unexpected("worker did not report done: %s" % res)
    deps.rest("ticket.progress", {"ticket_id": state["tid"], "agent_id": state["worker"],
                                  "note": "round %d: produced %s — %s"
                                          % (state["round"], res.get("ref"), res.get("note", "")),
                                  "steps_remaining": 2})
    return {"ref": res.get("ref"), "note": res.get("note", "")}


def n_commit(state, deps):
    """The HARNESS commits the deliverable onto the ticket's branch — every round."""
    cm = deps.forge.commit_deliverable(
        state["tid"], state["deliverable"],
        "ticket #%d: %s\n\n%s\n\nRound %d on %s; worker %s; deliverable %s"
        % (state["tid"], (state["title"] or "")[:64], state.get("note", ""), state["round"],
           state["branch"], state["worker"], state["deliverable"]))
    deps.rest("ticket.progress", {
        "ticket_id": state["tid"], "agent_id": state["forge"],
        "note": "round %d: %s on %s @ %s%s" % (
            state["round"],
            "committed %s" % state["deliverable"] if cm["committed"] else "no change to commit for %s" % state["deliverable"],
            state["branch"], cm["sha"][:10],
            ("; UNCOMMITTED strays left in the worktree (the mandate forbids them; they will not "
             "survive the reap): " + ", ".join(cm["strays"][:5])) if cm["strays"] else "")})
    return {"committed": cm["committed"], "sha": cm["sha"], "strays": cm["strays"]}


def n_run_auditor(state, deps):
    """VALIDATE: the adversary judges the artifact BLIND to the worker's reasoning."""
    ctx, focus = _prompt_ctx(state, deps)
    prompt = pair_loop.AUDITOR_PROMPT % {**ctx, "agent": state["auditor"], "role": state["a_role"]}
    res = deps.spawn("auditor", prompt, focus["auditor_tools"], state.get("timeout", 480),
                     state["worktree"], state["round"])
    verdict, findings = res.get("verdict"), res.get("findings", [])
    if verdict not in ("pass", "fail"):
        raise Unexpected("adversary returned no usable verdict (want 'pass' or 'fail'): %s" % res)
    deps.rest("ticket.progress", {
        "ticket_id": state["tid"], "agent_id": state["auditor"],
        "note": "round %d verdict: %s%s" % (state["round"], verdict,
                                            ("; findings: " + "; ".join(findings)) if findings else ""),
        "steps_remaining": 1 if verdict == "pass" else 3})
    return {"verdict": verdict, "findings": findings}


def n_decide(state, deps):
    """The routing node. Pure w.r.t. the ledger — it only RE-DERIVES `ahead` from git.

    `ahead` is read from git every single pass (never from the checkpoint) because it is a settled
    fact and git owns it: a resumed run must see what the repository actually holds now, not what the
    cursor believed before the kill.
    """
    return {"ahead": deps.forge.ahead_of(state["tid"], state["base"])}


def r_decide(state):
    """pass / fail / dry — the ticket's conditional edges."""
    if state.get("verdict") != "pass":
        return "fail" if state["round"] < state["rounds"] else "exhausted"
    return "pass" if int(state.get("ahead", 0)) > 0 else "dry"


def n_approval_gate(state, deps):
    """The INTERRUPT node: pause and demand a wallet-signed approval before the merge.

    Performs NO side effect before `interrupt()`: on resume this node re-executes from its start, so
    anything above the interrupt would run twice.
    """
    payload = {"kind": "merge_approval", "ticket": state["tid"], "branch": state["branch"],
               "base": state["base"], "verdict": "pass", "ahead": int(state.get("ahead", 0)),
               "sha": state.get("sha", ""), "deliverable": state["deliverable"]}
    decision = interrupt(payload)          # ── the graph pauses HERE; the process may exit ──

    if not isinstance(decision, dict):
        return {"approved": False, "approval_note": "malformed approval (want a JSON object with "
                                                    "approve/wallet/signature); nothing merged"}
    if not decision.get("approve"):
        return {"approved": False, "approval_note": "approval REFUSED by %s" % (decision.get("wallet") or "(unsigned)")}
    if not deps.wallet_key:
        return {"approved": False, "approval_note": "no CONGRUENCY_WALLET_KEY configured — the gate "
                                                    "fails closed; nothing merged"}
    if not wallet_verify(payload, decision.get("signature"), deps.wallet_key):
        return {"approved": False, "approval_note": "signature did NOT verify against the approval "
                                                    "payload — refusing to merge on an unsigned or "
                                                    "mis-scoped approval"}
    return {"approved": True, "approval_note": "wallet-signed approval verified (wallet %s)"
                                               % (decision.get("wallet") or "(anonymous)")}


def r_approval(state):
    return "approved" if state.get("approved") else "rejected"


def n_merge(state, deps):
    """SETTLE step 1: merge ticket/<id> into the base. `merge_to_base` is the sole authority on ok."""
    mg = deps.forge.merge_to_base(state["tid"], state["base"],
                                  "merge %s: ticket #%d — %s\n\n%s"
                                  % (state["branch"], state["tid"], (state["title"] or "")[:64],
                                     state.get("note", "")))
    if not mg.get("ok"):
        return {"reason": mg.get("reason", "merge refused")}
    return {"merge_sha": mg["sha"], "ahead": mg.get("ahead", 0), "reason": ""}


def r_merge(state):
    return "ok" if state.get("merge_sha") else "refused"


def n_settle(state, deps):
    """SETTLE step 2: the permanent UID and DONE — both through the governed routes.

    `process_status DONE` is refused by the db itself unless two DISTINCT agents hold two DISTINCT
    roles (tg_tickets_pair_completion). The checkpoint proves nothing to the db; only the pair does.
    """
    deps.rest("work.record", {"ticket_id": state["tid"],
                              "kind": "doc" if state["kind"] == "documentation" else "code",
                              "ref": state.get("ref") or state["deliverable"],
                              "note": "%s [%s @ %s merged to %s @ %s]"
                                      % (state.get("note", ""), state["branch"], state.get("sha", "")[:10],
                                         state["base"], state["merge_sha"][:10])})
    deps.rest("ticket.progress", {
        "ticket_id": state["tid"], "agent_id": state["forge"],
        "note": "MERGED %s -> %s (--no-ff): %d commit(s) landed in merge commit %s; %s; branch kept "
                "as the ticket's trace" % (state["branch"], state["base"], int(state.get("ahead", 0)),
                                           state["merge_sha"][:10], state.get("approval_note", ""))})
    deps.rest("process_status", {"id": state["tid"], "status": "DONE"})
    return {"history": (state.get("history") or []) + [{"round": state["round"], "findings": []}]}


def n_reap(state, deps):
    """The worktree is ephemeral; the BRANCH is kept as the ticket's durable trace."""
    reaped = False if state.get("keep_worktree") else deps.forge.reap_worktree(state["tid"])
    deps.rest("ticket.progress", {"ticket_id": state["tid"], "agent_id": state["forge"],
                                  "note": "worktree %s (base tree clean, #213/#216)"
                                          % ("reaped" if reaped else "KEPT (--keep-worktree)")})
    deps.rest("ticket.progress", {"ticket_id": state["tid"], "agent_id": state["auditor"],
                                  "note": "PASS — manifest updated, ticket DONE; pair retired (fresh "
                                          "agents next iteration)", "steps_remaining": 0})
    return {"reaped": reaped, "outcome": "settled"}


def n_respawn(state, deps):
    """fail + rounds left: advance the cursor. THIS increment is what a kill used to destroy."""
    return {"round": state["round"] + 1,
            "history": (state.get("history") or []) + [{"round": state["round"],
                                                        "findings": state.get("findings") or ["(none given)"]}]}


def n_halted(state, deps):
    print("== HALT == %s active stop ticket(s) aim at #%s — the ticket authorizes nothing"
          % (state.get("stops"), state["tid"]))
    return {"outcome": "halted"}


def n_dry(state, deps):
    """The dry edge's terminal: a passing verdict with nothing to land settles NOTHING."""
    reason = ("branch %s has NO commits that %s lacks — nothing to merge. The deliverable was never "
              "committed on the branch (the worker may have reproduced what %s already had), or a "
              "prior run already merged it. Branch and worktree kept; ticket stays open."
              % (state["branch"], state["base"], state["base"]))
    deps.rest("ticket.progress", {"ticket_id": state["tid"], "agent_id": state["forge"],
                                  "note": "DRY ROUND: %s" % reason, "steps_remaining": 2})
    print("== dry == #%s passed review but %s" % (state["tid"], reason))
    return {"outcome": "refused", "reason": reason,
            "history": (state.get("history") or []) + [{"round": state["round"],
                                                        "findings": ["dry round: %s" % reason]}]}


def n_merge_refused(state, deps):
    deps.rest("ticket.progress", {"ticket_id": state["tid"], "agent_id": state["forge"],
                                  "note": "MERGE REFUSED: %s. Branch %s and its worktree PERSIST; the "
                                          "ticket stays open — resolve and re-run."
                                          % (state.get("reason"), state["branch"]), "steps_remaining": 2})
    print("== not settled == #%s passed review but %s — branch %s kept, ticket stays open"
          % (state["tid"], state.get("reason"), state["branch"]))
    return {"outcome": "refused",
            "history": (state.get("history") or []) + [{"round": state["round"],
                                                        "findings": ["merge blocked: %s" % state.get("reason")]}]}


def n_held(state, deps):
    """The approval gate's refusal terminal. Nothing merged; the work is not thrown away."""
    deps.rest("ticket.progress", {"ticket_id": state["tid"], "agent_id": state["forge"],
                                  "note": "MERGE NOT APPROVED: %s. Branch %s and its worktree PERSIST; "
                                          "the ticket stays open." % (state.get("approval_note"), state["branch"]),
                                  "steps_remaining": 2})
    print("== held == #%s awaits approval — %s; branch %s kept, nothing merged"
          % (state["tid"], state.get("approval_note"), state["branch"]))
    return {"outcome": "held",
            "history": (state.get("history") or []) + [{"round": state["round"],
                                                        "findings": ["merge not approved: %s"
                                                                     % state.get("approval_note")]}]}


def n_gave_up(state, deps):
    deps.rest("ticket.progress", {"ticket_id": state["tid"], "agent_id": state["forge"],
                                  "note": "rounds exhausted — branch %s and worktree kept unmerged; "
                                          "ticket stays open" % state["branch"]})
    print("== gave up == %d rounds exhausted on #%s; branch %s and its worktree persist"
          % (state["rounds"], state["tid"], state["branch"]))
    return {"outcome": "gave_up",
            "history": (state.get("history") or []) + [{"round": state["round"],
                                                        "findings": state.get("findings") or ["(none given)"]}]}


def n_harvest_pass(state, deps):
    deps.harvest(state["tid"], state.get("history") or [], True, state.get("note", ""))
    print("== settled == ticket #%s DONE (round %d) — %s committed on %s @ %s, merged to %s @ %s; "
          "worktree %s" % (state["tid"], state["round"], state.get("ref"), state["branch"],
                           state.get("sha", "")[:10], state["base"], state.get("merge_sha", "")[:10],
                           "reaped" if state.get("reaped") else "kept"))
    return {}


def n_harvest_fail(state, deps):
    deps.harvest(state["tid"], state.get("history") or [], False, "")
    return {}


# ══ the graph ════════════════════════════════════════════════════════════════════════════════════
def build_graph(deps, checkpointer):
    """brake -> pair -> work -> validate -> settle -> harvest, with the conditional edges and the gate.

    Written once against the LangGraph builder API; compiled by real LangGraph when it is installed
    and by the embedded engine otherwise (see the module docstring, "THE ENGINE").
    """
    b = StateGraph(LifecycleState)

    def node(name, fn):
        """Bind deps, and give the selftest a seam to observe/kill at a named node."""
        def run(state, _fn=fn, _name=name):
            deps.on_node(_name)
            return _fn(state, deps)
        b.add_node(name, run)

    for name, fn in (("brake", n_brake), ("open_worktree", n_open_worktree), ("spawn_pair", n_spawn_pair),
                     ("run_worker", n_run_worker), ("commit", n_commit), ("run_auditor", n_run_auditor),
                     ("decide", n_decide), ("approval_gate", n_approval_gate), ("merge", n_merge),
                     ("settle", n_settle), ("reap", n_reap), ("respawn", n_respawn),
                     ("halted", n_halted), ("dry", n_dry), ("merge_refused", n_merge_refused),
                     ("held", n_held), ("gave_up", n_gave_up),
                     ("harvest_pass", n_harvest_pass), ("harvest_fail", n_harvest_fail)):
        node(name, fn)

    b.add_edge(START, "brake")
    b.add_conditional_edges("brake", r_brake, {"clear": "open_worktree", "halt": "halted"})
    b.add_edge("open_worktree", "spawn_pair")
    b.add_edge("spawn_pair", "run_worker")
    b.add_edge("run_worker", "commit")
    b.add_edge("commit", "run_auditor")
    b.add_edge("run_auditor", "decide")
    # the ticket's conditional edges: pass / fail / dry
    b.add_conditional_edges("decide", r_decide, {"pass": "approval_gate", "fail": "respawn",
                                                 "dry": "dry", "exhausted": "gave_up"})
    b.add_edge("respawn", "spawn_pair")                       # a FRESH pair, findings carried
    b.add_conditional_edges("approval_gate", r_approval, {"approved": "merge", "rejected": "held"})
    b.add_conditional_edges("merge", r_merge, {"ok": "settle", "refused": "merge_refused"})
    b.add_edge("settle", "reap")
    b.add_edge("reap", "harvest_pass")
    b.add_edge("harvest_pass", END)
    for terminal in ("dry", "merge_refused", "held", "gave_up"):
        b.add_edge(terminal, "harvest_fail")
    b.add_edge("harvest_fail", END)
    b.add_edge("halted", END)                                 # a halted ticket authorized nothing to harvest

    return b.compile(checkpointer=checkpointer)


def thread_config(tid, rounds=2):
    """One ticket, one resumable thread — the direct analogue of pair_loop's one-process-per-ticket.

    `recursion_limit` is raised to fit the rounds: one round costs ~6 super-steps (spawn_pair,
    run_worker, commit, run_auditor, decide, respawn) on top of ~8 for the brake/open/settle/harvest
    spans, and real LangGraph aborts a run with GraphRecursionError once it exceeds the limit (which
    defaults to 25 — i.e. it would kill a perfectly healthy --rounds 4 run partway through). The
    embedded engine reads only `configurable.thread_id` and ignores this key, so the value is set
    for the benefit of the LangGraph path.
    """
    return {"configurable": {"thread_id": "ticket-%d" % int(tid)},
            "recursion_limit": 20 + 10 * max(1, int(rounds or 1))}


def default_checkpoints():
    """The checkpointer's OWN file. Never congruency.sqlite: scratch must not touch the ledger."""
    return os.path.join(ROOT, "checkouts", "current", "state", "langgraph_checkpoints.sqlite")


def pending_interrupt(graph, cfg):
    """The approval payload a paused run is waiting on — engine-agnostic."""
    snap = graph.get_state(cfg)
    if getattr(snap, "interrupt", None):
        return snap.interrupt
    for t in (getattr(snap, "tasks", None) or []):            # real LangGraph surfaces it on the task
        for it in (getattr(t, "interrupts", None) or []):
            return getattr(it, "value", None)
    return None


def result_outcome(res):
    """Map a finished/paused invoke result to an outcome name."""
    if res.get("__interrupt__"):
        return "paused"
    return res.get("outcome") or "gave_up"


# ══ driving a real ticket ════════════════════════════════════════════════════════════════════════
def ticket_meta(tid):
    """Read the ticket + its kind's roles, exactly as pair_loop.main does before it brakes."""
    with urllib.request.urlopen(pair_loop.CONG + "/rest.php?api=tickets&id=%d" % tid, timeout=15) as r:
        tk = json.loads(r.read().decode()).get("row") or {}
    kind = tk.get("kind")
    if not kind:
        raise Unexpected("ticket #%s has no kind — set it via ticket.kind first" % tid)
    kinds = {k["kind"]: k for k in pair_loop.rows("kind.roster", {})}
    if kinds.get(kind, {}).get("pattern") != "pair":
        raise Unexpected("ticket #%s kind %r is not a pair kind — this graph harnesses pairs" % (tid, kind))
    return tk, kind, kinds[kind]["worker_role"], kinds[kind]["adversary_role"]


def run_ticket(a):
    """Drive (or resume) one ticket through the graph and return its exit code."""
    tid = a.ticket
    deps = real_deps()
    cfg = thread_config(tid, a.rounds)
    ckpt = a.checkpoints or default_checkpoints()

    # Only a real DRIVE may bring the checkpoint store into being. --status/--resume/--approve/
    # --reject all merely ask about a run that must already exist, and a question must not create
    # its own subject: opening the saver would materialize an empty sqlite file (and its directory)
    # in the state dir, so a read would leave a trace and "no checkpoint" would be reported by a
    # command that had just created one.
    if not os.path.isfile(ckpt) and (a.status or a.resume or a.approve or a.reject):
        print("no checkpoint store at %s — nothing has been driven through the graph yet, so there "
              "is no thread for ticket #%d to %s. Start one with:\n"
              "   python3 local_graph.py --ticket %d --deliverable <path>"
              % (ckpt, tid, "inspect" if a.status else "resume", tid))
        return 0 if a.status else 2

    with SqliteSaver.from_conn_string(ckpt) as saver:
        graph = build_graph(deps, saver)

        if a.status:
            snap = graph.get_state(cfg)
            if not snap.next:
                print("no checkpoint for thread ticket-%d in %s" % (tid, ckpt))
                return 0
            print("thread    ticket-%d  (engine: %s, checkpoints: %s)" % (tid, ENGINE, ckpt))
            print("next node %s" % snap.next)
            for k in ("round", "rounds", "branch", "worktree", "verdict", "ahead", "committed", "outcome"):
                if k in snap.values:
                    print("%-9s %s" % (k, snap.values[k]))
            p = pending_interrupt(graph, cfg)
            if p:
                print("PAUSED awaiting a wallet-signed approval of:\n  %s" % wallet_canonical(p))
            return 0

        if a.approve or a.reject:
            p = pending_interrupt(graph, cfg)
            if not p:
                print("ticket #%d is not paused at the approval gate — nothing to approve" % tid)
                return 2
            if a.reject:
                decision = {"approve": False, "wallet": a.wallet or "operator"}
            else:
                key = deps.wallet_key
                if not key:
                    print("no CONGRUENCY_WALLET_KEY (env or .secrets/ats.env) — cannot sign the approval")
                    return 2
                decision = {"approve": True, "wallet": a.wallet or "operator",
                            "signature": wallet_sign(p, key)}
            res = graph.invoke(Command(resume=decision), config=cfg)
            return OUTCOME_EXIT.get(result_outcome(res), 2)

        if a.resume:
            res = graph.invoke(None, config=cfg)
            return OUTCOME_EXIT.get(result_outcome(res), 2)

        tk, kind, w_role, a_role = ticket_meta(tid)
        base = a.base or deps.forge.current_branch()
        # NOTE: no forge agent here — registering one is an act, and the brake node has not run yet.
        # `open_worktree` registers it once the brake clears (see n_open_worktree).
        init = {"tid": tid, "kind": kind, "title": tk.get("title", ""), "body": tk.get("body", ""),
                "deliverable": a.deliverable, "base": base, "rounds": a.rounds, "round": 1,
                "timeout": a.timeout, "keep_worktree": bool(a.keep_worktree),
                "w_role": w_role, "a_role": a_role, "findings": [], "history": []}
        res = graph.invoke(init, config=cfg)
        outcome = result_outcome(res)
        if outcome == "paused":
            print("== paused == ticket #%d is at the approval gate. Approve with:\n"
                  "   python3 local_graph.py --ticket %d --approve" % (tid, tid))
        return OUTCOME_EXIT.get(outcome, 2)


# ══ --selftest ═══════════════════════════════════════════════════════════════════════════════════
# The acceptance is proven the only way it CAN be proven: a child process is really SIGKILLed
# mid-run, and a NEW process resumes from the checkpoint file and settles. No db, no network, no
# agents, and this repo is never touched.

def _fake_deps(repo, plan, ledger_path, kill_at=None):
    """pair_loop's Forge against a THROWAWAY repo; the routes and spawns recorded, not performed."""
    forge = pair_loop.Forge(repo)

    def record(route, obj):
        with open(ledger_path, "a") as fh:
            fh.write(json.dumps({"route": route, "obj": obj}) + "\n")

    # ticket -> {(agent, role)}: enough to emulate the db's pair-completion trigger. Rebuilt from the
    # recorded ledger, never from memory — `ticket_agents` is a TABLE, so the assignments a previous
    # process made are still there when a resuming process asks. (An in-memory map would make a
    # resumed --approve look like an unassigned ticket and refuse a DONE the real db would allow.)
    assigned = {}
    if os.path.isfile(ledger_path):
        for line in open(ledger_path):
            e = json.loads(line)
            if e["route"] == "ticket.assign":
                assigned.setdefault(e["obj"]["ticket_id"], set()).add((e["obj"]["agent_id"], e["obj"]["role"]))

    def rest(route, obj=None, method=None):
        if route == "ticket.assign":
            assigned.setdefault(obj["ticket_id"], set()).add((obj["agent_id"], obj["role"]))
        if route == "process_status" and str(obj.get("status")).upper() == "DONE":
            # emulate tg_tickets_pair_completion (0029_ticket_authorization.sql:133-141): the db
            # refuses DONE on a pair ticket without two DISTINCT agents in two DISTINCT roles.
            pairs = assigned.get(obj["id"], set())
            if len({a for a, _ in pairs}) < 2 or len({r for _, r in pairs}) < 2:
                raise Unexpected("a pair ticket is an adversarial network: DONE requires two DISTINCT "
                                 "agents in two DISTINCT roles")
        record(route, obj)
        return {"ok": True, "rowid": 1}

    def rows(route, params):
        if route == "ticket.stops":
            return [{"active_stops": plan.get("stops", 0)}]
        return []

    def spawn(role, prompt, tools, timeout, cwd, rnd):
        """The scripted stand-in for a `claude -p` spawn. `rnd` is the graph's own cursor, so a
        RESUMED process serves the round the checkpoint says it is on."""
        if role == "worker":
            content = plan["worker"][min(rnd, len(plan["worker"])) - 1]
            path = os.path.join(cwd, plan["deliverable"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                fh.write(content)
            return {"done": True, "ref": plan["deliverable"], "note": "round %d content" % rnd}
        v = plan["verdict"][min(rnd, len(plan["verdict"])) - 1]
        return {"verdict": v, "findings": [] if v == "pass" else ["round %d finding" % rnd]}

    def harvest(tid, history, passed, note):
        record("ticket.lesson", {"ticket_id": tid, "passed": passed, "rounds": len(history),
                                 "note": note})

    def forge_agent(tid):
        """Stands in for pair_loop.forge_agent, which agent.registers the ticket's git steward.

        It RECORDS the registration, so "a halted ticket registers no agents" is a real check on the
        real ordering: if this were ever called before the brake, the ledger would show it.
        """
        fid = "forge-t%d" % tid
        record("agent.register", {"agent_id": fid, "parent": "local_graph"})
        return fid

    def on_node(name):
        record("__node__", {"name": name})
        if kill_at and name == kill_at:
            with open(ledger_path, "a") as fh:                # flush the trail before we vanish
                fh.write(json.dumps({"route": "__killing__", "obj": {"at": name}}) + "\n")
            os.kill(os.getpid(), signal.SIGKILL)              # uncatchable: nothing can flush after this

    return Deps(forge, rest, rows, spawn, harvest, forge_agent, wkey=plan.get("wallet_key"),
                on_node=on_node)


def _selftest_child(a):
    """One graph run inside the throwaway repo, in its OWN process, so it can be really killed."""
    plan = json.load(open(a.plan))
    deps = _fake_deps(a.repo, plan, a.ledger, a.kill_at)

    with SqliteSaver.from_conn_string(a.ckpt) as saver:
        graph = build_graph(deps, saver)
        cfg = thread_config(a.tid, plan["rounds"])

        if a.mode == "fresh":
            init = {"tid": a.tid, "kind": "build", "title": "selftest ticket", "body": "drive the graph",
                    "deliverable": plan["deliverable"], "base": plan["base"], "rounds": plan["rounds"],
                    "round": 1, "timeout": 5, "keep_worktree": False, "w_role": "coder", "a_role": "tester",
                    "findings": [], "history": []}
            res = graph.invoke(init, config=cfg)
        elif a.mode == "resume":
            res = graph.invoke(None, config=cfg)
        else:                                                  # approve / approve-bad / reject
            p = pending_interrupt(graph, cfg)
            if p is None:
                print("child: not paused at the gate")
                return 2
            if a.mode == "reject":
                decision = {"approve": False, "wallet": "w-selftest"}
            elif a.mode == "approve-bad":
                decision = {"approve": True, "wallet": "w-evil",
                            "signature": wallet_sign(p, "the-WRONG-key")}
            else:
                decision = {"approve": True, "wallet": "w-selftest",
                            "signature": wallet_sign(p, plan["wallet_key"])}
            res = graph.invoke(Command(resume=decision), config=cfg)
        outcome = result_outcome(res)
        print("child: outcome=%s" % outcome)
        return OUTCOME_EXIT.get(outcome, 2)


def selftest():
    """Drive real graphs through throwaway repos and CHECK each acceptance claim.

    Prints one PASS/FAIL line per check; returns 0 only if every check passed.
    """
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name, ("  — %s" % detail) if detail and not cond else ""))

    base_dir = tempfile.mkdtemp(prefix="local_graph-selftest-")
    try:
        repo = pair_loop._st_repo(base_dir)        # the same throwaway-repo builder pair_loop --selftest uses
        f = pair_loop.Forge(repo)
        base = f.current_branch()
        ckpt = os.path.join(base_dir, "checkpoints.sqlite")
        print("== selftest == engine: %s; throwaway repo %s (base branch %r)" % (ENGINE, repo, base))
        print("== selftest == checkpoints: %s (its own file — the ledger is never touched)" % ckpt)

        def child(tid, mode, plan, kill_at=None):
            pf = os.path.join(base_dir, "plan-%d.json" % tid)
            with open(pf, "w") as fh:
                json.dump(plan, fh)
            cmd = [sys.executable, os.path.abspath(__file__), "--selftest-child", "--repo", repo,
                   "--ckpt", ckpt, "--tid", str(tid), "--plan", pf, "--mode", mode,
                   "--ledger", plan["ledger"]]
            if kill_at:
                cmd += ["--kill-at", kill_at]
            return subprocess.run(cmd, capture_output=True, text=True)

        def ledger_of(tid):
            p = os.path.join(base_dir, "ledger-%d.jsonl" % tid)
            if not os.path.isfile(p):
                return []
            return [json.loads(l) for l in open(p) if l.strip()]

        def routes(tid):
            return [e["route"] for e in ledger_of(tid)]

        def nodes_visited(tid):
            return [e["obj"]["name"] for e in ledger_of(tid) if e["route"] == "__node__"]

        def nodes_after_kill(tid):
            """The nodes the RESUMED process ran — everything recorded after the death marker."""
            ev = ledger_of(tid)
            at = [i for i, e in enumerate(ev) if e["route"] == "__killing__"]
            return [e["obj"]["name"] for e in ev[(at[0] + 1 if at else 0):] if e["route"] == "__node__"]

        def plan_for(tid, **kw):
            p = {"base": base, "rounds": 2, "deliverable": "tools/thing.py",
                 "worker": ["print('round 1')\n", "print('round 2')\n"], "verdict": ["pass"],
                 "stops": 0, "wallet_key": "selftest-wallet-key",
                 "ledger": os.path.join(base_dir, "ledger-%d.jsonl" % tid)}
            p.update(kw)
            return p

        def snapshot(tid):
            with _EmbeddedSqliteSaver.from_conn_string(ckpt) as s:
                return s.latest("ticket-%d" % tid)

        # ══ ACCEPTANCE: drive a ticket through the graph, KILL it mid-run, RESUME, settle ══
        print("-- acceptance: drive #221 -> KILL mid-run -> RESUME from checkpoint -> settle")
        tid = 221
        p221 = plan_for(tid)

        # (1) drive it, and really SIGKILL it at run_auditor (after the commit landed on the branch)
        r = child(tid, "fresh", p221, kill_at="run_auditor")
        ck("the run was KILLED mid-flight by SIGKILL (uncatchable)", r.returncode == -signal.SIGKILL,
           "returncode %s; stdout: %s" % (r.returncode, (r.stdout or "")[-200:]))
        ck("it died AT run_auditor, mid-lifecycle", routes(tid).count("__killing__") == 1, str(routes(tid)[-3:]))
        ck("the pre-kill work is on the branch (the commit really happened)",
           f.branch_exists("ticket/221") and "tools/thing.py" in f.git("show", "--name-only", "--format=", "ticket/221"))
        ck("the base does NOT have the deliverable yet (nothing merged)",
           "tools/thing.py" not in f.git("ls-tree", "-r", "--name-only", base))

        # (2) the checkpoint survived the kill and holds the cursor — this is the gap it closes
        snap = snapshot(tid)
        ck("a checkpoint survived the SIGKILL", bool(snap))
        ck("the checkpoint's next node is exactly where it died (run_auditor)",
           snap and snap["next"] == "run_auditor", snap and snap["next"])
        ck("the checkpoint holds the in-flight CURSOR (round 1 of 2)",
           snap and snap["state"].get("round") == 1 and snap["state"].get("rounds") == 2,
           str(snap and {k: snap["state"].get(k) for k in ("round", "rounds")}))
        ck("the checkpoint holds the worktree handle, not a second ledger",
           snap and snap["state"].get("branch") == "ticket/221" and "committed" in snap["state"])
        ck("the checkpoint file is NOT the governed db", os.path.basename(ckpt) != "congruency.sqlite")

        # (3) RESUME in a NEW process: it must pick up at run_auditor and reach the approval gate
        r = child(tid, "resume", p221)
        ck("RESUME from the checkpoint pauses at the wallet approval gate", r.returncode == 5,
           "exit %s; %s" % (r.returncode, (r.stdout or "")[-200:]))
        # THE point of the checkpointer: the resumed process picks up AT the dead node, and never
        # re-drives brake/open_worktree/spawn_pair/run_worker/commit. pair_loop would restart at
        # round 1 here (its cursor lives only on the dead process's stack).
        after = nodes_after_kill(tid)
        ck("the RESUMED run picked up exactly at run_auditor", after[:1] == ["run_auditor"], str(after))
        ck("the resumed run did NOT restart the lifecycle from the top",
           not ({"brake", "open_worktree", "spawn_pair", "run_worker", "commit"} & set(after)), str(after))
        ck("the resumed run did NOT re-spawn the worker (no duplicate work)",
           len([e for e in ledger_of(tid) if e["route"] == "ticket.progress"
                and "produced" in str(e["obj"].get("note", ""))]) == 1)
        snap = snapshot(tid)
        ck("the paused checkpoint is parked ON approval_gate", snap and snap["next"] == "approval_gate",
           snap and snap["next"])
        pend = snap["interrupt"] if snap else None
        ck("the gate surfaced a merge-approval payload to sign",
           bool(pend) and pend.get("kind") == "merge_approval" and pend.get("ticket") == 221, str(pend))
        ck("the payload names what is about to land (branch, base, ahead, sha)",
           bool(pend) and pend.get("branch") == "ticket/221" and pend.get("base") == base
           and int(pend.get("ahead", 0)) > 0 and bool(pend.get("sha")), str(pend))
        ck("still nothing merged while it waits for the signature",
           "tools/thing.py" not in f.git("ls-tree", "-r", "--name-only", base))

        # (4) an UNSIGNED/BADLY-SIGNED approval must NOT merge (the gate fails closed)
        r = child(tid, "approve-bad", p221)
        ck("an approval signed with the WRONG key is REFUSED (fails closed)", r.returncode == 6,
           "exit %s; %s" % (r.returncode, (r.stdout or "")[-200:]))
        ck("...and it merged NOTHING", "tools/thing.py" not in f.git("ls-tree", "-r", "--name-only", base))

        # (5) the properly wallet-signed approval settles it
        tid2 = 222                                            # a fresh thread: #221 is now terminal (held)
        p222 = plan_for(tid2)
        r = child(tid2, "fresh", p222)
        ck("a clean drive reaches the approval gate and pauses", r.returncode == 5,
           "exit %s; %s" % (r.returncode, (r.stdout or "")[-300:]))
        r = child(tid2, "approve", p222)
        ck("a WALLET-SIGNED approval settles the ticket (exit 0)", r.returncode == 0,
           "exit %s; %s" % (r.returncode, (r.stdout or "")[-300:]))
        ck("the branch MERGED into the base (the deliverable is there now)",
           os.path.isfile(os.path.join(repo, "tools/thing.py")))
        ck("the merge is a real merge COMMIT (--no-ff, not a fast-forward)", f.is_merge_commit())
        ck("work.record minted the permanent UID through the governed route", "work.record" in routes(tid2))
        ck("process_status DONE went through the governed route", any(
            e["route"] == "process_status" and e["obj"].get("status") == "DONE" for e in ledger_of(tid2)))
        ck("DONE was gated by the db's pair rule (two distinct agents, two distinct roles)",
           len({e["obj"]["agent_id"] for e in ledger_of(tid2) if e["route"] == "ticket.assign"}) >= 2
           and len({e["obj"]["role"] for e in ledger_of(tid2) if e["route"] == "ticket.assign"}) >= 2)
        ck("the harvest filed the lesson (the last lifecycle step)", "ticket.lesson" in routes(tid2))
        ck("the worktree was reaped", not os.path.exists(f.worktree_of(tid2)))
        ck("the branch is KEPT as the ticket's trace", f.branch_exists("ticket/%d" % tid2))
        ck("the base tree is CLEAN after the whole cycle (#213)", not f.git("status", "--porcelain").strip(),
           f.git("status", "--porcelain").strip())
        snap = snapshot(tid2)
        ck("the settled thread's checkpoint is parked at END", snap and snap["next"] == END,
           snap and snap["next"])
        ck("resuming a SETTLED thread is a harmless no-op (never a second merge)",
           child(tid2, "resume", p222).returncode == 0)
        ck("...and it did NOT merge twice", len([l for l in f.git("log", "--oneline", base).splitlines()
                                                 if "merge ticket/222" in l]) == 1)

        # ══ the conditional edges: pass / fail / dry ══
        print("-- conditional edges: fail -> respawn a FRESH worker -> pass")
        tid3 = 223
        p223 = plan_for(tid3, deliverable="tools/two23.py", verdict=["fail", "pass"],
                        worker=["print('r1')\n", "print('r2 fixed')\n"])
        r = child(tid3, "fresh", p223)
        ck("a FAIL verdict respawns instead of settling (reaches the gate on round 2)", r.returncode == 5,
           "exit %s; %s" % (r.returncode, (r.stdout or "")[-300:]))
        snap = snapshot(tid3)
        ck("the fail edge advanced the round cursor to 2", snap and snap["state"].get("round") == 2,
           str(snap and snap["state"].get("round")))
        ck("round 2 registered a FRESH worker (fresh spawn = cleared memory)",
           "coder-t223r2" in {e["obj"].get("agent_id") for e in ledger_of(tid3) if e["route"] == "agent.register"},
           str({e["obj"].get("agent_id") for e in ledger_of(tid3) if e["route"] == "agent.register"}))
        # count what the BRANCH added, not `git log` (which also walks the base history the branch
        # forked from — #223 branched off base after #222's merge had already landed there).
        ck("the branch kept BOTH rounds' commits (history is not erased)", f.ahead_of(223, base) == 2,
           "%d commit(s) ahead of %s" % (f.ahead_of(223, base), base))
        ck("the round-1 findings were carried into round 2's worker prompt",
           any(e["route"] == "agent.register" and e["obj"].get("agent_id") == "coder-t223r2"
               and "round 1 finding" in e["obj"].get("prompt", "") for e in ledger_of(tid3)))

        print("-- conditional edges: rounds exhausted -> gave up")
        tid4 = 224
        p224 = plan_for(tid4, deliverable="tools/two24.py", verdict=["fail", "fail"],
                        worker=["print('a')\n", "print('b')\n"])
        r = child(tid4, "fresh", p224)
        ck("two FAIL verdicts with 2 rounds gives up (exit 1)", r.returncode == 1,
           "exit %s; %s" % (r.returncode, (r.stdout or "")[-300:]))
        ck("the gave-up ticket never reached the approval gate", "approval_gate" not in nodes_visited(tid4),
           str(nodes_visited(tid4)))
        ck("nothing was merged when it gave up (the base lacks the deliverable)",
           "tools/two24.py" not in f.git("ls-tree", "-r", "--name-only", base))
        ck("no DONE was claimed when it gave up",
           not any(e["route"] == "process_status" and e["obj"].get("status") == "DONE" for e in ledger_of(tid4)))
        ck("the branch persists unmerged (work is not thrown away)", f.branch_exists("ticket/224")
           and f.ahead_of(224, base) > 0)
        ck("the gave-up ticket still harvested its lesson", "ticket.lesson" in routes(tid4))

        print("-- conditional edges: DRY (a passing verdict with nothing to land settles NOTHING)")
        tid5 = 300
        p300 = plan_for(tid5, deliverable="docs/seed.md", worker=["seed\n"], verdict=["pass"])
        head_before = f.head()
        r = child(tid5, "fresh", p300)
        ck("a byte-identical deliverable routes to the DRY edge (exit 4)", r.returncode == 4,
           "exit %s; %s" % (r.returncode, (r.stdout or "")[-300:]))
        ck("the dry round never reached the approval gate", "approval_gate" not in
           [e["obj"]["name"] for e in ledger_of(tid5) if e["route"] == "__node__"],
           str([e["obj"]["name"] for e in ledger_of(tid5) if e["route"] == "__node__"]))
        ck("the dry branch has 0 commits the base lacks", f.ahead_of(tid5, base) == 0)
        ck("the base HEAD did not move for a dry round", f.head() == head_before,
           "%s -> %s" % (head_before[:10], f.head()[:10]))
        ck("no UID was minted for a dry round", "work.record" not in routes(tid5))
        ck("no DONE was claimed for a dry round",
           not any(e["route"] == "process_status" and e["obj"].get("status") == "DONE" for e in ledger_of(tid5)))
        ck("the dry ticket's branch and worktree PERSIST (it stays open)",
           f.branch_exists("ticket/300") and os.path.exists(f.worktree_of(300)))

        # ══ the brake ══
        print("-- the brake: an active stop halts before anything acts")
        tid6 = 225
        p225 = plan_for(tid6, stops=2)
        r = child(tid6, "fresh", p225)
        ck("an active stop HALTS the graph (exit 3)", r.returncode == 3,
           "exit %s; %s" % (r.returncode, (r.stdout or "")[-300:]))
        ck("the halted ticket opened NO branch (nothing acted)", not f.branch_exists("ticket/225"))
        # "before anything acts" is an ORDERING claim, so check the order, not just the outcome:
        # registering the forge agent is itself an act, and it must not happen ahead of the brake.
        ck("the halted ticket registered NO agents — not even the forge (registering IS an act)",
           "agent.register" not in routes(tid6), str(routes(tid6)))
        ck("the halted ticket wrote NOTHING to the governed routes at all",
           [rt for rt in routes(tid6) if not rt.startswith("__")] == [], str(routes(tid6)))
        ck("brake was the ONLY node that ran", nodes_visited(tid6) == ["brake", "halted"],
           str(nodes_visited(tid6)))
        # and on a ticket that is NOT halted, the forge is registered only once the brake has cleared
        ck("on a cleared ticket the forge registers AFTER the brake, never before",
           nodes_visited(222).index("brake") == 0 and
           [e["route"] for e in ledger_of(222)].index("agent.register") >
           [i for i, e in enumerate(ledger_of(222)) if e["route"] == "__node__"
            and e["obj"]["name"] == "brake"][0])

        # ══ the explicit rejection path ══
        print("-- the gate: an explicit refusal holds the merge")
        tid7 = 226
        p226 = plan_for(tid7, deliverable="tools/two26.py")
        child(tid7, "fresh", p226)
        r = child(tid7, "reject", p226)
        ck("an explicitly REJECTED approval holds the ticket (exit 6)", r.returncode == 6,
           "exit %s; %s" % (r.returncode, (r.stdout or "")[-300:]))
        ck("the rejected ticket merged nothing (the base lacks the deliverable)",
           "tools/two26.py" not in f.git("ls-tree", "-r", "--name-only", base))
        ck("the rejected ticket's branch persists (nothing thrown away)", f.branch_exists("ticket/226")
           and f.ahead_of(226, base) > 0)

        # ══ the checkpoint is a cursor, not a ledger ══
        print("-- checkpoint discipline: a cursor, not a second ledger")
        ck("the checkpoint file is separate from any congruency.sqlite",
           os.path.isfile(ckpt) and not os.path.exists(os.path.join(repo, "state", "congruency.sqlite")))
        with _EmbeddedSqliteSaver.from_conn_string(ckpt) as s:
            hist = s.history("ticket-221")
        ck("the checkpointer wrote one checkpoint per super-step (a real history)", len(hist) >= 5,
           "%d checkpoints" % len(hist))
        ck("deleting the checkpoint loses NO settled fact (git still holds the merge)",
           os.path.isfile(os.path.join(repo, "tools/thing.py")))

        bad = [n for n, ok, _ in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad), len(checks), "" if not bad else "; FAILED: " + "; ".join(bad)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)
        print("== selftest == throwaway repo removed (this repo, the db, the real checkpoint file "
              "and the network were never touched)")


# ══ main ═════════════════════════════════════════════════════════════════════════════════════════
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(
        description="the ticket-authorization lifecycle as a LangGraph StateGraph: brake -> pair -> "
                    "work -> validate -> settle -> harvest, with a checkpointer, pass/fail/dry "
                    "conditional edges, and a wallet-signed approval interrupt before the merge")
    ap.add_argument("--ticket", type=int, help="the ticket id to drive through the graph")
    ap.add_argument("--deliverable", help="repo-relative path the worker must produce")
    ap.add_argument("--rounds", type=int, default=2, help="max worker rounds before giving up")
    ap.add_argument("--timeout", type=int, default=480, help="seconds per agent spawn")
    ap.add_argument("--base", default=None, metavar="BRANCH",
                    help="branch to fork ticket/<id> from and merge back into (default: the repo's current branch)")
    ap.add_argument("--checkpoints", default=None, metavar="PATH",
                    help="the checkpointer's sqlite file (default: state/langgraph_checkpoints.sqlite; "
                         "never congruency.sqlite)")
    ap.add_argument("--keep-worktree", action="store_true",
                    help="do not reap the worktree after a successful merge (debugging; the merge still happens)")
    ap.add_argument("--resume", action="store_true",
                    help="resume this ticket's thread from its last checkpoint (after a kill)")
    ap.add_argument("--status", action="store_true", help="print the checkpoint cursor for this ticket, then exit")
    ap.add_argument("--approve", action="store_true",
                    help="wallet-sign the pending merge approval and continue (needs CONGRUENCY_WALLET_KEY)")
    ap.add_argument("--reject", action="store_true", help="refuse the pending merge approval; nothing merges")
    ap.add_argument("--wallet", default=None, metavar="ID", help="the wallet id recorded with an --approve/--reject")
    ap.add_argument("--engine", action="store_true",
                    help="report which engine is live (langgraph or embedded), then exit")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the graph end-to-end in THROWAWAY repos: drive, SIGKILL mid-run, resume "
                         "from the checkpoint, settle (no db, no agents, no network)")
    # --selftest's own child process (it must be a real process so it can be really killed)
    ap.add_argument("--selftest-child", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--repo", help=argparse.SUPPRESS)
    ap.add_argument("--ckpt", help=argparse.SUPPRESS)
    ap.add_argument("--tid", type=int, help=argparse.SUPPRESS)
    ap.add_argument("--plan", help=argparse.SUPPRESS)
    ap.add_argument("--ledger", help=argparse.SUPPRESS)
    ap.add_argument("--mode", default="fresh", help=argparse.SUPPRESS)
    ap.add_argument("--kill-at", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args()

    if a.engine:
        print("engine: %s" % ENGINE)
        if ENGINE == "embedded":
            print("  langgraph is not importable here, so the same graph runs on this module's\n"
                  "  embedded, API-compatible engine (see the module docstring, 'THE ENGINE').\n"
                  "  Install langgraph + langgraph-checkpoint-sqlite and this reports 'langgraph'\n"
                  "  with no change to the graph definition.")
        print("checkpoints: %s" % default_checkpoints())
        return 0
    if a.selftest:
        return selftest()
    if a.selftest_child:
        return _selftest_child(a)

    if not a.ticket:
        ap.error("--ticket N is required")
    if not (a.resume or a.status or a.approve or a.reject) and not a.deliverable:
        ap.error("--deliverable is required to drive the pair (it is the path the worker must produce)")
    if a.approve and a.reject:
        ap.error("--approve and --reject are mutually exclusive")
    if not pair_loop.API_KEY and not a.status:
        # A one-line explanation, exit 2, and NO Variant-A bug report: an unset environment variable
        # is configuration the operator can fix, not an unexpected fault of this harness. The bug
        # sink is for the latter, and filing config errors into it would drown the real ones.
        print("no CONGRUENCY_API_KEY (env or .secrets/ats.env) — the governed token routes need it. "
              "This is configuration, not a bug: set the key and re-run.")
        return 2
    return run_ticket(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Unexpected as e:
        pair_loop.bug_report("main", e, "python3 local_graph.py " + " ".join(sys.argv[1:]), e)
        print("UNEXPECTED: %s" % e)
        sys.exit(2)
