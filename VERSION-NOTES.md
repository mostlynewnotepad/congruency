# VERSION-NOTES

Per-crank notes. Newest first. A crank = a commit + a `version-*` tag.

> Repo home moved to `origin` = `gitlab.com:testmonkeyalpha-group/jazz-forge/congruency`
> (`upstream` = `github.com:dudezilla/rebase`) as of 4.089.

---

## version-4.142 — the bug sweep + dispatch-01 takes the wheel (and correctly declines it)

- **Bug sweep, both round-1 passes with EXECUTING testers** (bug/build pairs now also carry the
  repo php at tooling/congruencey-harness/php/php, so PHP fixes are PROVEN, not read): ticket #79 →
  `ProductDAO.php` fixed (UID 8; `paw.product` MySQL notation → `Products`, provenance comment in
  place); ticket #139 → `ingest_self.py` non-utf8 fidelity fixed (UID 9). Lessons harvested.
- **`--dispatch [N]` mode** (`pair_loop.py do_dispatch` + `0032_dispatch_routes.sql` ticket.queue):
  the harness reads dispatch-01's REGISTERED birth prompt back out of the agents table (the
  registry is the instruction source, not decoration), shows it the queue with per-ticket
  active_stops, and executes its JSON plan — run (kind set-once + pair_loop on itself, same
  brake→pair→settle→harvest chain), skip (journaled reason), or stop (stop ticket + 'stops' edge).
  Cap N (default 5) bounds the blast radius. Every decision journals as dispatch-01.
- **Maiden dispatch**: queue was #140 + #154; dispatch-01 SKIPPED both with correct spec reasoning
  ("#140 authorizes nothing until a start ticket aimed at #154 releases it"; "#154 is a control
  ticket, resolved by a start-ticket graft, not routed to a pair"). A dispatcher that declines
  correctly is the safety case for letting it run.

## version-4.141 — the build campaign: kind-aware pairs, four deliverables, a triaged queue

pair_loop grew EXECUTING testers, then the whole open build queue went through it. Every open
ticket is now settled-with-artifact, closed-with-evidence, kinded for a later sweep, or stopped.

- **Kind-aware pairs** (`pair_loop.py` FOCUS): build/bug pairs get `Bash(python3:*)` — the coder
  must RUN its own work before reporting done; the tester's stance is "assume it's broken and
  PROVE it" by executing documented invocations ("a tester that cannot run code is a book
  reviewer, not an adversary"). Documentation pairs stay read-only.
- **Ticket #153 → `tools/ticket_status.py` (UID 3)** — one-glance rollup CLI (header/crew/journal/
  manifest/lessons/'steps remaining: X of Y'). Round-1 tester finding was a systems-level catch:
  `mode=ro` on a WAL db still CREATES -shm/-wal sidecars (proven before/after in isolation),
  violating "never creates files" — fixed round 2 with `immutable=1`. The tool reports its own
  birth ticket cleanly.
- **Sweep (fresh pair per ticket, all round-1 passes, spot-checked live)**: #147 →
  `tools/list_versions.py` (UID 4; 91 installable versions discoverable, latest marked); #46 →
  `tools/tag_test_harness.py` (UID 5; predicted-vs-rendered bets/tests as tickets); #43 →
  `invocators/tags/dev/CategoryBrowse.php` (UID 6; renders via ?page=tags&tag=CategoryBrowse).
- **Triage (triage-01, journaled evidence per ticket)**: CLOSED #146/#148/#149/#150 (already
  solved by the setup.py config object, pushed tags, and state/component.json); kinded #79/#139
  `bug` (future bug sweep); **stop ticket #154 aimed at #140** (WASM, shelved by its own body) via
  a 'stops' edge — the brake verifies active_stops=1 and pair_loop HALTS on it.
- **Playbook v2 (ticket #155, UID 7)** — recompiled from ALL six harvested lessons; every future
  worker is now born knowing the WAL/immutable=1 catch and the standalone-artifact discipline.
- Journal accounting: tickets #43/#46/#147/#153/#155 carry full pair provenance (crew, verdicts,
  lessons); the state db's stray committed -wal/-shm sidecars are dropped from the tree.

## version-4.140 — harvest + playbook: memory as an AUDITED ARTIFACT

The answer to "should agents keep memory for N turns?" — no: memory is bounded by SCOPE, not by
count, and an agent may remember only what it has FILED. Implemented as the harvest/playbook loop:

- **Harvest at settle** — every pair_loop run (pass, and gave-up too: failures teach most) now ends
  with a `scribe-t<id>` agent filing a `lesson` event: a MECHANICAL distillation composed from the
  journal (what the adversary caught, what resolved it) — no spawn, so it cannot confabulate.
  `--harvest N` retro-harvests an already-settled ticket (used on #151).
- **`0031_harvest_routes.sql`** — ticket.lesson [POST] (lessons are ticket_events, so they inherit
  0029's append-only triggers) and lessons.recent [GET] (cross-ticket, playbook input).
- **`--compile-playbook`** — files a documentation ticket embedding ALL harvested lessons and runs
  THE SAME adversarial pair over it: the playbook is itself an audited, permanent-UID work.
- **Birth-prompt injection** — when `docs/PLAYBOOK.md` exists, every future worker is told to read
  it first. The full loop: journal → harvest → lesson → pair-audited playbook → next worker's
  birth prompt. Stored memory is worthless; READ memory is the only kind that exists.
- **Proven live: ticket #152** — the compile ran through the pair (writer-t152r1 distilled #151's
  lesson into four checkable themes; the blind auditor passed it round 1), settled DONE, manifest
  **UID 2** (`docs/PLAYBOOK.md`, riding in this crank), and #152's own harvest fired — the playbook
  ticket's lesson feeds the NEXT playbook. Also: pair_loop output is now line-buffered (watchable
  when redirected).

## version-4.139 — pair_loop.py: the adversarial pair, harnessed — and its maiden voyage

The agent-pair loop the spec pointed at: a ticket authorizes a worker; a BLIND counterpart
validates; fresh spawns each round ARE the memory clear (the record never clears — trails, journal
and manifest persist; "an agent may remember only what it has filed").

- **`checkouts/current/congruency/tools/pair_loop.py`** — one iteration: BRAKE (ticket.stops:
  active stop tickets aimed at the target or any 'spawned'-ancestor HALT the run) → PAIR (register
  a fresh worker+adversary with full birth prompts; ticket.assign; ACTIVE — permitted only because
  assignment exists) → WORK (`claude -p`, tools limited; artifact + JSON done-line) → VALIDATE
  (adversary sees ticket + artifact, never the worker's reasoning; JSON verdict) → SETTLE (pass:
  work.record permanent UID + DONE, which the db refuses without two distinct agents in two
  distinct roles; fail: findings journaled, FRESH worker respawned with findings in its birth
  prompt, --rounds cap). Registry-gated (note-for-claude), Variant-A bug reports on unexpected
  outcomes, ALL writes through the governed token routes — the harness holds no SQL pen.
- **`migrations/0030_pair_loop_routes.sql`** — ticket.kind (the sanctioned set-once classify;
  re-kinding still aborts via the identity trigger) and ticket.stops (recursive-CTE stop-state:
  unreleased stops on the ticket or any ancestor; SELECT-first so the dispatcher returns rows).
- **Maiden voyage: ticket #151** (documentation, pair writer/readability-auditor) — the network
  WORKED: round-1 auditor FAILED the doc with two real findings (a documented invocation argparse
  actually rejects — required --deliverable; a route-order section contradicting the harness flow
  it documents), each cited to file:line. Fresh writer-t151r2 spawned with the findings, produced
  the corrected `docs/TICKETS.md`; round-2 auditor passed clean. DONE; manifest **UID 1**; all four
  agents remain on the crew record. The deliverable (docs/TICKETS.md) rides in this crank.

## version-4.137 — the ticket IS an authorization: spec kernel + agent roster

Implements the ticket spec (2026-07-13, Steven) as `migrations/0029_ticket_authorization.sql` —
one node type (ticket), one append-only journal, typed edges, permanent UIDs, projections for
state, and SQL triggers refusing the rest. Directly answers the erased-progress problem: the
dispatch agent deleted ledger rows because "never delete" lived in a docstring; it now lives in
the database (21 id-gaps in the config db, 11 in the serving db, remain as evidence).

- **Kinds + pairs**: `ticket_kinds` — pair kinds (build, bug, documentation, bet) name a worker
  and an adversary (coder/tester, writer/readability-auditor, claimant/adjudicator); solo kinds
  (test, rfc-investigation, audit, design, spec) where the adversary IS the work or the output is
  a spec. `stop`/`start` are kinds too: control is made of tickets ('stops'/'starts' edges).
- **Lifecycle as data**: `ticket_lifecycles` (versioned) — enumerable steps per kind, so
  `steps_remaining` is countable and a parent's distance-to-goal is a rollup, not a meeting.
- **Journal**: `ticket_events` — attributed, dated progress reports; status changes auto-journal
  via trigger; UPDATE/DELETE refused.
- **Manifest**: `ticket_works` — every authorized item gets a mechanical, PERMANENT uid;
  UPDATE/DELETE refused.
- **Authorization**: `ticket_agents` — only REGISTERED agents (0001 registry) can be assigned;
  ACTIVE requires an agent; pair-kind DONE requires two DISTINCT agents in two DISTINCT roles.
  Existing crankd flows untouched (status/approval_sig stay mutable; guards bind to new statuses).
- **Routes**: ticket.assign / ticket.crew / ticket.progress / ticket.journal / work.record /
  ticket.manifest / kind.roster / lifecycle.steps / agent.prompt; agent.roster's documented
  "omit n for all" contract FIXED (`LIMIT COALESCE(:n,-1)` — omitted params bind NULL).
- **Shadow gate**: `ticket-authorization-shadow.py` (20/20) pins additive-ness, every refusal,
  the auto-journal, pair completion, and the roster fix; added to `install.json` shadows.
- **Applied to BOTH live dbs** (serving db caught up 0002→0029 — it tracked only 0001; config db
  +0029). **Agent roster registered via the live agent.register route** with FULL birth prompts
  (the prompt column is unbounded TEXT; roster truncates to 160 for display; agent.prompt returns
  it whole): dispatch-01 and its spawns coder-01/tester-01 (coding pair), writer-01/reader-01
  (documentation pair), researcher-01 (rfc→spec), scribe-01 (progress metadata) — mirrored into
  the config db (roster there: 12 with 5 pre-existing).
- Verified live: DELETE refused on both dbs; roster/prompt/kind/lifecycle routes serve.

## version-4.136 — session log: source_db repoint to the new config home (docs crank)

Log of the 2026-07-13 maintenance session, each action in order:

1. **Status survey** — tree at `version-4.134`, tracked-clean; server down (nothing listening
   on :8899); live DB located at `~/code/installed/jazz-project/config/congruency/congruency.sqlite`
   (143 MB, WAL recently active), with `pre-4.111`…`pre-4.120` backups alongside it.
2. **Fault found** — `checkouts/current/state/STATE.json` `source_db` still named the RETIRED
   `~/bin/config/congruency/congruency.sqlite` (`~/bin` was snapshotted away to `~/bin.snapshot`).
   By design `make_state`/`restore` HALT on an absent `source_db`, so the next state-producing
   crank would have refused to mint.
3. **Repoint** — `source_db` → `~/code/installed/jazz-project/config/congruency/congruency.sqlite`.
   Verified `make_state.py` expanduser-resolves the `~`, and that the target DB carries all five
   `expect_tables` (Document_Templates, Documents, Products, forms, orders).
4. **Stale-path sweep** — updated the two remaining mentions of the old path:
   `tooling/congruencey-tests/db-preserve-shadow.py:12` (docstring) and
   `checkouts/current/congruency/tools/make_state.py:142` (the refusal error message, which would
   have pointed a future failure at the dead location). Grep confirms zero references remain.
5. **Mint version-4.135** — `mint_crank.py --no-patch --keep-state -m "Repoint STATE.json
   source_db …"`: shadow gate green (37/37 suites), PHP verify 3 passed / 0 failed,
   `install.json` re-stamped with the durable fields carried forward; state untouched
   (`state.lock` for 4.134 reused).
6. **This crank (4.136)** — this log entry, minted `--no-patch --keep-state`; then `main` plus
   tags `version-4.135` and `version-4.136` pushed to `origin` (gitlab).

Flagged, NOT fixed: the `forge` and `local` git remotes still point at dangling
`file:///…/bin/config/forge/remotes/*.git` paths, so `congruency_up.py restore` (which pulls
state from the forge registry) likely needs the registry's new home wired up before it will work.

## version-4.092 — native macOS arm64 (no x86 emulation): arch-aware php provisioner

congruency previously required a `linux/amd64` container on Apple Silicon only because
`provision_php.py` hardcoded a `linux-x86_64` static php (→ `Exec format error` native, hence the
emulation). Now the provisioner is arch-aware:

- `provision_php.platform_download()` maps the host's `platform.system()/machine()` to the
  static-php-cli asset — macOS arm64 → `php-<v>-cli-macos-aarch64.tar.gz`, a native arm64 php with
  `pdo_sqlite`. Linux/Intel-mac resolve to their own builds.
- A registry `php_provision.download.url` is honored ONLY if it matches the host platform;
  otherwise it's treated as a version hint and the native build is chosen — so a linux-pinned
  registry never forces x86 emulation on an arm Mac. `download.version` picks a build url-free.
- `registry.json` de-pinned (version-only).

Verified: `setup.py up` serves the CMS + REST + `agent.*` routes from a Mach-O **arm64** `php`,
no Rosetta/QEMU. The docker launcher stays as a convenience; native is now the arm-Mac default.

## version-4.091 — docs + self-hosting crank tool (Mac-native, lockstep)

Docs updated for 4.089/4.090 (README install steps + minting section; this file). Adapted the
in-base crank tool `checkouts/current/congruency/tools/mint_crank.py` so it mints natively here
and can never regress the config object:

- **lockstep + carry-forward** — `write_install_config` now emits `preserve_db`/`migrate`/`shadows`
  and CARRIES THEM FORWARD from the existing `install.json` (fixes a latent bug: it previously
  emitted a fixed subset and would drop those fields on the next mint).
- **capture mode** — `--no-patch` mints from the current working tree (docs/config cranks that
  aren't a runnable patch); `--keep-state` reuses the in-tree `database.tar.xz` (no `make_state`,
  which needs the `source_db`/php absent on macOS).
- **Mac-native shadow gate** — mint runs the pure-python `shadows` from `install.json` before
  capture; the PHP `verify` suite auto-skips when php isn't provisioned (or `--no-verify`), so a
  crank is still gated where the linux php can't exec.

This crank was itself minted with the adapted tool (`--no-patch --keep-state --no-verify`).

## version-4.090 — agent provenance (agents registry + register/trail/roster routes)

Follow the rabbit trail from an agent's prompt to every action it took. Tool/intent events already
land in `memories` keyed on `session` (= agent id); this adds the missing registry + REST surface.

- `migrations/0001_agents.sql`: `agents(agent_id,parent,prompt,tools,status,ts)` + three
  `api_routes` rows — `agent.register` [POST/token], `agent.trail` [GET/public]
  (`SELECT … memories WHERE session=:agent_id`), `agent.roster` [GET/public].
- `setup.py:do_migrate` — forward-only, ADDITIVE migration runner (CREATE IF NOT EXISTS /
  INSERT OR REPLACE), tracked in `schema_migrations`, run on every install after `do_state`. So the
  live db is upgraded in place and a fresh seed tarball need not carry the newest schema.
- Shadow `tooling/congruencey-tests/agents-migration-shadow.py` (8/8): migration is additive
  (pre-existing rows survive), routes land, the real route SQL registers + trails an agent,
  re-running is a no-op. The gate (agent_tools_suite) forwards `{session,tool,intent}` here.

## version-4.089 — DB-remembering install (do_state preserves the live db)

`do_state` used to unconditionally extract the seed `database.tar.xz` over
`state/congruency.sqlite` — a `setup.py install` against a tree whose state dir is (or is
bind-mounted from) the live db would erase every ticket/memory/api_key.

- `do_state(version, preserve_db)`: if a live `congruency.sqlite` is already present, verify + keep
  it instead of re-extracting the seed (mirrors `serve.py:ensure_db`). `preserve_db` defaults on in
  the config object + `resolve_config`, so the installer remembers our db even for pre-4.089 tags.
- Dropped `state/congruency.sqlite` from `RUNTIME_PATHS` so `uninstall` can't purge it.
- **Shadow gate** added to the ratchet: `install.json` names `shadows` run before state install
  (non-zero aborts). `tooling/congruencey-tests/db-preserve-shadow.py` (6/6) pins that `preserve_db`
  keeps the db, that off still wipes (guard is load-bearing), that fresh installs still seed.

## version-4.080 — `congruency/` layout repath + db installed in-crank

**Layout (the spec):** `checkouts/current/{congruency, state}` — the CMS app under
`congruency/`, the database in a sibling `state/`. The old flat `checkouts/current/*`
copies were removed.

**Where it runs:** dev server on `0.0.0.0:8899` (`serve.py`, `--port` to override).

**Paths corrected** (app root `checkouts/current` → `checkouts/current/congruency`; but
`state/` is a sibling, so `SOURCE/state` → `dirname(SOURCE)/state`):

Functional (app/tooling-breaking):

| File:line | Was | Now |
|---|---|---|
| `checkouts/current/congruency/tools/serve.py:36` | `join(SOURCE,"state")` | `join(dirname(SOURCE),"state")` |
| `checkouts/current/congruency/tools/make_state.py:31` | `join(SOURCE,"state")` | `join(dirname(SOURCE),"state")` |
| `checkouts/current/congruency/tools/make_state.py` (build_tarball) | seed-fabricates a stub when `source_db` gone | re-snapshots the **installed** `state/congruency.sqlite` (db installed every crank; never a stub) |
| `checkouts/current/congruency/boot/configure.php:42` | `CONGRUENCY_SQLITE = ABS_PATH.'state'` | `dirname(rtrim(ABS_PATH,SLASH)).'/state'` |
| `checkouts/current/congruency/tools/provision_php.py:156` | git-add `checkouts/current/tools/...` | `.../congruency/tools/...` |
| `tooling/congruencey-tests/verify:35` | `SOURCE = MONO/checkouts/current` | `MONO/checkouts/current/congruency` |
| `tooling/coverage/branch_test.php:10` | `$SRC = .../checkouts/current` | `.../checkouts/current/congruency` |
| `tooling/coverage/branch_test2.php:6` | `$SRC = .../checkouts/current` | `.../checkouts/current/congruency` |
| `install.py:240` (main/ratchet) | `checkouts/current/tools/provision_php.py` | `.../congruency/tools/provision_php.py` |
| `install.py:277` (main/ratchet) | `checkouts/current/tools/serve.py` | `.../congruency/tools/serve.py` |

Comment/docstring/usage strings also corrected: `serve.py:6,34`, `make_state.py:14,29-30`,
`mint_crank.py:10,15,33`, `verify:11`, `ENTRY_POINT.py:29`.

Left unchanged (already correct — `state/` is a sibling): `checkouts/current/state/*`,
`install.py` `_state_spec`/`do_state`, `mint_crank` `step_state` artifact, root-relative
`registry.json paths.php` and `STATE.json seed/artifact`.

Dormant, flagged not edited (one-shot applied patch scripts, not in the runtime path):
`fixes/install_config_loader.py:142`, `fixes/install_prod_seed.py:23`,
`fixes/install_state_db.py:22`, `fixes/prove_git_store.py:33`,
`fixes/state_rides_in_crank.py:16`.

**Verify:** 3 passed, 0 failed. **DB:** 23-table unified db installed in
`checkouts/current/state/`.
