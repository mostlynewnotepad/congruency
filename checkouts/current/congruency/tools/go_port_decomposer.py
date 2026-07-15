#!/usr/bin/env python3
"""go_port_decomposer.py — enumerate EVERY congruency-go port unit and file ONE small,
equivalence-gated build ticket per unit (the factory pattern of #201, applied to #230).

WHY (the operator's methodology correction on #230): dozens of SMALL iterative builds beat a few
big tournaments. congruency is ~150 portable units, and a "port the whole layer" tournament fails
at that size. So nothing here ports a layer. This tool enumerates every unit and files ONE build
ticket per unit, each SMALL (one unit, nothing else), ITERATIVE (build -> equivalence-diff vs the
PHP original for THAT unit -> iterate until identical), and individually settleable by a pair.
Tournament/competition is deliberately NOT the default: a unit ticket is a plain `build` kind (a
pair: coder + adversarial tester), and only a unit that genuinely benefits should be escalated.

TERMS (defined here because the artifact stands alone):
  unit      — the smallest independently portable + independently diffable piece of congruency:
              one api_route, one page, one tag, one rest.php helper, one ?api CRUD verb, one boot
              script, one render-engine class.
  unit key  — a stable identifier, e.g. `go-port:db:route:agent.roster`, embedded in the ticket
              title in square brackets. It IS the idempotency ledger: no side table is created,
              the key in the title is the record that the unit is already ticketed.
  bucket    — the dependency layer a unit belongs to, from #230's ordering:
                db     (#224) — pure-Go sqlite over the same schema + the api_routes engine
                server (#225) — net/http path surface + rest dispatch + ?api CRUD + auth + the
                                ?page= boot and render chain
                tags   (#226) — the tag engine + invocators rendering identical HTML
              Units are EMITTED db -> server -> tags so dependencies are filed first.
  gate      — the equivalence-diff that settles a unit ticket. Every gate in this tool exercises
              THE UNIT IT GATES; see "UNIT-SCOPED GATES" below.

WHAT IT ENUMERATES (every source is LIVE — nothing is a hardcoded inventory):
  routes  — every row of `api_routes` in the state db (62 today). Each carries its real
            method/auth/params/sql into its ticket, so the unit ticket is self-contained.
  helpers — every `function congruency_*` actually DEFINED in boot/rest.php (5 today), parsed from
            the source. A helper this tool has no bucket mapping for is emitted into the server
            bucket rather than dropped.
  crud    — the six generic ?api verbs rest.php's dispatch implements (tables/list/read/create/
            update/delete).
  php     — the boot scripts and render-engine classes a ?page= request actually runs (router,
            configure, shim, monitor, vault; ClassLoader, POM, Controller, ValidateFields,
            DocumentDAO, DocumentManager, Document; and the tag engine Tag_Wrapper/Tag_Parser/
            TagArguments/Tag_Interface). Each declared path is VERIFIED to exist at enumeration
            time — an entry whose file is gone is a hard error, never a silent claim.
  pages   — every `Documents.DocumentID` row (26 today) = the ?page= surface.
  tags    — every *.php under TAGS_DIR (invocators/tags/) whose source contains `Tag_Interface`,
            keyed by basename-minus-.php, deduped exactly as the gallery dedupes.

THE TAG UNIVERSE IS TagList::scan's, NOT dev/ (a deliberate, evidenced deviation from #230's
estimate). #230 says "31 tags"; that is the count of invocators/tags/dev/*.php. The live engine
scans wider: TagList::scan (invocators/tags/dev/TagList.php) walks TAGS_DIR with a
RecursiveIteratorIterator, and configure.php defines TAGS_DIR as invocators/tags/ — so the
gallery lists 45 tags, not 31. The extra 14 are not academic: Document_Templates embed
<<<TitleTag>>> in 27 of 27 templates and <<<MemoryList>>> in one, and NEITHER lives under dev/.
A dev-only universe would therefore leave every one of the 26 page units depending on a tag that
has no unit ticket, which is exactly the under-enumeration #230 forbids ("enumerate EVERY unit").
This tool mirrors the engine, and `--subset tag:` still lets a run drain only tags.

THE TAG GATE IS THE #282 HARNESS, NOT A DIFF (#323 — the systemic bug this tool used to cause).
Tag units used to state their gate as "byte-equivalent vs the PHP render". A blind auditor reads
that as a WHOLE-PAGE byte diff of ?page=tags — and that diff is STRUCTURALLY NON-EMPTY for EVERY
tag, including tags already merged byte-perfect (#323 measured ~6205B on CategoryView, TreeView and
TicketList, all three correct). The reason has nothing to do with any port: the PHP URL returns a
full CMS page, while the Go server frames the tag engine's render in its own chrome and says so in
its source — congruency-go/server.go:820-823, "the CMS Controller::control() page chrome is still
not reproduced here." So correct ports were rejected, pairs never self-settled, and #310/#311/#312
had to be hand-harvested against the harness that was already authoritative.

The authoritative gate already exists: congruency-go/tags/equivalence_test.go (#282) renders each
tag through tags.RenderTag and compares it to the tag's own bytes SLICED out of the live PHP page.
So a tag unit filed by this tool now names exactly that, and REFUSES the diff by name and with its
evidence — a gate stated only as a positive gets re-derived by the next reader into the same wrong
diff. tag_harness() verifies the file still defines the test before any tag ticket is filed, and
reads the harness's override knobs OUT OF IT (#323's own text sketches the gate as
`CONGRUENCY_SQLITE=<db> go test ...`, but the harness never reads CONGRUENCY_SQLITE — its db knob
is CONGRUENCY_EQUIV_DB, equivalence_test.go:199-206 — so that prefix would silently do nothing).
Tag-on-tag dependencies are derived too: see tag_emits().

UNIT-SCOPED GATES. Each unit ticket's gate exercises THAT unit and nothing less:
  * a route unit diffs ?route=<its own name>;
  * a page unit diffs /?page=<its own DocumentID>;
  * a tag unit settles on the #282 harness above (`go test ./tags/ -run TestTagEquivalence`) with
    its tag registered — never on a whole-page diff. The pages whose templates embed it are still
    derived per tag from Document_Templates, but they are CONTEXT (which argument forms the live
    site uses), not the gate: diffing a page is the same broken whole-page comparison;
  * each CRUD verb drives ITS OWN verb (list paginates/filters/orders, read fetches a real pk and
    a 404, create/update/delete run their own HTTP method against scratch db copies);
  * congruency_rest_route is gated on ?route= traffic (the engine's own success + error
    envelopes), NOT on ?api=tables — rest.php dispatches ?api= WITHOUT ever calling it;
  * congruency_rest_apikey / congruency_rest_authorized are gated with CONGRUENCY_AUTH_OVERRIDE
    flipped to false, because the constant is true by default (boot/constants.default.json) and
    short-circuits congruency_rest_authorized before either helper's logic can run;
  * a boot/engine unit is gated on the page-render outcomes that unit decides.

REPLY ENCODING IS DERIVED, NOT ASSERTED. rest.php does NOT use one encoder. It uses three, and a
unit ticket that names the wrong one is ordering a wrong port. So this tool lexes boot/rest.php
(one masking pass — see php_mask), finds every `echo json_encode(...)` statement in the span that
belongs to each unit, and reports, with THIS checkout's line numbers:
    PRETTY  json_encode(..., JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)  4-space indent, "/" bare
    COMPACT json_encode(...) with NO flags                                no indent, "/" -> "\\/"
plus whether that statement appends a trailing "\\n". All three combinations occur live: ?api=tables
is PRETTY + "\\n"; ?route=nosuchroute is COMPACT + "\\n" (a 48-byte one-liner); the CRUD 400 bodies
are COMPACT with NO trailing newline. Nothing about encoding is remembered — it is re-read each run.

IDEMPOTENCY (never re-file a unit already ticketed). Existing unit keys are read from the UNION of
two sources, and the union is what makes it airtight:
  (1) the state db, ALL statuses, opened via the sqlite URI flag `immutable=1`. This sees the units
      whose tickets have since gone CLOSED/DONE — which `ticket.queue` (OPEN/REQUESTED only)
      cannot. immutable=1 rather than mode=ro because the state db is WAL-journalled and mode=ro
      spins up `-wal`/`-shm` sidecar files on every open; immutable=1 creates ZERO files. This tool
      writes to no db directly.
  (2) the LIVE `ticket.queue` route over HTTP. immutable=1 deliberately ignores the `-wal`, so a row
      committed but not yet checkpointed is invisible to (1). Every ticket this tool files is born
      status REQUESTED (ticket.create hardcodes it), and REQUESTED is exactly what ticket.queue
      returns — so (2) covers precisely the window (1) can miss.
  With --file-tickets, an unreadable ticket.queue is fatal to the run: it refuses to file rather
  than risk duplicates.

BATCHED + SELF-REPOPULATING, AND THE CHAIN DOES NOT STALL (#196, #245). Append-only governance
means a ticket cannot reopen, so the work perpetuates by spawning a successor. Successors are
GENERATION-NUMBERED — `[go-port:successor:<chain>:g<N>]` — and a run's own generation keeps it alive:

    a run with nothing open (a human/dispatch starts it) -> files a batch -> spawns successor g1
    the pair executing g1 runs the decomposer again
      -> the run READS THE QUEUE, sees g1 is the highest OPEN successor of this chain, and concludes
         it IS g1's own run: it does not count itself, and spawns g2
    g1 settles; later the pair executing g2 runs -> spawns g3 ... until nothing remains.

A run at generation N declines to spawn ONLY IF an OPEN successor of generation > N already exists
(someone already filed its replacement). It ignores its own generation and any stale open predecessor
(gen <= N), because a predecessor will never file anything again — that is precisely the stall a
"does ANY open successor exist?" test causes: the run launched from the successor's own body always
sees itself, never spawns, and the chain dies with everything past the first batch un-ticketed.

THE GENERATION IS DERIVED FROM THE QUEUE, NOT DEMANDED ON THE COMMAND LINE (#245 — the stall this
tool actually shipped with; it was reproduced end-to-end before it was fixed). The generation used to
come ONLY from an explicit `--gen N`, defaulting to 0. That made the flag load-bearing and invisible:
a pair or dispatcher running the tool the obvious way — `--file-tickets`, no flag — was generation 0
while g1 sat OPEN in the queue, so `1 > 0` fired the decline branch. It filed its batch, spawned
NOTHING, and the chain died after the FIRST successor with every remaining unit stranded — and no
line of the output called that a failure. So the default generation is now READ FROM THE LIVE QUEUE:
the highest
OPEN successor of this chain, which is precisely what the run launched from that successor's ticket
is (or 0 for a fresh chain, where none is open). The no-flag invocation now continues the chain
instead of ending it, so the chain drains to the last unit however the command reaches the pair.

`--gen N` remains as an explicit OVERRIDE for the deliberate case: re-running an OLD generation's
command must still decline, because a NEWER open successor is the one carrying the chain. It is belt
and braces now, not the mechanism.

Successor numbers are MONOTONIC: the next generation is one past the highest this chain has EVER used
(the db, ALL statuses, UNION the live queue), so a chain whose g1 has since settled/closed never
re-mints the number g1 and the journal stays readable. The chain is scoped by --subset, so a
`--subset tag:` drain and a full drain never block each other.

CORRECTING THE TAG UNITS ALREADY FILED (--correct-open-tags, #323). Fixing the template only helps
units filed FROM NOW ON, and this tool is idempotent by design — it will never re-file a unit whose
key is already ticketed — so the tag units already carrying the broken wording would stay broken
forever. Their bodies cannot be rewritten either: ticket identity is immutable by SQL trigger
(tg_tickets_immutable_identity, migrations/0029_ticket_authorization.sql:111-117 — "ticket identity
(id, ts, title, body, component, kind) is permanent: append events"). The lawful move is the one
the trigger names: --correct-open-tags APPENDS one governed ticket.progress event, carrying the
corrected gate, to each still-open tag unit. It edits nothing, files nothing, re-opens nothing, and
is idempotent — a ticket whose journal already holds the correction marker is skipped. Candidates
come from the db (ALL statuses, minus DONE/CLOSED) UNION the live queue, because ticket.queue
returns only OPEN/REQUESTED and an ACTIVE unit — a pair working the broken gate RIGHT NOW — is the
one that most needs the correction.

SAFE BY DEFAULT: run with no flags this tool only REPORTS — it writes to no db and creates no file
(verified before/after in isolation: the state dir gains no `-wal`/`-shm`/anything and the db's hash
is unchanged). It writes exactly three things, each only when you ask: --json writes the one path you
name; --file-tickets POSTs — solely through the governed rest.php routes (ticket.create ->
ticket.kind -> edge.record); and --correct-open-tags POSTs ticket.progress events, equally governed.
Both POST paths use X-Api-Key from ../.secrets/ats.env, the same source pair_loop.py reads. It
appends to the registry's bug_reports sink only if it hits an unexpected exception (the Variant-A
report note-for-claude mandates). Pure-python stdlib, registry-gated (a tool that cannot see
registry.json throws).

Every invocation below is written from the REPO ROOT — the directory that holds registry.json — and
runs as written from there (`tools/go_port_decomposer.py` would NOT: the tool lives under
checkouts/current/congruency, so that shorter form only resolves from the CMS app root):

    python3 checkouts/current/congruency/tools/go_port_decomposer.py                 # report; writes NOTHING
    python3 checkouts/current/congruency/tools/go_port_decomposer.py --subset tag:   # only the tag units
    python3 checkouts/current/congruency/tools/go_port_decomposer.py --file-tickets  # file a batch
    python3 checkouts/current/congruency/tools/go_port_decomposer.py --subset route:agent. --file-tickets --batch 3
    python3 checkouts/current/congruency/tools/go_port_decomposer.py --json /tmp/units.json   # dump the enumeration
    python3 checkouts/current/congruency/tools/go_port_decomposer.py --correct-open-tags      # #323: fix filed tag units

Exit 0 on a clean run; exit 2 with a one-line message (never a traceback) on a bad invocation or an
unusable environment.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import textwrap
import time
import traceback
import urllib.error
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
# This tool's own path relative to the repo root. Derived, never hardcoded, so the invocation
# printed into a spawned successor ticket keeps running as written even if the tool is moved.
SELF_FROM_ROOT = os.path.relpath(os.path.abspath(__file__), ROOT)
SOURCE = os.path.join(ROOT, "checkouts", "current", "congruency")     # the CMS app root
STATE = os.path.join(ROOT, "checkouts", "current", "state")
CONG_DB = os.path.join(STATE, "congruency.sqlite")
REST_PHP = os.path.join(SOURCE, "boot", "rest.php")
TAGS_DIR = os.path.join(SOURCE, "invocators", "tags")                # configure.php: TAGS_DIR
SOURCE_FROM_ROOT = os.path.relpath(SOURCE, ROOT)

# ── the Go port, and the AUTHORITATIVE tag gate (#282, #323) ─────────────────────────────────────
# The tag harness is the ONLY thing that settles a tag unit. See "THE TAG GATE" in the module
# docstring for why the obvious whole-page diff is not, and cannot be, that gate.
GO_DIR = os.path.join(ROOT, "congruency-go")
GO_FROM_ROOT = os.path.relpath(GO_DIR, ROOT)
GO_TAGS_DIR = os.path.join(GO_DIR, "tags")
TAG_HARNESS = os.path.join(GO_TAGS_DIR, "equivalence_test.go")       # #282
TAG_HARNESS_FROM_ROOT = os.path.relpath(TAG_HARNESS, ROOT)
TAG_TEST_NAME = "TestTagEquivalence"
# The gate command a tag unit settles on, written from the REPO ROOT like every other invocation
# this tool prints. No env prefix: the harness resolves the db/app-root/URL itself (see
# tag_harness()), and every one of its knobs already defaults to the live server's own values.
TAG_GATE_CMD = "cd %s && go test ./tags/ -run %s -count=1 -v" % (GO_FROM_ROOT, TAG_TEST_NAME)
# The idempotency marker for --correct-open-tags. A ticket BODY is immutable by SQL trigger
# (tg_tickets_immutable_identity, migrations/0029_ticket_authorization.sql:111-117 — "ticket
# identity (id, ts, title, body, component, kind) is permanent: append events"), so an already-filed
# unit is corrected by APPENDING a journal event, and this marker in the note is what makes a second
# run skip it instead of appending the same correction twice.
GATE_CORRECTION_MARK = "[go-port:gate-correction:v1]"
CORRECTION_AGENT = "go_port_decomposer"

# The PHP interpreter the harness ships, and the boot invocation serve.py uses (php -S with
# boot/router.php as the router script, cwd = the app root). Both are quoted into the gates so a
# pair can boot the original exactly the way this repo boots it.
PHP_BIN = os.path.join(ROOT, "tooling", "congruencey-harness", "php", "php")
if not os.path.isfile(PHP_BIN):
    PHP_BIN = "php"

# The PHP original under test and the Go port under construction. Both are overridable so a pair can
# point the diff at whatever ports/hosts it booted.
PHP_BASE = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")
GO_BASE = (os.environ.get("CONGRUENCY_GO_URL") or "http://127.0.0.1:8900").rstrip("/")

DECOMPOSER_TICKET = 230              # the ticket that authorizes this factory; parent of every spawn
KEY_RE = re.compile(r"\[(go-port:[^\]]+)\]")
# `[go-port:successor:<chain>:g<N>]` — <chain> is the --subset (or "all"), <N> the generation.
# Greedy `(.+)` so a chain that itself contains colons (e.g. `route:doc.`) still parses.
SUCC_RE = re.compile(r"\[go-port:successor:(.+):g(\d+)\]")

# Dependency order: db (#224) -> server (#225) -> tags (#226), exactly as #230 requires.
BUCKETS = {
    "db":     (1, 224, "pure-Go sqlite over the SAME schema + the data-driven api_routes engine"),
    "server": (2, 225, "Go net/http serving the identical path surface: rest dispatch + ?api CRUD + "
                       "auth + the ?page= boot and render chain"),
    "tags":   (3, 226, "the tag engine + invocators rendering identical HTML (execute_all_tags in Go)"),
}
# Within a bucket: boot before engine before the data-driven surface that runs on them.
GROUP_RANK = {"boot": 0, "helper": 1, "crud": 2, "engine": 3, "page": 4, "route": 5, "tag": 6}

# The tag invocation syntax, mirroring the engine EXACTLY. Tag_Wrapper::identify_tag builds its
# pattern as TAG_KEY_PREFIX . FUNCTION_NAME . FUNCTION_ARGUMENTS . TAG_KEY_SUFFIX
# (lib/TagLoader/Tag/Tag_Wrapper.php), and boot/constants.default.json defines those as
# "/<<<", "[a-zA-Z]+", "(\([A-Za-z0-9]*\))*", "\>>>/" — i.e. the PHP regex /<<<[a-zA-Z]+(\([A-Za-z0-9]*\))*\>>>/.
# This is the same pattern in python, with the tag NAME captured so a page's embedded tags are read
# out of Document_Templates.Content the way the engine reads them.
TAG_INVOCATION_RE = re.compile(r"<<<([a-zA-Z]+)(?:\([A-Za-z0-9]*\))*>>>")

# A tag INVOCATION AS EMITTED BY ANOTHER TAG, matched on the name alone. The full TAG_INVOCATION_RE
# above cannot be used for this: an emitted invocation is usually built at run time, so its argument
# is a PHP expression in the source, not the literal [A-Za-z0-9]* the engine will see after
# interpolation. BodyTag.php:20 is the case that proves it —
#     return "<<<ContentTag(" . $this->body . ")>>>";
# — which TAG_INVOCATION_RE does NOT match (`" . $this->body . "` is not [A-Za-z0-9]*), while the
# engine matches the INTERPOLATED result at run time and substitutes ContentTag. So this matches
# TAG_KEY_PREFIX + FUNCTION_NAME only, and the name class is the engine's own FUNCTION_NAME —
# "[a-zA-Z]+" (boot/constants.default.json:33) — so a name this stops short of is a name the engine
# also refuses to substitute. `<<<Config_Form_Invocator($product)>>>`
# (invocators/tags/store/Catalog_Controller.php:19) is exactly that: both this pattern and the
# engine's read the name as "Config" and stop at the underscore, so the engine leaves that
# invocation LITERAL and it is correctly not reported as a dependency. See tag_emits().
TAG_EMIT_RE = re.compile(r"<<<([a-zA-Z]+)")

# A tag REGISTRATION in the Go port: `Register("<Name>", func(...) ...)`, the only supported way
# into the registry (congruency-go/tags/engine.go:1342-1368 — "Register ... is the ONLY supported
# way in"). Comment lines are skipped by the caller, so a docblock naming Register is not counted.
GO_REGISTER_RE = re.compile(r"\bRegister\(\"([A-Za-z0-9_]+)\"\s*,")

# ── the encoder legend. Every fact here is checked against boot/rest.php at run time by
#    rest_encoding(); nothing below is a standing claim about which reply uses which. ─────────────
ENC_LEGEND = (
    "  PRETTY  = json_encode(..., JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES): 4-space indent, \"/\"\n"
    "            left unescaped, PHP's key order, PHP's number formatting.\n"
    "  COMPACT = json_encode(...) with NO flags: no indent and no spaces at all, and \"/\" IS escaped\n"
    "            as \"\\/\". rest.php uses BOTH — do not assume one encoder for the whole surface.\n"
    "  The trailing newline is part of the bytes. A reply marked NO TRAILING NEWLINE must not have\n"
    "  one; a reply marked + \"\\n\" must. Byte-identical means all of it, including the HTTP status.")

# Which bucket each boot/rest.php helper belongs to, what it does, and which encode-site spans it
# owns (see rest_encoding()). A helper missing from this map is still enumerated — see helper_units().
HELPER_BUCKET = {
    "congruency_rest_route": (
        "db", ["route.engine"],
        "the data-driven api_routes engine: look the route row up by name, gate on its method/auth,\n"
        "  short-circuit telemetry.record, bind ONLY the declared :params the sql actually mentions\n"
        "  (casting int/float/str per the params json, NULL when the caller omitted one), execute,\n"
        "  then shape the reply — a SELECT (stripos(ltrim(sql),'select')===0) returns {route, rows},\n"
        "  anything else returns {route, affected, rowid}"),
    "congruency_telemetry_record": (
        "db", ["telemetry"],
        "the telemetry.record receiver congruency_rest_route short-circuits to BEFORE binding params,\n"
        "  because a client 'error' must also log + auto-file a de-duped front-end bug; emits\n"
        "  {route, ok, kind} and never throws (a beacon must not be able to fatal a page)"),
    "congruency_rest_dispatch": (
        "server", ["dispatch.all"],
        "the ?api / ?route front door: clean the boot buffer, set the JSON + CORS headers, open\n"
        "  CONGRUENCY_SQLITE, build the table allowlist from sqlite_master minus the admin denylist,\n"
        "  hand ?route= to the engine, gate writes, dispatch the CRUD verbs, and turn any Throwable\n"
        "  into a 500 {error}"),
    "congruency_rest_apikey": (
        "server", [],
        "the API key lookup: X-Api-Key header or ?key=, resolved to its {label, scope} row in\n"
        "  api_keys; false when the key is absent, empty, or the api_keys table does not exist"),
    "congruency_rest_authorized": (
        "server", [],
        "the write gate, in order: the CONGRUENCY_AUTH_OVERRIDE constant (TRUE by default today —\n"
        "  the app 'starts authenticated', so this returns true before anything else runs), then the\n"
        "  admin session (UserPrivilegeSet::logged_in), then a valid API key, then the optional\n"
        "  Vault-validated token"),
}

# The six generic ?api CRUD verbs boot/rest.php's dispatch implements. `spans` names the encode-site
# spans whose replies THIS verb can emit (resolved live by rest_encoding()); `gate` is built per-verb
# against real fixtures by crud_units(), so each verb's gate drives that verb.
CRUD_VERBS = [
    ("tables", "GET  /rest.php?api=tables", ["dispatch.tail"],
     "the table index: {\"tables\":[...]} — sqlite_master's tables minus the admin denylist, sorted\n"
     "  by name. ?api= empty behaves identically (the branch is $api === '' || $api === 'tables')."),
    ("list", "GET  /rest.php?api=<table>[&<col>=<v>][&order=<col>.<asc|desc>][&limit=|&per=][&p=]",
     ["dispatch.tail"],
     "the filtered/paginated list: filter by any REAL column named in the query string (the reserved\n"
     "  keys api/route/key/p/per/id/order/limit never filter), order only by a real column, per\n"
     "  clamped to 1..500 (default 50, and ?per= wins over ?limit=), p >= 1; returns\n"
     "  {table, pk, total, page, per, pages, filter, rows}. `filter` is the BOUND-PARAM names\n"
     "  (\":f_<col>\"), not the column names — port that literally."),
    ("read", "GET  /rest.php?api=<table>&id=<pk>", ["dispatch.tail"],
     "the single row by primary key: {table, pk, row}, or a 404 {error:'not found', table, id}.\n"
     "  Falls through to the list when the table has no pk. NOTE the pk scan here BREAKS at the\n"
     "  first pk column, while update/delete do NOT break and so take the LAST pk column — on a\n"
     "  composite-pk table the two disagree. Port the disagreement, not your idea of it."),
    ("create", "POST /rest.php?api=<table>", ["dispatch.write401", "dispatch.create", "dispatch.tail"],
     "insert from the JSON body, keeping ONLY real columns (the rest ignored); 201 {created, table,\n"
     "  rowid, used}; 400 when the body is not a JSON object, or when no key matched a column (that\n"
     "  400 echoes the column list)."),
    ("update", "PUT|PATCH /rest.php?api=<table>&id=<pk>",
     ["dispatch.write401", "dispatch.update", "dispatch.tail"],
     "update by primary key from the JSON body, real columns only and never the pk itself;\n"
     "  {updated, table, pk, id, set}; 400 without a single-column pk + ?id=, 400 on a non-object\n"
     "  body, 400 with nothing left to set."),
    ("delete", "DELETE /rest.php?api=<table>&id=<pk>",
     ["dispatch.write401", "dispatch.delete", "dispatch.tail"],
     "delete exactly one row by primary key ({deleted, table, pk, id}); no bulk deletes; 400 without\n"
     "  a single-column pk + ?id=."),
]

# The boot scripts and render-engine classes a request actually runs. These are DECLARED (they are
# not discoverable from a table the way routes/pages/tags are) but every path is verified to exist
# at enumeration time by php_units(), and each description was read from the file this session.
#   (bucket, name, relative path, headline, what-it-does, gate)
PHP_UNITS = [
    ("server", "boot_router", "boot/router.php",
     "Port boot/router.php (the request front door) to Go",
     "the front door every request enters. In order: ob_start() so buffered boot whitespace can be\n"
     "  dropped before JSON headers; require shim.php (mysql_* -> PDO/sqlite), configure.php\n"
     "  (constants), monitor.php + congruency_install_monitor() (the fatal net); set_include_path to\n"
     "  shadow the app's AutoLoader; require CLASS_LOADER_HEADER; session_start(); ?fresh unsets\n"
     "  $_SESSION['POM']; getClassLoader() + spl_autoload_register; PersistentObjectManager::getPOM()\n"
     "  and bin/Initialize_POM.php; require boot/rest.php; then THE BRANCH — if ?api= OR ?route= is\n"
     "  set it calls congruency_rest_dispatch() and EXITS, otherwise it calls Controller::control();\n"
     "  finally PersistentObjectManager::pack(), whose failure is swallowed to error_log",
     "GATE — this unit IS the branch, so diff every outcome of it:\n"
     "  1. ?api= short-circuits to rest dispatch (never to Controller):\n"
     "     diff <(curl -s '%(php)s/rest.php?api=tables') <(curl -s '%(go)s/rest.php?api=tables')\n"
     "  2. ?route= short-circuits to the same place:\n"
     "     diff <(curl -s '%(php)s/rest.php?route=%(route)s') <(curl -s '%(go)s/rest.php?route=%(route)s')\n"
     "  3. NEITHER is set -> Controller::control() renders a page:\n"
     "     diff <(curl -s '%(php)s/?page=%(page)s') <(curl -s '%(go)s/?page=%(page)s')\n"
     "  4. no ?page= at all -> Controller defaults the key to \"catalog\":\n"
     "     diff <(curl -s '%(php)s/') <(curl -s '%(go)s/')\n"
     "  5. ?fresh resets the POM session:\n"
     "     diff <(curl -s '%(php)s/?page=%(page)s&fresh=1') <(curl -s '%(go)s/?page=%(page)s&fresh=1')\n"
     "All five diffs empty. #1/#2 must reach rest dispatch even though ?page= is ALSO present:\n"
     "     diff <(curl -s '%(php)s/?page=%(page)s&api=tables') <(curl -s '%(go)s/?page=%(page)s&api=tables')"),

    ("server", "boot_configure", "boot/configure.php",
     "Port boot/configure.php (constants = data) to Go",
     "the configuration script. The constant VALUES are DATA: boot/constants.default.json, merged\n"
     "  (array_merge, override wins) with an install override — $CONGRUENCY_CONFIG if set, else\n"
     "  <deploy-root>/install.json — then one loop define()s every key that is not already defined.\n"
     "  Afterwards it computes the DERIVED path constants from ABS_PATH/SLASH (PLATFORMROOT,\n"
     "  ABS_PATH, CONGRUENCY_SQLITE, TAGS_DIR, CONTENT_DIR, CLASS_LOADER_DIR, CLASS_LOADER_HEADER,\n"
     "  ETC, LIB, BIN, HARNESS), each guarded by !defined() so the data can pre-empt any of them",
     "GATE — the constants have no URL, so prove them through the behaviour they DECIDE. Boot both\n"
     "servers with the SAME override file and diff; then boot with a DIFFERENT one and diff again —\n"
     "the override must move both servers identically:\n"
     "  printf '{\"CONGRUENCY_AUTH_OVERRIDE\": false}\\n' > /tmp/eq-cfg.json\n"
     "  CONGRUENCY_CONFIG=/tmp/eq-cfg.json <boot the PHP original>   # see BOOTING, below\n"
     "  CONGRUENCY_CONFIG=/tmp/eq-cfg.json <boot the Go port>\n"
     "  diff <(curl -s -X DELETE -o /dev/null -w '%%{http_code}' '%(php)s/rest.php?api=%(table)s&id=0') \\\n"
     "       <(curl -s -X DELETE -o /dev/null -w '%%{http_code}' '%(go)s/rest.php?api=%(table)s&id=0')\n"
     "  (401 from BOTH with the override false — that is the constant taking effect; re-run with the\n"
     "   override file removed and both must stop saying 401. If the Go port hardcodes the default,\n"
     "   the second run diverges and this unit is not done.)\n"
     "Also diff a page render (constants decide TAGS_DIR/CONTENT_DIR):\n"
     "  diff <(curl -s '%(php)s/?page=%(page)s') <(curl -s '%(go)s/?page=%(page)s')"),

    ("server", "boot_shim", "boot/shim.php",
     "Port boot/shim.php (the mysql_* -> PDO/sqlite shim) to Go",
     "the compatibility shim the legacy DAOs call: the mysql_* function surface reimplemented over\n"
     "  PDO/sqlite. Read the file and port the functions it actually defines — every DAO in the\n"
     "  render chain reaches the db through this",
     "GATE — the shim has no URL; it is exercised by every page whose DAO reads the db. Diff the\n"
     "pages, and add Go unit tests pinning each shim function's own return shape (including its\n"
     "failure/empty returns) against what the PHP function returns for the same call:\n"
     "  diff <(curl -s '%(php)s/?page=%(page)s') <(curl -s '%(go)s/?page=%(page)s')\n"
     "  diff <(curl -s '%(php)s/') <(curl -s '%(go)s/')"),

    ("server", "boot_monitor", "boot/monitor.php",
     "Port boot/monitor.php (the fatal net + telemetry ingest) to Go",
     "the fatal-error net: congruency_install_monitor() registers the shutdown + exception handlers\n"
     "  early (covering ?route= AND ?page=), logging an uncaught/fatal error and auto-filing a\n"
     "  de-duped bug. It also carries congruency_telemetry_ingest, which congruency_telemetry_record\n"
     "  hands its beacons to",
     "GATE — force the net to fire on BOTH servers and diff what the client sees, then compare what\n"
     "each logged/filed. Point both at scratch db copies first (this unit WRITES bug rows):\n"
     "  cp %(db)s /tmp/eq-php.sqlite && cp %(db)s /tmp/eq-go.sqlite\n"
     "  diff <(curl -s '%(php)s/?page=%(page)s') <(curl -s '%(go)s/?page=%(page)s')\n"
     "Then trip a fatal identically on each (e.g. point CONGRUENCY_SQLITE at an unreadable path) and\n"
     "diff both the HTTP body AND the rows the two scratch dbs now hold, allowing ONLY the clock\n"
     "columns to differ. The de-dupe must de-dupe on the second identical fatal, in both."),

    ("server", "boot_vault", "boot/vault.php",
     "Port boot/vault.php (optional Vault-validated authorization) to Go",
     "the optional Vault check rest.php requires at its top. When Vault is configured, the App\n"
     "  validates a presented token against its authorization secret in Vault, so the shared secret\n"
     "  lives in Vault rather than at rest in the CMS db. Unconfigured/unreachable must degrade\n"
     "  gracefully — congruency_rest_authorized only consults it via\n"
     "  function_exists('congruency_vault_authorizes'), and only when a token was presented",
     "GATE — Vault is the LAST branch of congruency_rest_authorized, so it is unreachable while\n"
     "CONGRUENCY_AUTH_OVERRIDE is true (the default) or a valid api key is sent. Flip the override\n"
     "off and present a token that is not in api_keys, so the request falls through to Vault:\n"
     "  printf '{\"CONGRUENCY_AUTH_OVERRIDE\": false}\\n' > /tmp/eq-cfg.json\n"
     "  (boot BOTH servers with CONGRUENCY_CONFIG=/tmp/eq-cfg.json and scratch db copies)\n"
     "  diff <(curl -s -X DELETE -H 'X-Api-Key: not-a-real-key' -o /dev/null -w '%%{http_code}' \\\n"
     "            '%(php)s/rest.php?api=%(table)s&id=%(id)s') \\\n"
     "       <(curl -s -X DELETE -H 'X-Api-Key: not-a-real-key' -o /dev/null -w '%%{http_code}' \\\n"
     "            '%(go)s/rest.php?api=%(table)s&id=%(id)s')\n"
     "Diff that with Vault UNCONFIGURED (both must degrade to the same refusal) and, if you can\n"
     "configure one, with Vault reachable. Same status, same body bytes, both ways."),

    ("server", "engine_classloader", "lib/ClassLoader/ClassLoaderHeader.php",
     "Port the ClassLoader (lib/ClassLoader) to Go",
     "the class loader boot/router.php requires as CLASS_LOADER_HEADER and then wires into PHP 8's\n"
     "  SPL autoloader (spl_autoload_register calling $LOADER->loadClassByName($class)). Go has no\n"
     "  autoloader, so this unit is the NAME->IMPLEMENTATION registry the port needs: the same\n"
     "  name-to-class resolution, including what happens for a name that resolves to nothing.\n"
     "  Tag_Wrapper::get_tag_wrapper leans on the same mechanism via the TAG_LOADER POM entry",
     "GATE — no URL of its own; it is proven by every class the render chain resolves. Diff the page\n"
     "surface, and specifically a tag name that does NOT resolve (the loader's failure path is part\n"
     "of the contract — whatever the PHP emits, byte for byte, the Go must emit):\n"
     "  diff <(curl -s '%(php)s/?page=%(page)s') <(curl -s '%(go)s/?page=%(page)s')\n"
     "  diff <(curl -s '%(php)s/?page=tags&tag=NoSuchTagName') <(curl -s '%(go)s/?page=tags&tag=NoSuchTagName')"),

    ("server", "engine_pom", "lib/PersistanceObjectManager/PersistentObjectManager.php",
     "Port PersistentObjectManager (the POM) to Go",
     "the session-backed object manager. boot/router.php calls getPOM(), includes\n"
     "  bin/Initialize_POM.php (which seeds entries such as TAG_LOADER), and pack()s it into\n"
     "  $_SESSION['POM'] at the end of a page render; ?fresh unsets that session entry.\n"
     "  Controller::display setData('WORKING_PAGE', $document) then executeCommands(); tags read it\n"
     "  back with getData(). Port getData/setData/executeCommands/getPOM/pack and the session\n"
     "  round-trip — a page's SECOND request must observe what the first packed",
     "GATE — the POM is stateful, so a single request cannot prove it. Drive a SESSION against each\n"
     "server with a cookie jar and diff request 2, then diff the ?fresh reset:\n"
     "  for b in '%(php)s' '%(go)s'; do\n"
     "    curl -s -c /tmp/eq-$(basename $b).jar -o /dev/null \"$b/?page=%(page)s\"\n"
     "    curl -s -b /tmp/eq-$(basename $b).jar \"$b/?page=%(page)s\" > /tmp/eq-2nd-$(basename $b).html\n"
     "    curl -s -b /tmp/eq-$(basename $b).jar \"$b/?page=%(page)s&fresh=1\" > /tmp/eq-fresh-$(basename $b).html\n"
     "  done\n"
     "  diff /tmp/eq-2nd-*.html && diff /tmp/eq-fresh-*.html\n"
     "Both diffs empty. (Run the two loops against one base each if your shell mangles the jar names\n"
     "— the point is: same cookie jar, second request, then ?fresh.)"),

    ("server", "engine_controller_control", "lib/Controller/Controller.php",
     "Port Controller::control (the ?page= front controller) to Go",
     "the front controller boot/router.php falls through to when neither ?api= nor ?route= is set.\n"
     "  control(): if ?page= is set it runs the key through ValidateFields::validatePageKey,\n"
     "  OTHERWISE the key is the literal \"catalog\"; then display($key) and print the string.\n"
     "  display(): DocumentManager::get_document($key), PersistentObjectManager::setData\n"
     "  ('WORKING_PAGE', $document), set_display_string($document->__toString()) — note the RENDER\n"
     "  HAPPENS HERE, inside display(), BEFORE executeCommands() runs — then executeCommands().\n"
     "  That ORDER is observable and part of the port",
     "GATE — drive control()'s own branches and diff each:\n"
     "  diff <(curl -s '%(php)s/?page=%(page)s') <(curl -s '%(go)s/?page=%(page)s')   # the ?page= branch\n"
     "  diff <(curl -s '%(php)s/') <(curl -s '%(go)s/')                               # no ?page= -> \"catalog\"\n"
     "  diff <(curl -s '%(php)s/?page=') <(curl -s '%(go)s/?page=')                   # SET but empty: still validated\n"
     "  diff <(curl -s '%(php)s/?page=nosuchpage') <(curl -s '%(go)s/?page=nosuchpage')  # valid key, no such row\n"
     "All empty. The empty/invalid keys matter: ?page= set-but-invalid does NOT default to catalog —\n"
     "it goes to validatePageKey, which is its own unit."),

    ("server", "engine_validatefields", "lib/IOControl/Validators/ValidateFields.php",
     "Port ValidateFields::validatePageKey to Go",
     "the page-key validator Controller::control gates ?page= on. validatePageKey: preg_match\n"
     "  \"/[A-Za-z]{2,}/\" against the key, then return the match ONLY if it equals the whole key,\n"
     "  else NULL. So \"tags\" passes; \"tags2\" does not (the match \"tags\" != the key); \"1\" does not.\n"
     "  BEWARE THE OBSERVABLE WARNING: on NO match, $result is empty and the code still reads\n"
     "  $result[0], which under this router's error_reporting (E_ALL & ~E_DEPRECATED) and\n"
     "  display_errors=1 PRINTS a PHP warning into the response body. That warning is part of the\n"
     "  bytes a byte-identical port must reproduce. (validateItemKey/validateNumericKey/\n"
     "  validateFormKey live here too — port the file, and check whether the render chain calls them\n"
     "  before deciding they are out of scope.)",
     "GATE — drive the validator's real branches through ?page= and diff the RAW BODIES (the warning\n"
     "text is body bytes, so a diff catches it; do not pipe through a DOM pretty-printer):\n"
     "  for k in %(page)s tags1 1 '' ab a 'tags%%20x' 'TAGS'; do\n"
     "    diff <(curl -s \"%(php)s/?page=$k\") <(curl -s \"%(go)s/?page=$k\") || echo \"DIVERGES: page=$k\";\n"
     "  done\n"
     "Every one empty, including whichever of those prints a PHP warning."),

    ("server", "engine_documentdao", "lib/Modules/Constructs/Document/DAO/DocumentDAO.php",
     "Port DocumentDAO (the Documents/Document_Templates read) to Go",
     "the DAO DocumentManager::produceDocument calls: getDocumentData($key) returns the row behind a\n"
     "  DocumentID, and its FIELD_NAME_* constants (CONTENT/TITLE/DESCRIPTION/DOCUMENT_ID/CONTENT_ID)\n"
     "  are the column names Document::sql_assoc_array indexes with. Read the file for its actual\n"
     "  SQL and constants and port them — the join that turns a DocumentID into its\n"
     "  Document_Templates.Content is this unit",
     "GATE — no URL of its own; every page render goes through it, so diff pages that exercise its\n"
     "hit AND miss paths (the miss is what triggers DocumentManager's \"invalid\" fallback):\n"
     "  diff <(curl -s '%(php)s/?page=%(page)s') <(curl -s '%(go)s/?page=%(page)s')       # a real row\n"
     "  diff <(curl -s '%(php)s/?page=nosuchpage') <(curl -s '%(go)s/?page=nosuchpage')   # no row -> fallback\n"
     "Add Go tests pinning getDocumentData's return for a real key, an unknown key, and the literal\n"
     "key \"invalid\", against the PHP's return for the same three."),

    ("server", "engine_documentmanager", "lib/Modules/Constructs/Document/DocumentInterface/DocumentManager.php",
     "Port DocumentManager::get_document to Go",
     "resolves a page key to a Document. get_document() lazily makes the singleton, then\n"
     "  loadDocument -> lookupDocument -> produceDocument. produceDocument: getDocumentData($key);\n"
     "  if that returned nothing it RETRIES with the literal key \"invalid\" and builds the document\n"
     "  from THAT row — so an unknown ?page= renders the 'invalid' document, it does not 404. If the\n"
     "  \"invalid\" lookup ALSO returns nothing, $document stays NULL and lookupDocument returns NULL\n"
     "  (falling off the end of its if) — Controller::display then calls __toString() on NULL, which\n"
     "  is a fatal in PHP 8. Port the fallback AND that edge; do not 'fix' it here.\n"
     "  NOTE it does not cache: the comment says \"Does not implement document caching\" and\n"
     "  $documentArray is written but never read as a cache",
     "GATE — drive the resolve, the fallback, and the shape of a miss:\n"
     "  diff <(curl -s '%(php)s/?page=%(page)s') <(curl -s '%(go)s/?page=%(page)s')\n"
     "  diff <(curl -s '%(php)s/?page=nosuchpage') <(curl -s '%(go)s/?page=nosuchpage')\n"
     "  diff <(curl -s -o /dev/null -w '%%{http_code}' '%(php)s/?page=nosuchpage') \\\n"
     "       <(curl -s -o /dev/null -w '%%{http_code}' '%(go)s/?page=nosuchpage')\n"
     "All empty — the unknown page must produce the SAME body and the SAME status in Go as in PHP."),

    ("server", "engine_document_tostring", "lib/Modules/Constructs/Document/Document/Document.php",
     "Port Document (the root Tag_Interface) to Go",
     "the document object, which is ITSELF a Tag_Interface — that is how a page enters the tag\n"
     "  engine. sql_assoc_array builds it from the DAO row (template/title/description/key/\n"
     "  content_outline) and returns NULL for an empty row; the constructor wraps it via\n"
     "  Tag_Wrapper::create_document_tag($this); get_document() returns the raw TEMPLATE (this is\n"
     "  the tag entry point: the engine calls get_document() to get the string it scans for tags);\n"
     "  __toString() returns Tag_Wrapper::execute_all_tags($this->document_tag)",
     "GATE — the document is the root of the render, so its diff is the page's bytes. Diff a page\n"
     "whose template embeds tags and one that is nearly bare, so a mistake in the ROOT (not in a\n"
     "tag) is visible:\n"
     "  diff <(curl -s '%(php)s/?page=%(page)s') <(curl -s '%(go)s/?page=%(page)s')\n"
     "  diff <(curl -s '%(php)s/') <(curl -s '%(go)s/')\n"
     "Whitespace counts. Diff raw bytes."),

    ("tags", "engine_tag_wrapper", "lib/TagLoader/Tag/Tag_Wrapper.php",
     "Port Tag_Wrapper::execute_all_tags (THE tag engine) to Go",
     "THE tag engine of #226 — every tag unit rests on it. execute_all_tags($tag_wrapper, $depth=0):\n"
     "  (1) $result_string = $tag_wrapper->tag->get_document(); (2) IF $depth >= 64 return that\n"
     "  string AS IS, leaving nested tags literal (BUG-06's recursion bound); (3) identify_tag()\n"
     "  preg_match_all's the pattern TAG_KEY_PREFIX.FUNCTION_NAME.FUNCTION_ARGUMENTS.TAG_KEY_SUFFIX\n"
     "  — /<<<[a-zA-Z]+(\\([A-Za-z0-9]*\\))*\\>>>/ — over that string; (4) for EACH match in match\n"
     "  order: add_child() builds a Tag_Wrapper (Tag_Parser -> function name -> the TAG_LOADER POM\n"
     "  entry loads the class -> new $tag_class($arguments)), recurse at $depth+1, and str_replace\n"
     "  the invocation string with the result. str_replace replaces EVERY occurrence, so a tag\n"
     "  appearing twice is rendered once and its output pasted at both sites — port that, it is\n"
     "  observable",
     "GATE — drive the engine's OWN branches, not one tag's output:\n"
     "  1. substitution + ordering, on the real pages:\n"
     "     for p in %(pages)s; do\n"
     "       diff <(curl -s \"%(php)s/?page=$p\") <(curl -s \"%(go)s/?page=$p\") || echo \"DIVERGES: $p\";\n"
     "     done\n"
     "  2. the depth>=64 bound and the repeat-tag str_replace behaviour: add a Document_Templates row\n"
     "     to a SCRATCH copy of the db (cp %(db)s /tmp/eq-php.sqlite && cp %(db)s /tmp/eq-go.sqlite,\n"
     "     one per server via CONGRUENCY_SQLITE) whose Content nests tags past 64 and repeats one\n"
     "     tag twice, point a Documents row at it, and diff that page on both servers.\n"
     "  3. an unresolvable tag name (<<<NoSuchTag>>> in that scratch template): whatever PHP emits\n"
     "     (including any warning/fatal text), Go must emit byte for byte.\n"
     "Never mutate the live state db."),

    ("tags", "engine_tag_parser", "lib/TagLoader/Parser/Tag_Parser.php",
     "Port Tag_Parser (invocation string -> name + arguments) to Go",
     "turns one raw invocation string into a tag name and its arguments. get_tag_parser($full_tag)\n"
     "  -> initialize(): extract_tag_name() strips KEY_PREFIX/KEY_SUFFIX (\"<<<\"/\">>>\") by LENGTH —\n"
     "  substr($tag, strlen(KEY_PREFIX), strlen($tag) - strlen(KEY_PREFIX.KEY_SUFFIX)); then\n"
     "  get_tag_identifier() preg_matches GET_TAG_IDENTIFIER\n"
     "  (/([a-zA-Z0-9]+\\s?(?=\\(\\s?[a-zA-Z0-9]*\\s?\\)))|(\\s?[a-zA-Z0-9]+\\s?)/) for the function name,\n"
     "  returning NULL when nothing matches; and TagArguments::argumentFactory($tag) builds the\n"
     "  argument wrapper. Port the exact regex semantics — an argument-bearing name and a bare name\n"
     "  take different alternatives of that pattern",
     "GATE — the parser has no URL. Pin it with Go tests whose expectations come from the PHP, not\n"
     "from reading the regex: for each invocation string below, run it through the PHP\n"
     "(%(php_bin)s -r ...) and through your Go parser, and compare name + arguments exactly —\n"
     "  <<<Style>>>  <<<FormTag(Login)>>>  <<<TagList()>>>  <<<Foo(a)(b)>>>  <<<Foo( )>>>\n"
     "Then diff the pages that carry argument-bearing tags end to end:\n"
     "  for p in %(pages)s; do\n"
     "    diff <(curl -s \"%(php)s/?page=$p\") <(curl -s \"%(go)s/?page=$p\") || echo \"DIVERGES: $p\";\n"
     "  done"),

    ("tags", "engine_tagarguments", "lib/TagLoader/Arguments/TagArguments.php",
     "Port TagArguments (the tag argument wrapper) to Go",
     "the argument wrapper every tag's constructor receives (`new $tag_class($arguments)`).\n"
     "  Tag_Parser calls TagArguments::argumentFactory($tag) on the tag string; read the file for\n"
     "  the accessor surface the tags actually use and port it, including what an argument-less tag\n"
     "  receives and what an out-of-range argument access returns — tags depend on both",
     "GATE — no URL of its own; it is proven through the tags that TAKE arguments. Diff every page\n"
     "carrying an argument-bearing tag, plus the gallery render of those tags:\n"
     "  for p in %(pages)s; do\n"
     "    diff <(curl -s \"%(php)s/?page=$p\") <(curl -s \"%(go)s/?page=$p\") || echo \"DIVERGES: $p\";\n"
     "  done\n"
     "Add Go tests comparing argumentFactory's accessors against the PHP's for the invocation strings\n"
     "<<<Foo>>>, <<<Foo()>>>, <<<Foo(a)>>>, <<<Foo(a)(b)>>> — same values, same count, same behaviour\n"
     "when a tag asks for an argument that was not supplied."),

    ("tags", "engine_tag_interface", "lib/Modules/taglib/Tag_Interface.php",
     "Port Tag_Interface (the contract every tag implements) to Go",
     "the interface every tag and the Document implement — read it for the exact method set (the\n"
     "  engine calls get_document() on a tag and __toString() through Tag_Wrapper). In Go this is\n"
     "  the interface the 45 tag units are written against, so it lands FIRST in this bucket: get it\n"
     "  wrong and every tag unit inherits the mistake",
     "GATE — an interface emits no bytes of its own, so it is gated on its IMPLEMENTORS. This unit is\n"
     "settled when the Go interface compiles against the tag engine AND at least one real tag renders\n"
     "byte-identically through it end to end:\n"
     "  diff <(curl -s '%(php)s/?page=tags&tag=Style') <(curl -s '%(go)s/?page=tags&tag=Style')\n"
     "  diff <(curl -s '%(php)s/?page=%(page)s') <(curl -s '%(go)s/?page=%(page)s')\n"
     "Both empty. Do not settle this on 'it compiles'."),
]


# ── Variant-A bug report (note-for-claude: every tool auto-files a timestamped report) ───────────
def bug_report(fn, exc, repro, cause):
    """Filename / function / time-of-occurance / methods-to-reproduce / possible-cause, to the
    registry's bug_reports sink. Best-effort: a failing bug report never masks the real error."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "go_port_decomposer.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:],
                "note": "go_port_decomposer (#%d) — congruency-go unit factory" % DECOMPOSER_TICKET,
            }) + "\n")
    except Exception:                                     # noqa: BLE001
        pass


def step(msg):
    """Per-step telemetry: one labeled line per step of the run, so a scheduled run's log shows what
    it enumerated, what it skipped, and what it filed."""
    print("== step == %s" % msg)


def die(msg):
    print("go_port_decomposer: %s" % msg)
    sys.exit(2)


# ── read-only db access (creates NO files; see the module docstring on immutable=1) ──────────────
def connect_ro(db_path):
    if not os.path.isfile(db_path):
        die("database not found: %s" % db_path)
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


def rest(base, route, obj=None, method=None, key=None, timeout=15):
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


# ── the PHP lexer: ONE masking pass ─────────────────────────────────────────────────────────────
def php_lex(src, blank_strings=True):
    """Return a SAME-LENGTH, SAME-LINE-NUMBERED copy of PHP source with every comment blanked to
    spaces (newlines preserved) and, when blank_strings, every string-literal BODY blanked too
    (quotes kept). Indices into the result are therefore valid indices into the original, so
    structure can be found on it while text is read from the real source.

    One pass, not stacked regexes — this is tools/tag_selfcheck.py's lex() lesson, and rest.php is
    exactly the file that proves it. A regex that strips `//` line comments BEFORE strings eats the
    closing quote of the real literal in file_get_contents('php://input'), and the stray quote then
    pairs with the next quote in the file and swallows whole functions. Scanning once means a `//`
    inside a string is seen as string content, and a quote inside a comment is seen as comment text.
    Line comments: // and #. Block comments: /* */. String escapes: \\<any>.

    THE TWO CALLERS WANT OPPOSITE THINGS, WHICH IS WHY THIS TAKES A FLAG:
      php_mask()      (blank_strings=True)  — structure only. Used to find rest.php's functions and
                                              branch guards, where a brace or paren inside a literal
                                              would mislead the balancer.
      php_code_only() (blank_strings=False) — comments gone, string bodies KEPT. Used to find the
                                              tag invocations a tag EMITS, which live inside string
                                              literals (BodyTag.php:20 returns the literal
                                              "<<<ContentTag(" . $this->body . ")>>>"). Blanking
                                              literals would erase exactly what that scan looks for,
                                              while keeping comments would report every usage
                                              example in a docblock as a real dependency."""
    def blank(text):
        return "".join(ch if ch == "\n" else " " for ch in text)

    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(blank(src[i:j]))
            i = j
        elif c == "#":
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(blank(src[i:j]))
            i = j
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(blank(src[i:j]))
            i = j
        elif c == "'" or c == '"':
            q = c
            j = i + 1
            while j < n:
                if src[j] == "\\" and j + 1 < n:           # escape: skip the escaped char verbatim
                    j += 2
                    continue
                if src[j] == q:
                    break
                j += 1
            if j >= n:                                    # unterminated literal: blank to EOF
                out.append(q + (blank(src[i + 1:n]) if blank_strings else src[i + 1:n]))
                i = n
            else:                                         # quotes always kept; body per the flag
                body = blank(src[i + 1:j]) if blank_strings else src[i + 1:j]
                out.append(q + body + q)
                i = j + 1
        else:
            out.append(c)
            i += 1
    mask = "".join(out)
    if len(mask) != len(src):                             # the whole design rests on this
        die("internal: php_lex changed the source length (%d -> %d)" % (len(src), len(mask)))
    return mask


def php_mask(src):
    """Comments AND string bodies blanked — the structural mask rest.php's parsing runs on."""
    return php_lex(src, blank_strings=True)


def php_code_only(src):
    """Comments blanked, string bodies KEPT — the view tag_emits() reads emitted tags out of."""
    return php_lex(src, blank_strings=False)


def php_functions(mask):
    """Every `function congruency_*(` DEFINED in a masked PHP source, in file order. Comments and
    string literals are already blanked, so a function merely NAMED in prose is never enumerated as a
    definition."""
    seen, out = set(), []
    for m in re.finditer(r"\bfunction\s+(congruency_[A-Za-z0-9_]*)\s*\(", mask):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


def brace_span(mask, from_idx, what):
    """(start, end) of the {...} block that opens at/after from_idx, by balancing braces on the mask
    (where braces inside comments/strings are already blanked away)."""
    i = mask.find("{", from_idx)
    if i < 0:
        die("boot/rest.php: no opening brace after %s — cannot read the source" % what)
    depth, j = 0, i
    while j < len(mask):
        if mask[j] == "{":
            depth += 1
        elif mask[j] == "}":
            depth -= 1
            if depth == 0:
                return i, j + 1
        j += 1
    die("boot/rest.php: unbalanced braces in %s — cannot read the source" % what)


def fn_span(mask, name):
    m = re.search(r"\bfunction\s+" + re.escape(name) + r"\s*\(", mask)
    if not m:
        die("boot/rest.php no longer defines %s() — this decomposer's map of rest.php is stale; "
            "re-read the file before filing tickets that describe it" % name)
    return brace_span(mask, m.end(), name + "()")


def sole_index(src, needle, lo, hi, what):
    """Index of `needle` in src[lo:hi], which MUST occur exactly once. rest.php's branch guards are
    the anchors that delimit each CRUD verb's span; if one drifts or doubles, a unit ticket would
    quote the wrong reply shapes — so fail loudly instead."""
    n = src.count(needle, lo, hi)
    if n != 1:
        die("boot/rest.php: expected exactly one occurrence of the %s anchor %r, found %d — this "
            "decomposer's map of rest.php is stale; re-read the file before filing tickets that "
            "describe it" % (what, needle, n))
    return src.index(needle, lo, hi)


def echo_sites(src, mask, lo, hi):
    """Every `echo json_encode(...)  [. "\\n"] ;` statement in src[lo:hi], classified. Structure is
    found on the mask (so a paren or semicolon inside a string literal cannot mislead the balancer);
    the argument TEXT is read from the real source."""
    sites = []
    for m in re.finditer(r"\becho\s+json_encode\s*\(", mask[lo:hi]):
        start = lo + m.start()
        popen = lo + m.end() - 1                          # index of json_encode's '('
        depth, j = 0, popen
        while j < hi:
            if mask[j] == "(":
                depth += 1
            elif mask[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth != 0:
            die("boot/rest.php: unbalanced parens in an echo json_encode(...) near line %d"
                % (src.count("\n", 0, start) + 1))
        args = src[popen + 1:j]
        semi = mask.find(";", j)
        tail = src[j + 1:semi] if semi > 0 else ""
        sites.append({
            "line": src.count("\n", 0, start) + 1,
            "pretty": "JSON_PRETTY_PRINT" in args,
            "newline": "\\n" in tail,
            "args": re.sub(r"\s+", " ", args).strip(),
        })
    return sites


def rest_encoding():
    """Read boot/rest.php and return {span_name: [encode-site, ...]} plus the admin denylist, both
    derived from the source THIS RUN. Nothing about rest.php's encoders or denylist is remembered:
    the spans are located by the file's own branch guards and the sites are lexed out of them."""
    if not os.path.isfile(REST_PHP):
        die("boot/rest.php not found at %s — cannot read the reply encoders it defines" % REST_PHP)
    src = open(REST_PHP, encoding="utf-8", errors="replace").read()
    mask = php_mask(src)

    route_lo, route_hi = fn_span(mask, "congruency_rest_route")
    tele_lo, tele_hi = fn_span(mask, "congruency_telemetry_record")
    disp_lo, disp_hi = fn_span(mask, "congruency_rest_dispatch")

    # The CRUD verbs are branches of congruency_rest_dispatch, delimited by their own guards. Each
    # anchor is verified unique WITHIN the dispatch span (e.g. `!congruency_rest_authorized($db)`
    # also appears in congruency_rest_route, which is why the search is scoped).
    a_gate = sole_index(src, "!congruency_rest_authorized($db)", disp_lo, disp_hi, "write-gate")
    a_create = sole_index(src, "$method === 'POST' && isset($tables[$api])", disp_lo, disp_hi, "create")
    a_update = sole_index(src, "($method === 'PUT' || $method === 'PATCH') && isset($tables[$api])",
                          disp_lo, disp_hi, "update")
    a_delete = sole_index(src, "$method === 'DELETE' && isset($tables[$api])", disp_lo, disp_hi, "delete")
    a_listread = sole_index(src, "$api === '' || $api === 'tables'", disp_lo, disp_hi, "list/read")
    a_catch = sole_index(src, "catch (\\Throwable $e)", disp_lo, disp_hi, "catch/tail")

    spans = {
        "route.engine":     (route_lo, route_hi),
        "telemetry":        (tele_lo, tele_hi),
        "dispatch.all":     (disp_lo, disp_hi),
        "dispatch.write401": (a_gate, a_create),
        "dispatch.create":  (a_create, a_update),
        "dispatch.update":  (a_update, a_delete),
        "dispatch.delete":  (a_delete, a_listread),
        # the tail echo: tables / list / read / unknown-table 404 / the 500 all assign $out and fall
        # through to the single echo after the catch block.
        "dispatch.tail":    (a_catch, disp_hi),
    }
    enc = dict((k, echo_sites(src, mask, lo, hi)) for k, (lo, hi) in spans.items())

    # the admin denylist, read from the loop that applies it rather than copied into this file
    m = re.search(r"foreach\s*\(\s*array\(([^)]*)\)\s*as\s*\$__deny\)", src)
    if not m:
        die("boot/rest.php: cannot find the `foreach (array(...) as $__deny)` admin denylist — this "
            "decomposer's map of rest.php is stale; re-read the file before filing tickets")
    deny = re.findall(r"'([^']+)'", m.group(1))
    return enc, deny


def enc_label(site):
    return "%s, %s" % ("PRETTY " if site["pretty"] else "COMPACT",
                       'trailing "\\n"' if site["newline"] else "NO TRAILING NEWLINE")


def encoding_block(sites, note=""):
    """The per-unit reply-encoding table, rendered from sites this run lexed out of boot/rest.php."""
    if not sites:
        return ("REPLY ENCODING: this unit emits no JSON of its own.%s" % (("\n  " + note) if note else ""))
    out = ["REPLY ENCODING — every `echo json_encode(...)` this unit can emit, lexed out of "
           "boot/rest.php by\nthe decomposer run that filed this ticket (so these line numbers are "
           "that checkout's, not a\nremembered claim — re-read them if the file has moved on):"]
    for s in sorted(sites, key=lambda x: x["line"]):
        out.append("  rest.php:%-4d %s" % (s["line"], enc_label(s)))
        out.append("       %s" % (s["args"][:110] + ("..." if len(s["args"]) > 110 else "")))
    if note:
        out.append("  %s" % note)
    out.append(ENC_LEGEND)
    return "\n".join(out)


# ── live fixtures: the real tables/ids/routes the gates below are driven with ────────────────────
def fixtures(con, deny):
    """Real values pulled from the state db so every gate command RUNS AS WRITTEN. A gate that names
    a table or id that does not exist is a step that cannot be executed — the exact class of defect
    the playbook's Theme 2 is about."""
    fx = {"deny": list(deny)}
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        if r[0] not in deny]
    if not tables:
        die("the state db exposes no REST-visible table — cannot build a runnable CRUD gate")
    fx["tables"] = tables

    single_pk, no_pk = [], []
    for t in tables:
        cols = list(con.execute('PRAGMA table_info("%s")' % t))
        pks = [c[1] for c in cols if c[5]]
        if len(pks) == 1:
            single_pk.append((t, pks[0], [c[1] for c in cols]))
        elif not pks:
            no_pk.append(t)
    if not single_pk:
        die("no REST-visible table has a single-column primary key — cannot build a runnable "
            "read/update/delete gate")
    # prefer `tickets` (big, stable, and the one every pair already knows) when it qualifies
    pick = next((x for x in single_pk if x[0] == "tickets"), single_pk[0])
    fx["table"], fx["pk"], cols = pick
    fx["no_pk_table"] = no_pk[0] if no_pk else ""

    row = con.execute('SELECT "%s" FROM "%s" ORDER BY "%s" LIMIT 1' % (fx["pk"], fx["table"], fx["pk"])).fetchone()
    fx["id"] = row[0] if row else 1
    other = [c for c in cols if c != fx["pk"]]
    fx["col"] = other[0] if other else fx["pk"]
    val = con.execute('SELECT "%s" FROM "%s" WHERE "%s" IS NOT NULL LIMIT 1' % (fx["col"], fx["table"], fx["col"])).fetchone()
    raw = "" if not val or val[0] is None else str(val[0])
    fx["val"] = urllib.request.quote(raw[:24], safe="")

    routes = list(con.execute("SELECT name, method, sql, auth FROM api_routes ORDER BY name"))
    if not routes:
        die("the state db holds no api_routes rows — cannot build a runnable route gate")
    def first(pred, dflt=""):
        return next((r[0] for r in routes if pred(r)), dflt)
    fx["route"] = first(lambda r: "GET" in (r[1] or "GET").upper()
                        and (r[2] or "").strip().lower().startswith("select")
                        and (r[3] or "public").lower() == "public", routes[0][0])
    fx["post_route"] = first(lambda r: "GET" not in (r[1] or "GET").upper())
    fx["token_route"] = first(lambda r: (r[3] or "public").lower() == "token")
    return fx


# ── the units ────────────────────────────────────────────────────────────────────────────────────
def unit(bucket, utype, name, source, headline, contract, probe):
    """One enumerated unit. `key` is the idempotency marker; `title` carries it verbatim."""
    key = "go-port:%s:%s:%s" % (bucket, utype, name)
    rank, layer, layer_text = BUCKETS[bucket]
    return {"bucket": bucket, "utype": utype, "name": name, "key": key,
            "layer_ticket": layer, "layer_text": layer_text,
            "sort": (rank, GROUP_RANK[utype], str(name).lower()),
            "source": source, "headline": headline, "contract": contract, "probe": probe,
            "title": "%s [%s]" % (headline, key)}


def booting(scratch=False):
    """The boot recipe every gate leans on, written the way tools/serve.py boots the original: php -S
    with boot/router.php as the ROUTER SCRIPT and the app root as the cwd/docroot."""
    txt = ("BOOTING THE TWO SERVERS (from the repo root — the directory holding registry.json):\n"
           "  # the PHP original, on %s (tools/serve.py boots it exactly this way):\n"
           "  ( cd %s && %s -S 127.0.0.1:%s boot/router.php )\n"
           "  # the Go port, on %s — however your port is started.\n"
           % (PHP_BASE.rsplit(":", 1)[-1], SOURCE_FROM_ROOT, PHP_BIN, PHP_BASE.rsplit(":", 1)[-1],
              GO_BASE.rsplit(":", 1)[-1]))
    if scratch:
        txt += ("  # THIS UNIT WRITES: give each server its OWN scratch db and never the live one:\n"
                "  cp %s /tmp/eq-php.sqlite && cp %s /tmp/eq-go.sqlite\n"
                "  # then boot each with CONGRUENCY_SQLITE pointed at its copy (install.json /\n"
                "  # $CONGRUENCY_CONFIG sets it: printf '{\"CONGRUENCY_SQLITE\": \"/tmp/eq-php.sqlite\"}\\n'\n"
                "  # > /tmp/eq-php.json, then CONGRUENCY_CONFIG=/tmp/eq-php.json before php -S).\n"
                % (CONG_DB, CONG_DB))
    return txt


# Per-helper gates. Each drives the helper THROUGH THE SURFACE THAT ACTUALLY CALLS IT — which is the
# whole point: rest.php dispatches ?api= WITHOUT ever calling congruency_rest_route (router.php hands
# the request to congruency_rest_dispatch, and the dispatch only calls the route engine when ?route=
# is non-empty), and it only consults congruency_rest_apikey/_authorized on POST/PUT/PATCH/DELETE.
# A ?api=tables diff would therefore be EMPTY for a Go port in which any of those is unimplemented,
# which is a gate that gates nothing.
HELPER_GATES = {
    "congruency_rest_route":
        "%(boot)s\nEQUIVALENCE-DIFF — this engine is reached ONLY via ?route= (rest.php calls it when\n"
        "$route !== ''; a ?api= request never touches it, so an ?api= diff would prove NOTHING about\n"
        "this unit). Drive its own branches:\n"
        "  1. the SELECT success shape {route, rows}:\n"
        "     diff <(curl -s '%(php)s/rest.php?route=%(route)s') <(curl -s '%(go)s/rest.php?route=%(route)s')\n"
        "  2. the unknown-route envelope (COMPACT — see REPLY ENCODING above; live it is the 48-byte\n"
        "     one-liner {\"error\":\"unknown route\",\"route\":\"nosuchroute\"} + \"\\n\", NOT pretty-printed):\n"
        "     diff <(curl -s '%(php)s/rest.php?route=nosuchroute') <(curl -s '%(go)s/rest.php?route=nosuchroute')\n"
        "     diff <(curl -s -o /dev/null -w '%%{http_code}' '%(php)s/rest.php?route=nosuchroute') \\\n"
        "          <(curl -s -o /dev/null -w '%%{http_code}' '%(go)s/rest.php?route=nosuchroute')   # 404 both\n"
        "  3. the method gate (405 + {\"error\":\"method not allowed\",\"route\":...,\"allowed\":[...]}):\n"
        "     diff <(curl -s -X POST '%(php)s/rest.php?route=%(route)s') \\\n"
        "          <(curl -s -X POST '%(go)s/rest.php?route=%(route)s')\n"
        "%(post_route)s"
        "  4. param binding — only params the SQL TEXT mentions are bound, and an omitted one binds\n"
        "     NULL. Pick a route with declared params and diff it with each param present, then\n"
        "     omitted, then with a junk param the sql does not mention (which must be ignored):\n"
        "     diff <(curl -s '%(php)s/rest.php?route=%(route)s&nosuchparam=x') \\\n"
        "          <(curl -s '%(go)s/rest.php?route=%(route)s&nosuchparam=x')\n"
        "  5. the write shape {route, affected, rowid} — pick a non-SELECT route and diff it against\n"
        "     SCRATCH copies of the db (never the live one).\n"
        "  6. the telemetry.record short-circuit: this engine hands that ONE route to\n"
        "     congruency_telemetry_record BEFORE binding any params. Its own unit gates it, but this\n"
        "     unit owns the short-circuit — prove ?route=telemetry.record still reaches it.\n"
        "  7. the auth gates: see below.\n"
        "%(authnote)s"
        "  8. no api_routes table at all -> 404 {\"error\":\"no api_routes table\"}: point BOTH servers\n"
        "     at a scratch db with that table dropped and diff.\n",

    "congruency_telemetry_record":
        "%(boot)s\nEQUIVALENCE-DIFF — this helper is reached ONLY as ?route=telemetry.record (the\n"
        "engine short-circuits to it by name). It WRITES (a stream row, and for kind=error a de-duped\n"
        "bug), so point each server at its own scratch db copy first. Drive each KIND — the branch is\n"
        "the whole unit:\n"
        "  for k in pageview event error; do\n"
        "    diff <(curl -s -X POST -H 'Content-Type: application/json' \\\n"
        "              -d \"{\\\"kind\\\":\\\"$k\\\",\\\"route\\\":\\\"r\\\",\\\"message\\\":\\\"m\\\",\\\"detail\\\":\\\"d\\\"}\" \\\n"
        "              '%(php)s/rest.php?route=telemetry.record') \\\n"
        "         <(curl -s -X POST -H 'Content-Type: application/json' \\\n"
        "              -d \"{\\\"kind\\\":\\\"$k\\\",\\\"route\\\":\\\"r\\\",\\\"message\\\":\\\"m\\\",\\\"detail\\\":\\\"d\\\"}\" \\\n"
        "              '%(go)s/rest.php?route=telemetry.record') || echo \"DIVERGES: kind=$k\";\n"
        "  done\n"
        "Every reply {route, ok, kind} byte-identical. Then:\n"
        "  * kind OMITTED entirely must default to 'pageview' — diff a body of '{}' on both.\n"
        "  * it MUST NOT throw: diff a hostile body (missing fields, wrong types, huge strings) on\n"
        "    both; a beacon must not be able to fatal the endpoint in either.\n"
        "  * compare the rows the two scratch dbs now hold (the stream row, and for kind=error the\n"
        "    auto-filed bug), allowing ONLY the clock columns to differ; and send the SAME error twice\n"
        "    — the de-dupe must fire identically in both.\n",

    "congruency_rest_dispatch":
        "%(boot)s\nEQUIVALENCE-DIFF — this IS the ?api / ?route front door, so drive each thing it\n"
        "decides:\n"
        "  1. the table allowlist + the admin denylist (these tables exist but must never appear):\n"
        "     diff <(curl -s '%(php)s/rest.php?api=tables') <(curl -s '%(go)s/rest.php?api=tables')\n"
        "     curl -s '%(go)s/rest.php?api=tables' | grep -E '%(deny_re)s' && echo 'LEAK — not done'\n"
        "  2. the HEADERS it sets (Content-Type: application/json, Access-Control-Allow-Origin: *) —\n"
        "     body-only diffs miss these:\n"
        "     diff <(curl -s -D- -o /dev/null '%(php)s/rest.php?api=tables' | grep -iE '^(content-type|access-control)') \\\n"
        "          <(curl -s -D- -o /dev/null '%(go)s/rest.php?api=tables' | grep -iE '^(content-type|access-control)')\n"
        "  3. the ob_clean(): boot whitespace must not precede the JSON. The FIRST byte of the body\n"
        "     must be '{' on both — `curl -s '%(php)s/rest.php?api=tables' | head -c1`.\n"
        "  4. it hands ?route= to the engine and does NOT run the CRUD path:\n"
        "     diff <(curl -s '%(php)s/rest.php?route=%(route)s') <(curl -s '%(go)s/rest.php?route=%(route)s')\n"
        "  5. the unknown-table 404 {\"error\":\"unknown table\",\"table\":...,\"tables\":[...]}:\n"
        "     diff <(curl -s '%(php)s/rest.php?api=nosuchtable') <(curl -s '%(go)s/rest.php?api=nosuchtable')\n"
        "  6. a denylisted table must read as UNKNOWN, not as forbidden:\n"
        "     diff <(curl -s '%(php)s/rest.php?api=api_keys') <(curl -s '%(go)s/rest.php?api=api_keys')\n"
        "  7. the Throwable -> 500 {\"error\": <message>} catch-all: point BOTH servers at an\n"
        "     unreadable/corrupt CONGRUENCY_SQLITE and diff body AND status. The PHP leaks the raw\n"
        "     exception message — port that, do not sanitize it here.\n"
        "The CRUD verbs themselves are their own units; this unit is the dispatch AROUND them.\n",

    "congruency_rest_apikey":
        "%(boot)s\nREACHABILITY FIRST — READ THIS OR THE GATE IS A LIE. This helper is called from\n"
        "congruency_rest_authorized, but ONLY AFTER the CONGRUENCY_AUTH_OVERRIDE check, and that\n"
        "constant is TRUE by default (boot/constants.default.json). With stock config\n"
        "congruency_rest_authorized returns true immediately and THIS HELPER NEVER RUNS — a diff taken\n"
        "against a stock server would be empty even if the Go port had no api-key lookup at all. So:\n"
        "  printf '{\"CONGRUENCY_AUTH_OVERRIDE\": false}\\n' > /tmp/eq-cfg.json\n"
        "  (boot BOTH servers with CONGRUENCY_CONFIG=/tmp/eq-cfg.json and their OWN scratch db copies)\n"
        "\nEQUIVALENCE-DIFF — with the override off, a write is the only thing that consults this\n"
        "helper, so drive one and vary ONLY the key. Every pair below must match in body and status:\n"
        "  KEY=$(sed -n 's/^CONGRUENCY_API_KEY=//p' ../.secrets/ats.env)\n"
        "  for k in \"-H 'X-Api-Key: $KEY'\" \"-H 'X-Api-Key: not-a-real-key'\" \"-H 'X-Api-Key: '\" \"\"; do\n"
        "    for base in '%(php)s' '%(go)s'; do\n"
        "      eval curl -s $k -X DELETE -o /dev/null -w \"'%%{http_code} '\" \\\n"
        "           \"'$base/rest.php?api=%(table)s&id=999999999'\";\n"
        "    done; echo;\n"
        "  done\n"
        "  (the two columns must be equal on every row: a valid key -> allowed; an unknown key, an\n"
        "   empty key, and NO key -> refused, identically)\n"
        "Also drive the ?key= query form, which this helper accepts as an alternative to the header:\n"
        "  diff <(curl -s -X DELETE -o /dev/null -w '%%{http_code}' \\\n"
        "            \"%(php)s/rest.php?api=%(table)s&id=999999999&key=$KEY\") \\\n"
        "       <(curl -s -X DELETE -o /dev/null -w '%%{http_code}' \\\n"
        "            \"%(go)s/rest.php?api=%(table)s&id=999999999&key=$KEY\")\n"
        "And its no-table branch: with the api_keys table DROPPED from a scratch db it must return\n"
        "false (not throw) on both. Add Go tests pinning the {label, scope} row it returns for a real\n"
        "key against what the PHP returns for that same key.\n",

    "congruency_rest_authorized":
        "%(boot)s\nREACHABILITY FIRST — READ THIS OR THE GATE IS A LIE. This helper's FIRST branch is\n"
        "`if (defined('CONGRUENCY_AUTH_OVERRIDE') && CONGRUENCY_AUTH_OVERRIDE) return true;` and that\n"
        "constant is TRUE by default (boot/constants.default.json), so with stock config it returns\n"
        "true before the session, the api key, or Vault is ever consulted. Its other branches are\n"
        "UNREACHABLE until you flip it. Gate BOTH configurations — the override IS branch 1:\n"
        "  # A. as shipped (override true): a keyless write must be ALLOWED, identically:\n"
        "  diff <(curl -s -X DELETE -o /dev/null -w '%%{http_code}' '%(php)s/rest.php?api=%(table)s&id=999999999') \\\n"
        "       <(curl -s -X DELETE -o /dev/null -w '%%{http_code}' '%(go)s/rest.php?api=%(table)s&id=999999999')\n"
        "  # B. override off — now the real gate runs:\n"
        "  printf '{\"CONGRUENCY_AUTH_OVERRIDE\": false}\\n' > /tmp/eq-cfg.json\n"
        "  (re-boot BOTH with CONGRUENCY_CONFIG=/tmp/eq-cfg.json and their OWN scratch db copies)\n"
        "  diff <(curl -s -X DELETE '%(php)s/rest.php?api=%(table)s&id=999999999') \\\n"
        "       <(curl -s -X DELETE '%(go)s/rest.php?api=%(table)s&id=999999999')\n"
        "  (the compact 401 {\"error\":\"authorization required for writes\",\"method\":\"DELETE\",\"hint\":...}\n"
        "   + \"\\n\" from BOTH — see REPLY ENCODING on the crud units for those bytes)\n"
        "Then walk its remaining branches IN ORDER, since order is observable:\n"
        "  * admin session (UserPrivilegeSet::logged_in) — log in via the Login form on each, keep the\n"
        "    cookie jar, and diff the same keyless write: allowed on both.\n"
        "  * a valid API key with NO session: allowed on both. An unknown key: refused on both.\n"
        "  * Vault last, and only when a token was presented — see the boot/vault.php unit.\n"
        "Every pair identical in body AND status, under BOTH configurations. Reads must stay public\n"
        "throughout: `curl -s '%(php)s/rest.php?api=tables'` must keep working with no key in both.\n",
}


def helper_units(enc, fx):
    mask = php_mask(open(REST_PHP, encoding="utf-8", errors="replace").read())
    post_route = ""
    if fx["post_route"]:
        post_route = ("     (and the mirror case, on the non-GET route %s — a GET must 405 on both:\n"
                      "      diff <(curl -s -o /dev/null -w '%%{http_code}' '%s/rest.php?route=%s') \\\n"
                      "           <(curl -s -o /dev/null -w '%%{http_code}' '%s/rest.php?route=%s'))\n"
                      % (fx["post_route"], PHP_BASE, fx["post_route"], GO_BASE, fx["post_route"]))
    authnote = (
        "     NOTE the auth branches are gated by config, not by this route alone: an auth='admin'\n"
        "     route answers the compact 401 {\"error\":\"admin login required\",...} without a session,\n"
        "     and an auth='token' route calls congruency_rest_authorized — which returns TRUE\n"
        "     unconditionally while CONGRUENCY_AUTH_OVERRIDE is set (the default), so its 401 is\n"
        "     unreachable until you flip it:\n"
        "       printf '{\"CONGRUENCY_AUTH_OVERRIDE\": false}\\n' > /tmp/eq-cfg.json\n"
        "     Boot both with CONGRUENCY_CONFIG=/tmp/eq-cfg.json and diff a keyless call to a token\n"
        "     route%s — the compact 401 {\"error\":\"API key or admin login required\",...} from both.\n"
        % (" (e.g. %s)" % fx["token_route"] if fx["token_route"] else ""))
    subst = {"boot": booting(), "php": PHP_BASE, "go": GO_BASE, "route": fx["route"],
             "table": fx["table"], "deny_re": "|".join(fx["deny"]), "post_route": post_route,
             "authnote": authnote}

    units = []
    for fn in php_functions(mask):
        # An unmapped helper is a helper rest.php grew after this map was written. Enumerate it into
        # the server bucket (rest.php is served there) rather than silently drop a unit.
        bucket, spans, what = HELPER_BUCKET.get(
            fn, ("server", [], "a boot/rest.php helper this decomposer has no description for — read\n"
                               "  the PHP and port it behaviourally"))
        sites = [s for sp in spans for s in enc.get(sp, [])]
        gate = HELPER_GATES.get(fn)
        if gate is None:
            gate = ("%s\nEQUIVALENCE-DIFF — this decomposer has no gate for %s(): it is a helper\n"
                    "boot/rest.php grew after this tool's map of the file was written. Read the PHP,\n"
                    "find the SURFACE that calls it (a gate that does not run this function proves\n"
                    "nothing), and diff that surface on both servers before settling this ticket.\n"
                    % (booting(), fn))
        else:
            gate = gate % subst
        units.append(unit(bucket, "helper", fn,
                          "boot/rest.php  (function %s)" % fn,
                          "Port rest helper %s() to Go, behaviour-identical vs rest.php" % fn,
                          "WHAT IT DOES (%s):\n  %s\n\n%s" % (fn, what, encoding_block(
                              sites, "" if spans else
                              "This helper returns a value rather than emitting JSON; the envelopes its "
                              "CALLER\n  emits on its verdict are shown on the units that own them.")),
                          gate))
    return units


def route_units(con, enc):
    engine = enc.get("route.engine", [])
    # the engine's own reply sites split into this route's success shape vs the shared envelopes
    succ = [s for s in engine if "'rows'" in s["args"] or "'affected'" in s["args"]]
    errs = [s for s in engine if s not in succ]
    units = []
    for name, method, auth, params, sql in con.execute(
            "SELECT name, method, auth, params, sql FROM api_routes ORDER BY name"):
        sql = (sql or "").strip()
        # rest.php's own reply-shape branch: a SELECT returns rows, anything else writes.
        is_read = sql.lower().startswith("select")
        mine = [s for s in succ if ("'rows'" in s["args"]) == is_read]
        contract = ("THE PHP ORIGINAL — the contract, read from this route's `api_routes` row:\n"
                    "  route  : %s\n  method : %s\n  auth   : %s\n  params : %s\n  sql    : %s\n\n"
                    "It replies %s.\n\n%s"
                    % (name, method or "GET", auth or "public", params or "{}", sql,
                       "{route, rows} (the sql is a SELECT)" if is_read
                       else "{route, affected, rowid} (the sql is a write)",
                       encoding_block(mine + errs,
                                      "The first line above is THIS route's success reply; the rest are the "
                                      "engine's\n  shared envelopes, which this route inherits and must "
                                      "reproduce identically.")))
        hdr = "" if (auth or "public") != "token" else " -H \"X-Api-Key: $CONGRUENCY_API_KEY\""
        bad_method = "POST" if is_read else "GET"
        if is_read:
            probe = ("%s\nEQUIVALENCE-DIFF — both servers on the SAME db, byte-identical JSON:\n"
                     "  diff <(curl -s%s '%s/rest.php?route=%s') \\\n"
                     "       <(curl -s%s '%s/rest.php?route=%s')\n"
                     "Exercise it once per declared param above (and once with each OMITTED — the engine\n"
                     "binds NULL for a param the caller did not send, and only binds params the sql text\n"
                     "actually mentions). Then this route's error envelopes, which are equally its bytes:\n"
                     "  diff <(curl -s%s -X %s -o /dev/null -w '%%{http_code}' '%s/rest.php?route=%s') \\\n"
                     "       <(curl -s%s -X %s -o /dev/null -w '%%{http_code}' '%s/rest.php?route=%s')\n"
                     "  (405 + the compact {\"error\":\"method not allowed\",...} envelope from BOTH)\n"
                     % (booting(), hdr, PHP_BASE, name, hdr, GO_BASE, name,
                        hdr, bad_method, PHP_BASE, name, hdr, bad_method, GO_BASE, name))
        else:
            probe = ("%s\nEQUIVALENCE-DIFF — this route WRITES, so it is probed against scratch copies,\n"
                     "never the live db. POST the SAME body to each server:\n"
                     "    curl -s%s -X %s -H 'Content-Type: application/json' \\\n"
                     "         -d '<the params above, as json>' '%s/rest.php?route=%s'\n"
                     "    (and the same against %s)\n"
                     "Two things must match: the JSON replies byte-for-byte, AND the rows the two dbs now\n"
                     "hold — compare the touched table in each, allowing ONLY the clock columns (ts/updated,\n"
                     "written by strftime('%%s','now')) to differ. Then the refusals:\n"
                     "  diff <(curl -s%s -X %s -o /dev/null -w '%%{http_code}' '%s/rest.php?route=%s') \\\n"
                     "       <(curl -s%s -X %s -o /dev/null -w '%%{http_code}' '%s/rest.php?route=%s')\n"
                     "  (405 from BOTH — this route does not accept %s)\n"
                     % (booting(scratch=True), hdr, (method or "POST").split(",")[0].strip(),
                        PHP_BASE, name, GO_BASE,
                        hdr, bad_method, PHP_BASE, name, hdr, bad_method, GO_BASE, name, bad_method))
        if (auth or "public").lower() == "token":
            probe += ("This route is auth=token, and CONGRUENCY_AUTH_OVERRIDE is TRUE by default —\n"
                      "congruency_rest_authorized returns true before the key is ever looked at, so the\n"
                      "401 envelope is UNREACHABLE with stock config. Diff it BOTH ways: as shipped (the\n"
                      "override lets a keyless call through), and with\n"
                      "  printf '{\"CONGRUENCY_AUTH_OVERRIDE\": false}\\n' > /tmp/eq-cfg.json\n"
                      "on both servers (CONGRUENCY_CONFIG=/tmp/eq-cfg.json), where a keyless call must\n"
                      "produce the compact 401 {\"error\":\"API key or admin login required\",...} from both.\n")
        u = unit("db", "route", name,
                 "the `api_routes` row named %s (in the state db)" % name,
                 "Port route %s to Go, byte-identical JSON vs rest.php" % name,
                 contract, probe)
        u["auth"] = (auth or "public")        # deps_for: a token route rests on the write gate
        units.append(u)
    return units


def crud_units(enc, fx, deny):
    gates = {
        "tables":
            "%(boot)s\nEQUIVALENCE-DIFF — drive THIS verb:\n"
            "  diff <(curl -s '%(php)s/rest.php?api=tables') <(curl -s '%(go)s/rest.php?api=tables')\n"
            "  diff <(curl -s '%(php)s/rest.php?api=')       <(curl -s '%(go)s/rest.php?api=')\n"
            "Both empty (?api= empty takes the same branch). Then prove the DENYLIST — these tables\n"
            "exist in sqlite_master and must NOT appear in either reply:\n"
            "  %(deny)s\n"
            "  curl -s '%(go)s/rest.php?api=tables' | grep -E '%(deny_re)s' && echo 'LEAK — not done'\n",
        "list":
            "%(boot)s\nEQUIVALENCE-DIFF — drive THIS verb across its own branches (real table `%(table)s`,\nreal column `%(col)s`):\n"
            "  for q in '' '&per=5' '&per=5&p=2' '&per=0' '&per=99999' '&p=0' '&limit=3' \\\n"
            "           '&per=5&limit=99' '&order=%(pk)s.desc' '&order=%(pk)s.asc' '&order=nosuchcol.desc' \\\n"
            "           '&%(col)s=%(val)s' '&nosuchcol=x' '&key=x'; do\n"
            "    diff <(curl -s \"%(php)s/rest.php?api=%(table)s$q\") \\\n"
            "         <(curl -s \"%(go)s/rest.php?api=%(table)s$q\") || echo \"DIVERGES: $q\";\n"
            "  done\n"
            "Every one empty. Those cover: the per/limit clamp to 1..500 and per winning over limit,\n"
            "p>=1, ordering only by a REAL column, filtering only by a REAL non-reserved column\n"
            "(`key` is reserved — it must NOT filter), and the `filter` field carrying \":f_\" names.\n",
        "read":
            "%(boot)s\nEQUIVALENCE-DIFF — drive THIS verb, hit and miss (real id %(id)s in `%(table)s`):\n"
            "  diff <(curl -s '%(php)s/rest.php?api=%(table)s&id=%(id)s') \\\n"
            "       <(curl -s '%(go)s/rest.php?api=%(table)s&id=%(id)s')\n"
            "  diff <(curl -s '%(php)s/rest.php?api=%(table)s&id=999999999') \\\n"
            "       <(curl -s '%(go)s/rest.php?api=%(table)s&id=999999999')\n"
            "  diff <(curl -s -o /dev/null -w '%%{http_code}' '%(php)s/rest.php?api=%(table)s&id=999999999') \\\n"
            "       <(curl -s -o /dev/null -w '%%{http_code}' '%(go)s/rest.php?api=%(table)s&id=999999999')\n"
            "  (404 + {\"error\":\"not found\",...} from BOTH)\n"
            "  diff <(curl -s '%(php)s/rest.php?api=nosuchtable') <(curl -s '%(go)s/rest.php?api=nosuchtable')\n"
            "  (the unknown-table 404 falls through to the tail echo — same bytes, same status)\n"
            "%(nopk)s",
        "create":
            "%(boot)s\nEQUIVALENCE-DIFF — POST to BOTH scratch servers and diff body AND status:\n"
            "  diff <(curl -s -X POST -H 'Content-Type: application/json' -d '{\"%(col)s\":\"eqtest\"}' \\\n"
            "            '%(php)s/rest.php?api=%(table)s') \\\n"
            "       <(curl -s -X POST -H 'Content-Type: application/json' -d '{\"%(col)s\":\"eqtest\"}' \\\n"
            "            '%(go)s/rest.php?api=%(table)s')\n"
            "  (201 from both — check with -o /dev/null -w '%%{http_code}')\n"
            "Then its 400s, which are DIFFERENT bytes from the success (see REPLY ENCODING above —\n"
            "they are COMPACT and carry NO trailing newline):\n"
            "  diff <(curl -s -X POST -H 'Content-Type: application/json' -d 'not-json' \\\n"
            "            '%(php)s/rest.php?api=%(table)s') \\\n"
            "       <(curl -s -X POST -H 'Content-Type: application/json' -d 'not-json' \\\n"
            "            '%(go)s/rest.php?api=%(table)s')            # 400 'body must be a JSON object'\n"
            "  diff <(curl -s -X POST -H 'Content-Type: application/json' -d '{\"nosuchcol\":1}' \\\n"
            "            '%(php)s/rest.php?api=%(table)s') \\\n"
            "       <(curl -s -X POST -H 'Content-Type: application/json' -d '{\"nosuchcol\":1}' \\\n"
            "            '%(go)s/rest.php?api=%(table)s')            # 400 'no valid columns' + the column list\n"
            "Compare the rows the two scratch dbs now hold, allowing ONLY clock columns to differ.\n"
            "%(auth)s",
        "update":
            "%(boot)s\nEQUIVALENCE-DIFF — PUT and PATCH against BOTH scratch servers:\n"
            "  for m in PUT PATCH; do\n"
            "    diff <(curl -s -X $m -H 'Content-Type: application/json' -d '{\"%(col)s\":\"eqtest\"}' \\\n"
            "              '%(php)s/rest.php?api=%(table)s&id=%(id)s') \\\n"
            "         <(curl -s -X $m -H 'Content-Type: application/json' -d '{\"%(col)s\":\"eqtest\"}' \\\n"
            "              '%(go)s/rest.php?api=%(table)s&id=%(id)s') || echo \"DIVERGES: $m\";\n"
            "  done\n"
            "Then each 400 (COMPACT, NO trailing newline — see REPLY ENCODING above):\n"
            "  ...&id= omitted entirely                       # 400 'update needs a single-column pk and ?id='\n"
            "  ...&id=%(id)s with body 'not-json'             # 400 'body must be a JSON object'\n"
            "  ...&id=%(id)s with body '{\"%(pk)s\":9}'          # 400 'no valid columns to update' (the pk is\n"
            "                                                 #      stripped: it is never settable)\n"
            "Diff each of those, body and status, on both servers. Compare the rows the two scratch dbs\n"
            "now hold, allowing ONLY clock columns to differ.\n"
            "%(auth)s",
        "delete":
            "%(boot)s\nEQUIVALENCE-DIFF — DELETE against BOTH scratch servers. NOTE from REPLY ENCODING above:\n"
            "this verb's SUCCESS reply is COMPACT (json_encode with no flags) + a trailing newline —\n"
            "it is NOT pretty-printed like create/update. Diff the bytes, do not assume:\n"
            "  diff <(curl -s -X DELETE '%(php)s/rest.php?api=%(table)s&id=%(id)s') \\\n"
            "       <(curl -s -X DELETE '%(go)s/rest.php?api=%(table)s&id=%(id)s')\n"
            "  diff <(curl -s -X DELETE '%(php)s/rest.php?api=%(table)s&id=999999999') \\\n"
            "       <(curl -s -X DELETE '%(go)s/rest.php?api=%(table)s&id=999999999')\n"
            "  (a miss still succeeds with deleted=0 — no 404 here; diff proves it)\n"
            "  diff <(curl -s -X DELETE '%(php)s/rest.php?api=%(table)s') \\\n"
            "       <(curl -s -X DELETE '%(go)s/rest.php?api=%(table)s')\n"
            "  (400 'delete needs a single-column pk and ?id=' — COMPACT, NO trailing newline)\n"
            "  diff <(curl -s -X DELETE '%(php)s/rest.php?api=nosuchtable') \\\n"
            "       <(curl -s -X DELETE '%(go)s/rest.php?api=nosuchtable')\n"
            "  (unknown table -> the tail 404)\n"
            "Check the STATUS of each with -o /dev/null -w '%%{http_code}', and compare the rows the two\n"
            "scratch dbs now hold: the same row, and ONLY that row, must be gone from each.\n"
            "%(auth)s",
    }
    auth_note = (
        "AUTHORIZATION — this verb is a WRITE, so congruency_rest_authorized gates it. With stock\n"
        "config it does NOT refuse: CONGRUENCY_AUTH_OVERRIDE is TRUE by default\n"
        "(boot/constants.default.json), so the 401 above is unreachable. Diff it BOTH ways:\n"
        "  printf '{\"CONGRUENCY_AUTH_OVERRIDE\": false}\\n' > /tmp/eq-cfg.json\n"
        "  (boot BOTH servers with CONGRUENCY_CONFIG=/tmp/eq-cfg.json, then repeat the calls above\n"
        "   with no key: each must return the compact 401 {\"error\":\"authorization required for\n"
        "   writes\",\"method\":...,\"hint\":...} + \"\\n\", byte-identical, from both servers.)\n")
    nopk_note = ("  diff <(curl -s '%s/rest.php?api=%s&id=1') <(curl -s '%s/rest.php?api=%s&id=1')\n"
                 "  (`%s` has NO pk, so ?id= falls through to the LIST branch — prove the Go port falls\n"
                 "   through the same way)\n" % (PHP_BASE, fx["no_pk_table"], GO_BASE, fx["no_pk_table"],
                                                 fx["no_pk_table"])) if fx["no_pk_table"] else \
                ("  (no REST-visible table lacks a primary key in this db, so the read verb's\n"
                 "   no-pk fall-through to the list branch has no live fixture — pin it with a Go test\n"
                 "   against a scratch table that has no pk.)\n")

    units = []
    for name, shape, spans, what in CRUD_VERBS:
        sites = [s for sp in spans for s in enc.get(sp, [])]
        writes = name in ("create", "update", "delete")
        subst = {"boot": booting(scratch=writes), "php": PHP_BASE, "go": GO_BASE, "table": fx["table"],
                 "pk": fx["pk"], "id": fx["id"], "col": fx["col"], "val": fx["val"],
                 "deny": ", ".join(deny), "deny_re": "|".join(deny),
                 "auth": auth_note if writes else "", "nopk": nopk_note if name == "read" else ""}
        gate = gates[name] % subst
        units.append(unit(
            "server", "crud", name,
            "boot/rest.php  (the generic ?api %s branch of congruency_rest_dispatch)" % name,
            "Port ?api CRUD verb %s to Go, byte-identical JSON vs rest.php" % name,
            "THE PHP ORIGINAL — the contract, as rest.php implements it:\n  %s\n  %s\n\n%s"
            % (shape, what, encoding_block(sites)),
            gate))
    return units


def php_units(fx, pages_for_tags):
    """The declared boot/engine units. Every path is verified against the checkout — a description of
    a file that is not there would be a claim this tool cannot stand behind."""
    some_pages = " ".join(str(p) for p in pages_for_tags[:4]) or str(fx.get("page", ""))
    units = []
    for bucket, name, rel, headline, what, gate in PHP_UNITS:
        path = os.path.join(SOURCE, rel)
        if not os.path.isfile(path):
            die("declared PHP unit %s does not exist at %s — this decomposer's map of the render "
                "chain is stale; re-read the source before filing tickets that describe it"
                % (name, rel))
        subst = {"php": PHP_BASE, "go": GO_BASE, "table": fx["table"], "pk": fx["pk"], "id": fx["id"],
                 "route": fx["route"], "page": fx.get("page", ""), "db": CONG_DB,
                 "pages": some_pages, "php_bin": PHP_BIN}
        units.append(unit(bucket, "boot" if name.startswith("boot_") else "engine", name,
                          rel, headline,
                          "WHAT IT DOES (%s):\n  %s" % (rel, what),
                          "%s\n%s" % (booting(scratch=(name == "boot_monitor")), gate % subst)))
    return units


def page_units(con, tags_by_page):
    units = []
    for (doc, title, desc, tmpl) in con.execute(
            "SELECT DocumentID, Title, Description, TemplateID FROM Documents ORDER BY DocumentID"):
        embedded = tags_by_page.get(doc, [])
        tag_text = ("  " + ", ".join(embedded)) if embedded else "  (none — this template embeds no tags)"
        units.append(unit(
            "server", "page", doc,
            "the `Documents` row DocumentID=%s (TemplateID=%s), in the state db" % (doc, tmpl),
            "Port page ?page=%s to Go, byte-identical HTML vs the PHP render" % doc,
            "THE PHP ORIGINAL — the contract, read from this page's `Documents` row:\n"
            "  DocumentID  : %s\n  Title       : %s\n  Description : %s\n  TemplateID  : %s\n\n"
            "The page is its Document_Templates.Content for that TemplateID, with every <<<Tag>>>\n"
            "placeholder in it executed. Port the PAGE — the plumbing that resolves ?page=%s to its row\n"
            "+ template and renders it.\n\n"
            "TAGS THIS PAGE'S TEMPLATE EMBEDS (read out of Document_Templates.Content with the engine's\n"
            "own pattern, /<<<[a-zA-Z]+(\\([A-Za-z0-9]*\\))*\\>>>/):\n%s\n\n"
            "Each is its OWN unit in the `tags` bucket (#226). They are filed AFTER this one because\n"
            "#230 orders the emission by layer (db -> server -> tags) — but this page's gate cannot go\n"
            "empty until they render, so this unit SETTLES after them. That is not a contradiction: the\n"
            "filing order is the layer order, and the build order is the DEPENDS ON list below."
            % (doc, title, desc, tmpl, doc, tag_text),
            "EQUIVALENCE-DIFF — both servers on the SAME db, byte-identical HTML:\n"
            "  diff <(curl -s '%s/?page=%s') <(curl -s '%s/?page=%s')\n"
            "  diff <(curl -s -o /dev/null -w '%%{http_code}' '%s/?page=%s') \\\n"
            "       <(curl -s -o /dev/null -w '%%{http_code}' '%s/?page=%s')\n"
            "Whitespace counts. Diff the raw bytes, not a pretty-printed DOM — and diff the STATUS too."
            % (PHP_BASE, doc, GO_BASE, doc, PHP_BASE, doc, GO_BASE, doc)))
    return units


def tag_harness():
    """The #282 tag-equivalence harness — VERIFIED to exist and to still define the test this tool's
    gate names, and its override knobs READ OUT OF IT rather than remembered.

    This mirrors what php_units() does for the render chain and what fn_span() does for rest.php: a
    unit ticket that names a gate command is a promise the command runs, so the file behind it is
    checked at enumeration time and a stale map is a hard error, never a silent claim. If this tool
    printed `go test -run TestTagEquivalence` after #282's test had been renamed, every tag unit it
    filed would carry a gate that exits "no tests to run" — a gate that passes while proving
    nothing, which is the exact class of defect #323 exists to remove.

    The knobs are derived because the gate must not name one the harness does not read. #323's own
    text sketches the gate as `CONGRUENCY_SQLITE=<state db> go test ...`, and CONGRUENCY_SQLITE is
    NOT among the four the harness reads (it resolves the db through equivDBPath(), whose override
    is CONGRUENCY_EQUIV_DB — congruency-go/tags/equivalence_test.go:199-206). Setting
    CONGRUENCY_SQLITE would do nothing at all, and a pair that pointed it at a scratch db and saw a
    PASS would be reading a result from the wrong database. So the names come from the source."""
    if not os.path.isfile(TAG_HARNESS):
        die("the tag-equivalence harness (#282) is not at %s — it is the ONLY gate that settles a "
            "tag unit, so this tool will not file tag tickets naming a gate that is not there; "
            "re-read congruency-go/tags/ before filing" % TAG_HARNESS_FROM_ROOT)
    src = open(TAG_HARNESS, encoding="utf-8", errors="replace").read()
    if not re.search(r"\bfunc\s+" + re.escape(TAG_TEST_NAME) + r"\s*\(", src):
        die("%s no longer defines func %s( — this decomposer's map of the #282 tag gate is stale, "
            "and every tag unit it filed would name a `go test -run %s` that matches no test and "
            "exits 0 without measuring anything; re-read the harness before filing"
            % (TAG_HARNESS_FROM_ROOT, TAG_TEST_NAME, TAG_TEST_NAME))
    knobs = sorted(set(re.findall(r"os\.Getenv\(\"([A-Z_0-9]+)\"\)", src)))
    if not knobs:
        die("%s reads no os.Getenv override at all — this tool's map of the #282 harness is stale; "
            "re-read it before filing tickets that describe its knobs" % TAG_HARNESS_FROM_ROOT)
    return {"rel": TAG_HARNESS_FROM_ROOT, "test": TAG_TEST_NAME, "cmd": TAG_GATE_CMD, "knobs": knobs}


def go_registered_tags(found):
    """The tag names the Go port has REGISTERED today, scanned out of congruency-go/tags/*.go.

    `Register(name, factory)` is the registry's only writer (engine.go:1342-1368), called from an
    init() in each tag's own file, so the set of Register("<Name>", ...) call sites IS the set of
    tags tags.IsPorted() answers true for — which is exactly what the #282 harness measures and what
    it SKIPs. Reporting it lets each tag unit say whether its own dependencies are satisfied yet.

    Static, and THREE-WAY conservative, because a static scan of call sites is not the registry:
      * comment lines are skipped, so a docblock naming Register is not a registration;
      * a line calling panics(...) is skipped — engine.go's own self-checks REGISTER-TO-PROVE-IT-
        FAILS, e.g. `check("Register: a nil factory panics", panics(func() {
        Register("NeverRegistered", nil) }), true)` (engine.go:4402). That registration is rejected
        by design, and counting it would report a tag that does not exist as ported;
      * the result is intersected with the scanned tag universe, so a name that is not a real tag
        under TAGS_DIR can never be reported as one.
    It is a REPORTING aid and nothing more. The GATE is `go test`, which asks the real registry at
    run time; this only decides how a dependency is LABELLED in a ticket body."""
    names = set()
    if not os.path.isdir(GO_TAGS_DIR):
        return names
    for f in sorted(os.listdir(GO_TAGS_DIR)):
        if not f.endswith(".go"):
            continue
        for line in open(os.path.join(GO_TAGS_DIR, f), encoding="utf-8", errors="replace"):
            s = line.lstrip()
            if s.startswith("//") or s.startswith("*") or "panics(" in line:
                continue
            names.update(GO_REGISTER_RE.findall(line))
    return names & set(found)


def tag_emits(found):
    """{tag: [other tags whose invocation this tag's own output embeds]} — a tag's REAL tag-on-tag
    prerequisites, derived from the PHP rather than assumed.

    WHY THIS IS A DEPENDENCY AT ALL. Tag_Wrapper::execute_all_tags RE-SCANS what a tag returns and
    substitutes any invocation it finds there (lib/TagLoader/Tag/Tag_Wrapper.php; the recursion is
    the `add_child` + recurse at $depth+1 step). So a tag whose get_document() emits <<<Other>>>
    does not render its own final bytes — Other's bytes land inside them. BodyTag is the canonical
    case: its whole body is `return "<<<ContentTag(" . $this->body . ")>>>";` (BodyTag.php:19-21), so
    BodyTag's bytes ARE ContentTag's, and BodyTag cannot be measured until ContentTag is registered.

    HOW IT IS READ. php_code_only() blanks comments and keeps string bodies, because an emitted
    invocation lives in a string literal while a DOCUMENTED one lives in a docblock — and the
    difference decides whether the engine ever sees it. Style.php is the file that proves both
    halves: its docblock says "Every page template embeds <<<Style>>> ... (like <<<TitleTag>>>)"
    (Style.php:8-9), which the engine never sees and which is NOT a dependency, while its return
    concatenates the literal "<<<TelemetryBeacon>>>" (Style.php:28), which the engine DOES
    substitute and which IS one. Names are then kept only if they are real scanned tags, so the
    engine's non-matches (`<<<Tag>>>`, `<<<Config...>>>` — see TAG_EMIT_RE) drop out.

    LIMIT, STATED PLAINLY BECAUSE THE TICKETS REST ON IT: this is a static scan. A name assembled
    entirely at run time (`"<<<" . $name . ">>>"`) has no literal for it to see and would be missed.
    No tag under TAGS_DIR builds one that way in this checkout — every emitted invocation has a
    literal `<<<Name` prefix — but the unit ticket tells the porter to read the source rather than
    trust this list as complete."""
    emits = {}
    for name in sorted(found):
        code = php_code_only(open(os.path.join(SOURCE, found[name]), encoding="utf-8",
                                  errors="replace").read())
        emits[name] = sorted(set(t for t in TAG_EMIT_RE.findall(code) if t in found and t != name))
    return emits


def scan_tags():
    """Every tag under TAGS_DIR, discovered the way the live engine discovers them: TagList::scan
    (invocators/tags/dev/TagList.php) walks TAGS_DIR recursively with a RecursiveIteratorIterator,
    keeps any *.php whose source contains `Tag_Interface`, and keys it by basename-minus-.php (so
    two files with the same basename collapse to one tag, exactly as they do here)."""
    if not os.path.isdir(TAGS_DIR):
        die("tag directory not found at %s (configure.php defines TAGS_DIR as invocators/tags/) — "
            "cannot enumerate the tags" % TAGS_DIR)
    found = {}
    for root, _dirs, files in os.walk(TAGS_DIR):
        for f in sorted(files):
            if not f.lower().endswith(".php"):
                continue
            path = os.path.join(root, f)
            if "Tag_Interface" not in open(path, encoding="utf-8", errors="replace").read():
                continue
            found.setdefault(f[:-4], os.path.relpath(path, SOURCE))
    if not found:
        die("no *.php under %s contains Tag_Interface — cannot enumerate the tags" % TAGS_DIR)
    return found


def tag_units(pages_by_tag, found, emits, registered, harness):
    """One unit per scanned tag, each gated on the #282 harness — see gate_block()."""
    units = []
    for name in sorted(found):
        rel = found[name]
        pages = pages_by_tag.get(name, [])
        if pages:
            inpage = ("PAGES WHOSE TEMPLATE EMBEDS <<<%s>>> (read out of Document_Templates with the\n"
                      "engine's own pattern). These are CONTEXT, not a gate — they tell you which argument\n"
                      "forms the live site actually uses, so you port the ones that matter:\n%s\n"
                      % (name, textwrap.fill(", ".join(str(p) for p in pages), width=94,
                                             initial_indent="  ", subsequent_indent="  ")))
        else:
            inpage = ("PAGES WHOSE TEMPLATE EMBEDS <<<%s>>>: none today — no Document_Templates row\n"
                      "mentions it.\n" % name)
        units.append(unit(
            "tags", "tag", name, rel,
            "Port tag %s to Go — settle on the #282 go-test harness, NOT a whole-page diff" % name,
            "THE PHP ORIGINAL — the contract:\n  %s\n\nIt is a `Tag_Interface` tag; the engine substitutes\n"
            "it wherever <<<%s>>> appears in a template, and the gallery renders it standalone at\n"
            "?page=tags&tag=%s (TagList::scan finds it under TAGS_DIR, so that URL resolves). Port THIS\n"
            "tag only — its arguments, its SQL, its markup, and its empty/error state (a tag that degrades\n"
            "gracefully against a missing dependency must degrade IDENTICALLY in Go; see\n"
            "tools/tag_selfcheck.py for what each tag depends on).\n\n%s"
            % (rel, name, name, inpage),
            gate_block(name, emits.get(name, []), registered, harness)))
    return units


def registering_block(name, harness):
    """How a tag enters the registry the harness measures. Without this the gate cannot even be
    attempted: an unregistered tag is SKIPped by the sweep, and a skip is a PASS."""
    return (
        "REGISTERING %s (the gate cannot pass until you do this):\n"
        "  Add an init() to your tag's own file in %s/tags/, exactly as every ported tag does\n"
        "  (congruency-go/tags/contenttag.go:151-153 is a one-tag example, and engine.go:1374-1385\n"
        "  registers the ten #226 landed together):\n"
        "\n"
        "      func init() {\n"
        "          Register(\"%s\", func(e *Engine, a *TagArguments) Tag { return &%sTag{e: e, args: a} })\n"
        "      }\n"
        "\n"
        "  Register is the registry's ONLY writer (engine.go:1342-1368) and it PANICS on a duplicate\n"
        "  name, so register in exactly ONE place. Registering is what flips tags.IsPorted(\"%s\") to\n"
        "  true, and THAT is what makes the harness measure this tag instead of skipping it — no edit\n"
        "  to %s is needed, or wanted.\n"
        % (name, GO_FROM_ROOT, name, name, name, harness["rel"]))


def deps_block(name, deps, registered):
    """The tag-on-tag prerequisites — see tag_emits() for how they are derived."""
    if not deps:
        return (
            "TAGS THIS TAG DEPENDS ON: none. Its own output embeds no other tag's invocation (derived\n"
            "  from its PHP source, comments excluded — see the decomposer's tag_emits()), so nothing\n"
            "  else has to be registered before the gate can measure it.\n")
    lines = ["TAGS THIS TAG DEPENDS ON — PORT AND REGISTER THESE FIRST:"]
    for d in deps:
        lines.append("  - %-24s %s" % (d, "already registered in the Go engine today"
                                       if d in registered else
                                       "NOT registered yet — the gate CANNOT pass until it is"))
    lines.append(
        "\n  This is not bookkeeping: Tag_Wrapper::execute_all_tags RE-SCANS whatever a tag returns and\n"
        "  substitutes any invocation it finds there, so the tag(s) above render INSIDE this tag's\n"
        "  bytes. BodyTag is the clearest case — its entire body is\n"
        "  `return \"<<<ContentTag(\" . $this->body . \")>>>\";` (invocators/tags/document/BodyTag.php:19-21),\n"
        "  so BodyTag's bytes ARE ContentTag's bytes and no correct BodyTag render exists until\n"
        "  ContentTag is registered. If a dependency is missing, the Go engine emits its marked\n"
        "  divergence notice where the tag should be, the harness reports a BYTE MISMATCH, and the\n"
        "  mismatch is in the DEPENDENCY, not in your port.\n"
        "  The list is derived from this tag's PHP source (string literals, comments excluded) and is\n"
        "  a floor, not a ceiling — read the source before trusting it as complete.")
    return "\n".join(lines) + "\n"


def gate_block(name, deps, registered, harness):
    """THE tag gate (#323). The whole-page diff is refused here, by name, with its evidence.

    #323's finding, in one line: a tag unit that says only "byte-equivalent vs the PHP render" gets
    read by a blind auditor as a whole-page byte diff of ?page=tags — which is STRUCTURALLY
    non-empty for every tag, including byte-perfect merged ones, because the Go server's page chrome
    is not the PHP's. So correct ports were rejected and #310/#311/#312 had to be hand-harvested
    against the harness that was already authoritative. This block names the harness, shows the
    PASS, and refuses the diff explicitly — a gate stated only as a positive gets re-derived by the
    next reader into the same wrong diff."""
    return (
        "THE GATE — THE ONLY THING THAT SETTLES THIS TICKET. Run the #282 tag-equivalence harness\n"
        "from the repo root (the directory holding registry.json):\n"
        "\n"
        "    %s\n"
        "\n"
        "SETTLE WHEN THAT COMMAND PASSES with %s registered. The harness answers exactly this\n"
        "unit's question — it renders THIS tag through tags.RenderTag (the same entry server.go's\n"
        "handleTagsPage calls) and compares it byte-for-byte against the live PHP's bytes for\n"
        "?page=tags&tag=%s. Paste this tag's own lines as the evidence:\n"
        "\n"
        "    --- PASS: %s/%s\n"
        "        equivalence_test.go:NNN: IDENTICAL: <N>B byte-for-byte\n"
        "\n"
        "  A SKIP IS NOT A PASS. A line reading `--- SKIP: %s/%s` with \"no Go port\n"
        "  yet\" means the tag is NOT registered and NOTHING was measured — and the sweep still exits 0,\n"
        "  green. Registering it (below) is what turns that skip into a measurement. Read this tag's own\n"
        "  line; never the exit code alone.\n"
        "\n"
        "DO NOT WHOLE-PAGE-DIFF ?page=tags. THIS IS NOT THE GATE, AND A NON-EMPTY DIFF HERE IS NOT A\n"
        "DEFECT IN YOUR PORT:\n"
        "\n"
        "    diff <(curl -s '%s/?page=tags&tag=%s') <(curl -s '%s/?page=tags&tag=%s')   # <-- WRONG GATE\n"
        "\n"
        "  That diff is STRUCTURALLY NON-EMPTY for EVERY tag — including tags already merged as\n"
        "  byte-perfect: #323 measured ~6205B of difference on CategoryView, TreeView and TicketList,\n"
        "  all three of them correct. The two sides are not the same kind of document: the PHP URL returns a\n"
        "  full CMS page (Controller::control's chrome, then the gallery, then the tag's bytes, then\n"
        "  the template tail), while the Go server wraps the tag engine's render in its OWN frame and\n"
        "  says so in its source — congruency-go/server.go:820-823 emits the comment \"the\n"
        "  doctype/title/h1 frame around it is this server's own: the CMS Controller::control() page\n"
        "  chrome is still not reproduced here.\" The difference is that missing chrome. It is a known,\n"
        "  separate, un-ported piece of the server; it is not this tag, it is not yours to fix here,\n"
        "  and no correct port can ever make that diff empty. Settling on it is what stalled the tag\n"
        "  fan-out and forced #310/#311/#312 to be hand-harvested (#323).\n"
        "\n"
        "  The harness exists precisely because the tag's bytes are a SLICE of that page: it cuts the\n"
        "  slice with TagList.php's own anchors (:62 and :76) and a page tail it MEASURES at run time,\n"
        "  fetches PHP twice around the Go render so a concurrent write shows up as VOLATILE instead of\n"
        "  a false failure, and compares only the tag. That is the comparison this ticket is asking for.\n"
        "  Read %s before arguing with its verdict.\n"
        "\n"
        "%s"
        "\n"
        "%s"
        "\n"
        "WHAT THE HARNESS DOES NOT MEASURE — port these anyway, do not bolt them onto the gate:\n"
        "  * ARGUMENTS. The gallery constructs the selected tag standalone (`new $sel(null)`,\n"
        "    TagList.php:67-68), so the sweep measures the ARGUMENT-LESS render only. If this tag takes\n"
        "    arguments, port them faithfully against the PHP source and the argument forms the pages\n"
        "    above use; a Go unit test of your own is the right place to pin them.\n"
        "  * THE IN-PAGE SUBSTITUTION SITES. Diffing ?page=<id> on both servers is the same broken\n"
        "    whole-page comparison as above and fails for the same chrome reason. Those pages settle on\n"
        "    their own page units, once the chrome is ported.\n"
        "\n"
        "IF THE HARNESS ITSELF SKIPS EVERYTHING (\"no API key\", \"state db absent\", \"server\n"
        "unreachable\", \"TAGS_DIR lists no tags\") it measured NOTHING and this ticket does not settle.\n"
        "Its four guards are deliberate — it never false-fails in CI — so a green run that skipped is\n"
        "not evidence. Fix the environment: boot the PHP original the way tools/serve.py does\n"
        "  ( cd %s && %s -S 127.0.0.1:%s boot/router.php )\n"
        "and re-run. The harness resolves the db, the app root and the URL itself; its overrides are\n"
        "%s\n"
        "and NOTHING ELSE — in particular CONGRUENCY_SQLITE is NOT one of them, so prefixing the gate\n"
        "with it changes nothing and would quietly measure the default database.\n"
        % (harness["cmd"], name, name,
           harness["test"], name, harness["test"], name,
           PHP_BASE, name, GO_BASE, name,
           harness["rel"],
           registering_block(name, harness),
           deps_block(name, deps, registered),
           SOURCE_FROM_ROOT, PHP_BIN, PHP_BASE.rsplit(":", 1)[-1],
           ", ".join("$" + k for k in harness["knobs"])))


def template_tag_map(con):
    """(tags_by_page, pages_by_tag) — which tags each page's template embeds, read from
    Document_Templates.Content with the ENGINE's own invocation pattern (see TAG_INVOCATION_RE).
    This is what makes a page's dependency list real instead of guessed."""
    content = dict(con.execute("SELECT TemplateID, Content FROM Document_Templates"))
    tags_by_page, pages_by_tag = {}, {}
    for doc, tmpl in con.execute("SELECT DocumentID, TemplateID FROM Documents ORDER BY DocumentID"):
        names = sorted(set(TAG_INVOCATION_RE.findall(content.get(tmpl) or "")))
        tags_by_page[doc] = names
        for n in names:
            pages_by_tag.setdefault(n, []).append(doc)
    return tags_by_page, pages_by_tag


def enumerate_units(con, enc, deny, fx):
    tags_by_page, pages_by_tag = template_tag_map(con)
    # a real page id for the boot/engine gates: prefer one that embeds tags, so a render gate renders
    fx["page"] = next((d for d, t in tags_by_page.items() if t), next(iter(tags_by_page), ""))
    found = scan_tags()
    harness = tag_harness()                 # hard-fails if the #282 gate this tool names is stale
    emits = tag_emits(found)
    registered = go_registered_tags(found)
    units = (helper_units(enc, fx) + route_units(con, enc) + crud_units(enc, fx, deny)
             + php_units(fx, [d for d, t in tags_by_page.items() if t])
             + page_units(con, tags_by_page)
             + tag_units(pages_by_tag, found, emits, registered, harness))
    units.sort(key=lambda u: u["sort"])
    return units, tags_by_page, emits, registered, harness


# ── the per-unit ticket body ─────────────────────────────────────────────────────────────────────
def unit_body(u, deps):
    dep_text = ("DEPENDS ON (build these first — each is its own unit ticket unless marked):\n%s"
                % "\n".join("  - %s" % d for d in deps)) if deps else \
               "DEPENDS ON: nothing — this unit is a leaf of the port; it can start now."

    # A tag unit is gated by the #282 harness, NOT by a diff, so it takes the harness wording for
    # both the build loop and the settle line. The generic text below says "EVERY diff above is
    # EMPTY", which on a tag unit would contradict its own gate block and send the reader straight
    # back to the whole-page diff that #323 exists to stop — the artifact must not argue with itself.
    if u["utype"] == "tag":
        build = ("THE BUILD — small, and ITERATIVE:\n"
                 "  1. Implement ONLY this tag in the Go port, and REGISTER it (see THE GATE below).\n"
                 "  2. Run the harness command in THE GATE below.\n"
                 "  3. If this tag's line is a BYTE MISMATCH, fix the Go side and go back to 2 — the\n"
                 "     harness prints the first differing lines. The PHP is the spec: when they disagree,\n"
                 "     the Go port is wrong; never 'improve' the behaviour here. If the PHP is genuinely\n"
                 "     defective, file a separate bug ticket and port the defect faithfully.\n")
        settle = ("SETTLING: this ticket settles when — and only when — the harness command in THE GATE\n"
                  "above PASSES for this tag. Paste the command you ran and this tag's own PASS/IDENTICAL\n"
                  "line as the evidence. Do NOT settle on a whole-page diff of ?page=tags, and do NOT\n"
                  "refuse a correct port because that diff is non-empty: it is non-empty for every tag,\n"
                  "always, for a reason THE GATE explains and no port can fix. A SKIP is not a PASS.\n")
    else:
        build = ("THE BUILD — small, and ITERATIVE:\n"
                 "  1. Implement ONLY this unit in the Go port.\n"
                 "  2. Run the gate below, PHP original vs Go port, over the SAME database.\n"
                 "  3. If any diff is non-empty, fix the Go side and go back to 2. The PHP is the spec: when they\n"
                 "     disagree, the Go port is wrong — never 'improve' the behaviour here. If the PHP is\n"
                 "     genuinely defective, file a separate bug ticket and port the defect faithfully.\n")
        settle = ("THE GATE (how this ticket settles): EVERY diff above is EMPTY. Not 'equivalent', not 'looks\n"
                  "right' — empty. Paste the exact diff invocations you ran and their empty output as the\n"
                  "evidence. A gate that does not exercise this unit is not this unit's gate: if you cannot make\n"
                  "a diff here run against THIS unit, say so on the ticket rather than settling on a diff that\n"
                  "would be empty even with the unit unimplemented.\n")
    return (
        "Port ONE unit of congruency to Go. ONE. This ticket is deliberately SMALL: porting a whole\n"
        "layer at once is what #230 corrected (~150 units exist; a layer-sized tournament fails at that\n"
        "size). Do not port anything outside this unit.\n"
        "\n"
        "UNIT KEY : %s\n"
        "           (the decomposer's idempotency marker — it lives in this ticket's TITLE. Do not edit\n"
        "            the title, or the unit will be re-filed as a duplicate.)\n"
        "LAYER    : %s — ticket #%d (%s)\n"
        "PHP SOURCE: %s\n"
        "\n"
        "%s\n"
        "\n"
        "%s\n"
        "\n"
        "%s"
        "\n"
        "%s\n"
        "%s"
        "\n"
        "Kind is `build` (a pair: coder + adversarial tester). This unit gets a tournament only if\n"
        "someone judges it genuinely worth one — that is the exception on #230, not the default.\n"
        "\n"
        "Filed mechanically by %s under ticket #%d."
        % (u["key"], u["bucket"], u["layer_ticket"], u["layer_text"], u["source"],
           u["contract"], dep_text, build, u["probe"], settle, SELF_FROM_ROOT, DECOMPOSER_TICKET))


def deps_for(u, units, tags_by_page, emits=None):
    """A unit's REAL prerequisites, by key — traced through the code, not assumed from the bucket.

    The trap this avoids: ?page= never touches congruency_rest_dispatch. boot/router.php calls the
    dispatch ONLY when ?api= or ?route= is set (and exits); otherwise it calls Controller::control().
    A page therefore depends on the boot + Controller + DocumentManager + Document chain and on the
    tag engine — never on the rest dispatch."""
    keys = {x["key"] for x in units}
    out = []
    if u["utype"] == "route":
        out.append("go-port:db:helper:congruency_rest_route")
        if (u.get("auth") or "").lower() == "token":
            out.append("go-port:server:helper:congruency_rest_authorized")
    elif u["utype"] == "crud":
        out.append("go-port:server:helper:congruency_rest_dispatch")
        if u["name"] in ("create", "update", "delete"):
            out.append("go-port:server:helper:congruency_rest_authorized")
    elif u["utype"] == "helper":
        if u["name"] in ("congruency_rest_route", "congruency_rest_apikey", "congruency_rest_authorized"):
            out.append("go-port:server:boot:boot_router")          # nothing is reached without the boot
        if u["name"] == "congruency_rest_authorized":
            out += ["go-port:server:helper:congruency_rest_apikey", "go-port:server:boot:boot_vault",
                    "go-port:server:boot:boot_configure"]          # the override constant is configure's
        if u["name"] == "congruency_telemetry_record":
            out.append("go-port:server:boot:boot_monitor")         # congruency_telemetry_ingest lives there
        if u["name"] == "congruency_rest_dispatch":
            out.append("go-port:server:boot:boot_configure")       # CONGRUENCY_SQLITE + the constants
    elif u["utype"] in ("boot", "engine"):
        chain = {
            "boot_router": ["go-port:server:boot:boot_configure", "go-port:server:boot:boot_shim",
                            "go-port:server:boot:boot_monitor", "go-port:server:engine:engine_classloader",
                            "go-port:server:engine:engine_pom"],
            "boot_monitor": ["go-port:server:boot:boot_configure"],
            "boot_vault": ["go-port:server:boot:boot_configure"],
            "boot_shim": ["go-port:server:boot:boot_configure"],
            "engine_pom": ["go-port:server:engine:engine_classloader"],
            "engine_controller_control": ["go-port:server:engine:engine_validatefields",
                                          "go-port:server:engine:engine_documentmanager",
                                          "go-port:server:engine:engine_pom"],
            "engine_documentmanager": ["go-port:server:engine:engine_documentdao",
                                       "go-port:server:engine:engine_document_tostring"],
            "engine_documentdao": ["go-port:server:boot:boot_shim"],
            "engine_document_tostring": ["go-port:tags:engine:engine_tag_wrapper",
                                         "go-port:tags:engine:engine_tag_interface"],
            "engine_tag_wrapper": ["go-port:tags:engine:engine_tag_parser",
                                   "go-port:tags:engine:engine_tag_interface",
                                   "go-port:server:engine:engine_pom"],
            "engine_tag_parser": ["go-port:tags:engine:engine_tagarguments"],
        }
        out += chain.get(u["name"], [])
    elif u["utype"] == "page":
        # the chain a ?page= request ACTUALLY runs (boot/router.php:40 -> Controller::control), plus
        # the tag engine and THIS page's own embedded tags — derived, not assumed.
        out += ["go-port:server:boot:boot_router",
                "go-port:server:engine:engine_controller_control",
                "go-port:server:engine:engine_documentmanager",
                "go-port:server:engine:engine_document_tostring",
                "go-port:tags:engine:engine_tag_wrapper"]
        out += ["go-port:tags:tag:%s" % t for t in tags_by_page.get(u["name"], [])]
    elif u["utype"] == "tag":
        out += ["go-port:tags:engine:engine_tag_wrapper", "go-port:tags:engine:engine_tag_parser",
                "go-port:tags:engine:engine_tagarguments", "go-port:tags:engine:engine_tag_interface"]
        # The tags THIS tag's own output embeds. execute_all_tags re-scans a tag's return value and
        # substitutes what it finds there, so those tags render INSIDE this one's bytes and the #282
        # harness cannot measure this tag until they are registered — BodyTag/ContentTag is the case
        # that proves it (#323). Derived from the PHP source; see tag_emits().
        out += ["go-port:tags:tag:%s" % t for t in (emits or {}).get(u["name"], [])]
    # keep only prerequisites that are real, enumerated units; anything else would be a dependency a
    # pair cannot act on (the exact defect of telling 26 pages to build the rest dispatch first).
    seen, kept = set(), []
    for d in out:
        if d != u["key"] and d in keys and d not in seen:
            seen.add(d)
            kept.append(d)
    return kept


# ── idempotency: which unit keys are already ticketed ────────────────────────────────────────────
def keys_from_db(con):
    """Unit keys already ticketed, from EVERY status (CLOSED/DONE included — ticket.queue cannot see
    those). immutable=1 means this read creates no files and cannot see an uncheckpointed -wal;
    keys_from_queue() covers exactly that window."""
    found = set()
    for (title,) in con.execute("SELECT title FROM tickets"):
        found.update(KEY_RE.findall(title or ""))
    return found


def queue_rows(base, key):
    """Every OPEN/REQUESTED ticket row, from the LIVE ticket.queue route. None if unreadable.
    (ticket.queue's SQL selects id, kind, status, component, title, body.)"""
    try:
        return rest(base, "ticket.queue", method="GET", key=key).get("rows", [])
    except Exception as e:                                # noqa: BLE001
        step("ticket.queue unreadable at %s (%s)" % (base, e))
        return None


def queue_titles(rows):
    """Titles out of queue_rows(); None passes through so callers keep telling 'unreadable' apart
    from 'readable and empty' — the distinction --file-tickets refuses to file without."""
    return None if rows is None else [(r.get("title") or "") for r in rows]


def queue_titles_by_id(rows):
    """{id: title} out of queue_rows(), for the correction pass. Empty when the queue is unreadable:
    the db read it is unioned with still supplies candidates, and every write is guarded by its own
    journal check anyway."""
    return dict((int(r["id"]), r.get("title") or "") for r in (rows or []) if r.get("id") is not None)


def keys_from_queue(titles):
    found = set()
    for t in titles:
        found.update(KEY_RE.findall(t))
    return found


# ── the successor chain ─────────────────────────────────────────────────────────────────────────
def chain_of(subset):
    """This drain chain's name. Scoped by --subset so a `--subset tag:` drain and a full drain never
    block each other. 'successor' is never a bucket name, so a chain marker can never collide with a
    unit key."""
    return subset or "all"


def successor_key(subset, gen):
    return "go-port:successor:%s:g%d" % (chain_of(subset), gen)


def max_open_generation(titles, subset):
    """The highest successor GENERATION currently OPEN for this chain, or -1 if none.

    This carries the anti-stall rule (see the module docstring), and it does two jobs:

      1. it DERIVES a run's own generation when --gen was not given (this_generation()). The run
         asking the question is, in practice, the run a pair launched from this chain's newest open
         successor — so that successor's generation IS this run's generation. Defaulting to 0 instead
         is what stalled the chain at its first successor (#245).
      2. it is the spawn guard: a run at generation N spawns unless some open successor has
         generation > N. It deliberately does NOT count itself (gen == N) or a stale open predecessor
         (gen < N): a predecessor will never file anything again, so a naive 'does ANY open successor
         exist?' test always sees itself, never spawns, and the chain dies after one batch."""
    hi = -1
    chain = chain_of(subset)
    for t in titles:
        m = SUCC_RE.search(t)
        if m and m.group(1) == chain:
            hi = max(hi, int(m.group(2)))
    return hi


def max_generation_ever(con, titles, subset):
    """The highest successor generation this chain has EVER used — the db (ALL statuses) UNION the
    live queue — or -1 if the chain is new. Successors are minted one past this, so a generation
    whose ticket has since settled/closed never has its number re-used by a later spawn."""
    hi = -1
    chain = chain_of(subset)
    seen = [(t or "") for (t,) in con.execute("SELECT title FROM tickets")] + list(titles or [])
    for t in seen:
        m = SUCC_RE.search(t)
        if m and m.group(1) == chain:
            hi = max(hi, int(m.group(2)))
    return hi


def this_generation(explicit, open_hi):
    """This run's own generation. An explicit --gen wins (the deliberate override). Otherwise it is
    DERIVED: the highest OPEN successor of this chain is the ticket a pair is running the decomposer
    from, so that is this run's generation; with none open the chain is fresh and this run is 0.

    Deriving is what keeps the chain alive when the command reaches the pair without the flag — the
    #245 stall. See the module docstring."""
    if explicit is not None:
        return explicit
    return open_hi if open_hi >= 0 else 0


def successor_body(remaining, batch, subset, gen):
    # The command must be the one that files exactly the `remaining` units counted above — so a subset
    # run's successor carries the same --subset, or it would misreport its own work. --gen PINS the run
    # launched from THIS body to generation `gen`, so it does not mistake this very ticket for a
    # successor someone else already filed, and it goes on to spawn generation gen+1. It is belt and
    # braces, NOT the mechanism: a run without the flag derives the same generation from the queue
    # (#245), so a pair that types a plain `--file-tickets` continues the chain instead of ending it.
    # The path is repo-root-relative on purpose: this ticket is executed from the repo root (dispatch
    # runs tools with cwd=ROOT), and the shorter `tools/...` form does not resolve from there.
    cmd = "python3 %s --file-tickets --batch %d --gen %d%s" % (
        SELF_FROM_ROOT, batch, gen, "" if not subset else " --subset %s" % subset)
    return (
        "Self-repopulating successor (the #196 pattern: append-only governance means a ticket cannot\n"
        "reopen, so the work perpetuates by spawning its successor).\n"
        "\n"
        "UNIT KEY   : %s\n"
        "CHAIN      : %s\n"
        "GENERATION : %d\n"
        "\n"
        "%d congruency-go port unit(s)%s are still un-ticketed. Run the decomposer again to file the\n"
        "next batch of at most %d, in dependency order (db #224 -> server #225 -> tags #226):\n"
        "\n"
        "    %s\n"
        "\n"
        "The `--gen %d` pins the run to THIS ticket's generation, so it will not mistake this very\n"
        "ticket for a successor someone else already filed; it then spawns generation %d, and the chain\n"
        "continues after this ticket settles.\n"
        "\n"
        "DROPPING THE FLAG DOES NOT KILL THE CHAIN (it used to — see #245). With no --gen the\n"
        "decomposer DERIVES its generation from the queue: the highest OPEN successor of this chain is\n"
        "normally this very ticket, so a plain `--file-tickets --batch %d` reaches the same conclusion\n"
        "and spawns the next generation anyway. Keep the flag regardless — it is what makes a run\n"
        "started from a STALE copy of this line (one the chain has already moved past, because a NEWER\n"
        "successor is open) correctly DECLINE, instead of adding a redundant successor.\n"
        "\n"
        "It is idempotent: it re-files nothing already ticketed. Run it with no flags first (and no\n"
        "--file-tickets) to see the enumeration without writing anything. A stop ticket aimed at this\n"
        "chain is the brake.\n"
        "\n"
        "Filed mechanically by %s under ticket #%d."
        % (successor_key(subset, gen), chain_of(subset), gen, remaining,
           "" if not subset else " matching --subset %s" % subset, batch, cmd, gen, gen + 1, batch,
           SELF_FROM_ROOT, DECOMPOSER_TICKET))


# ── correcting the tag units that were ALREADY filed with the broken gate (#323) ─────────────────
def correction_note(name, deps, registered, harness):
    """The gate correction appended to an already-open tag unit's journal. It carries
    GATE_CORRECTION_MARK so a second run recognises its own work and appends nothing."""
    return (
        "GATE CORRECTION (ticket #323) %s\n"
        "\n"
        "This tag unit's BODY states its gate as \"byte-equivalent vs the PHP render\". Read literally\n"
        "that has been taken to mean a WHOLE-PAGE byte diff of ?page=tags — and that diff is\n"
        "STRUCTURALLY NON-EMPTY for EVERY tag, including tags already merged byte-perfect, because the\n"
        "Go server's page chrome is not the PHP's (congruency-go/server.go:820-823 says so in its own\n"
        "comment: \"the CMS Controller::control() page chrome is still not reproduced here\"). Correct\n"
        "ports were rejected on it, and #310/#311/#312 had to be hand-harvested. The body cannot be\n"
        "rewritten — a ticket's identity is permanent by SQL trigger (tg_tickets_immutable_identity,\n"
        "migrations/0029_ticket_authorization.sql:111-117: \"append events\") — so this event is the\n"
        "correction, and it OVERRIDES the body's gate wording.\n"
        "\n"
        "THE GATE FOR THIS UNIT IS THE #282 HARNESS, AND NOTHING ELSE. From the repo root:\n"
        "\n"
        "    %s\n"
        "\n"
        "SETTLE when that PASSES with %s registered (`--- PASS: %s/%s`, logging\n"
        "\"IDENTICAL: <N>B byte-for-byte\"). It renders THIS tag through tags.RenderTag and compares it\n"
        "against the tag's own bytes SLICED out of the live PHP page, which is the comparison this unit\n"
        "actually wants. A `--- SKIP` (\"no Go port yet\") measured NOTHING and is NOT a pass — the sweep\n"
        "still exits 0. Register the tag with an init() calling Register(\"%s\", ...) in its own file\n"
        "under congruency-go/tags/ (engine.go:1342-1368; contenttag.go:151-153 is a worked example).\n"
        "\n"
        "%s"
        "\n"
        "Full detail — the four harness guards, its override knobs, and what it does not measure —\n"
        "is in %s and in any tag unit filed after #323.\n"
        % (GATE_CORRECTION_MARK, harness["cmd"], name, harness["test"], name, name,
           deps_block(name, deps, registered), harness["rel"]))


def open_tag_tickets(con, titles_by_id):
    """Tag units that are still WORKABLE — every ticket whose title carries a `go-port:tags:tag:<T>`
    key and whose status is not a terminal one.

    Read from the db (ALL statuses) UNION the live queue, for the same reason the idempotency read
    is: `ticket.queue` returns only OPEN/REQUESTED (its SQL is
    `WHERE upper(status) IN ('OPEN','REQUESTED')`), so it cannot see an ACTIVE unit — and ACTIVE is
    precisely a unit a pair is working RIGHT NOW on the broken gate, the most important one to
    correct. The db read can miss an uncheckpointed row that the queue then supplies."""
    out = {}
    for tid, title, status in con.execute("SELECT id, title, status FROM tickets"):
        if (status or "").upper() in ("DONE", "CLOSED"):
            continue
        for k in KEY_RE.findall(title or ""):
            if k.startswith("go-port:tags:tag:"):
                out[int(tid)] = (k.split(":")[-1], title, (status or "").upper())
    for tid, title in (titles_by_id or {}).items():
        for k in KEY_RE.findall(title or ""):
            if k.startswith("go-port:tags:tag:") and int(tid) not in out:
                out[int(tid)] = (k.split(":")[-1], title, "OPEN/REQUESTED")
    return out


def already_corrected(base, key, tid):
    """True if this ticket's journal already carries the correction. Unknown (None) if the journal
    cannot be read — the caller then SKIPS rather than risk a duplicate note."""
    try:
        rows = rest(base, "ticket.journal", {"ticket_id": tid}, method="GET", key=key).get("rows", [])
    except Exception as e:                                # noqa: BLE001
        step("ticket.journal unreadable for #%s (%s)" % (tid, e))
        return None
    return any(GATE_CORRECTION_MARK in (r.get("note") or "") for r in rows)


def correct_open_tags(base, key, con, titles_by_id, emits, registered, harness, subset):
    """Append the gate correction to every still-open tag unit that does not already carry it.

    APPEND-ONLY BY CONSTRUCTION. It writes exactly one `ticket.progress` event per ticket, through
    the governed route, and nothing else: no body is edited (the trigger forbids it), no ticket is
    re-filed (that would duplicate a unit key the decomposer is built never to duplicate), no status
    is touched. Re-running it is a no-op — every ticket whose journal already holds
    GATE_CORRECTION_MARK is skipped."""
    todo = open_tag_tickets(con, titles_by_id)
    if subset:
        todo = dict((t, v) for t, v in todo.items() if subset in "go-port:tags:tag:%s" % v[0])
    if not todo:
        step("no still-open tag unit to correct")
        return 0
    step("%d still-open tag unit(s) are candidates for the gate correction" % len(todo))
    done = 0
    for tid in sorted(todo):
        name, _title, status = todo[tid]
        seen = already_corrected(base, key, tid)
        if seen is None:
            print("== skip == #%-4s %-22s journal unreadable — not corrected" % (tid, name))
            continue
        if seen:
            print("== skip == #%-4s %-22s already carries %s" % (tid, name, GATE_CORRECTION_MARK))
            continue
        try:
            rest(base, "ticket.progress", {
                "ticket_id": tid, "agent_id": CORRECTION_AGENT, "steps_remaining": 0,
                "note": correction_note(name, emits.get(name, []), registered, harness)}, key=key)
        except Exception as e:                            # noqa: BLE001
            step("FAILED to correct #%s (%s): %s" % (tid, name, e))
            bug_report("correct_open_tags", e,
                       "python3 %s --correct-open-tags" % SELF_FROM_ROOT, e)
            continue
        done += 1
        print("== corrected == #%-4s %-22s [%s] gate -> the #282 harness" % (tid, name, status))
    step("%d tag unit(s) corrected; %d left alone" % (done, len(todo) - done))
    return done


# ── filing ───────────────────────────────────────────────────────────────────────────────────────
def file_ticket(base, key, title, body, kind="build"):
    """ticket.create -> ticket.kind, through the governed routes. Returns the new ticket id."""
    out = rest(base, "ticket.create", {"component": "congruency-go", "severity": "normal",
                                       "patch": "", "title": title, "body": body}, key=key)
    tid = int(out.get("rowid") or 0)
    if not tid:
        raise RuntimeError("ticket.create returned no rowid for %r" % title)
    rest(base, "ticket.kind", {"id": tid, "kind": kind}, key=key)   # set-once; refused if kinded
    return tid


def file_batch(base, key, todo, unticketed, batch, parent, spawn, subset, gen, ever_hi):
    """File this run's batch, then keep the chain alive. `unticketed` is how many units were
    un-ticketed BEFORE this run filed anything; what is left for the successor is derived from what
    actually got filed, so a partial failure understates nothing in the successor's own body."""
    filed = []
    for u in todo:
        try:
            tid = file_ticket(base, key, u["title"], u["body"])
        except Exception as e:                            # noqa: BLE001
            step("FAILED to file %s: %s" % (u["key"], e))
            bug_report("file_batch", e, "python3 %s --file-tickets" % SELF_FROM_ROOT, e)
            break
        filed.append((tid, u))
        print("== filed == #%-4s %s" % (tid, u["title"]))
    step("%d unit ticket(s) filed" % len(filed))

    # what the successor must still do, from what THIS run actually filed (not from what it hoped to)
    remaining_after = max(unticketed - len(filed), 0)

    if not filed:
        # main() never calls this with an empty todo, so this is a filing FAILURE, not a no-op re-run:
        # every ticket.create above broke. Spawning would go through the same route and break too.
        step("nothing filed — no successor spawned (every ticket.create failed; %d unit(s) remain "
             "un-ticketed and the chain needs a re-run once the route works)" % unticketed)
        return filed
    if not remaining_after:
        step("every unit is now ticketed — the chain is drained; no successor spawned")
        return filed
    if not spawn:
        step("--no-spawn — successor withheld (%d unit(s) still un-ticketed)" % remaining_after)
        return filed

    titles = queue_titles(queue_rows(base, key))
    if titles is None:
        # Unreadable queue AFTER filing. Spawn anyway: a duplicate successor is visible and harmless
        # (the next run files nothing new and stops), whereas a missing successor silently ends the
        # chain — the failure this whole generation scheme exists to prevent.
        step("ticket.queue unreadable after filing — spawning generation %d anyway (a stacked "
             "successor is recoverable; a dead chain is not)" % (max(ever_hi, gen) + 1))
    else:
        hi = max_open_generation(titles, subset)
        if hi > gen:
            step("chain %r already has an OPEN successor at generation %d (> this run's generation "
                 "%d) — not stacking another. %d unit(s) stay un-ticketed for IT to file; this run "
                 "did not end the chain" % (chain_of(subset), hi, gen, remaining_after))
            return filed
        ever_hi = max(ever_hi, hi)
        step("chain %r: highest open successor generation is %d, this run is generation %d — "
             "spawning generation %d" % (chain_of(subset), hi, gen, max(ever_hi, gen) + 1))
    # monotonic: never re-mint a number this chain already used (its g<N> ticket may have settled)
    nxt = max(ever_hi, gen) + 1
    try:
        sid = file_ticket(base, key,
                          "Continue the congruency-go decomposition: %d unit(s) left [%s]"
                          % (remaining_after, successor_key(subset, nxt)),
                          successor_body(remaining_after, batch, subset, nxt))
        rest(base, "edge.record", {"parent_id": parent, "child_id": sid, "kind": "spawned"}, key=key)
        print("== spawned == #%s successor generation %d (spawned edge from #%s) — %d unit(s) left"
              % (sid, nxt, parent, remaining_after))
    except Exception as e:                                # noqa: BLE001
        step("successor spawn FAILED: %s" % e)
        bug_report("file_batch", e, "python3 %s --file-tickets" % SELF_FROM_ROOT, e)
    return filed


# ── report ───────────────────────────────────────────────────────────────────────────────────────
def report(units, done, todo, subset, batch):
    print("== congruency-go decomposition ==  %d unit(s)%s"
          % (len(units), "" if not subset else " matching --subset %r" % subset))
    todo_keys = {u["key"] for u in todo}
    for b in sorted(BUCKETS, key=lambda x: BUCKETS[x][0]):
        inb = [u for u in units if u["bucket"] == b]
        if not inb:
            continue
        rank, layer, text = BUCKETS[b]
        print("\n-- %d. bucket %s — #%d: %s (%d unit(s))" % (rank, b, layer, text, len(inb)))
        for u in inb:
            mark = ("ticketed" if u["key"] in done else
                    "-> FILE" if u["key"] in todo_keys else "queued")
            print("   [%-8s] %-52s %s" % (mark, u["key"], u["headline"]))
    ticketed = len([u for u in units if u["key"] in done])
    print("\n== totals == %d unit(s): %d already ticketed, %d un-ticketed; this run files %d of them "
          "(--batch %d), leaving %d for the successor"
          % (len(units), ticketed, len(units) - ticketed, len(todo), batch,
             len(units) - ticketed - len(todo)))


def main():
    ap = argparse.ArgumentParser(
        description="Enumerate every congruency-go port unit and file one small, equivalence-gated "
                    "build ticket per unit (#230). A tag unit is gated on the #282 harness "
                    "(go test ./tags/ -run TestTagEquivalence), never on a whole-page diff (#323). "
                    "Reports and writes NOTHING unless --file-tickets, --correct-open-tags or "
                    "--json is given.")
    ap.add_argument("--file-tickets", action="store_true",
                    help="actually file one build ticket per un-ticketed unit, through rest.php's "
                         "governed ticket.create/ticket.kind routes (default: report only, no writes)")
    ap.add_argument("--batch", type=int, default=12, metavar="N",
                    help="file at most N unit tickets this run, then spawn a successor for the rest "
                         "(the #196 self-repopulating pattern; default 12)")
    ap.add_argument("--subset", default="", metavar="SPEC",
                    help="only units whose key contains SPEC, e.g. 'tag:', 'db:route', "
                         "'route:agent.' — the acceptance run of #230. It also names the drain chain, "
                         "so a subset drain and a full drain never block each other's successors")
    ap.add_argument("--gen", type=int, default=None, metavar="N",
                    help="OVERRIDE this run's successor GENERATION. By default it is DERIVED from the "
                         "live queue — the highest OPEN successor of this chain (0 if none is open, "
                         "i.e. a fresh chain) — because that successor's ticket is what a pair runs "
                         "the decomposer from. A run spawns unless an OPEN successor of a HIGHER "
                         "generation already exists, so a successor's own run never mistakes itself "
                         "for its replacement and the chain does not stall after one batch. Pass this "
                         "only to deliberately act as an OLDER generation (which then declines to "
                         "spawn, leaving the newer successor to carry the chain)")
    ap.add_argument("--parent", type=int, default=DECOMPOSER_TICKET, metavar="ID",
                    help="ticket the spawned-successor edge hangs from (default %d)" % DECOMPOSER_TICKET)
    ap.add_argument("--no-spawn", action="store_true", help="file the batch but spawn no successor")
    ap.add_argument("--correct-open-tags", action="store_true",
                    help="#323: APPEND the corrected gate (the #282 go-test harness) to the journal "
                         "of every still-open tag unit that was filed with the old whole-page-diff "
                         "wording. A ticket's body is immutable by SQL trigger, so this appends one "
                         "governed ticket.progress event per ticket and edits nothing; it is "
                         "idempotent (a ticket already carrying the correction is skipped) and it "
                         "files no tickets. Combines with --subset; independent of --file-tickets")
    ap.add_argument("--base", default=PHP_BASE, metavar="URL",
                    help="the congruency server carrying the governed routes (default %s)" % PHP_BASE)
    ap.add_argument("--db", default=CONG_DB, metavar="PATH", help="state db (default %s)" % CONG_DB)
    ap.add_argument("--json", metavar="PATH", help="also dump the enumeration as JSON to PATH")
    a = ap.parse_args()

    if a.batch < 1:
        die("--batch must be 1 or more (got %d)" % a.batch)
    if a.gen is not None and a.gen < 0:
        die("--gen must be 0 or more (got %d)" % a.gen)

    con = connect_ro(a.db)
    enc, deny = rest_encoding()
    step("boot/rest.php read: %d reply-encoding site(s) across %d span(s); admin denylist = %s"
         % (sum(len(v) for v in enc.values()), len(enc), ", ".join(deny)))
    fx = fixtures(con, deny)
    step("gate fixtures from the live db: table=%s pk=%s id=%s col=%s route=%s"
         % (fx["table"], fx["pk"], fx["id"], fx["col"], fx["route"]))

    units, tags_by_page, emits, registered, harness = enumerate_units(con, enc, deny, fx)
    for u in units:
        u["deps"] = deps_for(u, units, tags_by_page, emits)
        u["body"] = unit_body(u, u["deps"])
    step("enumerated %d unit(s): %s" % (len(units), ", ".join(
        "%d %s" % (len([u for u in units if u["utype"] == t]), t)
        for t in ("boot", "helper", "crud", "engine", "page", "route", "tag"))))
    step("tag gate = %s (%s), test %s; %d tag(s) registered in the Go engine today; %d tag(s) emit "
         "another tag and cannot be measured before it is registered"
         % (harness["cmd"], harness["rel"], harness["test"], len(registered),
            len([t for t in emits if emits[t]])))

    if a.subset:
        units = [u for u in units if a.subset in u["key"]]
        step("--subset %r -> %d unit(s)" % (a.subset, len(units)))
        if not units:
            die("--subset %r matched no unit (try a fragment of a key, e.g. 'tag:' or 'db:route')"
                % a.subset)

    # already ticketed = the db (all statuses) UNION the live queue. See the module docstring.
    key = api_key()
    done = keys_from_db(con)
    step("%d unit key(s) already ticketed per the state db (all statuses)" % len(done))
    rows = queue_rows(a.base, key)
    titles = queue_titles(rows)
    titles_by_id = queue_titles_by_id(rows)
    open_hi = max_open_generation(titles or [], a.subset)
    gen = this_generation(a.gen, open_hi)
    ever_hi = max_generation_ever(con, titles, a.subset)
    if titles is not None:
        live = keys_from_queue(titles)
        step("%d unit key(s) in the live queue (OPEN/REQUESTED); chain %r highest open successor "
             "generation = %d, this run is generation %d (%s)"
             % (len(live), chain_of(a.subset), open_hi, gen,
                "--gen override" if a.gen is not None else "derived from the queue"))
        done |= live
    elif a.file_tickets:
        die("cannot read the live ticket.queue at %s — refusing to file, to not risk duplicates (is "
            "the server up? try --base URL)" % a.base)
    else:
        step("live queue unreadable — the report below rests on the db read alone")

    unticketed = [u for u in units if u["key"] not in done]
    todo = unticketed[:a.batch]
    report(units, done, todo, a.subset, a.batch)

    if a.json:
        with open(a.json, "w") as fh:
            json.dump([{k: u[k] for k in ("key", "bucket", "utype", "name", "layer_ticket", "source",
                                          "title", "deps", "body")} for u in units], fh, indent=2)
        print("== json == %s" % a.json)

    # The #323 correction pass, before the dry-run exit so it runs with or without --file-tickets.
    # It is opt-in and append-only: see correct_open_tags().
    if a.correct_open_tags:
        if not key:
            die("no CONGRUENCY_API_KEY (../.secrets/ats.env or the environment) — cannot correct")
        print()
        correct_open_tags(a.base, key, con, titles_by_id, emits, registered, harness, a.subset)

    if not a.file_tickets:
        if a.correct_open_tags:
            print("\n== done == correction pass only; no unit ticket was filed (add --file-tickets "
                  "for that). The %d un-ticketed unit(s) above are untouched." % len(todo))
        else:
            print("\n== dry == reported only; nothing was written. Add --file-tickets to file the %d unit "
                  "ticket(s) above." % len(todo))
        return 0
    if not key:
        die("no CONGRUENCY_API_KEY (../.secrets/ats.env or the environment) — cannot file")
    if not todo:
        print("\n== nothing new == every enumerated unit is already ticketed; filed 0, spawned 0.")
        return 0

    print()
    file_batch(a.base, key, todo, len(unticketed), a.batch, a.parent, not a.no_spawn, a.subset,
               gen, ever_hi)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:                              # noqa: BLE001
        bug_report("main", exc, " ".join([sys.executable, os.path.abspath(__file__)] + sys.argv[1:]), exc)
        print("go_port_decomposer: unexpected failure: %s" % exc)
        sys.exit(2)
