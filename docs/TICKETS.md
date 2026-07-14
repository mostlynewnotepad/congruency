# Tickets: the ticket as an authorization

A ticket in congruency is not a to-do note. It is an **authorization**: a record that
*requires* a registered agent (or an adversarial pair of them) to act, within a
kind-specific lifecycle, producing a permanent manifest of work under an append-only
journal. Control is made of the same material — a `stop` ticket can be aimed at any
other ticket to halt it, a `start` ticket releases the stop, and grafting a successor is
just stop + spawn + a supersedes edge.

This document is grounded entirely in the schema and code that implement the model:

- `migrations/0029_ticket_authorization.sql` — the spec made schema (kinds, lifecycles,
  journal, manifest, authorization edges, and the governance triggers).
- `migrations/0030_pair_loop_routes.sql` — the two routes the pair-loop harness needs
  (`ticket.kind`, `ticket.stops`).
- `checkouts/current/congruency/tools/pair_loop.py` — the harness that drives one
  adversarial-pair iteration over the governed REST surface.

It also cross-references the tables and routes that 0029 explicitly composes with
(`0001_agents.sql`, `0002_ticket_approval.sql`, `0012_ticket_edges.sql`), named in the
0029 header at `migrations/0029_ticket_authorization.sql:18-20`.

---

## 1. The ticket object and its governance

### 1.1 The four tables behind a ticket

A ticket's `tickets` row (from `0002_ticket_approval.sql:12-15`) gains one column in 0029:

```sql
ALTER TABLE tickets ADD COLUMN kind TEXT;   -- NULL on legacy rows; set once, then immutable
```
(`migrations/0029_ticket_authorization.sql:25`)

Everything else about a ticket lives in four additive tables (0029):

| Table | Purpose | Key |
|---|---|---|
| `ticket_events`  | the **journal** — progress reports, dates, steps-until-goal | `id` (mechanical autoincrement) |
| `ticket_works`   | the **manifest** — every item the ticket authorized | `uid` (mechanical autoincrement, permanent) |
| `ticket_agents`  | the **authorization edge** — ticket → registered agent, in a role | `(ticket_id, agent_id, role)` |
| `ticket_kinds` / `ticket_lifecycles` | the ticket's kind and its lifecycle-as-data | see §2, §3 |

`ticket_events` carries `agent_id` (who reported), `event` (`status` | `progress` |
`assigned` | `work` | …), `status`, `note`, and `steps_remaining`
(`migrations/0029_ticket_authorization.sql:73-82`). `ticket_works` carries `kind`
(`code` | `doc` | `spec` | `patch` | `crank` | …), `ref` (where the item lives), and
`note` (`migrations/0029_ticket_authorization.sql:86-93`).

Both `id` and `uid` are **mechanical**: callers never set them, and a UID is never
reissued (`migrations/0029_ticket_authorization.sql:74,87`).

### 1.2 Current state is derived, never edited in place

The 0029 header states the rule (`:11-15`): current state is DERIVED from events + edges;
DELETE and identity-UPDATE on core tables are refused; only registered agents may be
authorized; a pair-kind ticket cannot reach DONE without two distinct agents in two
distinct roles. These are not conventions in a comment — they are triggers:

| Trigger | Enforces | Line |
|---|---|---|
| `tg_tickets_no_delete` | tickets are never deleted (aim a `stop` ticket instead) | `:106-109` |
| `tg_tickets_immutable_identity` | `id, ts, title, body, component, kind` are permanent; `kind` is set-once | `:111-117` |
| `tg_tickets_journal_status` | every `status` change auto-appends a `status` event to the journal | `:119-124` |
| `tg_tickets_active_needs_agent` | a ticket cannot go `ACTIVE` with no agent assigned | `:126-131` |
| `tg_tickets_pair_completion` | a `pair` ticket cannot go `DONE` without 2 distinct agents in 2 distinct roles | `:133-140` |
| `tg_ticket_events_no_update` / `_no_delete` | the journal is append-only | `:142-145` |
| `tg_ticket_works_no_update` / `_no_delete` | a work UID is permanent; the manifest only grows | `:147-150` |
| `tg_ticket_agents_registered` | only REGISTERED agents can be authorized | `:152-156` |
| `tg_ticket_agents_no_update` / `_no_delete` | an authorization is a fact/history, never edited or deleted | `:157-160` |

The `tg_tickets_immutable_identity` trigger fires on `kind` only when the old value is
non-NULL (`OLD.kind IS NOT NULL AND NEW.kind IS NOT OLD.kind`,
`migrations/0029_ticket_authorization.sql:114`), which is exactly what makes `kind`
**set-once**: `NULL → value` is allowed, any later change aborts.

The mutable fields the pre-0029 flows still touch (`status`, `updated`, `approval_sig`)
remain mutable; the new guards bind only to the new lifecycle statuses `ACTIVE` and
`DONE` that no prior flow used (`migrations/0029_ticket_authorization.sql:20-22`).

### 1.3 WHY append-only: the erased-history incident

The governance is not defensive theatre. It exists because a prior version of these rules
lived only in a docstring, and a docstring "has already failed to bind"
(`migrations/0029_ticket_authorization.sql:11`). The concrete incident, recorded in the
release notes:

> Directly answers the erased-progress problem: the dispatch agent deleted ledger rows
> because "never delete" lived in a docstring; it now lives in the database (21 id-gaps in
> the config db, 11 in the serving db, remain as evidence).
> — `VERSION-NOTES.md:14-16`

An agent erased history because nothing stopped it. The mechanical id-gaps left behind are
still visible. 0029's response is to move the rule from prose into SQL triggers that
`RAISE(ABORT)` — so "produce, don't erase" is enforced by the database, not trusted to an
agent's good behavior.

---

## 2. Kinds: pair and solo patterns, and role names

A ticket's `kind` selects a **pattern** (`pair` or `solo`) and the **role names** the
authorized agents occupy. Kinds are data in `ticket_kinds`
(`migrations/0029_ticket_authorization.sql:27-45`), readable via the `kind.roster` route:

| kind | pattern | worker_role | adversary_role | purpose (abridged) |
|---|---|---|---|---|
| `build` | pair | coder | tester | produce working code; tester adversarially proves/disproves it |
| `bug` | pair | coder | tester | fix a defect; tester proves the fix, hunts regressions |
| `documentation` | pair | writer | readability-auditor | document work; auditor adversarially reads for clarity |
| `bet` | pair | claimant | adjudicator | a speculative claim, adversarially adjudicated |
| `design` | solo | designer | — | shape an approach before a spec exists |
| `spec` | solo | spec-author | — | the artifact that authorizes building |
| `test` | solo | tester | — | prove/disprove already-produced functions (the adversary IS the work) |
| `rfc-investigation` | solo | researcher | — | research toward a spec; may spawn implementations + audits |
| `audit` | solo | auditor | — | examine delivered work; may spawn patch/refactor tickets |
| `stop` | solo | stopper | — | aimed at ANY ticket via a `stops` edge; halts it; facilitates a start |
| `start` | solo | starter | — | aimed at a `stop` ticket via a `starts` edge; resumes stopped work |

**pair** = an adversarial network: a worker produces, a distinct adversary (blind to the
worker's reasoning) validates. **solo** = the adversary *is* the work itself (`solo` kinds
have `adversary_role = NULL`, `migrations/0029_ticket_authorization.sql:32,38-45`).

In addition to a kind's worker/adversary roles, `scribe` is always a valid role on the
authorization edge (`ticket_agents.role` comment, `:101`; `ticket.assign` meta, `:183`).

---

## 3. Lifecycle-as-data and `steps_remaining`

Each kind's lifecycle is a **versioned list of ordered steps** in `ticket_lifecycles`
(`migrations/0029_ticket_authorization.sql:48-70`). It is data, not code, so refining a
lifecycle bumps `version` and never rewrites the history of in-flight tickets
(`:47`). Read it with the `lifecycle.steps` route.

Example — the `documentation` kind's version-1 lifecycle
(`migrations/0029_ticket_authorization.sql:60-61`):

```
1 filed → 2 authorized → 3 paired → 4 drafting → 5 readability-review → 6 revised → 7 done
```

And `build` (`:56-57`):

```
1 filed → 2 authorized → 3 paired → 4 implementing → 5 adversary-review
        → 6 revising → 7 verified → 8 done
```

`steps_remaining` on a journal event is the **countdown to the goal** over these steps.
It is an integer an attributed agent appends with each progress report; for a parent
ticket it is a rollup over its children
(`migrations/0029_ticket_authorization.sql:81`). The pair-loop harness, for instance,
appends `steps_remaining: 2` after the worker produces, then `1` on a passing verdict or
`3` on a failing one, then `0` when the ticket goes DONE
(`checkouts/current/congruency/tools/pair_loop.py:240,247,253-255`).

---

## 4. The routes an agent actually calls, in order

### 4.1 Calling convention

Every write goes through the **governed REST surface** — the harness holds no SQL pen
(`pair_loop.py:22`). The convention, as `pair_loop.py`'s `rest()` implements it
(`checkouts/current/congruency/tools/pair_loop.py:91-103`):

- Base URL: `http://127.0.0.1:8899`, overridable with `$CONGRUENCY_URL` (`:55`).
- Route selector: `…/rest.php?route=<name>`.
- **GET** (`auth: public`) routes take their params in the query string; no key needed.
- **POST** (`auth: token`) routes take a JSON body and require an `X-Api-Key` header
  (`$CONGRUENCY_API_KEY`, read from `.secrets/ats.env` or the environment,
  `pair_loop.py:58-67,98`).
- GET routes return `{"rows":[…]}`; any route returns `{"error":…}` on failure
  (`pair_loop.py:101-107`).

For the examples below:

```bash
CONG=http://127.0.0.1:8899          # or "$CONGRUENCY_URL"
KEY="$CONGRUENCY_API_KEY"           # required only for token (POST) routes
TID=151                             # the ticket you are authorized on
```

### 4.2 The routes, in the order they are used

This order tracks the actual flow the harness performs in §6 and the stop mechanics in §5:
a ticket is **classified at creation** (`ticket.kind`, before any agent is assigned —
`pair_loop.py:186-191`); the **brake** (`ticket.stops`) is then the **first** thing checked
on every run, before anything acts (`pair_loop.py:208-213`); only then is the pair
registered, authorized, and driven; and the read-only routes are the observation points you
call to see the state each write produced.

**`ticket.kind`** — POST, token. Classify a ticket that was created before the `kind`
column existed. Set-once: the identity trigger refuses re-kinding, and the SQL only matches
rows where `kind IS NULL` (`0030:14-19`; trigger `0029:111-117`). The harness sets this
immediately after `ticket.create`, before any assignment (`pair_loop.py:190`).

```bash
curl -X POST "$CONG/rest.php?route=ticket.kind" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"id":151,"kind":"documentation"}'
```

**`ticket.stops`** — GET, public. **The brake, checked first on every run.** Count active
(unreleased) `stop` tickets aimed at this ticket **or any ancestor**. `active_stops > 0`
means HALT (`0030:21-26`); the harness exits before acting if so (`pair_loop.py:208-213`).
See §5 for the recursion.

```bash
curl "$CONG/rest.php?route=ticket.stops&ticket_id=$TID"
```

**`agent.register`** — POST, token. Record a spawn (id + parent + full birth prompt +
tools). A ticket authorizes only *registered* agents, so this is a precondition of
`ticket.assign` (`0001_agents.sql:18-25`; enforced by `tg_ticket_agents_registered`,
`0029:152-156`).

```bash
curl -X POST "$CONG/rest.php?route=agent.register" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"writer-t151r1","parent":"pair_loop",
       "prompt":"<full birth prompt>","tools":"[\"claude -p\"]"}'
```

**`ticket.assign`** — POST, token. Authorize a registered agent on a ticket in a role
(worker/adversary per `ticket_kinds`, or `scribe`) (`0029:179-184`). Inserts a
`ticket_agents` row.

```bash
curl -X POST "$CONG/rest.php?route=ticket.assign" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"ticket_id":151,"agent_id":"writer-t151r1","role":"writer"}'
```

**`ticket.crew`** — GET, public. The agents authorized on a ticket, with roles and each
agent's status (`0029:186-191`).

```bash
curl "$CONG/rest.php?route=ticket.crew&ticket_id=$TID"
```

**`ticket.progress`** — POST, token. Append an attributed progress report plus
`steps_remaining`. The journal never edits (`0029:193-198`).

```bash
curl -X POST "$CONG/rest.php?route=ticket.progress" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"ticket_id":151,"agent_id":"writer-t151r1",
       "note":"round 1: drafted docs/TICKETS.md","steps_remaining":2}'
```

**`ticket.journal`** — GET, public. The full append-only journal (status changes +
progress), oldest first (`0029:200-205`).

```bash
curl "$CONG/rest.php?route=ticket.journal&ticket_id=$TID"
```

**`work.record`** — POST, token. Mint a **permanent** work UID into the ticket's manifest.
Returns nothing — read it back with `ticket.manifest` (`0029:207-212`).

```bash
curl -X POST "$CONG/rest.php?route=work.record" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"ticket_id":151,"kind":"doc","ref":"docs/TICKETS.md","note":"ticket surface doc"}'
```

**`ticket.manifest`** — GET, public. The ticket as a descriptive manifest: every UID'd
item it authorized, ordered by UID (`0029:214-219`).

```bash
curl "$CONG/rest.php?route=ticket.manifest&ticket_id=$TID"
```

**`agent.roster`** — GET, public. Registered agents, newest first; `LIMIT :n`, and
**omit `n` for all**. (0029 re-defines this route to fix that contract — the original
`LIMIT :n` was a datatype mismatch when `n` was omitted; the fix is `LIMIT COALESCE(:n,-1)`
(`0029:163-169`, superseding `0001_agents.sql:36-43`).)

```bash
curl "$CONG/rest.php?route=agent.roster"          # all
curl "$CONG/rest.php?route=agent.roster&n=20"     # newest 20
```

**`agent.prompt`** — GET, public. One agent's FULL birth prompt + registration record
(the roster shows only a 160-char preview) (`0029:171-177`).

```bash
curl "$CONG/rest.php?route=agent.prompt&agent_id=writer-t151r1"
```

**`agent.trail`** — GET, public. Pass an agent id → see every tool/intent event it
propagated, in order (from the `memories` table, keyed on `session = agent_id`)
(`0001_agents.sql:27-34`).

```bash
curl "$CONG/rest.php?route=agent.trail&agent_id=writer-t151r1"
```

---

## 5. Stop / start tickets and grafting via edges

Control is built from tickets and edges, not from a separate mechanism. The relevant edge
kinds live in `ticket_edges` (`0012_ticket_edges.sql:6-12`), and 0029 uses four of them:
`spawned`, `stops`, `starts`, `supersedes` (all `TEXT`, additive —
`0029:19-20`). Edges are written with `edge.record` (POST, token —
`0012_ticket_edges.sql:15-23`).

### 5.1 Stop and start

- A **`stop`** ticket (kind `stop`, `0029:44`) is aimed at ANY ticket via a `stops` edge
  whose `child_id` is the target ticket. It halts that ticket.
- A **`start`** ticket (kind `start`, `0029:45`) is aimed at the *stop ticket* it releases
  via a `starts` edge whose `child_id` is that stop ticket.

`ticket.stops` reads exactly this (`0030:21-26`). Decomposed:

1. Build the ancestor set: start from `:ticket_id` and walk `spawned` edges **upward**
   (`SELECT e.parent_id … JOIN anc ON e.child_id = anc.id AND e.kind = 'spawned'`), so a
   stop on a parent halts its descendants too.
2. Count `stops` edges whose `child_id` is the ticket or any ancestor.
3. **Exclude** any stop whose stop-ticket (`st.parent_id`) has a `starts` edge aimed at it
   (`NOT EXISTS … rel.kind = 'starts' AND rel.child_id = st.parent_id`) — i.e. a stop that
   has already been released.

The remaining count is `active_stops`. `> 0` ⇒ the ticket authorizes nothing right now
(`0030:9-10`).

### 5.2 Grafting

You never edit or delete a ticket to replace it. Grafting a successor is, per the 0029
header (`:7-9`): **stop + spawn + supersedes-edge**. Aim a `stop` at the old work, spawn
the successor (a `spawned` edge), and record a `supersedes` edge from the successor to the
predecessor. The old ticket, its journal, and its manifest all remain — nothing is erased;
the graph simply grows a new branch. This is why the delete/identity triggers point you at
grafting instead of mutation (e.g. `tg_tickets_no_delete`, `0029:106-109`;
`tg_ticket_works_no_delete`, `0029:149-150`).

---

## 6. The `pair_loop.py` harness: one iteration

`pair_loop.py` harnesses **one iteration of the adversarial network** for a `pair`-kind
ticket: a fresh worker acts, a fresh blind adversary validates, and the result settles
through the governed routes above. Every write goes through the token REST surface — the
harness holds no SQL pen (`checkouts/current/congruency/tools/pair_loop.py:22`).

Before doing anything it is **registry-gated**: it walks up from its own directory looking
for `registry.json` and refuses to run if it cannot find one
(`pair_loop.py:42-54`). Any unexpected outcome files a best-effort "Variant-A" bug report
to the registry's `bug_reports` sink and never blocks
(`pair_loop.py:70-83`).

**Invocation.** `--deliverable` is declared `required=True`
(`pair_loop.py:178`), so argparse rejects *any* invocation that omits it — including the
existing-ticket form. (The module's own usage comment at `pair_loop.py:27` writes
`--ticket 251` with no `--deliverable`; that line cannot run as written. Always pass
`--deliverable`.) You must also supply exactly one of `--ticket N` or `--file KIND`
(`pair_loop.py:186-195`), and `CONGRUENCY_API_KEY` must be set for the token routes
(`pair_loop.py:182-183`):

```bash
# Run the pair on an existing, already-kinded ticket:
python3 pair_loop.py --ticket 151 --deliverable docs/TICKETS.md

# File a NEW ticket of a kind, then run the pair on it:
python3 pair_loop.py --file documentation --title "…" --body "…" \
        --deliverable docs/X.md [--rounds 2] [--timeout 480]
```

With `--file KIND`, the harness first `ticket.create`s the ticket and then `ticket.kind`s
it (`pair_loop.py:186-191`). It then loads the ticket row, requires a `kind`, and requires
that kind to be a **pair** pattern via `kind.roster` — the loop only harnesses pairs
(`pair_loop.py:197-206`).

**One iteration**, as the module docstring lays it out (`pair_loop.py:5-20`) and `main()`
executes (`pair_loop.py:208-259`):

1. **BRAKE** — call `ticket.stops`; if `active_stops > 0`, print `HALT` and exit `3` before
   anything acts (`pair_loop.py:208-213`).
2. **PAIR** — register a *fresh* worker and adversary for this round (`agent.register` with
   full birth prompts) and authorize both on the ticket (`ticket.assign`), then set the
   ticket `ACTIVE` via `process_status`. Fresh spawns *are* the memory clear: a new agent
   has no context, while the old agents' trails stay on the record forever — the journal is
   append-only, nothing is erased (`pair_loop.py:221-231,9-11`). Agent ids are
   `<role>-t<tid>r<round>`, e.g. `writer-t151r1` (`pair_loop.py:217-218`).
3. **WORK** — spawn the worker as `claude -p` with tools limited to reading + writing the
   deliverable (`Read,Grep,Glob,Write,Edit`). It must print `{"done":true,"ref":…}` on its
   last line; the harness then appends a `ticket.progress` report with `steps_remaining: 2`
   (`pair_loop.py:233-240`).
4. **VALIDATE** — spawn the adversary **blind** to the worker's reasoning: it is given
   read-only tools (`Read,Grep,Glob`) and sees the ticket + the artifact, never the
   worker's transcript. It must print `{"verdict":"pass"|"fail","findings":[…]}` on its
   last line, which the harness journals via `ticket.progress`
   (`pair_loop.py:242-247,131-142`).
5. **SETTLE**:
   - **pass** → `work.record` the artifact (permanent UID), set status `DONE` via
     `process_status`, and append a final progress event with `steps_remaining: 0`. The
     database itself refuses `DONE` unless the pair is two distinct agents in two distinct
     roles (`tg_tickets_pair_completion`, `0029:133-140`), so the harness comment
     "db refuses without the pair" is literally enforced (`pair_loop.py:249-257`).
   - **fail** → the findings are journaled and the loop re-runs with a **fresh** worker,
     the prior findings appended to the new worker's birth prompt
     (`pair_loop.py:224,233-234,258-259`). Up to `--rounds` rounds (default 2); if all are
     exhausted, findings stay journaled and the ticket stays `ACTIVE` (exit `1`,
     `pair_loop.py:216,261-262`).

Exit codes: `0` settled/DONE, `1` rounds exhausted, `2` an `Unexpected` error (also
bug-reported), `3` halted by an active stop (`pair_loop.py:212,257,261,266-271`).

Note that the harness reads the raw ticket row through a separate read endpoint,
`…/rest.php?api=tickets&id=<id>` returning `{"row":…}` (`pair_loop.py:197-199`), distinct
from the `route=` REST surface used for every write.

---

## Quick reference

Ordered as the harness uses them (§4.2, §6): classify → brake → register/authorize →
drive → observe.

| Route | Method / auth | Reads or writes |
|---|---|---|
| `ticket.kind` | POST / token | classify a ticket (set-once), at creation |
| `ticket.stops` | GET / public | active (unreleased) stops on the ticket/ancestors — the brake, checked first |
| `agent.register` | POST / token | register a spawn (precondition for assignment) |
| `ticket.assign` | POST / token | authorize a registered agent in a role |
| `ticket.crew` | GET / public | agents authorized on the ticket, with roles |
| `ticket.progress` | POST / token | append an attributed progress report + `steps_remaining` |
| `ticket.journal` | GET / public | the append-only journal |
| `work.record` | POST / token | mint a permanent work UID into the manifest |
| `ticket.manifest` | GET / public | every UID'd work item |
| `agent.roster` | GET / public | registered agents, newest first (omit `n` for all) |
| `agent.prompt` | GET / public | one agent's full birth prompt |
| `agent.trail` | GET / public | an agent's tool/intent propagation trail |
| `kind.roster` | GET / public | the kinds (pattern + role names) |
| `lifecycle.steps` | GET / public | a kind's enumerable lifecycle steps |
| `edge.record` | POST / token | record a parent→child ticket edge (spawn/stop/start/supersede) |
