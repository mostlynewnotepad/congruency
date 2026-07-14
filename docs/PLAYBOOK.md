# The Playbook: audited lessons for the worker of a pair

You are reading this because the harness told you to. When `docs/PLAYBOOK.md` exists,
`pair_loop.py` builds a birth-prompt line — *"Before starting, read docs/PLAYBOOK.md — the
AUDITED playbook of lessons harvested from prior tickets. Apply what applies."*
(`checkouts/current/congruency/tools/pair_loop.py:307-308`) — and splices it into every
worker's prompt through the `%(playbook)s` slot (`pair_loop.py:125`). The line is injected
only when this file exists (`pair_loop.py:308`), so its presence *is* the instruction. This
is not advice you may skip: it is the distilled, adversary-tested experience of the workers
who came before you.

**Why you can trust it.** Each lesson below was not asserted by anyone — it was *forced out
of the record*. When a pair-loop ticket settles, the harness distills what actually happened
(the adversary findings that forced rework, and what resolved them) into an append-only
`lesson` event on the ticket's journal (`ticket.lesson`,
`migrations/0031_harvest_routes.sql:13-18`; filed by the mechanical `harvest()` at
`pair_loop.py:185-205`, esp. the `ticket.lesson` write at `:204`). This playbook is itself
compiled from those lessons (`lessons.recent`, `migrations/0031_harvest_routes.sql:20-25`;
gathered by `--compile-playbook` at `pair_loop.py:263-272`) and run through the *same*
adversarial pair before it is recorded. Nothing here is remembered that was not filed,
reviewed, and recorded.

**Know your judge.** Your counterpart is spawned *blind to your reasoning* — it sees the
ticket and the artifact, never your transcript (`AUDITOR_PROMPT`, `pair_loop.py:130-138`,
esp. `:135` — *"You did NOT see the worker's reasoning — judge the artifact alone: no
context, no charity"*). Its rubric is fixed and worth memorizing, because every lesson below
is one way to fail it. The rubric depends on your ticket's kind — the harness splices a
kind-specific `audit_focus` into the adversary's prompt at `pair_loop.py:136`:

- **documentation** pairs (`pair_loop.py:147-150`). A **finding** is: *"claims that don't
  match the code, steps that can't be executed as written, terms undefined at first use,
  anything a newcomer must read twice."*
- **build / bug** pairs (`pair_loop.py:158-161`). The adversary *executes* your code and a
  **finding** is: *"requirements not met, crashes, wrong output, side effects the ticket
  forbids."*

In both, *"Nitpicks are not findings"* (`pair_loop.py:136`) — but everything above is.

If the adversary files findings, a **fresh** worker (not you — you are retired; a new agent
with no memory is respawned each round, `pair_loop.py:311-313`) redoes the work with your
adversary's findings appended to its birth prompt (`pair_loop.py:321,330-331`; journaled and
respawned at `:341-344,357-359`). Passing on the first round is the goal. The lessons below
are how — and the clean-pass tickets (#43, #46, #147, #152) are cited as proof that they
work.

---

## Theme 1 — Ground every claim in the code as it is *now*

**Applies to writers and coders alike.** A doc citation is a promise that the reader will
find what you said at the line you named; a tool is a promise that it behaves the way the
code it builds on behaves. Both are checked against the live repository — the documentation
adversary is told to *"verify every claim against the actual repository (read the
migrations/routes/tools it cites)"* (`pair_loop.py:147-148`), and your own writer mandate is
*"Ground every claim in the actual repository — read the real code you describe; never
document intentions as behavior"* (`pair_loop.py:145-146`).

**What the clean passes did right.** Every 1-round pass grounded itself in real, current
code and *matched* it:

- **[ticket #43]** the category-browse view *"reads the real annotations/Categories/Documents
  schema and SQL-verified against the live DB"* — it did not invent columns; it queried the
  schema that exists.
- **[ticket #147]** the version-discovery tool *"mirrors setup.py's `_vkey`/`newest_version_tag`
  so its numbers match what `setup.py install --version` accepts."* Matching the real code
  is what makes its output *correct*, not merely plausible.
- **[ticket #46]** the tag harness *"discovers every `Tag_Interface` tag under
  invocators/tags (mirrors `TagList::scan`)"* and is modeled on the existing `predict.py`
  and `serve.py`. It reused the repo's own patterns instead of a parallel invention.

**What the failure taught.** **[ticket #151, round-1 finding]** a writer cited a
`--deliverable required=True` declaration at a fixed line — but the harness had moved, and
that enforcement is now the explicit guard `ap.error("--deliverable is required to run the
pair")` at `pair_loop.py:285-286`, not a `required=True` on the argument
(`pair_loop.py:245`). *The lesson survived; the line number did not.* This very playbook
proves the drift is real: the finding rubric it once cited at "the adversary's birth prompt,
:139-140" now lives in the `FOCUS` dict at `pair_loop.py:147-150` and `:158-161`. Code moves
under documentation.

**Check every claim:**

- [ ] Open the file and confirm the cited line says what you claim, in the *current* checkout
      — not from memory, not from an older doc that cited it before you.
- [ ] For code: read the real schema, route, or module you build against (the way #43 read
      the annotations schema and #147 mirrored `setup.py`), and confirm your tool's output
      matches what that real code produces or accepts.
- [ ] Prefer citing behavior you can point at (a route's SQL in
      `migrations/0030_pair_loop_routes.sql`, a trigger in
      `migrations/0029_ticket_authorization.sql`, a control-flow block in `pair_loop.py`)
      over paraphrasing intent.
- [ ] If you inherit a claim or a line number from a prior document, re-verify it. A stale
      citation you copied forward is *your* finding, not the previous author's.

---

## Theme 2 — Every command and code path must actually run as written

**Lesson (source: [ticket #151], round-1 finding).** A worker printed an invocation that
could not be executed as written: `python3 pair_loop.py --ticket 151` as a bare "run the
pair on an existing ticket" form. But the harness rejects any invocation that omits
`--deliverable` — the guard at `pair_loop.py:285-286` calls `ap.error(...)` and aborts. A
step that can't be executed as written is a finding, not a nitpick. (The trap is still live:
the module's own usage comment writes `python3 pair_loop.py --ticket 251` with no
`--deliverable` at `pair_loop.py:27`, so *that exact line does not run*. Do not copy a broken
example just because it lives in the source you document.)

**The coder's version of the same lesson.** The build/bug worker is told to *"RUN your own
work before reporting done"* (`pair_loop.py:156-157`) and the adversary to *"execute its
documented invocations … and compare ACTUAL behavior to the ticket's required behavior,
point by point"* (`pair_loop.py:158-161`). The clean passes all cleared this bar by running
end-to-end before reporting: **[ticket #46]** was *"verified end-to-end, 40/44 clean-pass
with 4 real refutations"* — it actually booted an ephemeral server and rendered each tag.
**[ticket #43]** and **[ticket #147]** likewise verified against the live DB and the real git
tags. If you print a command or ship a code path, the last thing you should have done is run
it.

**Check before you ship any command or invocation:**

- [ ] For each command, name the tool's required inputs and confirm every one is present.
      For `pair_loop.py`: exactly one of `--ticket N` or `--file KIND` (`pair_loop.py:281-284`),
      **and** `--deliverable` (`pair_loop.py:285-286`), **and** `CONGRUENCY_API_KEY` in the
      environment or `.secrets/ats.env` (`pair_loop.py:254-255,58-67`).
- [ ] The correct existing-ticket form is `python3 pair_loop.py --ticket 151 --deliverable
      docs/X.md`. Do not shorten it.
- [ ] For code: run the deliverable end-to-end against real inputs before reporting done, the
      way #43/#46/#147 did. "It should work" is an intention; the adversary checks behavior.
- [ ] Never transcribe an example from a comment or docstring without running it against the
      real parser first. The code being wrong is not a license for the docs to be wrong.

---

## Theme 3 — Ship no side effect the ticket forbids; prove it in isolation

**Lesson (source: [ticket #153], round-1 finding — the newest and sharpest lesson).** The
ticket said the tool *"must never write to the db or create files."* The first draft opened
the state DB read-only with the URI flag `mode=ro` — which *seems* side-effect-free. It is
not: the state DB is in **WAL** (write-ahead-log) journal mode, and opening a WAL database
with `mode=ro` forces SQLite to spin up `congruency.sqlite-shm` and `congruency.sqlite-wal`
sidecar files in the state directory *on every run*. The adversary proved it in **isolation**
— a fresh copy of the DB, directory listed *before* (only `congruency.sqlite`) and *after*
running the tool with nothing else touching it (`congruency.sqlite`, `-shm`, `-wal`). The DB
content hash was unchanged, but the "never create files" guarantee was broken, and the side
effect was *avoidable*.

**The resolution, now the shipped code.** Open the WAL database with the URI flag
`immutable=1` instead: it promises SQLite the file will not change, so it reads the identical
committed data with no locking and creates **zero** sidecar files. This is exactly what the
final `ticket_status.py` does — see its `connect_ro()` (`ticket_status.py:49-60`, the
`sqlite3.connect("file:%s?immutable=1" % db_path, uri=True)` at `:60`) and the rationale in
its module docstring (`ticket_status.py:13-18`). The build adversary's rubric names this
class of defect directly: *"side effects the ticket forbids"* (`pair_loop.py:161`).

**Check every "must never / read-only / must not" constraint the ticket states:**

- [ ] Enumerate each forbidden effect the ticket names (no writes, no new files, no network,
      idempotent, etc.) and, for each, prove you satisfy it — don't assume your happy path
      does.
- [ ] Test in isolation the way the adversary will: snapshot the state (directory listing,
      file hashes) *before* one run and *after*, with nothing else touching it, and diff. A
      side effect you can't see is one the adversary will.
- [ ] Know your dependencies' hidden writes. A "read-only" open is not automatically
      side-effect-free — `mode=ro` on a WAL SQLite DB creates `-wal`/`-shm` files;
      `immutable=1` does not (`ticket_status.py:49-60`). Reach for the option that touches
      nothing.
- [ ] If a side effect is truly unavoidable, the ticket's guarantee is wrong or your approach
      is — surface it; do not ship a tool whose behavior contradicts its ticket.

---

## Theme 4 — Never let your own words contradict your behavior or each other

**Lesson A — a document must not contradict itself (source: [ticket #151], round-1
finding).** A draft asserted an ordering in one section that its own other sections refuted:
§4.2 was headed "the routes, in the order an agent uses them" and listed `ticket.stops`
ninth, while the same document's walkthrough established `ticket.stops` as the **first** call
(the brake). The adversary did not need the code to catch this — the artifact disagreed with
itself, so a newcomer must read it twice, and that alone is a finding. (Grounded truth: the
brake `ticket.stops` is checked first, in the `# ── brake ──` block at `pair_loop.py:299-304`
— `ticket.stops` at `:300`, `HALT`/`return 3` at `:301-303`; route defined at
`migrations/0030_pair_loop_routes.sql:21-26`.)

**Lesson B — a docstring is a claim, and it must match behavior (source: [ticket #153]).**
The forbidden-file tool from Theme 3 didn't just create files — *"the tool's own docstring
claims it 'never creates a file'"* while it demonstrably did. A claim about your own behavior
is checkable against your behavior; when they diverge, the adversary files the gap. The fixed
`ticket_status.py` earns its docstring: it says *"the tool never writes to the db and creates
NO files"* (`ticket_status.py:13-18`) **and** the code makes it true (`:60`).

**Check for consistency — internal and claim-vs-behavior:**

- [ ] Any sequence you assert (an ordered list, a "first/then/finally", a numbered flow) must
      match every *other* place in your document that describes the same sequence. A section
      heading is a claim: "in the order an agent uses them" obligates the list under it to be
      in that order.
- [ ] Order steps the way the code executes them, so a reader who checks against the code
      finds agreement, not contradiction.
- [ ] Every docstring, comment, and usage note you write is a claim about behavior. Run the
      thing and confirm the claim holds. A docstring that over-promises is a finding waiting
      to be filed (#153).

---

## Theme 5 — Write for a hostile newcomer; the artifact stands alone

**Lesson (source: the pair contract itself).** The adversary judges *"the artifact alone …
no context, no charity"* (`pair_loop.py:135-136`), and your prompt warns it audits *"with no
access to your reasoning, so the artifact must stand alone"* (`pair_loop.py:123-124`). Two of
the documentation finding categories — *terms undefined at first use* and *anything a
newcomer must read twice* (`pair_loop.py:149-150`) — are purely about whether the artifact is
self-contained. You cannot answer a finding in conversation; there is no conversation. The
page (or the tool's `--help` / usage / error messages) has to answer it. #152 — the prior
compilation of this very playbook — passed clean by grouping its lessons into checkable
themes each tied to the rubric and cited to source, exactly so a blind reader needed no
outside context.

**Check for standalone clarity:**

- [ ] Define every non-obvious term at its first use (what a *kind*, a *pattern*, the *brake*,
      the *manifest*, a *stop edge*, WAL *journal mode* mean — see `docs/TICKETS.md` for the
      full ticket surface, grounded in `migrations/0029_ticket_authorization.sql`).
- [ ] Assume the reader has never seen this system and will not be charitable. Anything that
      requires them to already know something, or to read a passage twice to parse it, is a
      finding.
- [ ] For a tool, make its behavior legible without your transcript: a clear docstring/usage,
      and errors that explain themselves. #153's tool exits `2` with a *one-line message
      (never a traceback)* on a missing ticket id (`ticket_status.py:17-18,86-90`) and prints
      `(none)` for missing pieces rather than crashing — the blind adversary can read every
      state directly.
- [ ] Touch only your deliverable. Your mandate is to *produce, don't erase*
      (`GOVERNANCE`, `pair_loop.py:111-115`; worker deliverable line `:122`): create or
      overwrite exactly the file you were assigned and nothing else. History is append-only,
      enforced in SQL — `tg_tickets_no_delete` (`migrations/0029_ticket_authorization.sql:106`),
      `tg_ticket_works_no_delete` (`:149`) — do not fight it.

---

## The pre-flight checklist

Before you print your `{"done": true, ...}` line, walk the artifact once as the adversary
will:

1. **Grounded** — every claim, citation, and output matches the *current* code you read this
   session (Theme 1).
2. **Every command and code path runs** — required arguments present, traced against the real
   parser; the deliverable run end-to-end before reporting done (Theme 2).
3. **No forbidden side effect** — every "must never / read-only" constraint proven in
   isolation, before/after (Theme 3).
4. **No self-contradiction** — every ordering, cross-reference, and docstring agrees with
   itself and with actual behavior (Theme 4).
5. **Stands alone** — terms defined, nothing needs a second read, errors self-explain, only
   your deliverable touched (Theme 5).

---

## Provenance

This playbook is compiled from the harvested `lesson` events across settled tickets
(`lessons.recent`, `migrations/0031_harvest_routes.sql:20-25`), which `pair_loop.py
--compile-playbook` embeds into a documentation ticket and runs the adversarial pair over
(`pair_loop.py:263-272`). The harvested corpus at this compilation:

- **[ticket #43]** — Category-browse view (all categories with page counts + their
  annotation-tagged pages, plus single-category focus). *Clean pass, 1 round.* Grounded in
  the real annotations/Categories/Documents schema and SQL-verified against the live DB
  (Themes 1, 2).
- **[ticket #46]** — Bet/test tag harness (discovers every `Tag_Interface` tag, logs a `bet`
  per tag, boots an ephemeral server to render each, compares rendered-vs-predicted, logs
  PASS/FAIL). *Clean pass, 1 round.* Mirrored `TagList::scan`/`predict.py`/`serve.py`;
  verified end-to-end, 40/44 clean with 4 real refutations (Themes 1, 2).
- **[ticket #147]** — Read-only version-discovery tool (lists installable `version-*` git
  tags; `--latest`, `--json`). *Clean pass, 1 round.* Mirrors `setup.py`'s
  `_vkey`/`newest_version_tag` so its numbers match what `install --version` accepts
  (Theme 1).
- **[ticket #151]** — *Document the ticket-as-authorization surface* (`docs/TICKETS.md`).
  *Passed in 2 rounds;* rework forced on two findings — a non-executable invocation example
  (Theme 2) and a self-contradicting route ordering (Theme 4). Resolved by adding
  `--deliverable` to the examples and reordering the routes to the true harness flow.
- **[ticket #152]** — the prior compilation of this playbook from #151's lessons. *Clean
  pass, 1 round.* Grouped lessons into checkable themes tied to the rubric and cited to source
  (Theme 5).
- **[ticket #153]** — Read-only ticket-rollup CLI (`ticket_status.py`:
  header/crew/journal/manifest/lessons/progress). *Passed in 2 rounds;* rework forced by a
  **forbidden side effect** — opening the WAL-mode state DB with `mode=ro` created
  `-wal`/`-shm` sidecar files, violating "never create files." Resolved by opening with
  `immutable=1` (Themes 3, 4).

As more pair-loop tickets settle, their lessons are harvested and this playbook is recompiled
and re-audited. Everything here earned its place by surviving an adversary who had no reason
to be kind.
