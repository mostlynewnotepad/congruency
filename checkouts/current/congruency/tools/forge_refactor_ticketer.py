#!/usr/bin/env python3
"""forge_refactor_ticketer.py — enumerate EVERY unique module in the forge and file ONE
behavior-preserving rewrite build-ticket per UNIQUE module (ticket #201, per the refactor
standard #200).

WHY A SCRIPT. The forge is 262 bare repos holding 31,421 files at their tips, 25,175 of them source.
Hand-filing a rewrite ticket per module is thousands of tickets, so nothing here is hand-filed: this
instrument walks the forge, DEDUPLICATES to unique modules, and files one ticket per unique module —
batched, idempotent, and self-repopulating. The dedup is the point, and it is not theoretical: the
five `audio_tagger` mirrors carry 18 source files between them that are only 5 distinct modules, so
this tool files 5 tickets there and not 18.

TERMS (defined here because the artifact stands alone):
  forge repo   — a bare git repository under config/forge/remotes/*.git (the forge's mirror store).
                 "Bare" = no working tree; its files are read with git plumbing, never checked out.
  tip          — the commit this tool enumerates a repo at. Normally HEAD; see THE TIP below, which
                 is a documented, evidenced deviation, not a shortcut.
  module       — one source blob at a repo's tip whose extension is in --ext (default: the code
                 languages listed in SOURCE_EXT; .pyc/.json/.md/.txt and other non-source are not
                 modules and are never enumerated).
  module-sha   — THE DEDUP KEY, 16 hex chars. Two files with the same module-sha are the same module
                 and share ONE ticket. See IDENTITY below for how it is computed.
  module key   — `forge-rw:<module-sha>`, carried verbatim in the ticket TITLE in square brackets.
                 The title is one of the three idempotency sources; see IDEMPOTENCY.
  ledger       — this tool's OWN sqlite db (never the CMS state db) recording every module-sha it has
                 filed a ticket for, plus every location that module was found at, plus each chain's
                 high-water-mark. See THE LEDGER.
  chain        — a drain sequence of successor tickets, named by --subset (or "all"). #196's
                 self-repopulating pattern; see BATCHED + SELF-REPOPULATING.
  #std         — ticket #200, "the FORGE-wide refactor standard". Every rewrite ticket this tool
                 files quotes #200's four requirements and hangs off #200 by a `spawned` edge.

THE TIP — HEAD, WITH AN EVIDENCED FALLBACK. The ticket says "at HEAD", and HEAD is what this tool
asks for first. But HEAD RESOLVES IN ONLY 80 OF THE 262 FORGE REPOS. In 179 of the other 182 the
`HEAD` file says `ref: refs/heads/master` while the only branch the mirror actually carries is
`refs/heads/main` — a dangling symbolic HEAD, so `git rev-parse HEAD` exits 128 and `ls-tree HEAD`
enumerates nothing; the remaining 3 carry no branch at all and are genuinely empty. A tool that took
HEAD literally would silently enumerate 80 repos, report success, and leave 179 repos' modules with
no rewrite ticket — under-enumeration is exactly what "enumerate EVERY unique module" forbids, and it
would be invisible in the output. So tip resolution is, per repo:

    1. HEAD                     — when `git rev-parse --verify HEAD` resolves (80 repos today)
    2. refs/heads/main          — else, when it exists
    3. refs/heads/master        — else, when it exists
    4. the first refs/heads/*   — else, in lexicographic order (deterministic across runs)
    5. nothing                  — a repo carrying NO branch at all is EMPTY: it is reported as
                                  skipped with its reason, never silently dropped

Measured over the live forge: 80 repos resolve at HEAD, 179 more resolve by fallback, 3 carry no ref
at all. The fallback is the difference between 10,776 and 31,421 enumerable files (7,755 vs 16,975
.py). Every ticket records which ref its module was read from, so no ticket claims "HEAD" when the
module came from a fallback ref.

IDENTITY — HOW TWO FILES BECOME ONE TICKET (the ticket's "content sha256 + AST-normalized identity",
reusing codebean #183 rather than inventing a second definition of sameness):

  * a Python blob that PARSES  ->  AST-NORMALIZED identity.
        module-sha = sha256("ast:" + codebean._ast_norm(source))[:16]
    `_ast_norm` is codebean's own normalizer (codebean_mcp/prototype/code_wrapper.py) —
    `ast.dump(ast.parse(ast.unparse(ast.parse(src))))` — so two copies that differ only in
    comments, blank lines, quoting or spacing normalize to the SAME string and share one ticket.
    A docstring is real content and does NOT normalize away: two modules whose docstrings differ are
    genuinely different modules and get their own tickets. This is #194's rule ("grouped by
    AST-normalized function/module (codebean lower_*, #183)"), executed with #183's own function.
  * anything else (non-Python, non-UTF-8, or Python that does NOT parse — the forge holds python-2
    and truncated files) -> CONTENT SHA256 identity.
        module-sha = sha256("raw:" + bytes)[:16]
    Exact byte-copies still share one ticket; near-copies do not, because no AST is definable for
    them. That limit is stated on every ticket it applies to rather than papered over.

  The "ast:"/"raw:" prefixes keep the two namespaces disjoint, so an AST identity can never collide
  with a content identity. 16 hex = 64 bits: over ~20k modules the birthday probability of any
  collision is ~1e-11.

  #193 (the universal resolver) and #194 (the dedup engine) are both still REQUESTED — no resolver
  module exists to import today. This tool therefore reuses what IS built: the omni-git blob index
  and codebean's `_ast_norm`. It does NOT rebuild either, and when #193/#194 ship they can consume
  this tool's ledger, which already stores the cluster (canonical + every duplicate location) in
  #194's shape.

THE OMNI-GIT BLOB INDEX — REUSED, NOT REBUILT. `omni_index.db` (built by jazz-forge's omni_index.py;
resolved exactly as the CMS reader resolves it — OmniExplorer.php:34-36, `getenv('OMNI_INDEX_DB') ?:
$HOME/code/installed/jazz-project/config/forge/omni_index.db`) holds one `occ` row per OCCURRENCE:
(sha, path, ext, size, ref, repo, ts). `occ.sha` is the GIT BLOB SHA1 — the same address
`git ls-tree` prints — so a module's blob sha1 joins straight onto `occ` and yields the other places
that exact blob has appeared, historically. That is how a ticket's source-location list reaches
beyond today's tips into the corpus's past. Because `occ` carries one row per SNAPSHOT, the join is
reduced to the DISTINCT {repo, path} pairs (a file recurring across 40 snapshots is one location, not
forty), each shown with the index's own `ts` for its first row — `ts` is usually a snapshot stamp
(20260703T062230Z) but ~5k rows carry a source label like 'gitlab' instead, so it is labelled
`occ.ts` and never presented as if it were always a date. Measured: ~86% of tip blobs are present in
`occ`; a blob that is absent simply contributes no extra locations (the index is enrichment, and this
tool runs fine with it missing entirely). It is opened `immutable=1` and NEVER written.

TIP BEATS OMNI — A PLACE IS ONE PLACE, AND 'origin' IS ONLY HOW IT WAS LEARNED. Because the index
knows ~86% of tip blobs, most of a module's LIVE copies are seen FIRST as index rows: the module is
met in one repo, the index immediately names the other places that blob sits at, and the scan reaches
those repos only later. A location is therefore keyed by the PLACE it names — (repo, path) — and
`origin` records how that place was learned, NOT what it is:
    'tip'  — a scan ENUMERATED the module there, live, at that repo's tip. It is a source location
             the rewrite MUST satisfy, it is listed under the ticket body's "ALSO LIVES AT THESE
             FORGE TIPS", and it counts toward the report's "(+N copy/copies -> 1 ticket)".
    'omni' — the index records the blob there historically. Context the ticket carries, not work.
So when the scan enumerates a place the index had already named, the location is UPGRADED 'omni' ->
'tip' rather than dropped as a duplicate of it — in ONE place for the run (_add_location()) and one
for the ledger (_ledger_add_location()). The reverse is never applied: an index row for a place
already proven live adds nothing and is ignored, never a downgrade.
  This is not a hypothetical tidiness. Matching a location on (repo, path) while IGNORING origin
  made the enrichment index actively DESTROY truth, and only when it was working: a ticket declared
  its module "unique to <repo> among the repos scanned so far" while the very same run had already
  enumerated a byte-identical LIVE copy at another repo's tip, rendered that live copy under
  "HISTORICAL OCCURRENCES ... Context for the rewrite, not extra work" — directly contradicting the
  body's own "every location below is satisfied by that one rewrite" — and understated the
  "(+N copy/copies)" annotation that IS this tool's acceptance evidence for "copies share a ticket,
  verified". Measured on the real `coupler` subset: NINE of its fourteen tickets carried a live tip
  of a repo the same run had enumerated, typed 'omni' — so each printed "(+1 copy/copies)" for a
  module that in fact lives at THREE tips, and now correctly prints "(+2 copy/copies)". Toggling
  ONLY the index across two otherwise-identical runs used to change those tip facts, which is the
  plainest statement of the defect: an index documented as pure ENRICHMENT was deciding what the
  forge's live tips are. The dedup was never affected (one ticket per unique module always held);
  what was wrong was the ticket CONTENT this tool exists to produce, and the origin the ledger hands
  to #193/#194.
  WHAT THE UPGRADE DOES NOT DO, stated because the rule above must not be read as more than it is.
  A place is matched by the index's own (repo, path) STRINGS, and `occ.repo` is its OWN namespace:
  it does not always use the forge's remote-directory names (the index says
  `testmonkeyalpha/audio_tagger` where the forge mirror is `gitlab__testmonkeyalpha__audio_tagger`,
  though it says plain `coupler` for that one, which is why the demotion bit 9 of 14 coupler
  tickets). So where the two namespaces disagree, the index's row for a place is not recognised as
  the live tip it may describe and stays in the HISTORICAL list, possibly naming under another name
  a repo that also appears above. Reconciling repo identity across namespaces is the UNIVERSAL
  RESOLVER's job — #193, still REQUESTED — and this tool does not guess at it.
  This limit is one-directional and cannot cost a rewrite any work: THE TIP LIST IS BUILT SOLELY
  FROM WHAT THE SCAN ITSELF ENUMERATED, never from the index, so every live copy a run reads is
  listed as a tip and counted as a copy no matter what the index calls its repo. The worst the
  mismatch can do is leave a redundant line in the historical list, which is explicitly context and
  not work. The failure it replaces did the opposite: it took a live copy OUT of the tip list.

BEHAVIORAL EXEMPLARS (#200's "verified, not asserted"). For each module it files, this tool captures:
  * THE CALLABLE SURFACE — every top-level function and class method, lowered with codebean's
    `lower_node` (#183), giving each callable's real name/params/returns. This is the contract the
    rewrite must reproduce, and it is captured for every parseable Python module.
  * IO EXEMPLARS — concrete (input, output) pairs mined with criteria_miner's `mine` (the tool #200
    names), which runs the ORIGINAL as the oracle and records what it returned. The rewrite is
    accepted when it reproduces these pairs.
  criteria_miner mines ONLY obviously-pure functions and enforces that itself: it refuses any
  function whose source so much as mentions a world-touching or non-deterministic name (open/os/
  subprocess/socket/random/time/...), refuses methods and no-arg functions, execs the function alone
  in an isolated namespace (never importing the module), bounds every call with a 0.5s timer,
  discards any exemplar that does not round-trip through JSON, and returns nothing at all unless it
  got >= 2 exemplars. Mining therefore executes ONLY functions the corpus itself proves inert, and
  only for the <= --batch modules this run actually files. `--no-exemplars` skips it entirely; a
  module with nothing minable is filed with its callable surface and says so — it is never dropped.
  criteria_miner's own honest limit is carried onto each ticket: mined exemplars cover the SAMPLED
  inputs, so they are a strong refactor-drift net, not a proof of total equivalence.

THE EMBEDDED SOURCE — EVERY UNIT CARRIES ITS OWN BYTES (#346, the fix that unblocks the campaign).
Each rewrite ticket EMBEDS the original module's source verbatim in its BODY, between the marker
lines `===ORIGINAL SOURCE (...)===` and `===END SOURCE===`. Those embedded bytes are the
AUTHORITATIVE copy and the behavior-preserving basis the rewrite is judged against. The
`git --git-dir=... cat-file blob` command under CANONICAL SOURCE stays on the ticket as a REFERENCE
for a reader who has forge access, but nothing in the ticket requires running it.

  WHY THE BODY, AND NOWHERE ELSE. A unit is executed by pair_loop, whose WORKER is spawned into the
  ticket's own congruency worktree and SANDBOXED to it. The forge's bare repos live outside that
  directory, so the worker cannot run the cat-file command and there is no cached copy to read.
  Every forge unit therefore blocked with "canonical source unreadable, refused to fabricate" — the
  worker behaving CORRECTLY, because #200 demands behavior PRESERVED and you cannot preserve what you
  cannot read (#259 is the proof; #346 is the fix). This tool runs in the DISPATCH context, which CAN
  read the forge, so it is the one that can carry the bytes across. It puts them in the body because
  the body is the only channel that reaches a worker: pair_loop reads the ticket's TITLE and BODY and
  nothing else (pair_loop.py:990-992), passes `body` into the prompt context (:1028), and
  WORKER_PROMPT splices it into the birth prompt (:448). No journal, no manifest and no route is read
  into that prompt.

  HOW, exactly. All four cases are stated ON the ticket that carries them, never silently:
    * UTF-8 TEXT WITHIN THE CAP -> the bytes verbatim: no re-indentation, no re-wrapping, nothing
      elided. This is the normal case — every module of the acceptance runs is a few KB.
    * NOT UTF-8 TEXT, or it holds a NUL byte (which JSON transport and sqlite TEXT do not carry
      safely) -> the same bytes, BASE64-encoded, with a one-line python3 decode command on the
      ticket. Still zero forge access needed.
    * OVER THE CAP — MAX_EMBED_BYTES, 256 KiB (262144), below -> only the first 256 KiB are embedded,
      under a TRUNCATED banner that states both byte counts and tells the worker NOT to rewrite from
      an excerpt (a rewrite of a truncated original is a new program, not a preserved one). Such a
      unit DOES still need forge access and SAYS so, rather than pretending to be self-contained. The
      cap exists because a body is read into every prompt of the pair, so an unbounded blob blows the
      prompt, not merely the row.
    * THE FENCE COLLIDES — the module's own text contains `===END SOURCE===` -> both markers take a
      `:<module-sha>` suffix. The body NAMES its exact end marker directly above the block, so it is
      self-describing whichever pair is in use.

--patch-bodies — THE ALREADY-FILED UNITS ARE SUPERSEDED, NOT EDITED (#346). Units filed before #346
carry no embedded source: they are the blocked ones. They cannot be repaired in place, and that is
not a preference — A TICKET BODY IS IMMUTABLE IN SQL. `tg_tickets_immutable_identity` ABORTs any
UPDATE that changes id/ts/title/body/component/kind (migrations/0029_ticket_authorization.sql:
111-117), and no route edits a body. Appending the source with `ticket.progress` is permitted (the
journal is append-only and that is what it is for) but would NOT unblock anything: the worker's birth
prompt is title + body only (pair_loop.py:990-992,1028,448), so a journal event never reaches the
agent that needs the bytes — it would file one progress report per unit and leave every unit exactly
as blocked. So `--patch-bodies` does what the schema itself prescribes for this case, "stop + spawn +
supersedes-edge = graft" (0029_ticket_authorization.sql:8). Per sourceless OPEN unit:

    1. file a REPLACEMENT unit — same module key, same requirements, PLUS the embedded source (and
       the ledger's converged location cluster and freshly mined exemplars), edged `spawned` from
       #200 like every other unit;
    2. edge `supersedes` from the replacement to the original — the direction 0012's own header
       states, "a superseding ticket OWNS the predecessor it replaced" (0012_ticket_edges.sql:2-3);
    3. file a `stop` ticket aimed at the original through a `stops` edge, so the queue stops handing
       a sandboxed worker a ticket it provably cannot do (ticket.stops, 0030_pair_loop_routes.sql);
    4. append an attributed `ticket.progress` note to the original recording what superseded it and
       why — the journal used for what it IS good for: recording what happened.

  NOTHING IS DELETED OR EDITED. The original ticket, its journal and its edges stay on the record
  forever; it is halted, not erased, and a `start` ticket aimed at the stop would release it. The
  flag keeps the name #346 gave it; what it cannot do is patch a body, and it says so rather than
  pretending.

  IDEMPOTENT, AND RESUMABLE MID-GRAFT. A unit is skipped when its body already carries the source, or
  when an active stop already aims at it (`ticket.stops` > 0 — which is also how a HUMAN's stop is
  respected: this tool never grafts a ticket someone else has halted). If a run dies after filing the
  replacement but before the stop, the next run sees a self-contained OPEN unit ALREADY carrying that
  module key and files NO second replacement — it only finishes the stop. Re-running a completed
  patch pass reports "nothing to patch" and writes nothing.

  IT NEVER FABRICATES. The replacement's source is read from the canonical blob — located in the
  ledger, or parsed from the original's OWN "CANONICAL SOURCE" block when the ledger is gone — and is
  then PROVEN to be the right module: its identity is recomputed (the same module_identity() every
  filing uses) and must equal the module-sha carried in the unit's title. A blob that will not read,
  or that re-identifies as a DIFFERENT module, is reported and skipped. It is never guessed at.

THE LEDGER — WHAT IT WRITES. Its own sqlite db, a SIBLING of omni_index.db by default
(`forge_refactor_ledger.db`; --ledger or $FORGE_REFACTOR_LEDGER overrides). Five tables, all
IF NOT EXISTS. No RECORD is ever deleted — the one row that is rewritten is the bookmark, which is
what a bookmark is for, and every position it ever held is kept forever in `runs`:
    modules      (module_sha PK, ident_kind, ext, ticket_id, title, canonical repo/path/blob, ...)
                 -- the idempotency ledger the ticket requires: one row per module-sha ever filed.
                 -- `ticket_id` is the ticket FIRST filed for that module and is left alone even
                 -- when --patch-bodies later supersedes it, because rewriting it would erase which
                 -- ticket the filing run actually created. The succession is in `grafts` below.
    locations    (module_sha, repo, path, blob_sha, origin)  -- the cluster: every PLACE it lives,
                 ONE row per (repo, path), `origin` recording how that place was learned — 'tip'
                 (a scan enumerated it live at a repo's tip) or 'omni' (joined from the blob index,
                 historical only). A place learned BOTH ways is one row, typed 'tip': the live tip
                 supersedes the historical row rather than adding a second one for the same place.
                 See TIP BEATS OMNI above, and _ledger_add_location() for the rule.
    chain_state  (chain PK, hwm_repo, ...)  -- the HIGH-WATER-MARK per drain chain. ONE row per
                 chain, REPLACED as the drain advances, and set back (to an earlier repo, or to NULL
                 = nothing proven drained) when a run DISPROVES the standing mark. See THE
                 HIGH-WATER-MARK: a mark that could only ever move forward could not be corrected,
                 and an uncorrectable wrong mark is exactly how modules get orphaned.
    runs         (ts, chain, scanned, filed, hwm)            -- one append-only row per filing run,
                 including the mark that run resolved: the audit trail of every mark ever held
    grafts       (ts, module_sha, old_ticket, new_ticket, stop_ticket, reason)
                 -- one APPEND-ONLY row per --patch-bodies supersession: which sourceless unit was
                 -- superseded, by which self-contained replacement, halted by which stop ticket.
                 -- Written only after all three tickets exist, so it never claims a graft that did
                 -- not happen. Nothing here is ever updated or deleted.
THE CLUSTER KEEPS COMPLETING. A batch is bounded, so a module's ticket is filed knowing only the
copies scanned up to that point; later runs meet the rest. A --file-tickets run therefore records the
locations of copies of ALREADY-ticketed modules too — it does not re-file them (that is the whole
point), it records where they are. So `locations` converges on every copy in the forge as the drain
proceeds, and `modules.copies` is re-counted from those rows so the two never disagree. This is the
cluster in #194's shape (canonical + every duplicate location), which #193/#194 can consume when they
ship.
The ledger is written ONLY by a --file-tickets run, and each ticket's row is written AFTER that
ticket is filed, so a crash mid-batch cannot record a ticket that does not exist. It is the only db
this tool writes: the CMS state db, omni_index.db and omni.git are opened read-only or not at all.

IDEMPOTENCY — A RE-RUN FILES ZERO DUPLICATES. A module is "already ticketed" if its key appears in
ANY of three sources, and the union is what makes it airtight:
  (1) THE LEDGER (`modules.module_sha`) — this tool's own record, all statuses, forever.
  (2) THE STATE DB (`tickets.title`, EVERY status) via `immutable=1`. This sees tickets whose status
      has since gone CLOSED/DONE, which `ticket.queue` (OPEN/REQUESTED only) cannot. `immutable=1`
      rather than `mode=ro` because the state db is WAL-journalled and `mode=ro` spins up
      `-wal`/`-shm` sidecar files on every open; `immutable=1` creates ZERO files.
  (3) THE LIVE `ticket.queue` ROUTE over HTTP. `immutable=1` deliberately ignores the `-wal`, so a
      row committed but not yet checkpointed is invisible to (2). Every ticket filed here is born
      REQUESTED (ticket.create hardcodes it) and REQUESTED is exactly what ticket.queue returns — so
      (3) covers precisely the window (2) can miss.
  With --file-tickets an unreadable ticket.queue is FATAL: the run refuses to file rather than risk
  duplicates. Sources (2) and (3) also mean a ticket filed by a DIFFERENT machine's run, or a ledger
  that was lost, still suppresses a duplicate.

THE HIGH-WATER-MARK IS A BOOKMARK, NOT THE GUARANTEE — AND THE DIFFERENCE IS TESTABLE. Walking 262
repos every run to re-derive work already done is waste, so each chain records `hwm_repo`: the last
repo it has FULLY drained. The next run resumes at the repo after it, and (absent --rescan) NEVER
looks at a repo at or below the mark again — which is exactly why the mark's meaning has to be exact,
and why it is decided in ONE function, mark_for(), and nowhere else.

  THE INVARIANT. A repo is DRAINED only when (1) its tip enumerated, (2) EVERY blob at that tip was
  read, and (3) every module in it was already ticketed or was FILED by this run. The mark names the
  last repo in the drained PREFIX — every repo at or below it satisfies all three.

  A repo that fails ANY of the three is HELD, and the mark stays BELOW it no matter what comes after.
  The four ways to fail, all of them real:
      * the tip will not enumerate (`ls-tree` non-zero: a corrupt or partial mirror)
      * a blob will not read (`cat-file` non-zero on a path `ls-tree` listed)
      * the batch filled mid-repo, so the rest of its modules were never looked at
      * a module's ticket.create / ticket.kind / edge.record was REFUSED, so it was never ticketed
  The last is the one a long drain actually meets: across 262 repos and thousands of tickets over
  many unattended scheduled runs, one transient route refusal is near-certain.

  WHY A "HOLD" AND NOT A "STOP". The mark is a MINIMUM of two independent numbers — the highest repo
  proven drained, and one below the FIRST repo held (mark_for()). A hold can therefore never be
  lifted by a later repo draining cleanly. That is the trap an earlier version of this tool fell into
  at two separate sites: it tracked the mark as a single NAME that the next healthy repo simply
  overwrote, and advanced it from what was SCANNED rather than what was FILED. A repo whose tip
  failed, or whose module's ticket.create was refused, was left behind while the mark sailed past it
  — and since resumption is POSITIONAL, "past it" means "never revisited". Those modules were
  orphaned silently, with exit 0 and a success message, and only a --rescan nobody schedules would
  ever have found them. A held repo instead costs one thing and loses nothing: the next run re-walks
  it (and the healthy repos after it, which re-file NOTHING — the module-sha union collapses them),
  and the modules that were missed are filed then. A run that files a PARTIAL batch still spawns its
  successor, so the hold is worked off by the chain itself with no human in the loop.

  THE MARK NEVER MOVES ON A LIE. A run where EVERY ticket.create failed leaves the mark exactly where
  it was and spawns no successor — the route is down, a successor would need that same route to file
  anything, and a chain of successors that can never file is a runaway. A re-run once the route works
  resumes at that identical batch.

Correctness never rests on the bookmark: `--rescan` re-walks from the first repo in scope, and a
re-run with --rescan STILL files zero, because the module-sha union above is what suppresses a
duplicate. That is the honest way to prove the idempotency claim — it exercises the ledger, not the
bookmark. (See ACCEPTANCE at the bottom.) A --rescan KEEPS the mark it re-walks under unless the
re-walk DISPROVES it — meeting a repo that is not drained after all pulls the mark back below that
repo, while repos the bounded re-walk never reached keep the standing claim of the runs that did
drain them. A rescan therefore cannot lose the drain progress of 200 earlier runs, and cannot
preserve a mark it has just caught being wrong.

BATCHED + SELF-REPOPULATING, AND THE CHAIN DOES NOT STALL (#196, and #245's fix). Append-only
governance means a ticket cannot reopen, so the work perpetuates by SPAWNING a successor. Successors
are GENERATION-NUMBERED — `[forge-rw:successor:<chain>:g<N>]` — and a run's own generation keeps it
alive:

    a run with nothing open (a human/dispatch starts it) -> files a batch -> spawns successor g1
    the pair executing g1 runs this tool again
      -> it READS THE QUEUE, sees g1 is the highest OPEN successor of this chain, concludes it IS
         g1's own run: it does not count itself, and spawns g2
    g1 settles; later the pair executing g2 runs -> spawns g3 ... until the forge is drained.

A run at generation N declines to spawn ONLY IF an OPEN successor of generation > N already exists.
It ignores its own generation and any stale open predecessor (gen <= N), because a predecessor will
never file anything again — that is precisely the stall a "does ANY open successor exist?" test
causes: the run launched from the successor's own body always sees itself, never spawns, and the
chain dies with everything past the first batch un-ticketed. THE GENERATION IS DERIVED FROM THE
QUEUE, not demanded on the command line: defaulting to 0 while g1 sat OPEN made `1 > 0` fire the
decline branch and killed the chain after its first successor (#245, reproduced end-to-end before it
was fixed there). `--gen N` remains an explicit OVERRIDE so re-running an OLD generation's command
still declines. Successor numbers are MONOTONIC — one past the highest this chain has EVER used (the
db, all statuses, UNION the live queue) — so a settled g1's number is never re-minted.

THE BRAKE. `ticket.stops` is checked FIRST, before anything is enumerated or filed — the same brake
pair_loop.py checks first (pair_loop.py:1001-1006). The route counts active (unreleased) stop tickets
aimed at a ticket OR ANY ANCESTOR through `spawned` edges, and every successor of this chain hangs
off #201 by exactly such an edge — so ONE stop ticket aimed at #201 halts the whole drain chain, and
a stop aimed at a single successor halts that one. An active stop prints HALT and exits 3, filing
nothing.

SAFE BY DEFAULT: run with no flags this tool only REPORTS — it writes to no db, and on a forge it can
read it creates NO FILE (verified before/after in isolation: the forge dir, the state dir and the
ledger's directory gain nothing, no `-wal`/`-shm` appears, and no ledger is brought into being by a
read). THE ONE EXCEPTION, stated because a claim this tool's own behavior can falsify is worse than
no claim: if the scan meets something unexpected — a tip that will not enumerate, a blob that will
not read — it APPENDS a Variant-A bug report to the registry's bug_reports sink, on a dry run too.
That is the ticket's own requirement ("Variant-A bug report on any unexpected outcome"), it appends
only when something is genuinely wrong, and it is the same sink every tool here shares; it is not a
by-product of reporting. A dry run over a healthy forge writes nothing at all. Module source is
read through `git cat-file` into memory and normalized/mined AS TEXT — codebean's `_ast_norm`,
`lower_node` and criteria_miner's `mine` all take source, so not even a temp file is created. It
writes exactly three things, each only when asked: --file-tickets POSTs through the governed rest.php
routes (ticket.create -> ticket.kind -> edge.record, plus agent.register -> ticket.progress when it
is grafting under --patch-bodies) with X-Api-Key from ../.secrets/ats.env (the same source
pair_loop.py reads) and records what it filed in the ledger; --json writes the one path
you name; and it appends to the registry's bug_reports sink if it hits an unexpected exception (the
Variant-A report note-for-claude mandates: filename / function / time-of-occurance /
methods-to-reproduce / possible-cause). Pure-python stdlib + git plumbing, registry-gated (a tool
that cannot see registry.json throws).

Every invocation below is written from the REPO ROOT — the directory that holds registry.json — and
runs as written from there (`tools/forge_refactor_ticketer.py` would NOT: the tool lives under
checkouts/current/congruency, so that shorter form only resolves from the CMS app root):

    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py
        # report the next batch; writes NOTHING
    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py --subset audio_tagger
        # only repos whose name contains 'audio_tagger' (also names the drain chain)
    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py --file-tickets --batch 5
        # file a bounded batch, record the high-water-mark, spawn the successor
    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py --subset audio_tagger \
            --file-tickets --rescan
        # the idempotency proof: re-walk from repo 1, ignore the bookmark -> files ZERO
    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py --json /tmp/mods.json
        # dump the enumeration (keys, locations, exemplars, bodies incl. the embedded source) as JSON
    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py --patch-bodies
        # report which already-filed OPEN units carry no embedded source; writes NOTHING
    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py --patch-bodies --file-tickets
        # graft them: per unit a self-contained replacement + a `supersedes` edge + a `stop` ticket

ACCEPTANCE (#201) — a SUBSET of the forge, end to end. #201'S OWN ACCEPTANCE RUNS ARE ON THE RECORD,
so read them before re-running anything: `--subset audio_tagger` filed FIVE rewrite tickets — #259,
#260, #262, #263, #265 — for the 18 source files those five repos carry at their tips. THIRTEEN of
the eighteen collapsed as copies: audio_tagger/tagger.py, for instance, is identical in all five
repos and holds ONE ticket (#260), not five. Successors #261 and #264 were filed, each edged
`spawned` from #201. A later run drained `--subset artifact_tree_gen` too (4 tickets, successor
#274).

  A LATER ROUND DRAINED `--subset coupler`, and that run is the one to read for TIP BEATS OMNI
  above, because it is the chain the demotion bug was caught on. `--file-tickets --batch 4` filed
  #283-#286 and spawned successor #287 (generation 1, edged `spawned` from #201) with all 3 repos
  still left, exactly as a mid-repo cut should; the successor's own `--batch 20` run then scanned
  all 3 repos, filed #288-#297, recorded 9 further copy locations of the modules #283-#286 had
  already ticketed, and drained the chain (mark `gitlab__testmonkeyalpha__coupler`, 0 repos left,
  no successor — correctly, there is nothing left to file). 37 source files across those 3 repos
  are only 15 distinct modules, and 14 tickets cover them: the 15th, `coupler/tests/__init__.py`,
  was ALREADY held by #262 — filed from the audio_tagger chain, whose `audio_tagger/tests/__init__.py`
  is the same module. That is the dedup reaching ACROSS unrelated repos, and it is why #294's body
  lists `coupler:coupler/updater.py` and `gitlab__testmonkeyalpha__coupler:coupler/updater.py` as
  "2 copy/copies" of one ticket rather than the "1 copy/copies" the demotion used to print.

  ALL THREE OF THOSE CHAINS ARE NOW DRAINED. That is not a footnote, it is how to read step A: a drain
  chain is a ONE-WAY street, so an acceptance step that must FILE something cannot name a chain that
  has already been drained — re-run on one, and the honest result is "nothing new", which is step B's
  test, not step A's. ALWAYS dry-run first (no --file-tickets) and read the totals line: a chain
  reporting "0 unique un-ticketed module(s) to file" and "0 repo(s) left" is drained — pick another
  --subset for step A. The chain named below was dry-run-verified FRESH as this was written, and the
  same one-way logic means it may not be by the time you read this. The dry run is the check; this
  paragraph is not.

  A CAVEAT WORTH READING, because it is the honest shape of a BOUNDED batch: the audio_tagger run
  used --batch 2, so #260 was filed while only the FIRST of the five repos had been scanned — and its
  body therefore says this module is "unique to audio_tagger among the repos scanned so far", because
  at filing time that was true. The other four copies were met by later runs, which correctly did NOT
  re-file them and recorded their locations in the ledger instead (`locations` now holds all five
  tips for that module-sha — see THE CLUSTER KEEPS COMPLETING). A ticket's body is a SNAPSHOT of what
  was known when it was filed; the LEDGER is the live cluster. Run with a --batch large enough to
  cover a subset in one pass (step B's --batch 20 covers all three of its repos) and the body carries
  every copy from the start — that is how #294 above came to list both of its live tips at filing
  time; step A's --batch 4 does NOT — it deliberately stops mid-repo, which is what
  makes it spawn a successor. That snapshot is a bounded batch's honest limit and is NOT the demotion
  bug of TIP BEATS OMNI: "unique ... among the repos scanned so far" is true of a repo not yet
  scanned, and false of one the same run has already enumerated. The rule fixes only the second.

    A. FILE A BATCH + SPAWN THE SUCCESSOR — on a chain nobody has drained yet (dry-run it first, per
       the paragraph above):
           python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py \
               --subset crank_pi --file-tickets --batch 4
       -> one build ticket per UNIQUE module, each EMBEDDING its module's original source (#346) and
          referencing its source repo(s)/path(s), #200, the control-config + installable
          requirements, and its captured behavior; each edged `spawned` from #200; then a successor
          edged `spawned` from #201, primed for the next batch. `crank_pi` is 3 repos and the first
          alone carries 23 source files, so --batch 4 fills MID-REPO: the mark stays before that
          repo, all 3 repos are reported left, and the successor finishes it. (Run it WITHOUT
          --file-tickets first to see the same batch and write nothing. Dry-run verified fresh as
          this was written: 1 repo scanned, 4 unique un-ticketed modules — all four `.sh`, so all
          four take the CONTENT-SHA256 identity — 4 complete sources embedded, 0 truncated, 3 repos
          left. `dz_debug`, which this step named before that chain was drained, and `coupler` before
          it, are the one-way street in action: BOTH are now step B examples, not step A ones.)
    B. A RE-RUN FILES ZERO — on a drained chain, with --rescan so what is tested is the LEDGER and
       not the bookmark:
           python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py \
               --subset coupler --file-tickets --batch 20 --rescan
       -> it re-walks all three repos, re-identifies all thirty-seven source files, collapses every
          one, and prints "== nothing new == every unique module enumerated is already ticketed;
          filed 0." It also reports "0 new copy location(s)": the cluster has CONVERGED, so the
          re-walk is a no-op in the ledger too, not merely in the queue. (`--subset audio_tagger
          --file-tickets --batch 20 --rescan` is the same test on the older chain: 5 repos, 18
          files, filed 0.)
          ZERO duplicates. (It still RECORDS any copy location it had not seen before — see THE
          CLUSTER KEEPS COMPLETING — which is knowledge, not a duplicate.)

ACCEPTANCE (#346) — THE UNITS ARE SELF-CONTAINED, and both steps check it while writing NOTHING:

    C. A FRESHLY-FILED UNIT CARRIES ITS SOURCE — on any chain that still has un-ticketed modules
       (`bakery_shreds` was dry-run-verified fresh as this was written; the one-way street of step A
       applies here too, so dry-run first and pick another --subset if it reports 0):
           python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py \
               --subset bakery_shreds --batch 2 --json /tmp/units.json
       -> files nothing (no --file-tickets) and writes only /tmp/units.json. Each entry's "body"
          holds that module's original bytes between the "source_begin_marker" and
          "source_end_marker" lines it names, and "source_embedded" is true. Take the lines strictly
          between those two markers, base64-decode them if "source_base64" is true, and diff against
          `git --git-dir=<remotes>/<repo>.git cat-file blob <blob_sha>`: BYTE-IDENTICAL (verified for
          both of that chain's modules, and for all 31 replacement bodies of step D). A worker
          reading only that body has everything the rewrite needs, and no forge access.
    D. THE ALREADY-FILED UNITS ARE PATCHED (or reported as needing nothing):
           python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py --patch-bodies
       -> the plan: every OPEN forge unit whose body carries no source, the self-contained
          replacement that would supersede it, and the stop that would halt it. Verified as this was
          written: 31 open units, 31 planned supersessions, every one's canonical blob read and
          PROVEN to re-identify as the module its title names. Add --file-tickets to execute it. A
          re-run afterwards reports every unit "already halted" and plans nothing — the graft is
          idempotent, and a graft interrupted between filing the replacement and filing the stop is
          finished by the next run rather than duplicated.

Exit 0 on a clean run (including "nothing new to file" and "nothing to patch", the expected results
of a re-run). Exit 2 with a one-line message (never a traceback) on a bad invocation or an unusable
environment. Exit 3 when an active stop ticket brakes the chain.
"""
import argparse
import ast
import base64
import contextlib
import glob
import hashlib
import importlib.util
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.request


# ── registry gate (note-for-claude: a tool that cannot see the registry throws) ──────────────────
def find_registry(start):
    d = os.path.abspath(start)
    while True:
        p = os.path.join(d, "registry.json")
        if os.path.isfile(p):
            return d, json.load(open(p))
        nxt = os.path.dirname(d)
        if nxt == d:
            raise RuntimeError("registry.json not found walking up from %s — refusing to run" % start)
        d = nxt


ROOT, REGISTRY = find_registry(os.path.dirname(os.path.abspath(__file__)))
# This tool's own path relative to the repo root. Derived, never hardcoded, so the invocation printed
# into a spawned successor ticket keeps running as written even if the tool is moved.
SELF_FROM_ROOT = os.path.relpath(os.path.abspath(__file__), ROOT)
STATE = os.path.join(ROOT, "checkouts", "current", "state")
CONG_DB = os.path.join(STATE, "congruency.sqlite")

HOME = os.path.expanduser("~")

# The omni-git index — resolved exactly as the CMS reader resolves it (OmniExplorer.php:34-36:
# getenv('OMNI_INDEX_DB') ?: $HOME/code/installed/jazz-project/config/forge/omni_index.db), which is
# also what tools/code_sim_indexer.py:156-159 does. Never written.
OMNI_DB = os.environ.get("OMNI_INDEX_DB") or os.path.join(
    HOME, "code/installed/jazz-project/config/forge/omni_index.db")
FORGE_DIR = os.path.dirname(OMNI_DB)
# The forge's bare mirror store: the *.git the ticket names as config/forge/remotes/*.git.
REMOTES = os.environ.get("FORGE_REMOTES") or os.path.join(FORGE_DIR, "remotes")
# This tool's OWN ledger — a sibling of the index it is derived from, the way code_sim.db is.
LEDGER = os.environ.get("FORGE_REFACTOR_LEDGER") or os.path.join(FORGE_DIR, "forge_refactor_ledger.db")
# codebean (#183) — the package dir holding prototype/code_wrapper.py + prototype/criteria_miner.py.
CODEBEAN = os.environ.get("CODEBEAN_MCP") or os.path.join(HOME, "code/installed/jazz-project/codebean_mcp")

# The congruency server carrying the governed routes.
BASE = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")

FACTORY_TICKET = 201        # the ticket that authorizes this factory; parent of every successor
STD_TICKET = 200            # #std — the refactor standard; parent of every rewrite ticket
FIX_TICKET = 346            # the ticket that made every unit carry its own source (see THE EMBEDDED
                            # SOURCE); cited on the artifacts --patch-bodies files, so a reader of a
                            # stop or a replacement can find why it exists

# The agent this tool journals as when it grafts. REGISTERED (agent.register) but deliberately never
# ticket.assign'd — exactly how pair_loop's forge steward and dispatch-01 journal onto tickets they
# are not authorized on, and for the same reason: tg_tickets_pair_completion (0029) refuses DONE on a
# pair ticket without two DISTINCT agents in two DISTINCT roles, and an always-present third agent on
# ticket_agents would hollow that backstop out. This tool files and journals; it never does the work.
TICKETER_AGENT = "forge-refactor-ticketer"

# A module key is `forge-rw:` + EXACTLY 16 hex chars. A successor key is
# `forge-rw:successor:<chain>:g<N>` — "successor" is not 16 hex chars, so the two patterns are
# disjoint by construction and a chain marker can never be mistaken for a module.
KEY_RE = re.compile(r"\[forge-rw:([0-9a-f]{16})\]")
SUCC_RE = re.compile(r"\[forge-rw:successor:(.+):g(\d+)\]")   # greedy: a chain may contain colons

# What counts as a source module. The forge's resolved tips hold 31,421 files, of which these
# extensions are 25,175 — the CODE among them (.py 16,975, .php 7,197, .js 307, .sh 239, .sql 140,
# .tsx 116, then a long tail). Every count here is measured at the tips THIS tool resolves (i.e. with
# the HEAD fallback above), so they are comparable with each other. Deliberately NOT source: .pyc
# (bytecode, not source), .json/.yml/.toml (data), .md/.txt (prose), .bin/.mp3/.pdf (assets).
# --ext overrides the whole set.
SOURCE_EXT = (".py", ".php", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh", ".bash",
              ".rb", ".pl", ".go", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".lua", ".r",
              ".sql", ".sol")
PY_EXT = (".py",)

MAX_BODY_LOCATIONS = 40     # locations printed per ticket; any excess is COUNTED, never hidden
MAX_BODY_CALLABLES = 40
MAX_BODY_EXEMPLAR_FNS = 8
MAX_BODY_EXEMPLARS = 6
GIT_TIMEOUT = 60

# ── the embedded source (#346; see THE EMBEDDED SOURCE in the module docstring) ───────────────────
# THE SIZE CAP. 256 KiB of a module's own bytes go into the ticket body verbatim; a blob larger than
# this is embedded TRUNCATED to its first MAX_EMBED_BYTES, under a banner that says so on the ticket.
# The cap is not about the db column (sqlite TEXT is effectively unbounded) — it is about the PROMPT:
# a body is spliced into the birth prompt of every agent of the pair (pair_loop.py:448,461,1028), so
# an unbounded blob costs that budget twice per round. 256 KiB is ~40x the largest module either
# acceptance chain met (the biggest is a few KB), so truncation is the pathological case it is meant
# to be and not the normal one.
MAX_EMBED_BYTES = 262144
B64_LINE = 76               # base64 wrap width, so a binary blob's block stays readable in a prompt

# The fence. The `(...)` description states which of the four cases produced the block — verbatim
# text, base64, or either of those truncated — so the block is never ambiguous about what it holds.
EMBED_BEGIN_FMT = "===ORIGINAL SOURCE (%s)==="
EMBED_END = "===END SOURCE==="
# Collision fence: used only when the module's OWN text contains a marker line (see _marks()).
EMBED_BEGIN_NONCE_FMT = "===ORIGINAL SOURCE:%s (%s)==="
EMBED_END_NONCE_FMT = "===END SOURCE:%s==="
# What a body is TESTED for when deciding whether a ticket already carries its source. Both the plain
# and the nonce'd fences start with these, so the test holds for either — see body_has_source().
EMBED_BEGIN_SENTINEL = "===ORIGINAL SOURCE"
EMBED_END_SENTINEL = "===END SOURCE"

EMBED_DESC_TEXT = "verbatim, the behavior-preserving basis"
EMBED_DESC_B64 = "verbatim, base64 — this blob is not UTF-8 text"
EMBED_DESC_TEXT_CUT = "TRUNCATED EXCERPT — NOT the whole module"
EMBED_DESC_B64_CUT = "TRUNCATED EXCERPT, base64 — NOT the whole module"

B64_DECODE_CMD = ("python3 -c \"import base64,sys;"
                  "sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))\"")


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2."""


# ── Variant-A bug report (note-for-claude: every tool auto-files a timestamped report) ───────────
def bug_report(fn, exc, repro, cause):
    """Filename / function / time-of-occurance / methods-to-reproduce / possible-cause, to the
    registry's bug_reports sink. Best-effort: a failing bug report never masks the real error."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "forge_refactor_ticketer.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:],
                "note": "forge_refactor_ticketer (#%d) — forge rewrite-ticket factory per #%d"
                        % (FACTORY_TICKET, STD_TICKET),
            }) + "\n")
    except Exception:                                     # noqa: BLE001
        pass


def step(msg):
    """Per-step telemetry: one labeled line per step of the run, so a scheduled run's log shows what
    it enumerated, what it skipped and why, and what it filed."""
    print("== step == %s" % msg)


def die(msg):
    print("forge_refactor_ticketer: %s" % msg)
    sys.exit(2)


# ── read-only sqlite (immutable=1: reads committed data, creates NO -wal/-shm sidecars) ──────────
def connect_ro(db_path, what):
    if not os.path.isfile(db_path):
        raise Fault("%s not found at %s" % (what, db_path))
    return sqlite3.connect("file:%s?immutable=1" % db_path, uri=True)


# ── REST (every write goes through the governed surface, as pair_loop.py does) ───────────────────
def api_key():
    """CONGRUENCY_API_KEY from ../.secrets/ats.env relative to the repo root (as pair_loop.py reads
    it), or the environment."""
    path = os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env")
    if os.path.isfile(path):
        for line in open(path):
            if line.strip().startswith("CONGRUENCY_API_KEY="):
                return line.strip().split("=", 1)[1]
    return os.environ.get("CONGRUENCY_API_KEY")


def rest(base, route, obj=None, method=None, key=None, timeout=20):
    """One governed route call. Returns the decoded JSON; raises on transport failure or on a route
    that answered with an {"error": ...} envelope."""
    url = base + "/rest.php?route=" + route
    if obj is not None and (method or "POST") == "GET":
        url += "&" + "&".join("%s=%s" % (k, urllib.request.quote(str(v))) for k, v in obj.items())
        obj = None
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json", "X-Api-Key": key or ""})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode())
    if isinstance(out, dict) and "error" in out:
        raise RuntimeError("route %s refused: %s" % (route, out["error"]))
    return out


# ── codebean (#183): the AST normalizer, the lowering, and criteria_miner's exemplars ────────────
def load_prototype(name, filename):
    """Load one codebean prototype module BY PATH, or raise Fault with a one-line reason.

    By path rather than as a package: codebean_mcp/__init__.py pulls in the FastMCP server (an
    optional dependency this tool does not need) — the same reason code_wrapper.py itself loads
    model.py by path. Two things this loader must get right, both learned from
    tools/code_sim_indexer.py's loader:
      * the module is registered in sys.modules BEFORE exec_module — code_wrapper.py declares a
        @dataclass, and dataclasses resolves a field's type through sys.modules[cls.__module__],
        which is None for an unregistered module;
      * its import-time stdout is captured — code_wrapper.py PRINTS a '[telemetry] unavailable'
        notice when jazz_telemetry is absent, which is not this tool's output.
    """
    src = os.path.join(CODEBEAN, "prototype", filename)
    if not os.path.isfile(src):
        raise Fault("codebean's %s not found at %s — set CODEBEAN_MCP or pass --codebean"
                    % (filename, src))
    spec = importlib.util.spec_from_file_location(name, src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(mod)
    except Exception as e:
        raise Fault("codebean's %s at %s failed to load: %r" % (filename, src, e))
    return mod


def load_codebean():
    """(code_wrapper, criteria_miner). code_wrapper gives `_ast_norm` (the AST-normalized identity)
    and `lower_node` (the callable surface); criteria_miner gives `mine` (the IO exemplars). Both
    are checked for the exact names this tool calls, so a codebean that has moved on fails with one
    line here rather than mis-identifying a module."""
    cw = load_prototype("frt_code_wrapper", "code_wrapper.py")
    for attr in ("_ast_norm", "lower_node"):
        if not hasattr(cw, attr):
            raise Fault("codebean's code_wrapper.py defines no %s — wrong codebean version? The "
                        "AST-normalized module identity is defined by that function, so this tool "
                        "refuses to guess at it" % attr)
    cm = load_prototype("frt_criteria_miner", "criteria_miner.py")
    if not hasattr(cm, "mine"):
        raise Fault("codebean's criteria_miner.py defines no mine() — wrong codebean version?")
    return cw, cm


# ── git plumbing (bare repos, read-only: ls-tree + cat-file only) ────────────────────────────────
def git(repo, *args, **kw):
    """(returncode, stdout). `text=False` returns bytes (blob content must not be decoded here)."""
    text = kw.get("text", True)
    try:
        r = subprocess.run(["git", "--git-dir", repo] + list(args), capture_output=True,
                           text=text, timeout=GIT_TIMEOUT)
    except FileNotFoundError:
        raise Fault("git not found on PATH — this tool reads the forge's bare repos with git plumbing")
    except subprocess.TimeoutExpired:
        return 1, ("" if text else b"")
    return r.returncode, r.stdout


def forge_repos(subset):
    """Every bare repo under REMOTES, sorted (the deterministic drain order the high-water-mark
    indexes into), optionally filtered to those whose NAME contains `subset`."""
    if not os.path.isdir(REMOTES):
        raise Fault("forge remotes not found at %s — set FORGE_REMOTES (the ticket names "
                    "config/forge/remotes/*.git)" % REMOTES)
    repos = sorted(glob.glob(os.path.join(REMOTES, "*.git")))
    if not repos:
        raise Fault("no *.git under %s — nothing to enumerate" % REMOTES)
    if subset:
        repos = [r for r in repos if subset in repo_name(r)]
    return repos


def repo_name(path):
    return os.path.basename(path)[:-4] if path.endswith(".git") else os.path.basename(path)


def resolve_tip(repo):
    """(ref, how) — the commit-ish this repo is enumerated at, or (None, reason).

    HEAD first, exactly as the ticket says. The fallback exists because 182 of the forge's 262 repos
    carry `ref: refs/heads/master` in HEAD while their only branch is refs/heads/main, so HEAD does
    not resolve and a literal reading would enumerate nothing there. See THE TIP in the module
    docstring — this is an evidenced deviation, and every ticket records which ref it used."""
    rc, _ = git(repo, "rev-parse", "--verify", "--quiet", "HEAD")
    if rc == 0:
        return "HEAD", "HEAD"
    rc, out = git(repo, "for-each-ref", "--format=%(refname)", "refs/heads/")
    heads = [h for h in (out or "").splitlines() if h.strip()]
    if not heads:
        return None, "no branch at all (empty mirror)"
    for pref in ("refs/heads/main", "refs/heads/master"):
        if pref in heads:
            return pref, "fallback (HEAD dangles)"
    return sorted(heads)[0], "fallback (HEAD dangles)"


def tip_blobs(repo, ref, exts):
    """[(blob_sha, path)] — every source blob at `ref`, in ls-tree order."""
    rc, out = git(repo, "ls-tree", "-r", ref)
    if rc != 0:
        return None
    found = []
    for line in (out or "").splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) < 3 or parts[1] != "blob":
            continue
        if os.path.splitext(path)[1].lower() in exts:
            found.append((parts[2], path))
    return found


def blob_bytes(repo, sha):
    rc, raw = git(repo, "cat-file", "blob", sha, text=False)
    return None if rc != 0 else raw


# ── identity: the module-sha (see IDENTITY in the module docstring) ──────────────────────────────
def module_identity(cw, raw, path):
    """(module_sha, ident_kind, text). AST-normalized for a Python blob that PARSES; content sha256
    for everything else. The 'ast:'/'raw:' prefixes keep the two namespaces disjoint."""
    text = None
    if os.path.splitext(path)[1].lower() in PY_EXT:
        try:
            text = raw.decode("utf-8")
            norm = cw._ast_norm(text)
            return hashlib.sha256(("ast:" + norm).encode("utf-8")).hexdigest()[:16], "ast", text
        except (UnicodeDecodeError, SyntaxError, ValueError, RecursionError):
            pass                                          # python-2 / truncated / not really python
    if text is None:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
    return hashlib.sha256(b"raw:" + raw).hexdigest()[:16], "sha256", text


def module_key(module_sha):
    return "forge-rw:%s" % module_sha


# ── the embedded source: the module's own bytes, carried INSIDE the ticket (#346) ────────────────
def _marks(desc, payload, sha):
    """(begin, end) — the fence for one embedded block.

    Normally the plain markers. If the payload itself contains a marker line, the module's own text
    would end the block early and the worker would silently read a PREFIX of the source as if it were
    the whole module — so both markers take a `:<module-sha>` suffix, which the payload cannot
    contain (it would have had to embed its own identity). The body always names its exact end marker
    directly above the block, so a reader never has to know which pair was chosen."""
    begin, end = EMBED_BEGIN_FMT % desc, EMBED_END
    if EMBED_BEGIN_SENTINEL in payload or EMBED_END_SENTINEL in payload:
        begin, end = EMBED_BEGIN_NONCE_FMT % (sha, desc), EMBED_END_NONCE_FMT % sha
    return begin, end


def embed_source(raw, sha):
    """The module's bytes, rendered for a ticket body. Never raises on corpus input.

    Returns {"begin", "end", "payload", "binary", "truncated", "shown", "total"} where `payload` is
    what goes between the two marker lines, `shown` is how many of the module's `total` bytes it
    represents, and `binary`/`truncated` say which of the four cases produced it (see THE EMBEDDED
    SOURCE in the module docstring). Every case is stated on the ticket by source_block().

    The two decisions, in order:
      TRUNCATE — a blob over MAX_EMBED_BYTES contributes only its first MAX_EMBED_BYTES bytes.
      ENCODE   — those bytes go in verbatim when they are UTF-8 text with no NUL (a NUL is not safe
                 through JSON transport into a sqlite TEXT column), and base64 otherwise. Only a
                 TRUNCATION can split a multi-byte character, so the decode is retried backing off at
                 most 3 bytes — and only when truncating. An UNCUT blob that will not decode is
                 genuinely not text, so it is base64'd rather than mangled."""
    total = len(raw)
    truncated = total > MAX_EMBED_BYTES
    head = raw[:MAX_EMBED_BYTES] if truncated else raw
    text, shown = None, len(head)
    for back in ((0, 1, 2, 3) if truncated else (0,)):
        try:
            text = head[:len(head) - back].decode("utf-8")
            shown = len(head) - back
            break
        except UnicodeDecodeError:
            text = None
    if text is not None and "\x00" in text:
        text = None                                       # valid UTF-8, but not body-safe: base64 it
    if text is None:
        b64 = base64.b64encode(head).decode("ascii")
        payload = "\n".join(b64[i:i + B64_LINE] for i in range(0, len(b64), B64_LINE))
        shown, binary = len(head), True
    else:
        payload, binary = text, False
    begin, end = _marks((EMBED_DESC_B64_CUT if truncated else EMBED_DESC_B64) if binary else
                        (EMBED_DESC_TEXT_CUT if truncated else EMBED_DESC_TEXT), payload, sha)
    return {"begin": begin, "end": end, "payload": payload, "binary": binary,
            "truncated": truncated, "shown": shown, "total": total}


def source_block(m):
    """The ticket body's ORIGINAL SOURCE section: the bytes, fenced, with everything a worker needs
    to know about them and nothing it has to take on trust. m["embed"] is set by prepare()."""
    e = m["embed"]
    out = []
    out.append(
        "THE ORIGINAL SOURCE, EMBEDDED — YOU NEED NO FORGE ACCESS TO DO THIS TICKET.\n"
        "The module's own bytes are reproduced below, inside this ticket. THEY are the\n"
        "authoritative copy and the behavior-preserving basis: rewrite from them. The\n"
        "`git --git-dir=... cat-file blob` command under CANONICAL SOURCE above is kept only as a\n"
        "REFERENCE for a reader who happens to have forge access — running it is NOT part of this\n"
        "ticket. (Why the bytes are here at all: the pair_loop worker that executes this ticket is\n"
        "sandboxed to the ticket's own congruency worktree and cannot read the forge's bare repos.\n"
        "Ticket #%d is the fix that put them on the ticket.)\n"
        "\n"
        "The block BEGINS at the line\n"
        "    %s\n"
        "and ENDS at the first line\n"
        "    %s\n"
        "Everything strictly between those two lines is the module%s."
        % (FIX_TICKET, e["begin"], e["end"],
           " — %d byte(s), byte for byte, with no re-indentation, no re-wrapping and nothing\n"
           "elided" % e["shown"] if not e["binary"] else
           " base64-encoded (see the decode line below)"))
    if e["binary"]:
        out.append("THIS BLOB IS NOT UTF-8 TEXT (or it carries a NUL byte, which does not survive the\n"
                   "JSON transport into a ticket body intact), so it is embedded BASE64-ENCODED\n"
                   "rather than mangled. Recover the exact original bytes by piping the block below\n"
                   "into:\n"
                   "    %s\n"
                   "That yields the %d byte(s) embedded here, and nothing about it needs the forge."
                   % (B64_DECODE_CMD, e["shown"]))
    if e["truncated"]:
        out.append("!! TRUNCATED — READ THIS BEFORE YOU REWRITE ANYTHING !!\n"
                   "This module is %d bytes, over this ticketer's %d-byte embedding cap, so ONLY ITS\n"
                   "FIRST %d BYTE(S) ARE BELOW. The block is an EXCERPT, not the module: %d byte(s)\n"
                   "are NOT in this ticket. Do NOT rewrite from the excerpt as though it were the\n"
                   "whole module — a rewrite of a truncated original is not behavior-preserving, it\n"
                   "is a different program. THIS ONE TICKET therefore still needs the canonical\n"
                   "location above: read the complete source with the `cat-file` command, and if you\n"
                   "cannot reach the forge, report BLOCKED. Do not fabricate the missing bytes."
                   % (e["total"], MAX_EMBED_BYTES, e["shown"], e["total"] - e["shown"]))
    out.append("%s\n%s\n%s" % (e["begin"], e["payload"], e["end"]))
    return "\n\n".join(out)


def body_has_source(body):
    """True when a ticket body already carries an embedded source block. Both fences (plain and
    `:<module-sha>`-nonce'd) begin with these sentinels, so one test covers either. Used by
    --patch-bodies to leave an already-self-contained unit alone — its only false positive would be a
    body that names both markers without fencing anything, which nothing this tool writes does."""
    b = body or ""
    return EMBED_BEGIN_SENTINEL in b and EMBED_END_SENTINEL in b


# ── the omni-git blob index: extra locations for a blob, joined on the git blob sha1 ─────────────
def omni_locations(omni, blob_sha):
    """[(repo, path, ts)] — every DISTINCT {repo, path} this exact blob has appeared at, from
    omni_index.db's `occ`. Enrichment only: no index (or no row) simply means no extra locations.

    `occ` carries one row per SNAPSHOT, so a file recurring across 40 snapshots is reduced here to
    ONE (repo, path) carrying the index's own earliest `ts` for that place — its first row.

    This reports what the INDEX knows and decides nothing about it: whether a place named here is
    merely historical or is ALSO a live forge tip is settled by _add_location(), which types it
    'omni' only while no scan has claimed — or later claims — that same place as a 'tip'."""
    if omni is None:
        return []
    try:
        rows = omni.execute("SELECT repo, path, MIN(ts) FROM occ WHERE sha=? "
                            "GROUP BY repo, path ORDER BY repo, path", (blob_sha,)).fetchall()
    except sqlite3.Error:
        return []
    return [(repo or "", path or "", ts or "") for repo, path, ts in rows]


# ── behavioral exemplars: codebean lower_node (#183) + criteria_miner IO pairs (#200) ────────────
def capture_behavior(cw, cm, text, mine):
    """{'callables': [...], 'exemplars': [...], 'note': str} for one module's source.

    callables — every top-level function and class method, lowered with codebean's `lower_node`, so
      each carries its REAL name/params/returns: the contract the rewrite must reproduce.
    exemplars — criteria_miner `mine` specs for the pure top-level functions, i.e. concrete
      (input, output) pairs with the ORIGINAL as the oracle. This mirrors criteria_miner's own
      mine_module loop (top-level FunctionDef -> mine(src, node)) but passes the SOURCE TEXT rather
      than a path, so no temp file is ever created.

    Never raises on corpus input: a module that does not parse yields no capture and says why."""
    cap = {"callables": [], "exemplars": [], "note": ""}
    if text is None:
        cap["note"] = ("not UTF-8 text, so no AST could be built: the rewrite's behavior must be "
                       "established by reading the original bytes.")
        return cap
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError) as e:
        cap["note"] = ("this blob is not parseable as python 3 (%s), so no AST surface or IO "
                       "exemplar could be captured: the rewrite's behavior must be established by "
                       "reading the original source." % e.__class__.__name__)
        return cap
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cap["callables"].append(("", _lower(cw, node)))
        elif isinstance(node, ast.ClassDef):
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cap["callables"].append((node.name, _lower(cw, m)))
    if not mine:
        cap["note"] = "IO-exemplar mining was disabled for this run (--no-exemplars)."
        return cap
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):         # mine() refuses async itself; skip early
            continue
        try:
            spec = cm.mine(text, node)
        except BaseException:                             # noqa: BLE001  — mined code may do anything
            continue
        if spec:
            cap["exemplars"].append(spec)
    return cap


def _lower(cw, node):
    """One callable's signature via codebean's `lower_node`, degraded to the bare ast facts if
    codebean refuses it — a callable is never dropped from the surface."""
    try:
        f = cw.lower_node(node)
        return {"name": f.name, "params": f.params, "returns": f.returns or "",
                "is_async": bool(getattr(f, "is_async", False))}
    except Exception:                                     # noqa: BLE001
        return {"name": node.name, "params": ast.unparse(node.args), "returns": "",
                "is_async": isinstance(node, ast.AsyncFunctionDef)}


# ── the ledger (this tool's OWN db; see THE LEDGER in the module docstring) ──────────────────────
LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS modules (
  module_sha  TEXT PRIMARY KEY,
  ident_kind  TEXT,
  ext         TEXT,
  ticket_id   INTEGER,
  title       TEXT,
  repo        TEXT,
  path        TEXT,
  blob_sha    TEXT,
  ref         TEXT,
  size        INTEGER,
  copies      INTEGER,
  filed_ts    REAL
);
-- `modules.copies` is the number of PLACES recorded for that module-sha below — DISTINCT
-- (repo, path) pairs, live tips plus historical omni occurrences. It has exactly ONE definition,
-- _recount_copies(), which every writing path calls, so `copies` and the rows can never disagree.
-- A LATER run that meets another copy of an already-ticketed module adds its place here and
-- re-counts, so the cluster keeps completing as the forge drains — see ledger_record_locations().
--
-- `locations` is ONE row per PLACE, with `origin` naming how the place was learned ('tip' = a scan
-- enumerated it live; 'omni' = the blob index records it historically). origin is PART OF THE
-- PRIMARY KEY below — the shape the first ledgers shipped with, and CREATE TABLE IF NOT EXISTS
-- never migrates a table that already exists — so a place learned BOTH ways could hold two rows,
-- double-counting the place and leaving a live forge tip recorded as historical. It does not: a tip
-- UPGRADES the historical row for its place rather than adding a second one (_ledger_add_location).
CREATE TABLE IF NOT EXISTS locations (
  module_sha  TEXT,
  repo        TEXT,
  path        TEXT,
  blob_sha    TEXT,
  origin      TEXT,
  ts          TEXT,
  PRIMARY KEY (module_sha, repo, path, origin)
);
CREATE TABLE IF NOT EXISTS chain_state (
  chain     TEXT PRIMARY KEY,
  hwm_repo  TEXT,
  updated   REAL
);
CREATE TABLE IF NOT EXISTS runs (
  ts       REAL,
  chain    TEXT,
  scanned  INTEGER,
  filed    INTEGER,
  hwm_repo TEXT
);
-- `grafts` — one APPEND-ONLY row per --patch-bodies supersession (#346). `modules.ticket_id` is
-- deliberately NOT rewritten when a unit is superseded: it records the ticket the filing run really
-- created, and this table records what replaced it. A reader following a module-sha therefore sees
-- both the original filing and its succession, and neither erases the other.
CREATE TABLE IF NOT EXISTS grafts (
  ts          REAL,
  module_sha  TEXT,
  old_ticket  INTEGER,
  new_ticket  INTEGER,
  stop_ticket INTEGER,
  reason      TEXT
);
"""


def ledger_rw():
    """The ledger, opened read-WRITE and created if absent. Called ONLY on a --file-tickets run —
    a report must never bring the ledger into being."""
    d = os.path.dirname(LEDGER)
    if d and not os.path.isdir(d):
        raise Fault("ledger directory %s does not exist — pass --ledger PATH" % d)
    con = sqlite3.connect(LEDGER)
    con.executescript(LEDGER_SCHEMA)
    con.commit()
    return con


def ledger_keys_and_hwm(chain):
    """(keys, hwm_repo) read from the ledger WITHOUT creating it, and without -wal/-shm sidecars.

    An absent ledger is an empty one — a fresh chain, not an error. `immutable=1` on a db that does
    not exist would raise, so the file's existence is checked first."""
    if not os.path.isfile(LEDGER):
        return set(), None
    try:
        con = sqlite3.connect("file:%s?immutable=1" % LEDGER, uri=True)
        keys = set(module_key(r[0]) for r in con.execute("SELECT module_sha FROM modules"))
        row = con.execute("SELECT hwm_repo FROM chain_state WHERE chain=?", (chain,)).fetchone()
        con.close()
        return keys, (row[0] if row else None)
    except sqlite3.Error as e:
        raise Fault("ledger at %s is unreadable (%s) — pass --ledger PATH or move it aside" % (LEDGER, e))


def _ledger_add_location(con, sha, repo, path, blob_sha, origin, ts):
    """Write ONE place to `locations`, applying the ledger's copy of _add_location's tip-over-omni
    rule (TIP BEATS OMNI in the module docstring). Returns 1 when this taught the ledger something
    new about that place.

    Because `origin` is part of the table's PRIMARY KEY (see the schema), a place learned both ways
    would otherwise hold TWO rows — one 'tip', one 'omni' — double-counting the place and leaving a
    live forge tip typed as history for whoever reads the cluster (#193/#194). So a tip UPGRADES the
    historical row for its place. That is an origin CORRECTION to the one row describing that place:
    the place, its blob and its module keep their row, and nothing is deleted."""
    if origin == "tip":
        # OR IGNORE: on a ledger that already carries BOTH rows for this place (written before this
        # rule existed), the upgrade would collide with the tip row already there. The tip is then
        # already recorded — which is the whole point — so the collision is not an error.
        if con.execute("UPDATE OR IGNORE locations SET origin='tip', blob_sha=?, ts='' "
                       "WHERE module_sha=? AND repo=? AND path=? AND origin<>'tip'",
                       (blob_sha, sha, repo, path)).rowcount:
            return 1
    elif con.execute("SELECT 1 FROM locations WHERE module_sha=? AND repo=? AND path=? AND "
                     "origin='tip'", (sha, repo, path)).fetchone():
        return 0                            # already proven live: a historical row adds nothing
    return con.execute("INSERT OR IGNORE INTO locations (module_sha, repo, path, blob_sha, origin, "
                       "ts) VALUES (?,?,?,?,?,?)",
                       (sha, repo, path, blob_sha, origin, ts)).rowcount


def _recount_copies(con, shas):
    """Re-derive `modules.copies` from the rows — THE one definition of `copies`, called by every
    path that writes a location, so the count and the rows can never drift apart. It counts PLACES
    (DISTINCT repo, path), not rows, so it stays true even on a ledger still carrying a pre-rule
    duplicate pair for one place."""
    for sha in shas:
        con.execute("UPDATE modules SET copies=(SELECT COUNT(*) FROM (SELECT DISTINCT repo, path "
                    "FROM locations WHERE module_sha=?)) WHERE module_sha=?", (sha, sha))


def ledger_record(con, m, tid):
    """Record ONE filed module. Called after its ticket exists, so a crash mid-batch can never leave
    the ledger claiming a ticket that was never created."""
    con.execute(
        "INSERT OR REPLACE INTO modules (module_sha, ident_kind, ext, ticket_id, title, repo, path, "
        "blob_sha, ref, size, copies, filed_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (m["sha"], m["ident_kind"], m["ext"], tid, m["title"], m["repo"], m["path"], m["blob_sha"],
         m["ref"], m["size"], len(m["locations"]), time.time()))
    for loc in m["locations"]:
        _ledger_add_location(con, m["sha"], loc["repo"], loc["path"], loc.get("blob_sha", ""),
                             loc["origin"], loc.get("ts", ""))
    _recount_copies(con, [m["sha"]])        # `copies` always from the rows, never from a guess
    con.commit()


def ledger_record_locations(con, extras):
    """Record copy locations of modules that were ALREADY ticketed (by an earlier run, or earlier in
    this one). Returns how many were NEW.

    Why this exists: a batch is bounded, so a module's ticket is filed knowing only the copies seen
    up to that point — later runs meet the rest. Without this, the cluster would freeze at whatever
    the filing run happened to have scanned, and the ledger's claim to hold every duplicate location
    would be false. `modules.copies` is re-counted from the rows so the two never disagree.

    Every place here was ENUMERATED live at a repo's tip by this scan, so each is recorded 'tip' —
    UPGRADING the historical row when an earlier run had only ever learned that place from the blob
    index, rather than adding a second row for the one place (_ledger_add_location)."""
    n, touched = 0, set()
    for sha, repo, path, blob_sha in extras:
        n += _ledger_add_location(con, sha, repo, path, blob_sha, "tip", "")
        touched.add(sha)
    _recount_copies(con, touched)
    con.commit()
    return n


def ledger_mark(con, chain, hwm, scanned, filed):
    """Append this run to `runs`, and SET the chain's mark to `hwm` — including UNSETTING it.

    The mark is written UNCONDITIONALLY, never only-when-truthy. A run can resolve the mark to "no
    repo is proven drained" (mark_for() returning None) after DISPROVING the standing mark — a
    --rescan that meets a held repo below it. Dropping that resolution because it is falsy would
    leave the stale row in place and resume the next run PAST the repo just held, which is the
    orphaning bug of THE HIGH-WATER-MARK in a third disguise: the mark would move on a lie by not
    moving at all. `runs` is the append-only record of what happened; `chain_state` is a bookmark,
    and a bookmark is meant to move — in BOTH directions."""
    con.execute("INSERT OR REPLACE INTO chain_state (chain, hwm_repo, updated) VALUES (?,?,?)",
                (chain, hwm, time.time()))                # hwm None -> SQL NULL: the mark is unset
    con.execute("INSERT INTO runs (ts, chain, scanned, filed, hwm_repo) VALUES (?,?,?,?,?)",
                (time.time(), chain, scanned, filed, hwm or ""))
    con.commit()


# ── idempotency sources (2) and (3): the state db, and the live queue ────────────────────────────
def keys_from_titles(titles):
    found = set()
    for t in titles:
        found.update("forge-rw:%s" % s for s in KEY_RE.findall(t or ""))
    return found


def db_titles(db_path):
    """Every ticket title, EVERY status. None when the state db is not there — a legitimate state
    for a worktree (the db is not tracked in git), and the queue still covers OPEN/REQUESTED."""
    try:
        con = connect_ro(db_path, "state db")
    except Fault:
        return None
    try:
        return [(t or "") for (t,) in con.execute("SELECT title FROM tickets")]
    except sqlite3.Error:
        return None


def queue_rows(base, key):
    """Every OPEN/REQUESTED ticket from the LIVE ticket.queue route. None if unreadable."""
    try:
        return rest(base, "ticket.queue", method="GET", key=key).get("rows", [])
    except Exception as e:                                # noqa: BLE001
        step("ticket.queue unreadable at %s (%s)" % (base, e))
        return None


# ── the brake: ticket.stops, checked FIRST (pair_loop.py:1001-1006) ──────────────────────────────
def active_stops(base, key, tid):
    """Active (unreleased) stop tickets aimed at `tid` or any ancestor through `spawned` edges.
    None when the route cannot be read."""
    try:
        rows = rest(base, "ticket.stops", {"ticket_id": tid}, method="GET", key=key).get("rows", [])
    except Exception:                                     # noqa: BLE001
        return None
    return int(rows[0].get("active_stops", 0)) if rows else 0


def brake(base, key, tid, label):
    """True when the chain is braked (and it says so). Every successor hangs off the factory ticket
    by a `spawned` edge and ticket.stops walks that ancestry, so ONE stop aimed at the factory halts
    the whole chain. An unreadable route is not a brake: it returns False, and a --file-tickets run
    has already died on the unreadable queue before reaching here."""
    n = active_stops(base, key, tid)
    if n is None:
        return False
    if n > 0:
        print("== HALT == %d active stop ticket(s) aim at %s #%d — the ticket authorizes nothing"
              % (n, label, tid))
        return True
    step("brake: no active stops on %s #%d" % (label, tid))
    return False


# ── the successor chain (#196; the generation rules are #245's fix — see the module docstring) ───
def chain_of(subset):
    return subset or "all"


def successor_key(subset, gen):
    return "forge-rw:successor:%s:g%d" % (chain_of(subset), gen)


def max_open_generation(titles, subset):
    """The highest successor GENERATION currently OPEN for this chain, or -1 if none. It both
    DERIVES this run's generation and guards the spawn — see this_generation() and the docstring."""
    hi, chain = -1, chain_of(subset)
    for t in titles:
        m = SUCC_RE.search(t or "")
        if m and m.group(1) == chain:
            hi = max(hi, int(m.group(2)))
    return hi


def max_generation_ever(all_titles, subset):
    """The highest generation this chain has EVER used (db, all statuses, UNION the live queue), or
    -1. Successors are minted one past this, so a settled g1's number is never re-used."""
    hi, chain = -1, chain_of(subset)
    for t in all_titles:
        m = SUCC_RE.search(t or "")
        if m and m.group(1) == chain:
            hi = max(hi, int(m.group(2)))
    return hi


def this_generation(explicit, open_hi):
    """This run's own generation. An explicit --gen wins. Otherwise DERIVED: the highest OPEN
    successor of this chain is the ticket a pair is running this tool from, so that is this run's
    generation; with none open the chain is fresh and this run is 0 (#245)."""
    if explicit is not None:
        return explicit
    return open_hi if open_hi >= 0 else 0


def successor_ticket_id(rows, subset):
    """The ticket id of this chain's highest OPEN successor, so the brake can be aimed at it too."""
    best, chain = None, chain_of(subset)
    hi = -1
    for r in rows or []:
        m = SUCC_RE.search(r.get("title") or "")
        if m and m.group(1) == chain and int(m.group(2)) > hi:
            hi, best = int(m.group(2)), r.get("id")
    return best


# ── THE MARK RULE — the one place the high-water-mark is decided ─────────────────────────────────
def mark_for(names, drained_idx, cap_idx):
    """(hwm_name_or_None, mark_idx, repos_left) — THE high-water-mark rule, in ONE place because two
    code sites once each got it wrong in a different way (see THE HIGH-WATER-MARK in the docstring).

    Two INDEPENDENT numbers decide the mark, and the mark is the MINIMUM of them:

      drained_idx — the HIGHEST repo index this run can assert is fully drained. It is a max() over
                    repos proven drained, seeded with the mark's OWN index, so a bounded run never
                    forgets what earlier runs proved.
      cap_idx     — one BEFORE the FIRST repo this run PROVED is NOT drained (its tip would not
                    enumerate, one of its blobs would not read, the batch cut it short, or one of its
                    modules failed to file). It is a min() over every such hold.

    The minimum is what makes a HOLD absolute: nothing a later repo proves can lift a cap an earlier
    repo set, because these are two separate accumulators and the cap always wins. A held repo is
    therefore re-walked next run — which costs a re-scan and orphans nothing, the trade this tool
    always takes. A `mark_idx` below 0 means "no repo is proven drained", and the mark is UNSET —
    which ledger_mark() writes as NULL rather than skipping, so it can pull a disproven mark back."""
    # drained_idx is a max() over real repo indices (and the standing mark's own index), so it is
    # always <= len(names)-1: the min() below can never name a repo that does not exist.
    idx = min(drained_idx, cap_idx)
    return (names[idx] if 0 <= idx < len(names) else None), idx, len(names) - (idx + 1)


# ── the scan: bounded, resumable, deduplicating ──────────────────────────────────────────────────
def scan(cw, omni, repos, start_at, exts, batch, done, old_idx):
    """Walk repos from `start_at`, building this run's batch of UN-TICKETED unique modules.

    Returns (todo, drained_idx, cap_idx, scanned, skipped, dupes_collapsed, extras). The two indices
    are the scan's HALF of the mark rule — the caller applies the other half (a module that failed to
    file) and resolves both through mark_for(). The scan NEVER decides the mark itself.

    The scan is BOUNDED: it stops as soon as `batch` new modules are found, so a run never reads the
    whole forge. `done` is the union of the three idempotency sources and is added to as the scan
    runs, so a module recurring later in the SAME run collapses into the first ticket.

    A repo is DRAINED only when its tip enumerated, EVERY blob at that tip read, and every module in
    it was either already ticketed or is in this run's `todo`. Anything less HOLDS the cap at that
    repo (mark_for()), so the mark can never land past it — including the case where a LATER repo
    drains cleanly, which is precisely the bug this shape exists to make unrepresentable.

    `extras` is [(module_sha, repo, path, blob_sha)] for every copy of an ALREADY-ticketed module
    met this scan. They are not re-filed (that is the whole point), but they ARE new knowledge about
    where that module lives, so a --file-tickets run records them — see ledger_record_locations()."""
    todo, scanned, skipped, dupes, extras = [], [], [], 0, []
    drained_idx = old_idx                                 # what earlier runs already proved
    cap_idx = len(repos)                                  # nothing proven un-drained yet
    by_key = {}
    for i in range(start_at, len(repos)):
        repo, name = repos[i], repo_name(repos[i])
        if len(todo) >= batch:
            break
        ref, how = resolve_tip(repo)
        if ref is None:
            skipped.append((name, how))
            drained_idx = max(drained_idx, i)             # an empty mirror IS fully drained
            continue
        blobs = tip_blobs(repo, ref, exts)
        if blobs is None:
            # The tip would not enumerate: this repo's modules are UNKNOWN, so it is not drained and
            # the mark is held before it — no later repo can lift that hold.
            skipped.append((name, "ls-tree FAILED at %s — repo HELD, mark kept before it" % ref))
            cap_idx = min(cap_idx, i - 1)
            bug_report("scan", RuntimeError("ls-tree failed at %s in %s" % (ref, name)),
                       "python3 %s --subset %s" % (SELF_FROM_ROOT, name),
                       "unreadable tip (corrupt/partial mirror?) — repo held, mark not advanced past "
                       "it; its modules stay un-enumerated until the tip reads")
            continue
        scanned.append((name, ref, how, len(blobs)))
        unread, filled = [], False
        for blob_sha, path in blobs:
            raw = blob_bytes(repo, blob_sha)
            if raw is None:
                unread.append(path)                       # a module we could not even identify
                continue
            sha, kind, text = module_identity(cw, raw, path)
            key = module_key(sha)
            if key in done:                               # already ticketed, or already in this batch
                dupes += 1
                if key in by_key:                         # a copy of something THIS run is filing:
                    _add_location(by_key[key], name, path, blob_sha, "tip")   # goes in its body
                else:                                     # a copy of something filed EARLIER:
                    extras.append((sha, name, path, blob_sha))                # goes in the ledger
                continue
            if len(todo) >= batch:
                filled = True
                break
            # `raw` is kept because the ticket body EMBEDS it (#346). It is bounded by --batch, and
            # only for the modules this run actually files: `raw` is dropped for every blob that
            # collapses as a duplicate, and no un-batched blob is ever held.
            m = {"sha": sha, "ident_kind": kind, "ext": os.path.splitext(path)[1].lower(),
                 "repo": name, "repo_idx": i, "path": path, "blob_sha": blob_sha, "ref": ref,
                 "ref_how": how, "size": len(raw), "text": text, "raw": raw, "locations": []}
            _add_location(m, name, path, blob_sha, "tip")
            # The index's places go through the SAME single writer as tip copies, so one of them
            # naming this module's canonical place (or a place a LATER repo's tip turns out to
            # carry live) resolves to 'tip' by _add_location's rule instead of masking it.
            for orepo, opath, ots in omni_locations(omni, blob_sha):
                _add_location(m, orepo, opath, blob_sha, "omni", ots)
            todo.append(m)
            by_key[key] = m
            done.add(key)
        if unread:
            # cat-file failed on a blob ls-tree listed. That module cannot be identified, so it cannot
            # be ticketed, so this repo is NOT drained — the same hold as a failed tip.
            skipped.append((name, "%d blob(s) UNREADABLE (cat-file) — repo HELD, mark kept before it"
                            % len(unread)))
            cap_idx = min(cap_idx, i - 1)
            bug_report("scan", RuntimeError("cat-file failed for %d blob(s) in %s: %s"
                                            % (len(unread), name, ", ".join(unread[:5]))),
                       "python3 %s --subset %s" % (SELF_FROM_ROOT, name),
                       "blob(s) listed by ls-tree but unreadable — repo held, mark not advanced past "
                       "it; those modules stay un-enumerated until they read")
        if filled:
            cap_idx = min(cap_idx, i - 1)                 # batch cut this repo short: NOT drained
            break
        if not unread:
            drained_idx = max(drained_idx, i)
    return todo, drained_idx, cap_idx, scanned, skipped, dupes, extras


def _add_location(m, repo, path, blob_sha, origin, ts=""):
    """Record ONE place this module lives. THE ONLY writer of m["locations"], so the tip-over-omni
    rule is applied in exactly one place and the body's two blocks are disjoint by construction.

    A location is keyed by the PLACE — (repo, path) — and `origin` says how the place was learned:
    'tip' (a scan enumerated it live at that repo's tip) or 'omni' (the blob index records it there
    historically). 'tip' is the STRONGER claim — a live source location the rewrite must satisfy,
    versus context — so meeting a real tip UPGRADES a place already recorded as 'omni' instead of
    being dropped as a duplicate of it. See TIP BEATS OMNI in the module docstring for why silently
    dropping it made the index destroy the very truth it was there to enrich. The reverse never
    applies: an index row for a place already proven live adds nothing, so it is ignored."""
    for l in m["locations"]:
        if l["repo"] == repo and l["path"] == path:
            if origin == "tip" and l["origin"] != "tip":
                # Same place, stronger evidence. `ts` is the index's `occ.ts` for a historical row
                # and means nothing for a live tip, so it is cleared to match every other tip.
                l["origin"], l["blob_sha"], l["ts"] = "tip", blob_sha or l["blob_sha"], ""
            return
    m["locations"].append({"repo": repo, "path": path, "blob_sha": blob_sha, "origin": origin,
                           "ts": ts})


# ── the per-module ticket ────────────────────────────────────────────────────────────────────────
def module_title(m):
    return ("Rewrite %s:%s as behavior-preserving, installable, control-config'd Python [%s]"
            % (m["repo"], m["path"], module_key(m["sha"])))


def locations_block(m):
    tip = [l for l in m["locations"] if l["origin"] == "tip"]
    omni = [l for l in m["locations"] if l["origin"] == "omni"]
    out = []
    # "read it, from anywhere" is what this block used to say above the git command, and it was not
    # true of the one reader that matters: the pair_loop worker is sandboxed to its own worktree and
    # cannot reach the forge at all (#346). The bytes now travel ON the ticket — see source_block() —
    # so what this command is FOR depends on whether they all fit, and the block says which. It must
    # not tell a worker it needs no forge access on the one kind of ticket where it does.
    if m["embed"]["truncated"]:
        why = ("  YOU DO NEED THIS COMMAND FOR THIS TICKET — and it is the only ticket kind that\n"
               "  does. This module is %d bytes, over the %d-byte embedding cap, so THE ORIGINAL\n"
               "  SOURCE block below carries a TRUNCATED excerpt (its first %d bytes) and the\n"
               "  complete source exists only here:\n" % (m["embed"]["total"], MAX_EMBED_BYTES,
                                                          m["embed"]["shown"]))
    else:
        why = ("  REFERENCE ONLY — you do NOT need this command. This module's bytes are embedded\n"
               "  COMPLETE in THE ORIGINAL SOURCE block below, and that is what the rewrite is based\n"
               "  on. For a reader who does have forge access:\n")
    out.append("CANONICAL SOURCE (the location this ticket is named for):\n"
               "  repo : %s\n  path : %s\n  ref  : %s (%s)\n  blob : %s (git blob sha1)\n"
               "%s"
               "    git --git-dir=%s/%s.git cat-file blob %s"
               % (m["repo"], m["path"], m["ref"], m["ref_how"], m["blob_sha"], why,
                  REMOTES, m["repo"], m["blob_sha"]))
    others = [l for l in tip if not (l["repo"] == m["repo"] and l["path"] == m["path"])]
    if others:
        shown = others[:MAX_BODY_LOCATIONS]
        out.append("THE SAME MODULE ALSO LIVES AT THESE FORGE TIPS — %d copy/copies. They SHARE THIS\n"
                   "ticket: this module is rewritten ONCE, and every location below is satisfied by\n"
                   "that one rewrite. Do not file a ticket per copy.\n%s%s"
                   % (len(others),
                      "\n".join("  %s:%s" % (l["repo"], l["path"]) for l in shown),
                      "" if len(others) <= MAX_BODY_LOCATIONS else
                      "\n  ... and %d more (the full list is in the ticketer's ledger `locations`\n"
                      "      table, keyed by module-sha %s)" % (len(others) - MAX_BODY_LOCATIONS, m["sha"])))
    else:
        out.append("THE SAME MODULE ALSO LIVES AT THESE FORGE TIPS: none — this module is unique to\n"
                   "%s among the repos scanned so far." % m["repo"])
    if omni:
        shown = omni[:MAX_BODY_LOCATIONS]
        # One line per DISTINCT (repo, path) the blob occurs at — occ holds one row per snapshot, so
        # a file recurring across snapshots would otherwise repeat identically. `occ.ts` is shown
        # verbatim and labelled: it is USUALLY a snapshot stamp (20260703T062230Z) but ~5k rows carry
        # a source label such as 'gitlab' instead, so it is not presented as if it were always a date.
        out.append("HISTORICAL OCCURRENCES of this exact blob — every OTHER DISTINCT {repo, path}\n"
                   "the omni-git index (`occ`, joined on the git blob sha1) records this\n"
                   "byte-identical file at, with the index's own `ts` for the first row of each.\n"
                   "Any place this run enumerated LIVE is listed under the forge tips above, not\n"
                   "here. Context for the rewrite, not extra work:\n%s%s"
                   % ("\n".join("  %s:%s   [occ.ts %s]" % (l["repo"], l["path"], l["ts"] or "(none)")
                                for l in shown),
                      "" if len(omni) <= MAX_BODY_LOCATIONS else
                      "\n  ... and %d more" % (len(omni) - MAX_BODY_LOCATIONS)))
    else:
        out.append("HISTORICAL OCCURRENCES (omni-git `occ`): none to add — either the index has no\n"
                   "row for this blob (it is newer than the index's last snapshot, or the index does\n"
                   "not cover its repo), or every place it records is already listed live above.")
    return "\n\n".join(out)


def identity_block(m):
    if m["ident_kind"] == "ast":
        how = ("AST-NORMALIZED — codebean's `_ast_norm` (#183), i.e.\n"
               "             ast.dump(ast.parse(ast.unparse(ast.parse(src)))).\n"
               "             Copies of this module that differ only in comments, blank lines,\n"
               "             quoting or spacing carry the SAME module-sha and are covered by THIS\n"
               "             ticket. A differing docstring is real content, so a module whose\n"
               "             docstring differs is a DIFFERENT module with its own ticket.")
    else:
        how = ("CONTENT SHA256 of the raw bytes. This blob is not parseable python (it is\n"
               "             non-Python source, python-2, or a truncated file), so no AST identity\n"
               "             is definable for it: only BYTE-IDENTICAL copies share this ticket. A\n"
               "             near-copy of this module elsewhere in the forge will get its own\n"
               "             ticket — a known and stated limit of this identity, not an oversight.")
    return ("MODULE KEY : %s\n"
            "             (the ticketer's idempotency marker — it lives in this ticket's TITLE. Do\n"
            "              not edit the title, or the module will be re-filed as a duplicate.)\n"
            "IDENTITY   : %s\n"
            "SIZE       : %d bytes\n"
            "EXTENSION  : %s"
            % (module_key(m["sha"]), how, m["size"], m["ext"] or "(none)"))


def behavior_block(m):
    cap = m["capture"]
    out = []
    if cap["callables"]:
        shown = cap["callables"][:MAX_BODY_CALLABLES]
        lines = []
        for ns, f in shown:
            sig = "%s%s(%s)%s" % ("async " if f["is_async"] else "",
                                  ("%s.%s" % (ns, f["name"])) if ns else f["name"],
                                  f["params"], (" -> %s" % f["returns"]) if f["returns"] else "")
            lines.append("  %s" % sig)
        out.append("THE CALLABLE SURFACE — every callable in the original, lowered with codebean's\n"
                   "`lower_node` (#183). The rewrite must present THIS surface (same names, same\n"
                   "parameters, same defaults) so callers of the original keep working:\n%s%s"
                   % ("\n".join(lines),
                      "" if len(cap["callables"]) <= MAX_BODY_CALLABLES else
                      "\n  ... and %d more callable(s) — read the source above for the full surface"
                      % (len(cap["callables"]) - MAX_BODY_CALLABLES)))
    elif not cap["note"]:
        out.append("THE CALLABLE SURFACE: this module defines no top-level function or method. Its\n"
                   "behavior is whatever its module-level code does — read the source above.")

    if cap["exemplars"]:
        shown = cap["exemplars"][:MAX_BODY_EXEMPLAR_FNS]
        blocks = []
        for spec in shown:
            ex = spec["exemplars"][:MAX_BODY_EXEMPLARS]
            # repr(), not json.dumps(): the rewrite is PYTHON, so an exemplar must read as python.
            # criteria_miner already guarantees every value round-trips through JSON, so each one is
            # a plain int/float/str/bool/None/list/dict whose repr IS a valid python literal — json
            # would render True as `true` and None as `null`, which is not what a pair would type.
            rows = ["      %s(%s) == %r" % (spec["name"], ", ".join(repr(a) for a in args), outv)
                    for args, outv in ex]
            more = ("\n      ... %d more exemplar(s) for this function — re-mine them with\n"
                    "          criteria_miner.mine() on the source above"
                    % (len(spec["exemplars"]) - len(ex))) if len(spec["exemplars"]) > len(ex) else ""
            blocks.append("  %s(%s) — %d exemplar(s) captured:\n%s%s"
                          % (spec["name"], spec["params"], len(spec["exemplars"]),
                             "\n".join(rows), more))
        omitted = ("\n  ... and %d more mined function(s) — re-mine the source above to see them."
                   % (len(cap["exemplars"]) - len(shown))) if len(cap["exemplars"]) > len(shown) else ""
        out.append("CAPTURED BEHAVIORAL EXEMPLARS — real (input, output) pairs mined from THIS module\n"
                   "with criteria_miner (#200's \"verified, not asserted\"), running the ORIGINAL as the\n"
                   "oracle. THE REWRITE MUST REPRODUCE EVERY PAIR BELOW, exactly:\n\n%s%s\n\n"
                   "  HONEST LIMIT (criteria_miner's own): these cover the SAMPLED inputs, probed\n"
                   "  around the function's own branch constants. They are a strong refactor-drift net,\n"
                   "  NOT a proof of total equivalence — so treat them as the FLOOR of this ticket's\n"
                   "  equivalence evidence and add the edge cases they miss (see ACCEPTANCE)."
                   % ("\n\n".join(blocks), omitted))
    else:
        why = cap["note"] or ("no function in this module is minable — criteria_miner mines only\n"
                              "  self-contained pure functions (it refuses anything that mentions a\n"
                              "  world-touching or non-deterministic name, plus methods and no-arg\n"
                              "  functions), and nothing here qualified")
        out.append("CAPTURED BEHAVIORAL EXEMPLARS: none. %s\n"
                   "  This does NOT weaken the ticket's bar — it MOVES the work: you must write the\n"
                   "  equivalence exemplars by hand from the original's behavior before rewriting, and\n"
                   "  they are what settles this ticket." % why)
    return "\n\n".join(out)


def supersedes_block(old_ids):
    """The preamble a REPLACEMENT unit carries (--patch-bodies only). It names what this ticket
    replaces and why, so the graft is legible from the replacement alone — the superseded unit's own
    journal and the `supersedes` edge say the same thing from the other side."""
    return (
        "THIS UNIT SUPERSEDES %s — it is the SAME module and the same work, re-filed to be\n"
        "SELF-CONTAINED. The superseded unit named its source only as a `git cat-file` command\n"
        "against the forge's bare repos, which the sandboxed pair_loop worker that executes these\n"
        "tickets cannot run, so it could not be done as filed (#%d; #259 is the proof). A ticket body\n"
        "is permanent in SQL (tg_tickets_immutable_identity, migrations/0029_ticket_authorization\n"
        ".sql:111-117), so that body could not be repaired — this ticket carries the fix instead, and\n"
        "the original is halted by a stop ticket rather than erased. Do the work HERE.\n"
        % (", ".join("#%d" % i for i in old_ids), FIX_TICKET))


def module_body(m, supersedes=None):
    """One rewrite unit's body. `supersedes` is a list of ticket ids this unit replaces (set only by
    --patch-bodies); a freshly-filed unit replaces nothing and carries no such preamble.

    The SOURCE goes above the behavior section on purpose: that section tells the reader to "read the
    source above" for the callables it had to elide and for re-mining exemplars, so the source has to
    BE above it. Before #346 there was no source in the body at all and those lines pointed at
    nothing a sandboxed worker could reach."""
    return (
        "%sRewrite ONE unique forge module as entirely new, behavior-preserving, installable,\n"
        "control-config'd Python, per the FORGE-wide refactor standard #%d (#std).\n"
        "\n"
        "This ticket covers ONE module — the one identified below — and nothing else. It was filed\n"
        "against the module's DEDUPLICATED identity, so if that module was copy-pasted across the\n"
        "forge, every copy is covered by this single ticket.\n"
        "\n"
        "%s\n"
        "\n"
        "%s\n"
        "\n"
        "%s\n"
        "\n"
        "%s\n"
        "\n"
        "THE STANDARD — #%d's four requirements, which this ticket exists to enforce. All four are\n"
        "the standard's own words; none is optional:\n"
        "  1. BEHAVIOR-PRESERVING, VERIFIED NOT ASSERTED — the deliverable is ENTIRELY NEW source\n"
        "     code (rewritten, not copied). It must reproduce the ORIGINAL's behavior, and the proof\n"
        "     is the exemplars above (captured via codebean lower_* #183 + criteria_miner\n"
        "     IO-exemplars, exactly as #%d specifies).\n"
        "  2. A PYTHON MODULE — regardless of the source language. This module's source is `%s`;\n"
        "     the rewrite is Python either way.\n"
        "  3. INSTALLABLE — a proper package: pyproject.toml, `pip install -e .` works, console\n"
        "     entry points where applicable. WRITE ONLY YOUR OWN MODULE FILE at\n"
        "     forge2/<repo>/<module>.py. Do NOT hand-author pyproject.toml or __init__.py: the\n"
        "     harness DERIVES them ADDITIVELY from the modules present (congruency/tools/\n"
        "     forge_package.py, #410 — the analogue of the tag-registry fix #281), so your unit never\n"
        "     conflicts with, or clobbers, a sibling module of the same forge2/<repo>/ package. A\n"
        "     package-level pyproject includes every .py in the directory, so your module installs\n"
        "     and imports as `<repo>.<module>` the moment it lands.\n"
        "  4. CONTROL-CONFIG'D — NO hardcoded paths or params. A JSON/registry config object drives\n"
        "     it (the install.json / registry.json idiom of this repo), and per note-for-claude a\n"
        "     tool that cannot see its config THROWS rather than guessing a default. Add ONLY your\n"
        "     own `forge2.<repo>.<module>` section to the package's registry.json (create the file if\n"
        "     it is absent); NEVER read, edit or drop a sibling module's section — the sections are\n"
        "     disjoint keys and stay additive that way.\n"
        "\n"
        "ACCEPTANCE (#%d's, per rewrite ticket) — this ticket settles when ALL of:\n"
        "  a. the new source reproduces every captured exemplar above, plus the edge cases you add\n"
        "     for what sampling cannot reach (paste the runs as evidence);\n"
        "  b. it presents the callable surface above, so existing callers keep working;\n"
        "  c. `pip install -e .` installs it clean from its own pyproject.toml;\n"
        "  d. it runs off a config object with ZERO hardcoded settings, and throws without one.\n"
        "\n"
        "Kind is `build` (a pair: coder + adversarial tester). This ticket hangs off #%d by a\n"
        "`spawned` edge, so a stop ticket aimed at #%d brakes every rewrite in this programme.\n"
        "\n"
        "Filed mechanically by %s under ticket #%d, from the forge bare repos at\n"
        "%s. Its original source is embedded above (#%d), so this ticket is complete on its own."
        % ("" if not supersedes else supersedes_block(supersedes) + "\n",
           STD_TICKET, identity_block(m), locations_block(m), source_block(m), behavior_block(m),
           STD_TICKET, STD_TICKET, m["ext"] or "(no extension)", STD_TICKET, STD_TICKET, STD_TICKET,
           SELF_FROM_ROOT, FACTORY_TICKET, REMOTES, FIX_TICKET))


def prepare(m, cw, cm, mine, supersedes=None):
    """Give one enumerated module everything a ticket needs: its embedded source, its captured
    behavior, its title and its body. THE ONE place a unit's body is composed, so a freshly-filed
    unit and a --patch-bodies replacement are the same artifact by construction and cannot drift
    apart — the replacement differs only by the `supersedes` preamble it is asked for."""
    m["embed"] = embed_source(m["raw"], m["sha"])
    m["capture"] = capture_behavior(cw, cm, m["text"], mine)
    m["title"] = module_title(m)
    m["body"] = module_body(m, supersedes)
    return m


def embed_tag(m):
    """The one-column summary of what a unit's source block holds, for the report."""
    e = m["embed"]
    return "src %s%s%dB" % ("b64 " if e["binary"] else "", "CUT " if e["truncated"] else "",
                            e["shown"])


def successor_body(chain_repos_left, batch, subset, gen, hwm):
    # The command must be the one that continues exactly this chain, so a subset run's successor
    # carries the same --subset. --gen PINS the run launched from THIS body to generation `gen`, so
    # it does not mistake this very ticket for a successor someone else already filed, and goes on to
    # spawn gen+1. It is belt and braces, NOT the mechanism: a run without the flag derives the same
    # generation from the queue (#245). The path is repo-root-relative on purpose: this ticket is
    # executed from the repo root (dispatch runs tools with cwd=ROOT).
    cmd = "python3 %s --file-tickets --batch %d --gen %d%s" % (
        SELF_FROM_ROOT, batch, gen, "" if not subset else " --subset %s" % subset)
    return (
        "Self-repopulating successor (the #196 pattern: append-only governance means a ticket cannot\n"
        "reopen, so the work perpetuates by spawning its successor).\n"
        "\n"
        "UNIT KEY        : %s\n"
        "CHAIN           : %s\n"
        "GENERATION      : %d\n"
        "HIGH-WATER-MARK : %s\n"
        "\n"
        "%d forge repo(s) past the high-water-mark are still un-enumerated. Run the ticketer again to\n"
        "file the next batch of at most %d unique module(s), resuming from the mark:\n"
        "\n"
        "    %s\n"
        "\n"
        "The `--gen %d` pins the run to THIS ticket's generation, so it will not mistake this very\n"
        "ticket for a successor someone else already filed; it then spawns generation %d, and the\n"
        "chain continues after this ticket settles.\n"
        "\n"
        "DROPPING THE FLAG DOES NOT KILL THE CHAIN (it used to — see #245). With no --gen the ticketer\n"
        "DERIVES its generation from the queue: the highest OPEN successor of this chain is normally\n"
        "this very ticket, so a plain `--file-tickets --batch %d` reaches the same conclusion and\n"
        "spawns the next generation anyway. Keep the flag regardless — it is what makes a run started\n"
        "from a STALE copy of this line (one the chain has already moved past, because a NEWER\n"
        "successor is open) correctly DECLINE, instead of adding a redundant successor.\n"
        "\n"
        "It is IDEMPOTENT: it re-files nothing already ticketed — a module already carrying a rewrite\n"
        "ticket is skipped by its module-sha, whether this chain filed it or another did. Run it with\n"
        "no --file-tickets first to see the next batch without writing anything. A stop ticket aimed\n"
        "at #%d (or at this ticket) is the brake for this chain.\n"
        "\n"
        "Filed mechanically by %s under ticket #%d."
        % (successor_key(subset, gen), chain_of(subset), gen, hwm or "(none — chain is fresh)",
           chain_repos_left, batch, cmd, gen, gen + 1, batch, FACTORY_TICKET, SELF_FROM_ROOT,
           FACTORY_TICKET))


# ── filing ───────────────────────────────────────────────────────────────────────────────────────
def file_ticket(base, key, title, body, kind="build"):
    """ticket.create -> ticket.kind, through the governed routes. Returns the new ticket id."""
    out = rest(base, "ticket.create", {"component": "forge-refactor", "severity": "normal",
                                       "patch": "", "title": title, "body": body}, key=key)
    tid = int(out.get("rowid") or 0)
    if not tid:
        raise RuntimeError("ticket.create returned no rowid for %r" % title)
    rest(base, "ticket.kind", {"id": tid, "kind": kind}, key=key)   # set-once; refused if kinded
    return tid


def file_batch(base, key, todo, names, drained_idx, cap_idx, batch, subset, gen, ever_hi, spawn,
               chain, scanned_n):
    """File this run's batch, record what is PROVEN drained in the ledger, then keep the chain alive.

    THE MARK IS CAPPED BY WHAT WAS FILED, NOT BY WHAT WAS SCANNED. The filing loop stops at the first
    module it cannot file (a route refusal, a server blip — near-certain at least once across a
    262-repo drain of unattended scheduled runs). Every module from that one on is UN-filed, and
    `todo` is in scan order, so the un-filed remainder starts at that module's repo: its `repo_idx`
    holds the cap, the mark stays BEHIND that repo, and the successor re-walks it and files what was
    missed. Without the cap a partial batch would advance the mark past modules that were never
    ticketed and orphan them permanently — with a success exit code and no signal."""
    con = ledger_rw()
    filed, failed = [], None
    for m in todo:
        try:
            tid = file_ticket(base, key, m["title"], m["body"])
            rest(base, "edge.record", {"parent_id": STD_TICKET, "child_id": tid, "kind": "spawned"},
                 key=key)
            ledger_record(con, m, tid)
        except Exception as e:                            # noqa: BLE001
            step("FAILED to file %s (%s:%s): %s" % (module_key(m["sha"]), m["repo"], m["path"], e))
            bug_report("file_batch", e, "python3 %s --file-tickets" % SELF_FROM_ROOT, e)
            failed = m
            break
        filed.append((tid, m))
        print("== filed == #%-5s %s" % (tid, m["title"]))
    if todo:
        step("%d rewrite ticket(s) filed, each edged `spawned` from #%d (#std)"
             % (len(filed), STD_TICKET))

    if failed is not None:
        # The mark may not pass the repo holding the first un-filed module. This is a HOLD, not a
        # loss: the repo is re-walked next run and its un-filed modules are filed then.
        cap_idx = min(cap_idx, failed["repo_idx"] - 1)
        # Says only what is true either way: the NEXT run of this chain re-walks the held repo,
        # whether that run comes from the successor spawned below or from a plain re-run. Promising
        # a successor here would contradict the total-failure branch, which spawns none.
        step("%d module(s) of this batch were NOT filed — repo %r is HELD and the mark is kept "
             "BEFORE it, so the next run of this chain re-walks it and files them. Nothing is "
             "orphaned; no --rescan is needed" % (len(todo) - len(filed), failed["repo"]))

    if todo and not filed:
        # Every attempt failed, so the route itself is down and a successor would need the SAME route
        # to be filed and to file anything. Spawning here would mint successors that can never file —
        # a runaway. The mark did not move (the cap sits before the first module's repo), so a re-run
        # once the route works picks up exactly this batch. Nothing is lost; nothing is stacked.
        con.close()
        step("nothing filed — no successor spawned and the high-water-mark did NOT move (every "
             "ticket.create failed; the chain resumes at this same batch on a re-run once the route "
             "works)")
        return filed

    new_hwm, _, repos_left = mark_for(names, drained_idx, cap_idx)
    ledger_mark(con, chain, new_hwm, scanned_n, len(filed))
    step("ledger: high-water-mark for chain %r is now %r — every repo through it is drained, %d "
         "repo(s) remain" % (chain, new_hwm or "(unset — no repo proven drained)", repos_left))
    con.close()

    if repos_left <= 0:
        step("every repo in chain %r is enumerated — the chain is drained; no successor spawned" % chain)
        return filed
    if not spawn:
        step("--no-spawn — successor withheld (%d repo(s) still un-enumerated)" % repos_left)
        return filed

    rows = queue_rows(base, key)
    if rows is None:
        # Unreadable queue AFTER filing. Spawn anyway: a duplicate successor is visible and harmless
        # (the next run files nothing new and stops), whereas a missing successor silently ends the
        # chain — the failure this whole generation scheme exists to prevent.
        step("ticket.queue unreadable after filing — spawning generation %d anyway (a stacked "
             "successor is recoverable; a dead chain is not)" % (max(ever_hi, gen) + 1))
    else:
        hi = max_open_generation([r.get("title") or "" for r in rows], subset)
        if hi > gen:
            step("chain %r already has an OPEN successor at generation %d (> this run's generation "
                 "%d) — not stacking another. %d repo(s) stay un-enumerated for IT to file; this run "
                 "did not end the chain" % (chain, hi, gen, repos_left))
            return filed
        ever_hi = max(ever_hi, hi)
        step("chain %r: highest open successor generation is %d, this run is generation %d — "
             "spawning generation %d" % (chain, hi, gen, max(ever_hi, gen) + 1))
    nxt = max(ever_hi, gen) + 1                           # monotonic: never re-mint a used number
    try:
        sid = file_ticket(base, key,
                          "Continue the forge refactor decomposition: %d repo(s) left [%s]"
                          % (repos_left, successor_key(subset, nxt)),
                          successor_body(repos_left, batch, subset, nxt, new_hwm))
        rest(base, "edge.record", {"parent_id": FACTORY_TICKET, "child_id": sid, "kind": "spawned"},
             key=key)
        print("== spawned == #%s successor generation %d (spawned edge from #%d) — %d repo(s) left"
              % (sid, nxt, FACTORY_TICKET, repos_left))
    except Exception as e:                                # noqa: BLE001
        step("successor spawn FAILED: %s" % e)
        bug_report("file_batch", e, "python3 %s --file-tickets" % SELF_FROM_ROOT, e)
    return filed


# ── --patch-bodies: the already-filed units are SUPERSEDED, not edited (#346) ────────────────────
# See "--patch-bodies" in the module docstring for why an edit is impossible (a body is immutable in
# SQL) and why ticket.progress alone would not unblock anything (the worker's prompt is title + body
# only). What follows is the schema's own remedy: stop + spawn + supersedes-edge = graft.
def unit_key(title):
    """The module-sha a rewrite unit's title carries, or None if this title is not a unit. A
    successor's key is `forge-rw:successor:<chain>:g<N>`, which is not 16 hex characters, so KEY_RE
    cannot match one: a chain marker is never mistaken for a unit."""
    m = KEY_RE.search(title or "")
    return m.group(1) if m else None


# The canonical block every unit's body carries (locations_block()), parsed back out. This is the
# FALLBACK for a lost ledger — and it cannot cause a wrong graft even if it mis-parses, because
# graft_module() re-derives the module's identity from the bytes it reads and refuses anything that
# is not the module named in the unit's own title.
CANON_REPO_RE = re.compile(r"^ {2}repo\s*:\s*(\S+)\s*$", re.M)
CANON_PATH_RE = re.compile(r"^ {2}path\s*:\s*(\S+)\s*$", re.M)
CANON_BLOB_RE = re.compile(r"^ {2}blob\s*:\s*([0-9a-f]{40})\b", re.M)
CANON_REF_RE = re.compile(r"^ {2}ref\s*:\s*(\S+)", re.M)


def _ledger_canon(sha):
    """The canonical location + the CONVERGED location cluster for a module-sha, from this tool's own
    ledger. None when the ledger is absent, unreadable, or does not know this module.

    The cluster is worth taking from here rather than from the superseded body: `locations` keeps
    completing as the drain proceeds (see THE CLUSTER KEEPS COMPLETING), so a replacement filed today
    can list copies that the original's body — a snapshot of one bounded batch — could not know."""
    if not os.path.isfile(LEDGER):
        return None
    try:
        con = sqlite3.connect("file:%s?immutable=1" % LEDGER, uri=True)
    except sqlite3.Error:
        return None
    try:
        row = con.execute("SELECT repo, path, blob_sha, ref, ext FROM modules WHERE module_sha=?",
                          (sha,)).fetchone()
        if not row or not (row[0] and row[1] and row[2]):
            return None
        locs = con.execute("SELECT repo, path, blob_sha, origin, ts FROM locations WHERE "
                           "module_sha=? ORDER BY origin<>'tip', repo, path", (sha,)).fetchall()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return {"repo": row[0], "path": row[1], "blob_sha": row[2], "ref": row[3] or "(unrecorded)",
            "ext": row[4] or "", "locations": locs, "from": "the ledger"}


def _body_canon(body):
    """The canonical location parsed out of the superseded unit's OWN body — the fallback used when
    the ledger is gone or never knew this module. No cluster comes with it: the body's copy list is
    prose, and inventing locations from prose is guessing. The replacement then lists only the
    canonical tip, which UNDERSTATES the cluster and never overstates it."""
    b = body or ""
    r, p, blob = CANON_REPO_RE.search(b), CANON_PATH_RE.search(b), CANON_BLOB_RE.search(b)
    if not (r and p and blob):
        return None
    ref = CANON_REF_RE.search(b)
    return {"repo": r.group(1), "path": p.group(1), "blob_sha": blob.group(1),
            "ref": ref.group(1) if ref else "(unrecorded)",
            "ext": os.path.splitext(p.group(1))[1].lower(), "locations": [],
            "from": "the superseded unit's own CANONICAL SOURCE block (no ledger row)"}


def graft_module(cw, sha, canon):
    """(module, None) or (None, reason) — read the canonical blob and PROVE it is this module.

    The proof is the point. A replacement embeds bytes that a worker will treat as the whole truth,
    so the bytes are re-identified with the SAME module_identity() every filing uses, and must equal
    the module-sha carried in the unit's own title. A blob that will not read, or that identifies as
    something else, yields a reason and no module — never a guess, and never a fabricated source."""
    repo_dir = os.path.join(REMOTES, canon["repo"] + ".git")
    if not os.path.isdir(repo_dir):
        return None, "forge repo %r is not at %s" % (canon["repo"], repo_dir)
    raw = blob_bytes(repo_dir, canon["blob_sha"])
    if raw is None:
        return None, ("canonical blob %s will not read from %s (cat-file failed)"
                      % (canon["blob_sha"][:12], canon["repo"]))
    got, kind, text = module_identity(cw, raw, canon["path"])
    if got != sha:
        return None, ("blob %s re-identifies as module %s, not the %s this unit is titled for"
                      % (canon["blob_sha"][:12], got, sha))
    m = {"sha": sha, "ident_kind": kind, "repo": canon["repo"], "path": canon["path"],
         "ext": canon["ext"] or os.path.splitext(canon["path"])[1].lower(),
         "blob_sha": canon["blob_sha"], "ref": canon["ref"],
         "ref_how": "as recorded when this module was first filed", "size": len(raw),
         "text": text, "raw": raw, "locations": []}
    # Through the SAME single writer the scan uses, so tip-beats-omni holds here too and the body's
    # two location blocks stay disjoint. The canonical place goes first and is a proven live tip.
    _add_location(m, m["repo"], m["path"], m["blob_sha"], "tip")
    for lrepo, lpath, lblob, lorigin, lts in canon["locations"]:
        _add_location(m, lrepo or "", lpath or "", lblob or "", lorigin or "omni", lts or "")
    return m, None


def plan_grafts(cw, cm, rows, base, key, mine, batch):
    """(plan, notes, unexamined) — what --patch-bodies would do, deciding nothing by guesswork.

    Units are grouped BY MODULE KEY, because the question "is this module's source already on an open
    ticket?" is asked per module, not per ticket. Per key:
      * every open unit whose body already carries the source -> nothing to do.
      * a sourceless unit with an ACTIVE STOP -> left alone. It is either already grafted, or halted
        by someone else; either way this tool does not act on a ticket that authorizes nothing.
      * a sourceless, unhalted unit WITH a self-contained sibling already open -> STOP-ONLY: a
        replacement exists (this is a graft that died between filing it and stopping the original),
        so the stop is finished and NO second replacement is filed.
      * a sourceless, unhalted unit with no such sibling -> GRAFT: file the replacement, then stop it.
    `unexamined` is how many further keys carry a sourceless open unit that --batch stopped this run
    from looking at; it is reported, never silently dropped, and a re-run continues from there."""
    by_key = {}
    for r in rows or []:
        k = unit_key(r.get("title"))
        if k:
            by_key.setdefault(k, []).append(r)
    keys = sorted(by_key)
    plan, notes, unexamined = [], [], 0
    for i, sha in enumerate(keys):
        if len(plan) >= batch:
            unexamined = len([k for k in keys[i:]
                              if any(not body_has_source(u.get("body")) for u in by_key[k])])
            break
        group = by_key[sha]
        good = [u for u in group if body_has_source(u.get("body"))]
        bad = [u for u in group if not body_has_source(u.get("body"))]
        if not bad:
            notes.append((sha, "self-contained already: %s carries the source"
                          % ", ".join("#%s" % u["id"] for u in good)))
            continue
        live = []
        for u in bad:
            n = active_stops(base, key, int(u["id"]))
            if n is None:
                notes.append((sha, "#%s: ticket.stops unreadable — leaving a unit whose brake state "
                                   "is unknown alone" % u["id"]))
            elif n > 0:
                notes.append((sha, "#%s: already halted (%d active stop(s)) — already grafted, or "
                                   "stopped by someone else" % (u["id"], n)))
            else:
                live.append(u)
        if not live:
            continue
        olds = [int(u["id"]) for u in live]
        if good:
            # No blob is read here: nothing is being embedded, so the module only has to be NAMED on
            # the stop ticket. Whatever names it — ledger or the unit's own body — is enough, and if
            # neither does, the stop points at the replacement, which certainly does.
            c = _ledger_canon(sha) or _body_canon(live[0].get("body")) or {}
            plan.append({"kind": "stop-only", "sha": sha, "olds": olds, "new": int(good[0]["id"]),
                         "m": None, "canon_from": "", "repo": c.get("repo", ""),
                         "path": c.get("path", "")})
            continue
        canon = _ledger_canon(sha) or _body_canon(live[0].get("body"))
        if canon is None:
            notes.append((sha, "#%d: no canonical source is recorded for this module — no ledger row, "
                               "and its body names no blob. Refusing to embed a source without "
                               "knowing which one it is" % olds[0]))
            continue
        m, why = graft_module(cw, sha, canon)
        if m is None:
            notes.append((sha, "#%d: %s — REFUSED to fabricate" % (olds[0], why)))
            bug_report("plan_grafts", RuntimeError(why),
                       "python3 %s --patch-bodies" % SELF_FROM_ROOT,
                       "the canonical blob of an already-filed unit could not be read and proven — "
                       "the unit is left exactly as it is, and nothing was filed for it")
            continue
        prepare(m, cw, cm, mine, supersedes=olds)
        plan.append({"kind": "graft", "sha": sha, "olds": olds, "new": None, "m": m,
                     "canon_from": canon["from"], "repo": m["repo"], "path": m["path"]})
    return plan, notes, unexamined


def stop_title(old_id):
    """The stop ticket's title. It deliberately carries NO `[forge-rw:<16 hex>]` marker: a module key
    in this title would make the stop look like a rewrite unit to KEY_RE and pollute the idempotency
    sources every filing run reads."""
    return "STOP: #%d — forge rewrite unit names a source its worker cannot read (#%d)" % (old_id,
                                                                                           FIX_TICKET)


def stop_body(old_id, new_id, sha, module_desc):
    return (
        "HALT #%d. It cannot be executed as filed, and its body cannot be repaired.\n"
        "\n"
        "MODULE        : %s\n"
        "MODULE KEY    : %s\n"
        "SUPERSEDED BY : #%d — the same module, the same requirements, plus that module's ORIGINAL\n"
        "                SOURCE embedded verbatim in the body. THE WORK HAPPENS THERE.\n"
        "\n"
        "WHY THIS UNIT IS HALTED. #%d names its module's source only as a\n"
        "`git --git-dir=<forge>/remotes/<repo>.git cat-file blob <sha>` command. The pair_loop WORKER\n"
        "that executes these units is spawned into the ticket's own congruency worktree and is\n"
        "SANDBOXED to it: the forge's bare repos are outside that directory, so it cannot run that\n"
        "command, and no cached copy exists. The unit blocks with \"canonical source unreadable,\n"
        "refused to fabricate\" — which is the worker behaving CORRECTLY, because #%d demands\n"
        "behavior PRESERVED and a source you cannot read cannot be preserved. The pilot #259 proved\n"
        "it end to end. Ticket #%d is the fix, and #%d above is this module's share of it.\n"
        "\n"
        "WHY A STOP AND NOT AN EDIT. A ticket's body is PERMANENT in SQL: tg_tickets_immutable_\n"
        "identity ABORTs any UPDATE that changes id/ts/title/body/component/kind\n"
        "(migrations/0029_ticket_authorization.sql:111-117), and no route edits a body. So #%d's body\n"
        "cannot be given the source it lacks. The schema's own remedy for exactly this case is a\n"
        "GRAFT — \"stop + spawn + supersedes-edge\" (0029_ticket_authorization.sql:8) — and that is\n"
        "what happened: #%d was filed carrying the source, a `supersedes` edge runs from #%d to #%d,\n"
        "and this ticket is the stop.\n"
        "\n"
        "NOTHING WAS DELETED. #%d, its journal and its edges stay on the record forever; it is halted,\n"
        "not erased. To release it, aim a `start` ticket at THIS ticket through a `starts` edge (a\n"
        "start is aimed at the stop ticket it releases — migrations/0030_pair_loop_routes.sql).\n"
        "Releasing it hands a sandboxed worker the same unreadable unit again, so prefer #%d.\n"
        "\n"
        "Filed mechanically by %s under ticket #%d."
        % (old_id, module_desc, module_key(sha), new_id, old_id, STD_TICKET, FIX_TICKET, new_id,
           old_id, new_id, new_id, old_id, old_id, new_id, SELF_FROM_ROOT, FIX_TICKET))


def progress_note(new_id, stop_id):
    """The attributed journal entry appended to the superseded unit. The journal is used here for
    what it IS good for — recording what happened, on the record, forever. It is NOT where the source
    goes: pair_loop builds a worker's birth prompt from a ticket's title and body only
    (pair_loop.py:990-992,1028,448), so a journal event never reaches the agent that needs bytes."""
    return ("superseded by #%d and halted by stop ticket #%d (ticket #%d). This unit named its "
            "module's source only as a `git cat-file` command against the forge's bare repos, which "
            "the sandboxed pair_loop worker that executes it cannot run — it blocks with \"canonical "
            "source unreadable, refused to fabricate\" (proven by the pilot, #259). A ticket body is "
            "permanent in SQL (tg_tickets_immutable_identity, migrations/0029_ticket_authorization"
            ".sql:111-117), so this unit was superseded rather than edited: #%d carries the identical "
            "requirements plus the module's original source embedded verbatim, and needs no forge "
            "access. Nothing here is deleted — this ticket and its journal stay on the record. Filed "
            "mechanically by %s." % (new_id, stop_id, FIX_TICKET, new_id, SELF_FROM_ROOT))


def register_ticketer(base, key):
    """Register the agent this tool journals as, before it appends to any ticket's journal.

    agent.register is INSERT OR REPLACE (migrations/0001_agents.sql:19-25), so re-registering every
    run is the idempotent, intended thing — pair_loop re-registers its git steward the same way on
    every round. This agent is REGISTERED but never ticket.assign'd; see TICKETER_AGENT."""
    rest(base, "agent.register", {
        "agent_id": TICKETER_AGENT, "parent": "forge_refactor_ticketer",
        "tools": json.dumps(["git ls-tree", "git cat-file", "rest.php governed routes"]),
        "prompt": "You are %s, the MECHANICAL forge rewrite-ticket factory (%s, authorized by #%d "
                  "under the refactor standard #%d). You enumerate the forge's unique modules and "
                  "file one self-contained rewrite unit per module, each carrying that module's "
                  "original source verbatim so the sandboxed worker that executes it needs no forge "
                  "access (#%d). You file tickets and journal what you filed; you never author or "
                  "judge work product, and you are never assigned to a ticket."
                  % (TICKETER_AGENT, SELF_FROM_ROOT, FACTORY_TICKET, STD_TICKET, FIX_TICKET)},
        key=key)


def has_edge(base, key, parent, child, kind):
    """True when this exact parent->child edge of `kind` is already recorded. edge.record has no
    uniqueness (0012_ticket_edges.sql), so this is what keeps a RESUMED graft — one whose replacement
    was filed before an earlier run died — from recording its `supersedes` edge a second time. An
    unreadable route answers False: a duplicate edge is untidy, a missing one loses the provenance."""
    try:
        rows = rest(base, "children.list", {"parent_id": parent}, method="GET", key=key).get("rows", [])
    except Exception:                                     # noqa: BLE001
        return False
    return any(int(r.get("child_id") or 0) == child and (r.get("kind") or "") == kind for r in rows)


def ledger_graft(con, sha, old, new, stop, reason):
    """Record ONE supersession — AFTER all three tickets exist, so the ledger can never claim a graft
    that did not happen. Append-only: `modules.ticket_id` still names the ticket the filing run really
    created, and nothing here is ever updated or deleted."""
    con.execute("INSERT INTO grafts (ts, module_sha, old_ticket, new_ticket, stop_ticket, reason) "
                "VALUES (?,?,?,?,?,?)", (time.time(), sha, old, new, stop, reason))
    con.commit()


def do_grafts(base, key, plan):
    """Execute the plan: per module, a self-contained replacement (unless one is already open), then
    per superseded unit a `supersedes` edge, a `stop` ticket, a `stops` edge and a journal note.

    ON THE FIRST FAILURE IT STOPS, the way file_batch() does, and for the same reason: a route that
    just refused will refuse the next call too, and 30 more attempts buy 30 more bug reports and no
    tickets. Nothing is lost by stopping — every step of this is idempotent, so a re-run once the
    route works resumes exactly here, including finishing a graft that died mid-way (the plan's
    stop-only path)."""
    con = ledger_rw()
    register_ticketer(base, key)
    filed = stopped = 0
    for e in plan:
        try:
            if e["kind"] == "graft":
                m = e["m"]
                new_id = file_ticket(base, key, m["title"], m["body"])
                rest(base, "edge.record", {"parent_id": STD_TICKET, "child_id": new_id,
                                           "kind": "spawned"}, key=key)
                filed += 1
                print("== filed == #%-5s %s  [%s, source from %s]"
                      % (new_id, m["title"], embed_tag(m), e["canon_from"]))
            else:
                new_id = e["new"]
                step("module %s already has a self-contained OPEN unit (#%d) — a graft that did not "
                     "finish. Filing no second replacement; completing its stop(s) only"
                     % (module_key(e["sha"]), new_id))
            for old in e["olds"]:
                if not has_edge(base, key, new_id, old, "supersedes"):
                    rest(base, "edge.record", {"parent_id": new_id, "child_id": old,
                                               "kind": "supersedes"}, key=key)
                sid = file_ticket(base, key, stop_title(old),
                                  stop_body(old, new_id, e["sha"],
                                            "%s:%s" % (e["repo"], e["path"]) if e["repo"] else
                                            "the module keyed %s — named on #%d"
                                            % (module_key(e["sha"]), new_id)),
                                  kind="stop")
                rest(base, "edge.record", {"parent_id": sid, "child_id": old, "kind": "stops"},
                     key=key)
                rest(base, "ticket.progress", {"ticket_id": old, "agent_id": TICKETER_AGENT,
                                               "note": progress_note(new_id, sid)}, key=key)
                ledger_graft(con, e["sha"], old, new_id, sid,
                             "body carried no embedded source; a body is immutable in SQL, so the "
                             "unit was superseded (#%d)" % FIX_TICKET)
                stopped += 1
                print("== superseded == #%-5s -> #%-5s (stop #%s, journaled)" % (old, new_id, sid))
        except Exception as exc:                          # noqa: BLE001
            step("FAILED while grafting %s: %s — stopping here. Nothing is lost: every step is "
                 "idempotent, so a re-run once the route works resumes at this module and finishes "
                 "any half-done graft" % (module_key(e["sha"]), exc))
            bug_report("do_grafts", exc,
                       "python3 %s --patch-bodies --file-tickets" % SELF_FROM_ROOT, exc)
            break
    con.close()
    step("%d self-contained replacement(s) filed (each edged `spawned` from #%d); %d superseded "
         "unit(s) halted and journaled" % (filed, STD_TICKET, stopped))
    return filed, stopped


def report_grafts(plan, notes, unexamined, units, batch):
    print("== forge unit source back-fill (--patch-bodies) ==  %d open forge rewrite unit(s) in the "
          "queue" % units)
    if notes:
        print("\n-- units needing nothing, or deliberately left alone (reported, never silently "
              "dropped)")
        for sha, why in notes:
            print("   %s  %s" % (module_key(sha), why))
    print("\n-- planned supersessions (%d; --batch %d)" % (len(plan), batch))
    for e in plan:
        olds = ", ".join("#%d" % o for o in e["olds"])
        if e["kind"] == "graft":
            m = e["m"]
            print("   %s  %-14s %-22s %s:%s"
                  % (module_key(e["sha"]), embed_tag(m),
                     "%s -> new unit" % olds, m["repo"], m["path"]))
        else:
            print("   %s  %-14s %-22s %s:%s  (replacement is already open — only the stop is left)"
                  % (module_key(e["sha"]), "(no re-file)", "%s -> #%d" % (olds, e["new"]),
                     e["repo"] or "?", e["path"] or "?"))
    if unexamined:
        print("\n   ... and at most %d further module key(s) with a sourceless open unit were NOT "
              "examined\n       this run (--batch %d). Nothing is lost: re-run to continue — this "
              "mode is idempotent." % (unexamined, batch))
    print("\n== totals == %d unit(s) would be superseded by %d self-contained replacement(s); %d "
          "module key(s) need nothing" % (sum(len(e["olds"]) for e in plan),
                                          len([e for e in plan if e["kind"] == "graft"]), len(notes)))


def patch_bodies(a, cw, cm, key, rows):
    """--patch-bodies, end to end: plan, report, and (only with --file-tickets) graft."""
    units = len([r for r in rows if unit_key(r.get("title"))])
    plan, notes, unexamined = plan_grafts(cw, cm, rows, a.base, key, not a.no_exemplars, a.batch)
    report_grafts(plan, notes, unexamined, units, a.batch)

    if a.json:
        with open(a.json, "w") as fh:
            json.dump([{"action": e["kind"], "key": module_key(e["sha"]), "module_sha": e["sha"],
                        "supersedes": e["olds"], "replacement_already_open": e["new"],
                        "canonical_source_from": e["canon_from"],
                        "repo": e["repo"], "path": e["path"],
                        "blob_sha": (e["m"] or {}).get("blob_sha", ""),
                        "size": (e["m"] or {}).get("size", 0),
                        # Same shape the scan's --json uses, so ONE check verifies either: extract
                        # between the markers, decode if base64, diff against `cat-file blob`.
                        "source_embedded": bool(e["m"]),
                        "source_truncated": bool(e["m"] and e["m"]["embed"]["truncated"]),
                        "source_base64": bool(e["m"] and e["m"]["embed"]["binary"]),
                        "source_bytes_embedded": (e["m"] or {}).get("embed", {}).get("shown", 0),
                        "source_begin_marker": (e["m"] or {}).get("embed", {}).get("begin", ""),
                        "source_end_marker": (e["m"] or {}).get("embed", {}).get("end", ""),
                        "title": (e["m"] or {}).get("title", ""),
                        "body": (e["m"] or {}).get("body", "")} for e in plan], fh, indent=2)
        print("== json == %s" % a.json)

    if not a.file_tickets:
        print("\n== dry == reported only; no ticket was filed, nothing was stopped, no journal entry "
              "was appended and no db was written%s. Add --file-tickets to execute the %d "
              "supersession(s) above."
              % (" (only the --json dump at %s was created)" % a.json if a.json
                 else ", and no file was created", len(plan)))
        return 0
    if not key:
        die("no CONGRUENCY_API_KEY (../.secrets/ats.env or the environment) — cannot file")
    if not plan:
        print("\n== nothing to patch == every open forge rewrite unit either already carries its "
              "original source or is already halted; filed 0, stopped 0.")
        return 0
    print()
    do_grafts(a.base, key, plan)
    return 0


# ── report ───────────────────────────────────────────────────────────────────────────────────────
def report(todo, scanned, skipped, repos, chain, batch, hwm, start_at, dupes, repos_left):
    print("== forge refactor ticketer ==  chain %r: %d repo(s) in scope, resuming at #%d of them "
          "(high-water-mark: %s)" % (chain, len(repos), start_at + 1, hwm or "none — fresh chain"))
    # Repo names run to 55+ chars in this forge, so every padded column comes FIRST and the
    # unbounded name/path comes LAST — a table that only lines up for short names is worse than none.
    if scanned:
        print("\n-- repos enumerated this run")
        for name, ref, how, n in scanned:
            print("   %4d source file(s)  %-23s %-18s %s" % (n, how, ref, name))
    if skipped:
        print("\n-- repos SKIPPED this run (reported, never silently dropped). A repo marked HELD is "
              "NOT\n   drained: the mark is kept before it and the next run of this chain re-walks it.")
        for name, why in skipped:
            print("   %-52s %s" % (why, name))
    print("\n-- unique modules this run would file (%d; --batch %d). `src` is what each ticket's\n"
          "   EMBEDDED SOURCE block carries (#%d): the module's own bytes, so its worker needs no\n"
          "   forge access. `CUT` marks a blob over the %d-byte cap, embedded truncated."
          % (len(todo), batch, FIX_TICKET, MAX_EMBED_BYTES))
    for m in todo:
        copies = len([l for l in m["locations"] if l["origin"] == "tip"])
        print("   [%-6s] %s  %-16s %-28s %s:%s"
              % (m["ident_kind"], module_key(m["sha"]), embed_tag(m),
                 "" if copies < 2 else "(+%d copy/copies -> 1 ticket)" % (copies - 1),
                 m["repo"], m["path"]))
    # `repos_left` here is the SCAN's projection — what would be left if every module below files.
    # It is not the last word: a module that fails to file holds its repo too, so file_batch() prints
    # the mark and the repo count it actually recorded. Saying "would leave" keeps this line from
    # contradicting that one on a run where filing goes wrong.
    cut = [m for m in todo if m["embed"]["truncated"]]
    print("\n== totals == scanned %d repo(s) -> %d unique un-ticketed module(s) to file; %d file(s) "
          "collapsed into an existing/earlier ticket by module-sha (the dedup); %d ticket(s) embed "
          "their module's COMPLETE source and %d embed a TRUNCATED excerpt (over the %d-byte cap, so "
          "those DO still need forge access and say so); filing them all would leave %d repo(s) for "
          "the successor" % (len(scanned), len(todo), dupes, len(todo) - len(cut), len(cut),
                             MAX_EMBED_BYTES, repos_left))


def main():
    global LEDGER, REMOTES, CODEBEAN
    ap = argparse.ArgumentParser(
        description="Enumerate every UNIQUE module in the forge's bare repos and file one "
                    "behavior-preserving rewrite build-ticket per unique module, per the refactor "
                    "standard #%d (#201). Reports and writes NOTHING unless --file-tickets."
                    % STD_TICKET)
    ap.add_argument("--file-tickets", action="store_true",
                    help="actually file one build ticket per un-ticketed unique module, through "
                         "rest.php's governed ticket.create/ticket.kind/edge.record routes, and "
                         "record them in the ledger (default: report only, no writes, no files)")
    ap.add_argument("--patch-bodies", action="store_true",
                    help="BACK-FILL the original source into the forge units ALREADY FILED without "
                         "it (#%d). It does NOT edit a body — it cannot: a ticket body is immutable "
                         "in SQL (tg_tickets_immutable_identity, migrations/"
                         "0029_ticket_authorization.sql:111-117). Per sourceless OPEN unit it does "
                         "the graft the schema itself prescribes (0029:8): files a self-contained "
                         "REPLACEMENT carrying the module's source, edges it `supersedes` -> the "
                         "original, aims a `stop` ticket at the original, and journals why on it "
                         "(ticket.progress). Idempotent: a unit already carrying its source, or "
                         "already halted, is left alone. Reports only unless --file-tickets; honors "
                         "--batch, --no-exemplars and --json; refuses --subset (this mode reads the "
                         "ticket QUEUE, which is not scoped by forge repo)" % FIX_TICKET)
    ap.add_argument("--batch", type=int, default=25, metavar="N",
                    help="file at most N module tickets this run, then spawn a successor for the "
                         "rest (the #196 self-repopulating pattern; default 25). Under "
                         "--patch-bodies it bounds the supersessions per run instead, and no "
                         "successor is involved: re-run to continue")
    ap.add_argument("--subset", default="", metavar="SPEC",
                    help="only forge repos whose NAME contains SPEC — the acceptance run of #201. It "
                         "also names the drain chain, so a subset drain and a full drain never block "
                         "each other's successors or share a high-water-mark")
    ap.add_argument("--rescan", action="store_true",
                    help="re-walk from the FIRST repo in scope instead of resuming at the "
                         "high-water-mark. The honest idempotency proof: a re-run with --rescan "
                         "still files ZERO, because the module-sha ledger — not the bookmark — is "
                         "what suppresses duplicates. The mark is kept unless the re-walk disproves "
                         "it (meets a repo that is not drained after all), so a rescan cannot throw "
                         "away the drain progress of the runs before it")
    ap.add_argument("--no-exemplars", action="store_true",
                    help="skip criteria_miner IO-exemplar mining (which execs only the pure "
                         "functions criteria_miner itself certifies inert). Tickets are still filed, "
                         "carrying the codebean callable surface and saying exemplars were skipped")
    ap.add_argument("--gen", type=int, default=None, metavar="N",
                    help="OVERRIDE this run's successor GENERATION. By default it is DERIVED from "
                         "the live queue — the highest OPEN successor of this chain (0 if none is "
                         "open, i.e. a fresh chain) — because that successor's ticket is what a pair "
                         "runs this tool from. A run spawns unless an OPEN successor of a HIGHER "
                         "generation already exists, so a successor's own run never mistakes itself "
                         "for its replacement and the chain does not stall after one batch (#245). "
                         "Pass this only to deliberately act as an OLDER generation")
    ap.add_argument("--no-spawn", action="store_true", help="file the batch but spawn no successor")
    ap.add_argument("--ext", default="", metavar="LIST",
                    help="comma-separated source extensions to treat as modules (default: %s)"
                         % ",".join(SOURCE_EXT))
    ap.add_argument("--base", default=BASE, metavar="URL",
                    help="the congruency server carrying the governed routes (default %s)" % BASE)
    ap.add_argument("--db", default=CONG_DB, metavar="PATH",
                    help="state db, read immutable=1 for already-filed titles (default %s)" % CONG_DB)
    ap.add_argument("--ledger", default=LEDGER, metavar="PATH",
                    help="this tool's own module-sha ledger (default %s)" % LEDGER)
    ap.add_argument("--remotes", default=REMOTES, metavar="PATH",
                    help="the forge's bare repo store (default %s)" % REMOTES)
    ap.add_argument("--codebean", default=CODEBEAN, metavar="PATH",
                    help="codebean package dir, for _ast_norm/lower_node/criteria_miner (default %s)"
                         % CODEBEAN)
    ap.add_argument("--json", metavar="PATH", help="also dump this run's enumeration as JSON to PATH")
    a = ap.parse_args()

    LEDGER, REMOTES, CODEBEAN = a.ledger, a.remotes, a.codebean

    if a.batch < 1:
        die("--batch must be 1 or more (got %d)" % a.batch)
    if a.gen is not None and a.gen < 0:
        die("--gen must be 0 or more (got %d)" % a.gen)
    if a.patch_bodies and a.subset:
        # Refused rather than ignored: --subset LOOKS like it scopes the work, and here it cannot.
        # --patch-bodies works from the ticket QUEUE, whose units are keyed by module-sha and carry
        # no forge-repo scope, so honouring it would mean silently doing nothing or silently doing
        # everything. Both are worse than one line.
        die("--subset selects forge repos to SCAN; --patch-bodies works from the ticket queue "
            "instead, which is not scoped by forge repo — re-run --patch-bodies without --subset")
    exts = tuple(e if e.startswith(".") else "." + e
                 for e in (x.strip().lower() for x in a.ext.split(",")) if e) or SOURCE_EXT

    key = api_key()
    chain = chain_of(a.subset)

    # ── brake, FIRST — before anything is enumerated or filed (pair_loop.py:1001-1006) ──────────
    rows = queue_rows(a.base, key)
    if rows is None and a.file_tickets:
        die("cannot read the live ticket.queue at %s — refusing to file, to not risk duplicates (is "
            "the server up? try --base URL)" % a.base)
    if rows is not None:
        if brake(a.base, key, FACTORY_TICKET, "this factory"):
            return 3
        sid = successor_ticket_id(rows, a.subset)
        if sid and brake(a.base, key, int(sid), "chain %r's open successor" % chain):
            return 3
    else:
        step("live queue unreachable — reporting only; the brake could not be checked, and nothing "
             "will be written")

    cw, cm = load_codebean()
    step("codebean loaded: _ast_norm + lower_node (#183)%s"
         % ("" if a.no_exemplars else ", criteria_miner.mine (#200 exemplars)"))

    # ── --patch-bodies: a distinct mode. It reads the ticket QUEUE, not the forge's repo list, so it
    #    never walks the forge, never touches the high-water-mark and never spawns a successor. It
    #    still reads the forge — one cat-file per module it grafts, to embed the real bytes.
    if a.patch_bodies:
        if rows is None:
            die("cannot read the live ticket.queue at %s — --patch-bodies works FROM the queue (is "
                "the server up? try --base URL)" % a.base)
        return patch_bodies(a, cw, cm, key, rows)

    repos = forge_repos(a.subset)
    if not repos:
        die("--subset %r matched no forge repo under %s (it matches a repo NAME substring, e.g. "
            "'audio_tagger')" % (a.subset, REMOTES))

    # ── the three idempotency sources (see IDEMPOTENCY in the module docstring) ─────────────────
    done, hwm = ledger_keys_and_hwm(chain)
    step("%d module-sha(s) already ticketed per the ledger%s" % (len(done), " at " + LEDGER))
    titles = db_titles(a.db)
    if titles is None:
        step("state db not readable at %s — idempotency rests on the ledger + the live queue "
             "(both cover every ticket this factory has filed)" % a.db)
        titles = []
    else:
        from_db = keys_from_titles(titles)
        done |= from_db
        step("%d module key(s) in the state db titles (ALL statuses)" % len(from_db))
    open_hi = max_open_generation([r.get("title") or "" for r in rows or []], a.subset)
    gen = this_generation(a.gen, open_hi)
    ever_hi = max_generation_ever(titles + [r.get("title") or "" for r in rows or []], a.subset)
    if rows is not None:
        live = keys_from_titles([r.get("title") or "" for r in rows])
        done |= live
        step("%d module key(s) in the live queue (OPEN/REQUESTED); chain %r highest open successor "
             "generation = %d, this run is generation %d (%s)"
             % (len(live), chain, open_hi, gen,
                "--gen override" if a.gen is not None else "derived from the queue"))

    # ── resume point ────────────────────────────────────────────────────────────────────────────
    names = [repo_name(r) for r in repos]
    old_idx = names.index(hwm) if (hwm and hwm in names) else -1
    start_at = old_idx + 1
    if a.rescan:
        start_at = 0
        step("--rescan: re-walking from repo 1. Duplicates are suppressed by the module-sha union, "
             "not by the bookmark. The mark %r is KEPT unless this re-walk DISPROVES it by meeting a "
             "repo that is not drained after all — a claim about repos this bounded run never "
             "reaches is not evidence against them" % (hwm or "(none)"))
    elif hwm and hwm not in names:
        step("high-water-mark %r is not among the %d repo(s) in scope (renamed or removed) — "
             "restarting this chain from repo 1; the module-sha union still suppresses duplicates"
             % (hwm, len(repos)))

    try:
        omni = connect_ro(OMNI_DB, "omni-git index")
        step("omni-git index open (read-only, immutable=1): %s" % OMNI_DB)
    except Fault as e:
        omni = None
        step("%s — continuing without historical occurrences (the index is enrichment; tip "
             "locations are unaffected)" % e)

    todo, drained_idx, cap_idx, scanned, skipped, dupes, extras = scan(
        cw, omni, repos, start_at, exts, a.batch, done, old_idx)
    # What this run WOULD mark if every module in `todo` files. A repo is "left" when it is at or past
    # that mark: the mark lands only past a proven-drained repo, so a repo the batch cut short, or one
    # this run could not read, is counted as left and finished next run. file_batch() re-resolves the
    # same rule with the filing outcome folded in — a module that fails to file holds the mark too.
    new_hwm, _, repos_left = mark_for(names, drained_idx, cap_idx)

    for m in todo:
        prepare(m, cw, cm, not a.no_exemplars)
    step("captured behavior for %d module(s): %d with mined IO exemplars, %d with a callable "
         "surface only" % (len(todo), len([m for m in todo if m["capture"]["exemplars"]]),
                           len([m for m in todo if not m["capture"]["exemplars"]])))
    step("embedded source for %d module(s): %d complete, %d truncated at the %d-byte cap, %d "
         "base64'd (not UTF-8 text). Every ticket below is readable by a worker with NO forge "
         "access%s (#%d)"
         % (len(todo), len([m for m in todo if not m["embed"]["truncated"]]),
            len([m for m in todo if m["embed"]["truncated"]]), MAX_EMBED_BYTES,
            len([m for m in todo if m["embed"]["binary"]]),
            "" if not any(m["embed"]["truncated"] for m in todo) else
            " EXCEPT the truncated one(s), which say so on their own face", FIX_TICKET))

    report(todo, scanned, skipped, repos, chain, a.batch, hwm, start_at, dupes, repos_left)

    if a.json:
        with open(a.json, "w") as fh:
            json.dump([{"key": module_key(m["sha"]), "module_sha": m["sha"],
                        "ident_kind": m["ident_kind"], "repo": m["repo"], "path": m["path"],
                        "ref": m["ref"], "blob_sha": m["blob_sha"], "size": m["size"],
                        # The #346 acceptance is checkable straight off this dump: "body" holds the
                        # module's own bytes between the markers, and these say which of the four
                        # embedding cases produced them.
                        "source_embedded": True,
                        "source_truncated": m["embed"]["truncated"],
                        "source_base64": m["embed"]["binary"],
                        "source_bytes_embedded": m["embed"]["shown"],
                        "source_begin_marker": m["embed"]["begin"],
                        "source_end_marker": m["embed"]["end"],
                        "locations": m["locations"], "title": m["title"], "body": m["body"],
                        "callables": m["capture"]["callables"],
                        "exemplars": m["capture"]["exemplars"]} for m in todo], fh, indent=2)
        print("== json == %s" % a.json)

    if not a.file_tickets:
        # Says what THIS run did, not what the flagless run does: --json just wrote a file, and a
        # blanket "no file was created" here would be contradicted by the "== json ==" line directly
        # above it.
        print("\n== dry == reported only; no ticket was filed and no db was written%s. Add "
              "--file-tickets to file the %d rewrite ticket(s) above."
              % (" (only the --json dump at %s was created)" % a.json if a.json
                 else ", and no file was created", len(todo)))
        return 0
    if not key:
        die("no CONGRUENCY_API_KEY (../.secrets/ats.env or the environment) — cannot file")

    # New knowledge about where an ALREADY-ticketed module lives is worth recording even on a run
    # that files nothing: it is what completes the dedup cluster as the forge drains.
    if extras:
        lcon = ledger_rw()
        added = ledger_record_locations(lcon, extras)
        lcon.close()
        step("ledger: %d new copy location(s) of already-ticketed module(s) recorded (%d copy/copies "
             "seen, the rest already known)" % (added, len(extras)))

    if not todo:
        print("\n== nothing new == every unique module enumerated is already ticketed; filed 0.%s"
              % ("" if repos_left <= 0 else
                 "\n   (%d repo(s) remain un-drained past the high-water-mark %r — this run found "
                 "nothing new\n    in the repos it walked, and any repo it could not read is HELD "
                 "below the mark. A\n    successor is spawned below to walk them; nothing is "
                 "orphaned.)" % (repos_left, new_hwm or "(none)")))
        if repos_left <= 0:
            return 0                                      # chain drained: no mark to move, none to spawn

    print()
    # Called even with an EMPTY batch when repos remain: a repo HELD by an unreadable tip or blob
    # leaves work behind while filing nothing, and the chain must still spawn a successor to revisit
    # it. Returning early there would end the drain with those modules un-ticketed — the same silent
    # loss as an over-advanced mark, wearing a success message.
    file_batch(a.base, key, todo, names, drained_idx, cap_idx, a.batch, a.subset, gen, ever_hi,
               not a.no_spawn, chain, len(scanned))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as f:
        die(str(f))
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("forge_refactor_ticketer: interrupted")
        sys.exit(2)
    except Exception as exc:                              # noqa: BLE001
        bug_report("main", exc, " ".join([sys.executable, os.path.abspath(__file__)] + sys.argv[1:]), exc)
        print("forge_refactor_ticketer: unexpected failure: %s" % exc)
        sys.exit(2)
