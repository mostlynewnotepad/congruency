# The Playbook: audited lessons for the worker of a pair

You are reading this because the harness told you to. When `docs/PLAYBOOK.md` exists,
`pair_loop.py` injects a line into every worker's birth prompt — *"Before starting, read
docs/PLAYBOOK.md — the AUDITED playbook of lessons harvested from prior tickets. Apply
what applies."* (`checkouts/current/congruency/tools/pair_loop.py:282-284`, spliced into
the worker prompt at `:126`). So this is not advice you may skip: it is the distilled,
adversary-tested experience of the workers who came before you.

**Why you can trust it.** Each lesson below was not asserted by anyone — it was *forced
out of the record*. When a pair-loop ticket settles, the harness distills what actually
happened (the adversary findings that forced rework, and what resolved them) into an
append-only `lesson` event on the ticket's journal
(`ticket.lesson`, `migrations/0031_harvest_routes.sql:13-18`; harvested in
`pair_loop.py:161-181`). This playbook is itself compiled from those lessons and run
through the *same* adversarial pair before it is recorded
(`migrations/0031_harvest_routes.sql:1-8`). Nothing here is remembered that was not
filed, reviewed, and recorded.

**Know your judge.** Your counterpart is spawned *blind to your reasoning* — it sees the
ticket and the artifact, never your transcript (`pair_loop.py:131-142`, esp. `:136`). Its
rubric is fixed and worth memorizing, because every lesson below is one way to fail it. A
**finding** is:

> claims that don't match the code, steps that can't be executed as written, terms
> undefined at first use, anything a newcomer must read twice. Nitpicks are not findings.
> — the adversary's birth prompt, `pair_loop.py:139-140`

If the adversary files findings, a **fresh** worker (not you — you are retired; a new
agent with no memory is respawned) redoes the work with your adversary's findings appended
to its prompt (`pair_loop.py:287-333`, findings threaded at `:295,304`). Passing on the
first round is the goal. The lessons below are how.

---

## Theme 1 — Every command you print must actually run

**Lesson (source: ticket #151, round-1 finding).** A worker wrote an invocation example
that could not be executed as written. Ticket #151's draft showed
`python3 pair_loop.py --ticket 151` as a bare "run the pair on an existing ticket" form —
but the harness rejects any invocation that omits `--deliverable`. The adversary traced
the command against the actual argument handling and filed it: a step that can't be
executed as written is a finding, not a nitpick.

This is still live and still verifiable. `pair_loop.py` accepts `--deliverable`
(`pair_loop.py:221`) but *requires* it to run the pair — the check
`if not a.deliverable: ap.error("--deliverable is required to run the pair")` at
`pair_loop.py:261-262` aborts otherwise. The module's own usage comment
(`pair_loop.py:27`) *still* writes `python3 pair_loop.py --ticket 251` with no
`--deliverable`, so that exact line does not run. Do not copy a broken example just because
it lives in the source you're documenting.

**Check before you ship any command:**

- [ ] For each command, name the tool's required inputs and confirm every one is present.
      For `pair_loop.py`: exactly one of `--ticket N` or `--file KIND`
      (`pair_loop.py:257-260`), **and** `--deliverable` (`pair_loop.py:261-262`), **and**
      `CONGRUENCY_API_KEY` in the environment or `.secrets/ats.env`
      (`pair_loop.py:230-231,58-67`).
- [ ] The correct existing-ticket form is `python3 pair_loop.py --ticket 151 --deliverable
      docs/X.md`. Do not shorten it.
- [ ] Never transcribe an example from a comment or docstring without running it against
      the real parser first. The code being wrong is not a license for the docs to be wrong.

---

## Theme 2 — A document must not contradict itself

**Lesson (source: ticket #151, round-1 finding).** A worker's draft stated an ordering in
one section that its own other sections refuted. §4.2 was headed "the routes, in the order
an agent uses them" and listed `ticket.stops` ninth and `ticket.kind` eighth — but the
same document's walkthrough established that `ticket.stops` is the **first** call (the
brake) and `ticket.kind` is set **at ticket creation**. The adversary did not need the
code to catch this; the artifact disagreed with itself, so a newcomer must read it twice.
That alone is a finding.

The true order, grounded in the harness flow: `ticket.kind` is written immediately after
`ticket.create`, before any agent is assigned (`pair_loop.py:255`, right after the create
at `:252`); the brake `ticket.stops` is the first thing checked on every run, before
anything acts (`pair_loop.py:276`, in the `# ── brake ──` block at `:275-280`;
route defined in `migrations/0030_pair_loop_routes.sql:21-26`).

**Check for internal consistency:**

- [ ] Any sequence you assert (an ordered list, a "first/then/finally", a numbered flow)
      must match every *other* place in your document that describes the same sequence.
- [ ] A section heading is a claim. "In the order an agent uses them" obligates the list
      under it to be in that order. If it isn't, fix the list or the heading.
- [ ] When you order steps, order them the way the code executes them — then a reader who
      checks against the code finds agreement, not contradiction.

---

## Theme 3 — Ground every claim in the code as it is *now*, not as it was

**Lesson (source: ticket #151, and the standing worker mandate).** Your birth prompt
orders it directly: *"Ground every claim in the actual repository — read the real
migrations, routes, and tools you describe; never document intentions as behavior"*
(`pair_loop.py:122-125`). The adversary verifies claims against the actual repository
(`pair_loop.py:137-138`). A citation is a promise that the reader will find what you said
at the line you named.

Take this playbook's own writing as the cautionary example. Ticket #151's deliverable,
`docs/TICKETS.md`, cited `pair_loop.py:178` for a `--deliverable required=True`
declaration. The harness has since changed: line 178 is now inside a different function,
and `--deliverable` is enforced by the explicit `ap.error` at `pair_loop.py:261-262`, not
by `required=True`. The *lesson* survived the change; the *line number* did not. Code moves
under documentation. Re-read the file you are citing at the moment you cite it.

**Check every citation:**

- [ ] Open the file and confirm the cited line says what you claim, in the *current*
      checkout — not from memory, not from an older doc that cited it before you.
- [ ] Prefer citing behavior you can point at (a route's SQL in
      `migrations/0030_pair_loop_routes.sql`, a trigger in
      `migrations/0029_ticket_authorization.sql`, a control-flow block in `pair_loop.py`)
      over paraphrasing intent. "The db refuses DONE without two distinct agents in two
      distinct roles" is checkable — it is the `tg_tickets_pair_completion` trigger, and
      the harness comment "db refuses without the pair" at `pair_loop.py:324` names it.
- [ ] If you inherit a claim from a prior document, re-verify it. A stale citation you
      copied forward is your finding, not the previous author's.

---

## Theme 4 — Write for a hostile newcomer, and make the artifact stand alone

**Lesson (source: the pair contract itself).** The adversary judges "the artifact alone,
as a hostile newcomer: no context, no charity" (`pair_loop.py:136-137`), and your prompt
warns that it audits "with no access to your reasoning, so the artifact must stand alone"
(`pair_loop.py:124-125`). Two of the four finding categories — *terms undefined at first
use* and *anything a newcomer must read twice* — are purely about whether the document is
self-contained. You cannot answer a finding in conversation; there is no conversation. The
page has to answer it.

**Check for standalone clarity:**

- [ ] Define every non-obvious term at its first use (what a *kind*, a *pattern*, the
      *brake*, the *manifest*, a *stop edge* mean — see `docs/TICKETS.md` for the full
      surface, grounded in `migrations/0029_ticket_authorization.sql`).
- [ ] Assume the reader has never seen this system and will not be charitable. Anything
      that requires them to already know something, or to read a passage twice to parse it,
      is a finding waiting to be filed.
- [ ] Touch only your deliverable. Your mandate is to *produce, don't erase*
      (`pair_loop.py:112-115`): create or overwrite exactly the file you were assigned and
      nothing else (`pair_loop.py:122`). The history is append-only and enforced in SQL
      (`migrations/0029_ticket_authorization.sql` triggers); do not fight it.

---

## The pre-flight checklist

Before you print your `{"done": true, ...}` line, walk the artifact once as the adversary
will:

1. **Every command runs** — required arguments present, traced against the real parser
   (Theme 1).
2. **No self-contradiction** — every ordering and cross-reference agrees with itself
   (Theme 2).
3. **Every citation is live** — you opened the current file and it says what you claim
   (Theme 3).
4. **Stands alone** — terms defined, nothing needs a second read, only your deliverable
   touched (Theme 4).

---

## Provenance

This playbook is compiled from the harvested `lesson` events across settled tickets
(`lessons.recent`, `migrations/0031_harvest_routes.sql:20-25`), which `pair_loop.py
--compile-playbook` embeds into a documentation ticket and runs the adversarial pair over
(`pair_loop.py:239-248`). As of ticket #152, the harvested corpus is:

- **ticket #151** — *Document the ticket-as-authorization surface* (`docs/TICKETS.md`).
  Passed in 2 rounds; rework was forced by the adversary on two findings — a
  non-executable invocation example (Theme 1) and a self-contradicting route ordering
  (Theme 2). Resolved in round 2 by correcting the invocations to include `--deliverable`
  and reordering the routes to the true harness flow.

As more pair-loop tickets settle, their lessons are harvested and this playbook is
recompiled and re-audited. Everything here earned its place by surviving an adversary who
had no reason to be kind.
