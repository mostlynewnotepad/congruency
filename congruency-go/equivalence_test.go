package main

// equivalence_test.go — the standing PHP<->Go route-equivalence sweep.
//
//	#227 built the READ half: the 38 GET routes, compared byte-for-byte against the live rest.php.
//	#451 adds the WRITE half: all 24 POST routes, compared on BOTH the response bytes AND the rows
//	     they leave behind, against throwaway scratch databases. Before #451 every POST route was
//	     skipped, so the governance spine (process_status, ticket.create, ticket.assign,
//	     edge.record) had ZERO equivalence proof between the two engines.
//
// It answers one question: does this Go port of the api_routes engine (RunRoute) behave EXACTLY as
// the live boot/rest.php does? An endpoint is a ROW of the `api_routes` table (62 rows), not code —
// boot/rest.php's congruency_rest_route() and congruency-go's db.go are two engines over that one
// table. So the whole test is: same row + same bound params -> same response + same resulting rows.
// Every route below is driven FROM its row (its declared `params`, its `method`, its `sql`), never
// from hand-written per-route request code.
//
// ── TERMS (this file stands alone) ───────────────────────────────────────────────────────────────
//
//	route        one row of `api_routes`, keyed by `name`. Its `sql` is admin-authored; caller
//	             values are only ever BOUND (:param), never concatenated.
//	params       the route row's `params` column: a JSON object {"<name>":"<type>"} declaring the
//	             :placeholders its sql may use. A DECLARATION, not a schema — nothing is rejected.
//	the engine   row -> method gate -> auth gate -> bind -> execute -> shape the reply. db.go's
//	             RunRoute in Go; congruency_rest_route() in PHP.
//	scratch db   a private, throwaway copy of the state db under the test's temp dir. Deleted with
//	             the temp dir when the test ends. The LIVE state db is never opened for writing.
//	the spine    process_status, ticket.create, ticket.assign, edge.record — the four routes the
//	             dispatch machinery itself runs. #279 shipped a pair_loop change that set
//	             process_status ACTIVE *before* ticket.assign; nothing verified that write path, it
//	             merged, and every new dispatch died with HTTP 500 until it was reverted. These four
//	             are PROVEN below, and the _279_governance_guard subtest reproduces the #279 abort.
//
// ── PART 1: THE GET SWEEP (#227) ─────────────────────────────────────────────────────────────────
//
// The Go engine runs in-process against the SERVER's own db; the golden is the live rest.php over
// HTTP (curl-equivalent). resolveDB() prefers, in order: $CONGRUENCY_EQUIV_DB, the server's state db
// (checkouts/current/state/congruency.sqlite), then the config db.
//
// Concurrency — the stability sandwich. The server's db has live writers (the pair_loop agents), so
// a route's rows can change between the Go read and the PHP read. Each route is fetched from PHP
// twice, bracketing the Go run (php1, go, php2). If php1 != php2 the db changed inside the window,
// so the route is reported VOLATILE and skipped for this run rather than false-failing.
//
// ── PART 2: THE WRITE SWEEP (#451) ───────────────────────────────────────────────────────────────
//
// A write cannot be verified the way a read is: running it against the live governed db would mutate
// real state. It also cannot be verified by its response alone — a route that returns identical JSON
// but writes different rows is EXACTLY the #279 failure. So each POST route is proven on two things:
//
//	(a) the RESPONSE bytes match (status + body), as the GET half already asserts, AND
//	(b) the RESULTING DB STATE matches — the rows the route actually left behind.
//
// The discipline is per_unit_test_harness.py's: copy the db to a throwaway scratch file under a temp
// dir and drive the target against the copy. Per route:
//
//	 1. snapshot   ONE consistent snapshot of the live state db is taken up front, with
//	                sqlite's `VACUUM INTO` from an immutable=1 handle (see SIDE EFFECTS below).
//	 2. seed       the snapshot is copied once to a SEED db and the preconditions are applied to it
//	               (a registered agent + two probe tickets + a crew — see seedScratchDB). The seed is
//	               built ONCE and every route forks from it, so no route ever sees another's writes.
//	 3. fork       the seed is byte-copied TWICE per route: one scratch db for PHP, one for Go. Both
//	               forks are byte-identical and come from the SAME pristine seed, so neither engine
//	               can see the other's writes.
//	 4. drive      PHP runs against its fork, Go runs against its fork, with the same route row and
//	               the same request body.
//	 5. diff       the rows each engine left behind (its fork vs the seed) are compared to each other.
//
// THE PHP SIDE IS THE REAL rest.php. PHP's CLI SAPI cannot deliver php://input (measured: it returns
// "" while php://stdin returns the body), and congruency_rest_route() reads the POST body from
// php://input — so a CLI driver would silently bind every param NULL and prove nothing. The test
// therefore boots an EPHEMERAL `php -S` web server on a free localhost port whose router
// (phpShimSource, below) does nothing but `require` the same boot/rest.php the live server does and
// call the same congruency_rest_route(). It is a front door onto the real engine, not a second
// implementation of it: the shim contains no route logic, no SQL and no JSON shaping. Its catch
// block mirrors congruency_rest_dispatch()'s exactly (500 + a PRETTY {"error": msg}), which is what
// goWriteRoute() mirrors on the Go side. The _shim_fidelity subtest proves the shim is not a fork
// and not a tilted golden: it re-runs all 38 GET routes through the shim against the seed and
// requires byte-equality with the Go engine over that same seed — the same equality PART 1 measures
// against the LIVE server. If the shim ever stopped agreeing with the engine the live server runs,
// that subtest fails before any write proof is believed.
//
// AUTHORIZATION IS MATCHED ON BOTH SIDES. 23 of the 24 POST routes are auth='token'. The live
// deployment sets CONGRUENCY_AUTH_OVERRIDE (boot/constants.default.json:52), which makes
// congruency_rest_authorized() return true for everything (boot/rest.php:45); the shim defines the
// same constant, and the Go side passes AllowAll{}, whose doc-comment says it mirrors exactly that.
// Neither engine is given an advantage the other lacks.
//
// ── WHAT "THE RESULTING ROWS MATCH" MEANS HERE ───────────────────────────────────────────────────
//
// EVERY table is diffed, not just the one the route's sql names. That is deliberate: process_status
// is an `UPDATE tickets`, but the tg_tickets_journal_status trigger turns it into a second write
// into ticket_events. A per-route "touched table" list would have missed that row entirely. A full
// fingerprint of all 46 tables costs ~0.15s (measured), so there is no reason to guess.
//
// Each row is canonicalised IN SQLITE as `typeof(c)||':'||quote(c)` per column — sqlite's own view of
// what is stored, so the comparison cannot be fooled by a driver that hands back int64 where the
// other hands back a string. TEXT '2' and INTEGER 2 are different cells here, which is the point:
// db.go's note 1 (every bound value reaches sqlite as TEXT, because PDO binds PARAM_STR) is a claim
// this diff would catch if the Go port ever broke it.
//
// VOLATILE COLUMNS — the exclusions, and why each is excluded (printed by the test at run time):
//
//	ts       EXCLUDED from row equality. Every one of the 24 route SQLs that stamps a time does it
//	         with strftime('%s','now') into a column named `ts` (agents, ticket_artifacts, tickets,
//	         clause_bindings, repo_docs, ticket_edges, guarantees, crank_jobs, journey, mandates,
//	         crank_policies, crank_runs, embeddings, source_commits, ticket_agents, ticket_events,
//	         ticket_works), as does tg_tickets_journal_status's auto-journal row. PHP and Go run a
//	         few milliseconds apart, so the two can legitimately straddle a second boundary.
//	updated  EXCLUDED, same reason: `tickets.updated` is set by strftime('%s','now') in
//	         process_status, ticket.approve, ticket.kind, ticket.create and authorize_process.
//
// The exclusion is NOT a blind hole. An excluded cell is still required to have the SAME sqlite
// TYPE on both sides (so a port that wrote TEXT where PHP wrote REAL still fails) and to be within
// volatileWindowSecs of the other. Only the exact second is forgiven.
//
// AUTOINCREMENT ids are NOT excluded — they are COMPARED. The ticket that ordered this work
// anticipated excluding them, and that would be right for two independent databases; it is wrong
// here. Both forks are byte-copies of ONE seed, so both carry the same sqlite_sequence and both
// allocate the SAME next id. Comparing them is strictly stronger than excluding them, and the
// response body's own `rowid` field (PDO::lastInsertId(), a JSON string) asserts it a second time.
// If the two engines ever allocated different ids from the same snapshot, this test fails.
//
// ── NO SILENT SKIPS ──────────────────────────────────────────────────────────────────────────────
//
// The blanket "skipped write (POST) routes (24)" line this file used to print is what hid the gap
// for so long. Every one of the 24 is now driven. writeRouteInputs holds one entry per route, and
// the test ASSERTS (a) that its key set is exactly the set of POST routes `api_routes` actually
// declares — so a 25th POST row can never be silently uncovered — and (b) that each entry's params
// are exactly the params that route's row declares — so a param added to a row can never be silently
// left unbound. A route may carry a NAMED skip reason; today none does, and the summary prints the
// count either way.
//
// ── SIDE EFFECTS: READ-ONLY TOWARD THE WORLD ─────────────────────────────────────────────────────
//
// No writes to the live state db, no agents spawned, and the only network is localhost (the live
// rest.php the GET half already used, plus the test's own ephemeral php server on a free port).
//
// The live db is opened ONCE, with the `immutable=1` URI flag, purely to `VACUUM INTO` a snapshot in
// the temp dir. immutable=1 is not a stylistic choice — MEASURED THIS SESSION: the live state db is
// in WAL journal mode, and opening a WAL db read-only with `mode=ro` CREATES congruency.sqlite-shm
// and congruency.sqlite-wal next to it. immutable=1 promises sqlite the file will not change, so it
// reads the committed main-file data with no locking and creates ZERO sidecar files. (db.go's header
// says the live db is journal_mode=delete; that reading was itself taken through an immutable handle,
// which reports 'delete' regardless. A plain handle reports 'wal'.)
//
// Because immutable=1 ignores locking, a snapshot taken while a live writer is mid-checkpoint could
// in principle be torn, so the snapshot is verified with PRAGMA quick_check before it is used; a
// torn read skips the write sweep with a named reason rather than reporting a false divergence.
//
// The guarantee is asserted, not asserted-in-prose: assertLiveDBUntouched() captures the live db's
// mtime+size AND the full listing of its directory before and after the run, and fails on any
// change. The directory listing is the stronger half — it is what catches the -wal/-shm class that
// mtime+size alone cannot see.
//
// ── KNOWN, BY-DESIGN NON-EQUIVALENCE ─────────────────────────────────────────────────────────────
//
// A route whose SQL errors yields a 500 whose ENVELOPE both sides reproduce ({"error": <msg>}) but
// whose MESSAGE is the driver's: go-sqlite says "datatype mismatch (20)", PDO says
// "SQLSTATE[HY000]: General error: 20 datatype mismatch". db.go's header documents this as
// unreproducible-by-design. Such routes (knownDriverMsgDiff) are reported as a documented DIFFERENCE
// (t.Log), not a hard failure. No POST route in the PROVEN set lands here — all 24 execute cleanly.
//
// ── RUNNING IT ───────────────────────────────────────────────────────────────────────────────────
//
//	go test . -run TestRouteEquivalence -v
//
// Guards: each part skips cleanly (never false-fails) if its inputs are missing — the GET half needs
// the live server and an API key, the write half needs the repo's php binary and boot/rest.php.
// Overrides: $CONGRUENCY_EQUIV_DB (the db), $CONGRUENCY_REST_URL (the live server),
// $CONGRUENCY_PHP (the php binary), $CONGRUENCY_EQUIV_BOOT (the directory holding rest.php).

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"
)

const (
	defaultServerURL = "http://127.0.0.1:8899/rest.php"
	secretsEnvFile   = "/Users/stevenpeterson/code/installed/jazz-project/.secrets/ats.env"
	serverStateDB    = "/Users/stevenpeterson/code/installed/jazz-project/congruency/checkouts/current/state/congruency.sqlite"
	configDB         = "/Users/stevenpeterson/code/installed/jazz-project/config/congruency/congruency.sqlite"

	// mainCheckoutPHP is the repo's own PHP build (8.4.23), the one db.go measured its
	// PHP-mirroring conversions against. It is gitignored and lives only in the main checkout, so a
	// pair_loop worktree has no relative path to it; hence the absolute fallback.
	mainCheckoutPHP = "/Users/stevenpeterson/code/installed/jazz-project/congruency/tooling/congruencey-harness/php/php"

	// volatileWindowSecs is how far apart the two engines' strftime('%s','now') stamps may be. PHP
	// and Go run milliseconds apart; 5s is slack for a loaded machine, and is only ever applied to
	// the columns named in volatileColumns.
	volatileWindowSecs = 5.0
)

// getRoutes are the read-only routes this sweep covers: every route whose method is GET and whose
// auth is "public" (measured from api_routes). They run without required params — the engine binds
// missing params the way rest.php does — so empty input is a faithful request.
var getRoutes = []string{
	"agent.prompt", "agent.roster", "agent.trail", "artifact.list", "binding.list",
	"bug.list", "bug.stats", "children.list", "doc.list", "doc.read", "doc.repos",
	"error.recent", "error.stats", "guarantee.held", "guarantee.list", "job.get",
	"journey.list", "kind.roster", "lessons.recent", "lifecycle.steps", "mandate.list",
	"policy.active", "processes.running", "repo.list", "run.get", "run.recent",
	"search.facets", "search.stats", "search.text", "source.commits", "telemetry.recent",
	"ticket.approval", "ticket.crew", "ticket.journal", "ticket.manifest", "ticket.queue",
	"ticket.stops", "tickets.recent",
}

// knownDriverMsgDiff: routes whose only divergence is the driver-specific text inside a 500 error
// envelope (the PDO vs go-sqlite message). Reported as documented, not failed. See file header.
var knownDriverMsgDiff = map[string]bool{
	"run.recent":     true,
	"tickets.recent": true,
}

// volatileColumns names the columns excluded from row equality, each with the reason printed in the
// test output. Both are written by strftime('%s','now') — `ts` by every stamping route SQL and by
// tg_tickets_journal_status's auto-journal row, `updated` by the four tickets-writing routes — so
// PHP's value and Go's value legitimately differ when the two runs straddle a second boundary.
//
// An excluded cell is still required to carry the same sqlite TYPE on both sides and to sit within
// volatileWindowSecs of its counterpart (see volatileCellCompatible). Only the exact second is
// forgiven; a type divergence or a wild value still fails.
var volatileColumns = map[string]string{
	"ts": "written by the route sql's strftime('%s','now') (and by tg_tickets_journal_status); " +
		"PHP and Go stamp it a few ms apart and may straddle a second boundary",
	"updated": "tickets.updated, written by strftime('%s','now') in process_status, ticket.approve, " +
		"ticket.kind, ticket.create and authorize_process; same second-boundary reason as ts",
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The write sweep's inputs.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// seedRef is a placeholder for a value only known after the seed db is built (a probe ticket's
// AUTOINCREMENT id). resolveWriteParam swaps it for the real id.
type seedRef string

const (
	refTicketA seedRef = "<seeded probe ticket A>" // kind IS NULL, status REQUESTED, HAS a crew
	refTicketB seedRef = "<seeded probe ticket B>" // kind IS NULL, status REQUESTED, NO crew
)

// seededAgentID is the agent seedScratchDB registers. ticket_agents' tg_ticket_agents_registered
// trigger ABORTs an assignment of an agent that is not in `agents`, so ticket.assign cannot be
// driven without it. It is a row in a throwaway scratch db; no agent is spawned.
const seededAgentID = "t451-equiv-agent"

// writeRouteInput is one POST route's request. `params` carries exactly one value per param the
// route's row DECLARES — the test asserts that key set against the row itself, so neither a new
// param nor a new route can be silently left uncovered.
//
// `skip`, when non-empty, is the NAMED reason a route cannot be driven (a live agent, an external
// side effect). It is printed in the summary. Today every route is driven and no entry sets it; the
// field exists because the ticket allows a named skip and forbids an unnamed one.
//
// `precondition` documents, in the test output, the seeded state a route needs to succeed.
type writeRouteInput struct {
	params       map[string]any
	skip         string
	precondition string
}

// writeRouteInputs: one entry per POST route. Values are plausible-but-inert probe data written only
// into throwaway scratch dbs. Where a value must be MEANINGFUL for the route's real code path to run
// (a registered agent, an existing ticket, a NULL kind), it refers to the seed and says why.
var writeRouteInputs = map[string]writeRouteInput{
	"agent.register": {params: map[string]any{
		"agent_id": "t451-equiv-registrant", "parent": seededAgentID,
		"prompt": "equivalence probe (#451)", "tools": "[]",
	}},
	"artifact.record": {params: map[string]any{
		"ticket_id": refTicketA, "name": "equiv-probe", "version": "0.0.1",
		"forge_sha": "0000000000000000000000000000000000000000000000000000000000000451",
		"kind":      "run-output",
	}},
	"authorize_process": {params: map[string]any{
		"name": "congruency-go", "body": "equivalence probe (#451)", "meta": "{}",
	}},
	"binding.record": {params: map[string]any{
		"ticket_id": refTicketA, "clause_seq": int64(1),
		"guarantee_label": "route equivalence holds", "digest": "sha256:t451-binding",
	}},
	"bug.record": {params: map[string]any{
		"bug_id": "t451-equiv-bug", "source": "equivalence", "title": "probe",
		"severity": "info", "location": "congruency-go/equivalence_test.go",
		"repro": "go test . -run TestRouteEquivalence", "success": "n/a",
		"fanout": int64(1), "repos": int64(1), "status": "open",
		"pattern": "equivalence-probe", "meta": "{}",
	}},
	"doc.record": {params: map[string]any{
		"repo": "congruency", "path": "docs/t451-equiv.md", "kind": "doc",
		"body": "equivalence probe (#451)",
	}},
	"edge.record": {params: map[string]any{ // SPINE
		"parent_id": refTicketA, "child_id": refTicketB, "kind": "spawned",
	}, precondition: "two seeded probe tickets (A -> B); 'spawned' is a live ticket_edges kind"},
	"guarantee.record": {params: map[string]any{
		"ticket_id": refTicketA, "version": "0.0.1", "shadow": "tests/down-shadow.py",
		"guarantee": "route equivalence holds", "clause_seq": int64(1), "digest": "sha256:t451-guarantee",
	}},
	"job.put": {params: map[string]any{
		"hash": "t451equivhash", "spec": "{}",
	}},
	"journey.record": {params: map[string]any{
		"ticket_id": refTicketA, "kind": "note", "text": "equivalence probe (#451)",
	}},
	"mandate.record": {params: map[string]any{
		"ticket_id": refTicketA, "seq": int64(1),
		"clause": "the 24 POST routes are proven", "digest": "sha256:t451-mandate",
	}},
	"policy.create": {params: map[string]any{
		"component": "congruency-go", "max_version": "9.9.9",
		"expires": int64(1900000000), "sig": "t451-equiv-sig",
	}},
	"process_status": {params: map[string]any{ // SPINE — the #279 route
		"status": "ACTIVE", "id": refTicketA,
	}, precondition: "probe ticket A is REQUESTED and HAS a crew row in ticket_agents — " +
		"tg_tickets_active_needs_agent ABORTs an ACTIVE with no assignment (the #279 failure; " +
		"the _279_governance_guard subtest drives that abort deliberately). The status change also " +
		"fires tg_tickets_journal_status, which writes a SECOND row into ticket_events; the " +
		"all-tables diff proves both engines write it identically"},
	"run.record": {params: map[string]any{
		"component": "congruency-go", "version": "0.0.1", "ticket_id": refTicketA,
		"authorized_by": "ticket-signature", "ok": int64(1),
		"shadow_output": "equivalence probe (#451)", "digest": "sha256:t451-run",
	}},
	"search.record": {params: map[string]any{
		"repo": "congruency", "path": "docs/t451-equiv.md", "chunk_seq": int64(0),
		"section": "probe", "text": "equivalence probe (#451)", "dim": int64(3),
		"model": "t451-equiv-model", "vector": "[0.0,0.5,1.0]",
	}},
	"source.record": {params: map[string]any{
		"repo": "congruency", "commit_sha": "0000000000000000000000000000000000000451",
		"is_current": int64(0), "forge_remote": "t451-equiv-remote",
	}},
	"telemetry.record": {params: map[string]any{
		"kind": "event", "route": "t451-equiv", "message": "probe", "detail": "equivalence probe (#451)",
	}, precondition: "none — but note this route SHORT-CIRCUITS in both engines and writes NOTHING. " +
		"rest.php:90 checks function_exists('congruency_telemetry_record'), which rest.php itself " +
		"defines, so the route's INSERT never runs and the reply is the {route,ok,kind} ack. The row " +
		"is written by boot/monitor.php's congruency_telemetry_ingest, which rest.php calls only " +
		"if it is defined; the shim does not load monitor.php and db.go's DB.TelemetryIngest hook is " +
		"nil, so the hook is ABSENT ON BOTH SIDES — a matched configuration, not a tilted one. What " +
		"is proven here is the ack and the empty write; the ingest branch is out of this test's reach"},
	"ticket.approve": {params: map[string]any{
		"id": refTicketA, "approval_sig": "t451-equiv-approval",
	}, precondition: "probe ticket A exists (an UPDATE ... WHERE id=:id on a missing id affects 0 rows)"},
	"ticket.assign": {params: map[string]any{ // SPINE
		"ticket_id": refTicketB, "agent_id": seededAgentID, "role": "tester",
	}, precondition: "agent '" + seededAgentID + "' is registered in `agents` — " +
		"tg_ticket_agents_registered ABORTs an unregistered assignment. Probe ticket B is used " +
		"(not A) because A already carries a crew row, and the sql is INSERT OR IGNORE: assigning " +
		"a row that exists would report affected=0 and prove nothing"},
	"ticket.create": {params: map[string]any{ // SPINE
		"component": "congruency-go", "title": "#451 equivalence probe (scratch db only)",
		"severity": "info", "body": "equivalence probe (#451)", "patch": "",
	}},
	"ticket.kind": {params: map[string]any{
		"kind": "build", "id": refTicketA,
	}, precondition: "probe ticket A has kind IS NULL — the sql is UPDATE ... WHERE id=:id AND kind " +
		"IS NULL, so a ticket with a kind already set would affect 0 rows. 'build' is a live " +
		"ticket_kinds row"},
	"ticket.lesson": {params: map[string]any{
		"ticket_id": refTicketA, "agent_id": seededAgentID, "note": "equivalence probe (#451)",
	}},
	"ticket.progress": {params: map[string]any{
		"ticket_id": refTicketA, "agent_id": seededAgentID,
		"note": "equivalence probe (#451)", "steps_remaining": int64(3),
	}},
	"work.record": {params: map[string]any{
		"ticket_id": refTicketA, "kind": "code",
		"ref": "congruency-go/equivalence_test.go", "note": "equivalence probe (#451)",
	}},
}

// spineRoutes are the four routes the ticket names as the governance spine: the ones the dispatch
// machinery itself runs, and the ones #279 broke. The write sweep FAILS if any of them is not in the
// PROVEN set at the end of the run — a named skip is not good enough for these.
var spineRoutes = []string{"process_status", "ticket.create", "ticket.assign", "edge.record"}

// phpShimSource is the ephemeral `php -S` router. It is a FRONT DOOR onto the real engine, not a
// second implementation of it: it holds no route logic, no SQL and no JSON shaping. It requires the
// same boot/rest.php the live server does and calls the same congruency_rest_route().
//
// Three details are load-bearing:
//   - CONGRUENCY_AUTH_OVERRIDE mirrors the live deployment (boot/constants.default.json:52), where
//     congruency_rest_authorized() returns true for everything (rest.php:45). The Go side passes
//     AllowAll{}, which db.go documents as mirroring exactly this. Neither side is favoured.
//   - the scratch db path arrives per-request in the X-Equiv-Db header, so ONE server serves every
//     route while each route still gets its own private fork. congruency_rest_route() takes the PDO
//     handle as an argument (rest.php:59), so no CONGRUENCY_SQLITE constant is needed; a fresh PDO
//     per request is exactly what congruency_rest_dispatch() does (rest.php:146), and it matters:
//     PDO::lastInsertId() is a property of ONE connection, so a shared handle would leak the
//     previous route's rowid into this route's reply.
//   - the catch block reproduces congruency_rest_dispatch()'s (rest.php:272-276): status 500 and a
//     PRETTY-printed {"error": msg}. goWriteRoute() mirrors the same shape on the Go side.
const phpShimSource = `<?php
// Written at run time by congruency-go/equivalence_test.go (#451). Ephemeral, localhost-only,
// deleted with the test's temp dir. It adds NO behaviour: it requires the real boot/rest.php and
// calls the real congruency_rest_route() against a throwaway scratch db named by the request.
if (!defined('CONGRUENCY_AUTH_OVERRIDE')) { define('CONGRUENCY_AUTH_OVERRIDE', true); }
require_once getenv('EQUIV_BOOT') . '/rest.php';

$dbPath = isset($_SERVER['HTTP_X_EQUIV_DB']) ? (string) $_SERVER['HTTP_X_EQUIV_DB'] : '';
$route  = (string) ($_GET['route'] ?? '');
$method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');
header('Content-Type: application/json');
if ($dbPath === '') { http_response_code(400); echo json_encode(array('error' => 'no X-Equiv-Db header')) . "\n"; return; }
try {
    $db = new PDO('sqlite:' . $dbPath);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    congruency_rest_route($db, $route, $method);
} catch (\Throwable $e) {
    // congruency_rest_dispatch()'s own catch, reproduced: 500 + a PRETTY {"error": msg}.
    http_response_code(500);
    echo json_encode(array('error' => $e->getMessage()), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
}
`

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Locating the pieces. Each returns ("", reason) rather than failing, so a missing input SKIPS with
// a named reason instead of false-failing.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

func resolveDB(t *testing.T) string {
	for _, p := range []string{os.Getenv("CONGRUENCY_EQUIV_DB"), serverStateDB, configDB} {
		if p == "" {
			continue
		}
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	t.Skip("no congruency.sqlite found (set $CONGRUENCY_EQUIV_DB); skipping equivalence sweep")
	return ""
}

// resolveLiveDB is resolveDB without the t.Skip, for the write sweep's own guard.
func resolveLiveDB() (string, string) {
	for _, p := range []string{os.Getenv("CONGRUENCY_EQUIV_DB"), serverStateDB, configDB} {
		if p == "" {
			continue
		}
		if _, err := os.Stat(p); err == nil {
			return p, ""
		}
	}
	return "", "no congruency.sqlite found (set $CONGRUENCY_EQUIV_DB)"
}

// resolvePHP finds the php binary to drive rest.php with: $CONGRUENCY_PHP, then this checkout's own
// harness build, then the main checkout's (the harness php is gitignored, so a pair_loop worktree
// has only the absolute path), then $PATH.
func resolvePHP() (string, string) {
	for _, p := range []string{os.Getenv("CONGRUENCY_PHP"), "../tooling/congruencey-harness/php/php", mainCheckoutPHP} {
		if p == "" {
			continue
		}
		if fi, err := os.Stat(p); err == nil && !fi.IsDir() && fi.Mode()&0o111 != 0 {
			abs, err := filepath.Abs(p)
			if err != nil {
				continue
			}
			return abs, ""
		}
	}
	if p, err := exec.LookPath("php"); err == nil {
		return p, ""
	}
	return "", "no php binary found (looked at $CONGRUENCY_PHP, ../tooling/congruencey-harness/php/php, " +
		mainCheckoutPHP + ", and $PATH)"
}

// resolveBoot finds the directory holding the rest.php under test. It prefers THIS checkout's copy,
// so the Go engine in this tree is compared against the PHP engine in the same tree.
func resolveBoot() (string, string) {
	cands := []string{
		os.Getenv("CONGRUENCY_EQUIV_BOOT"),
		"../checkouts/current/congruency/boot",
		"/Users/stevenpeterson/code/installed/jazz-project/congruency/checkouts/current/congruency/boot",
	}
	for _, p := range cands {
		if p == "" {
			continue
		}
		if _, err := os.Stat(filepath.Join(p, "rest.php")); err == nil {
			abs, err := filepath.Abs(p)
			if err != nil {
				continue
			}
			return abs, ""
		}
	}
	return "", "no boot/rest.php found (looked at $CONGRUENCY_EQUIV_BOOT and " + strings.Join(cands[1:], ", ") + ")"
}

func apiKey() string {
	if k := os.Getenv("CONGRUENCY_API_KEY"); k != "" {
		return k
	}
	f, err := os.Open(secretsEnvFile)
	if err != nil {
		return ""
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if strings.HasPrefix(line, "CONGRUENCY_API_KEY=") {
			return strings.TrimSpace(strings.TrimPrefix(line, "CONGRUENCY_API_KEY="))
		}
	}
	return ""
}

func serverURL() string {
	if u := os.Getenv("CONGRUENCY_REST_URL"); u != "" {
		return u
	}
	return defaultServerURL
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PART 1 — the GET sweep (#227).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// phpFetch pulls one route's golden output from the live rest.php. Returns (status, body).
func phpFetch(t *testing.T, client *http.Client, base, key, route string) (int, []byte, error) {
	req, err := http.NewRequest("GET", base+"?route="+route, nil)
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("X-Api-Key", key)
	resp, err := client.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	return resp.StatusCode, body, err
}

// goRoute runs a route through the Go engine exactly as main() does, including main()'s wrapping of
// a RunRoute error into a pretty {"error": msg} 500 body — so the bytes are what the CLI would print.
func goRoute(d *DB, route string) (int, []byte) {
	reply, err := d.RunRoute(route, "GET", map[string]any{}, AllowAll{})
	if err != nil {
		body, _ := phpJSONEncode(Obj{{"error", err.Error()}}, jsonPretty|jsonUnescapedSlashes)
		return 500, append(body, '\n')
	}
	return reply.Status, reply.Body
}

// unifiedish renders a compact line-oriented diff for the failure message.
func unifiedish(got, want []byte) string {
	gl := strings.Split(string(got), "\n")
	wl := strings.Split(string(want), "\n")
	var b strings.Builder
	n := len(gl)
	if len(wl) > n {
		n = len(wl)
	}
	shown := 0
	for i := 0; i < n && shown < 40; i++ {
		var g, w string
		if i < len(gl) {
			g = gl[i]
		}
		if i < len(wl) {
			w = wl[i]
		}
		if g != w {
			b.WriteString(fmt.Sprintf("  - go : %q\n  + php: %q\n", g, w))
			shown++
		}
	}
	return b.String()
}

func isErrorEnvelope(b []byte) bool {
	return bytes.Contains(b, []byte(`"error"`))
}

// runGetSweep is #227's sweep, unchanged in substance. It reports its own skips so that the write
// sweep still runs when the live server is down.
func runGetSweep(t *testing.T) {
	key := apiKey()
	if key == "" {
		t.Skip("no CONGRUENCY_API_KEY available (set it or provide " + secretsEnvFile + ")")
	}
	base := serverURL()
	client := &http.Client{Timeout: 10 * time.Second}

	// Reachability probe: skip (never fail) if the PHP server is down.
	if _, _, err := phpFetch(t, client, base, key, "kind.roster"); err != nil {
		t.Skipf("live rest.php at %s unreachable (%v)", base, err)
	}

	dbPath := resolveDB(t)
	if dbPath == configDB {
		t.Logf("NOTE: comparing against %s, which is NOT the DB rest.php reads (%s). Volatile "+
			"routes will report VOLATILE/DIFF due to divergent data, not an engine bug. Set "+
			"$CONGRUENCY_EQUIV_DB to the server DB for a true engine comparison.",
			filepath.Base(dbPath), serverStateDB)
	}

	d, err := Open(dbPath)
	if err != nil {
		t.Skipf("cannot open %s (%v)", dbPath, err)
	}
	defer d.Close()

	t.Logf("DB under test: %s", dbPath)
	t.Logf("golden source: %s", base)

	var identical, documented, volatile []string

	for _, route := range getRoutes {
		route := route
		t.Run(route, func(t *testing.T) {
			// Stability sandwich: php1, go, php2. A live write inside the window makes php1 != php2.
			pStatus1, php1, err := phpFetch(t, client, base, key, route)
			if err != nil {
				t.Skipf("php fetch failed (%v)", err)
			}
			gStatus, goBody := goRoute(d, route)
			_, php2, err := phpFetch(t, client, base, key, route)
			if err != nil {
				t.Skipf("php re-fetch failed (%v)", err)
			}
			if !bytes.Equal(php1, php2) {
				volatile = append(volatile, route)
				t.Skipf("VOLATILE: rest.php output changed under concurrent writes during the window; "+
					"not an engine signal (php1=%dB php2=%dB)", len(php1), len(php2))
			}

			if bytes.Equal(goBody, php1) {
				identical = append(identical, route)
				if gStatus != pStatus1 {
					t.Errorf("bytes match but status differs: go=%d php=%d", gStatus, pStatus1)
				}
				return
			}

			// Bytes differ. Distinguish the documented driver-message class from a real regression.
			if knownDriverMsgDiff[route] && isErrorEnvelope(goBody) && isErrorEnvelope(php1) {
				documented = append(documented, route)
				t.Logf("DOCUMENTED non-equivalence (PDO vs go-sqlite error text; not a float bug):\n%s",
					unifiedish(goBody, php1))
				return
			}

			t.Errorf("BYTE MISMATCH for route %s (go=%dB php=%dB, status go=%d php=%d):\n%s",
				route, len(goBody), len(php1), gStatus, pStatus1, unifiedish(goBody, php1))
		})
	}

	t.Logf("GET SUMMARY: %d/%d GET routes byte-identical; %d documented driver-msg diffs (%s); %d volatile this run (%s)",
		len(identical), len(getRoutes), len(documented), strings.Join(documented, ","),
		len(volatile), strings.Join(volatile, ","))
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PART 2 — the write sweep (#451): the scratch-db machinery.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// liveDirState is the proof material for "the live state db was not touched": the db's own size and
// mtime, plus the FULL listing (name -> size) of its directory. The listing is the half that catches
// the sqlite sidecar class — opening a WAL db with mode=ro creates -wal/-shm without changing the db
// file's mtime or size at all.
type liveDirState struct {
	size    int64
	modTime time.Time
	dir     map[string]int64
}

func captureLiveDirState(path string) (liveDirState, error) {
	fi, err := os.Stat(path)
	if err != nil {
		return liveDirState{}, err
	}
	ents, err := os.ReadDir(filepath.Dir(path))
	if err != nil {
		return liveDirState{}, err
	}
	dir := map[string]int64{}
	for _, e := range ents {
		info, err := e.Info()
		if err != nil {
			continue
		}
		dir[e.Name()] = info.Size()
	}
	return liveDirState{size: fi.Size(), modTime: fi.ModTime(), dir: dir}, nil
}

// assertLiveDBUntouched fails if this test changed the live db or added/removed any file beside it.
//
// It is tolerant of the live db GROWING or its neighbours changing — the pair_loop agents write to
// it continuously and this test cannot stop them — but it is NOT tolerant of a file APPEARING or
// DISAPPEARING that this test could have caused. The sidecars (-wal/-shm) are the reason: they are
// the one class this test could plausibly create, and their appearance is exactly what
// PRAGMA-less "read-only" opens leave behind (Playbook #153).
func assertLiveDBUntouched(t *testing.T, path string, before liveDirState) {
	after, err := captureLiveDirState(path)
	if err != nil {
		t.Errorf("cannot re-stat the live db %s: %v", path, err)
		return
	}
	for name := range after.dir {
		if _, had := before.dir[name]; !had {
			t.Errorf("SIDE EFFECT: %s appeared beside the live state db during this run. The write "+
				"sweep must create NO file next to %s (it snapshots via immutable=1, which creates "+
				"no -wal/-shm). Before: %v  After: %v",
				name, path, sortedKeys(before.dir), sortedKeys(after.dir))
		}
	}
	for name := range before.dir {
		if _, still := after.dir[name]; !still {
			t.Errorf("SIDE EFFECT: %s disappeared from beside the live state db during this run", name)
		}
	}
	if after.size != before.size || !after.modTime.Equal(before.modTime) {
		// Concurrent pair_loop agents write to this db, so a change is not proof this test did it.
		// It IS proof the mtime+size assertion can say nothing, so say that rather than pass quietly.
		t.Logf("NOTE: the live state db changed under us during the run (size %d -> %d, mtime %s -> %s). "+
			"That is the concurrent pair_loop agents, not this test: this test opens it exactly once, "+
			"with immutable=1, to VACUUM INTO a snapshot in a temp dir, and never for writing. The "+
			"directory-listing check above is the assertion that still holds.",
			before.size, after.size, before.modTime.Format(time.RFC3339Nano), after.modTime.Format(time.RFC3339Nano))
	}
}

func sortedKeys(m map[string]int64) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// snapshotLiveDB takes ONE consistent snapshot of the live state db into dst, using `VACUUM INTO`
// from an immutable=1 handle. immutable=1 is required, not preferred: the live db is in WAL journal
// mode (measured), and a `mode=ro` open of a WAL db CREATES -wal/-shm sidecars beside it. immutable=1
// promises sqlite the file will not change, so it reads the committed main-file data with no locking
// and creates ZERO files. VACUUM INTO only ever writes to dst.
//
// The cost of immutable=1 is that it ignores locking, so a snapshot taken while a writer is
// mid-checkpoint could be torn — hence the quick_check before the snapshot is trusted.
func snapshotLiveDB(live, dst string) error {
	d, err := sql.Open("sqlite", "file:"+live+"?immutable=1")
	if err != nil {
		return err
	}
	defer d.Close()
	// The path is the test's own temp dir; single-quote it the way sqlite wants a string literal.
	if _, err := d.Exec("VACUUM INTO '" + strings.ReplaceAll(dst, "'", "''") + "'"); err != nil {
		return fmt.Errorf("VACUUM INTO %s: %w", dst, err)
	}

	s, err := sql.Open("sqlite", "file:"+dst+"?immutable=1")
	if err != nil {
		return err
	}
	defer s.Close()
	var res string
	if err := s.QueryRow("PRAGMA quick_check").Scan(&res); err != nil {
		return fmt.Errorf("quick_check on the snapshot: %w", err)
	}
	if res != "ok" {
		return fmt.Errorf("the snapshot is torn (quick_check: %s) — the live db was probably "+
			"mid-checkpoint; immutable=1 does not lock. Re-run", res)
	}
	return nil
}

// copyFile byte-copies src to dst. Both forks of a route come through here from the SAME seed, so
// they start byte-identical and neither engine can see the other's writes.
func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}

// seedIDs are the ids the seed allocated, resolved into the route inputs by resolveWriteParam.
type seedIDs struct {
	ticketA int64
	ticketB int64
}

// seedScratchDB applies the preconditions the POST routes need, to the ONE seed db every route forks
// from. Everything here is a row in a throwaway file; nothing is spawned and nothing leaves the temp
// dir. The three preconditions and why each exists:
//
//	a registered agent   ticket_agents' tg_ticket_agents_registered ABORTs an assignment of an
//	                     agent that is not in `agents`, so ticket.assign cannot run without one.
//	probe ticket A       kind IS NULL (ticket.kind's sql is UPDATE ... WHERE kind IS NULL), status
//	                     REQUESTED, and it carries a crew row — tg_tickets_active_needs_agent ABORTs
//	                     a move to ACTIVE with no assignment. That trigger is the #279 failure, and
//	                     satisfying it is what lets process_status be PROVEN rather than skipped.
//	probe ticket B       a second ticket with NO crew: edge.record's child, and ticket.assign's
//	                     target (assigning A's existing agent+role again would be an INSERT OR
//	                     IGNORE no-op and prove nothing).
//
// Timestamps are seeded with a FIXED constant, not strftime('now'), so the seed is deterministic.
func seedScratchDB(path string) (seedIDs, error) {
	var ids seedIDs
	d, err := sql.Open("sqlite", path)
	if err != nil {
		return ids, err
	}
	defer d.Close()

	const seedTS = 1700000000 // fixed, so the seed carries no wall-clock

	if _, err := d.Exec(
		`INSERT OR REPLACE INTO agents (agent_id, parent, prompt, tools, status, ts)
		 VALUES (?, NULL, '#451 route-equivalence probe (scratch db only)', '[]', 'active', ?)`,
		seededAgentID, seedTS); err != nil {
		return ids, fmt.Errorf("seed agent: %w", err)
	}

	newTicket := func(title string) (int64, error) {
		res, err := d.Exec(
			`INSERT INTO tickets (ts, updated, component, title, severity, status, body, meta, kind)
			 VALUES (?, ?, 'congruency-go', ?, 'info', 'REQUESTED', '#451 route-equivalence probe', NULL, NULL)`,
			seedTS, seedTS, title)
		if err != nil {
			return 0, err
		}
		return res.LastInsertId()
	}
	if ids.ticketA, err = newTicket("#451 equivalence probe ticket A (scratch db only)"); err != nil {
		return ids, fmt.Errorf("seed ticket A: %w", err)
	}
	if ids.ticketB, err = newTicket("#451 equivalence probe ticket B (scratch db only)"); err != nil {
		return ids, fmt.Errorf("seed ticket B: %w", err)
	}

	// A's crew: what tg_tickets_active_needs_agent demands before process_status may set ACTIVE.
	if _, err := d.Exec(
		`INSERT INTO ticket_agents (ts, ticket_id, agent_id, role) VALUES (?, ?, ?, 'coder')`,
		seedTS, ids.ticketA, seededAgentID); err != nil {
		return ids, fmt.Errorf("seed crew for ticket A: %w", err)
	}
	return ids, nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The row fingerprint: what "the resulting rows match" is measured with.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// tableShape is the column list of one table, in sqlite's column order.
type tableShape struct {
	name string
	cols []string
}

// dbShape lists every user table and its columns, ordered by name so two scans line up.
func dbShape(d *sql.DB) ([]tableShape, error) {
	rows, err := d.Query(
		"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
	if err != nil {
		return nil, err
	}
	var names []string
	for rows.Next() {
		var n string
		if err := rows.Scan(&n); err != nil {
			rows.Close()
			return nil, err
		}
		names = append(names, n)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}

	var out []tableShape
	for _, n := range names {
		cr, err := d.Query(`SELECT name FROM pragma_table_info(?) ORDER BY cid`, n)
		if err != nil {
			return nil, err
		}
		var cols []string
		for cr.Next() {
			var c string
			if err := cr.Scan(&c); err != nil {
				cr.Close()
				return nil, err
			}
			cols = append(cols, c)
		}
		cr.Close()
		if err := cr.Err(); err != nil {
			return nil, err
		}
		if len(cols) == 0 {
			continue // a table with no columns cannot hold a row
		}
		out = append(out, tableShape{name: n, cols: cols})
	}
	return out, nil
}

// rowSelect builds `SELECT rowid, typeof("c")||':'||quote("c"), ... FROM "t"`.
//
// typeof()+quote() is SQLITE's own canonical view of a stored cell, computed inside sqlite and
// returned as TEXT — so the comparison is driver-independent. It distinguishes what matters:
//
//	null:NULL   integer:42   real:1.5   text:'a''b'   blob:X'00FF'
//
// TEXT '2' and INTEGER 2 are DIFFERENT cells here, which is the whole point — db.go's note 1 says
// every bound value reaches sqlite as TEXT because PDO binds PARAM_STR, and this diff is what would
// catch the Go port binding an int64 instead. quote(NULL) returns the TEXT 'NULL' (not SQL NULL), so
// the concatenation never collapses.
func rowSelect(ts tableShape) string {
	parts := make([]string, 0, len(ts.cols))
	for _, c := range ts.cols {
		q := `"` + strings.ReplaceAll(c, `"`, `""`) + `"`
		parts = append(parts, "typeof("+q+")||':'||quote("+q+")")
	}
	return `SELECT rowid, ` + strings.Join(parts, ", ") + ` FROM "` + strings.ReplaceAll(ts.name, `"`, `""`) + `"`
}

// scanRowHashes fingerprints every row of every table as table -> rowid -> hash(full row). The hash
// covers the volatile columns too, so ANY change is detected here; the volatile columns are only
// forgiven later, when two engines' deltas are compared. Storing a 16-byte hash rather than the
// cells keeps a 31k-row / 17MB db to about half a megabyte.
func scanRowHashes(d *sql.DB, shape []tableShape) (map[string]map[int64]string, error) {
	out := make(map[string]map[int64]string, len(shape))
	for _, ts := range shape {
		rows, err := d.Query(rowSelect(ts))
		if err != nil {
			return nil, fmt.Errorf("fingerprint %s: %w", ts.name, err)
		}
		m := map[int64]string{}
		cells := make([]string, len(ts.cols))
		dest := make([]any, len(ts.cols)+1)
		var rowid int64
		dest[0] = &rowid
		for i := range cells {
			dest[i+1] = &cells[i]
		}
		for rows.Next() {
			if err := rows.Scan(dest...); err != nil {
				rows.Close()
				return nil, fmt.Errorf("fingerprint %s: %w", ts.name, err)
			}
			m[rowid] = hashCells(cells)
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return nil, fmt.Errorf("fingerprint %s: %w", ts.name, err)
		}
		out[ts.name] = m
	}
	return out, nil
}

func hashCells(cells []string) string {
	h := sha256.New()
	for _, c := range cells {
		h.Write([]byte(c))
		h.Write([]byte{0})
	}
	return hex.EncodeToString(h.Sum(nil)[:16])
}

// deltaRow is one row a route added, changed or removed, relative to the seed.
type deltaRow struct {
	table string
	rowid int64
	kind  string // "added" | "changed" | "removed"
	cols  []string
	cells []string // canonical typeof:quote per column; nil for "removed"
}

func (d deltaRow) String() string {
	if d.cells == nil {
		return fmt.Sprintf("%s[rowid %d] %s", d.table, d.rowid, d.kind)
	}
	parts := make([]string, len(d.cols))
	for i := range d.cols {
		parts[i] = d.cols[i] + "=" + d.cells[i]
	}
	return fmt.Sprintf("%s[rowid %d] %s {%s}", d.table, d.rowid, d.kind, strings.Join(parts, ", "))
}

// scanDelta walks EVERY table of a post-run db and returns the rows that differ from the seed. The
// walk is ordered (tables by name, rowids ascending) so two engines' deltas line up positionally.
//
// Every table is walked, not just the one the route's sql names, because a trigger can write
// somewhere the sql never mentions: process_status is an `UPDATE tickets`, and
// tg_tickets_journal_status turns it into a second INSERT into ticket_events.
func scanDelta(d *sql.DB, shape []tableShape, seed map[string]map[int64]string) ([]deltaRow, error) {
	var out []deltaRow
	for _, ts := range shape {
		seedRows := seed[ts.name]
		seen := make(map[int64]bool, len(seedRows))

		rows, err := d.Query(rowSelect(ts))
		if err != nil {
			return nil, fmt.Errorf("delta %s: %w", ts.name, err)
		}
		cells := make([]string, len(ts.cols))
		dest := make([]any, len(ts.cols)+1)
		var rowid int64
		dest[0] = &rowid
		for i := range cells {
			dest[i+1] = &cells[i]
		}
		var found []deltaRow
		for rows.Next() {
			if err := rows.Scan(dest...); err != nil {
				rows.Close()
				return nil, fmt.Errorf("delta %s: %w", ts.name, err)
			}
			seen[rowid] = true
			was, existed := seedRows[rowid]
			h := hashCells(cells)
			if existed && was == h {
				continue
			}
			kind := "added"
			if existed {
				kind = "changed"
			}
			found = append(found, deltaRow{
				table: ts.name, rowid: rowid, kind: kind,
				cols: ts.cols, cells: append([]string(nil), cells...),
			})
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return nil, fmt.Errorf("delta %s: %w", ts.name, err)
		}
		for rowid := range seedRows {
			if !seen[rowid] {
				found = append(found, deltaRow{table: ts.name, rowid: rowid, kind: "removed", cols: ts.cols})
			}
		}
		sort.Slice(found, func(i, j int) bool { return found[i].rowid < found[j].rowid })
		out = append(out, found...)
	}
	return out, nil
}

// volatileCellCompatible decides whether two canonical cells of an EXCLUDED column may differ.
//
// The exclusion is narrow on purpose. The two engines must still agree on the sqlite TYPE (a port
// that wrote text:'1784178764' where PHP wrote real:1784178764.0 is a real divergence and fails
// here), and the two values must sit within volatileWindowSecs of each other. Only the exact second
// is forgiven — which is the only thing strftime('%s','now') can legitimately disagree about.
func volatileCellCompatible(a, b string) (bool, string) {
	if a == b {
		return true, ""
	}
	at, av, aok := strings.Cut(a, ":")
	bt, bv, bok := strings.Cut(b, ":")
	if !aok || !bok {
		return false, "uninterpretable canonical cell"
	}
	if at != bt {
		return false, fmt.Sprintf("sqlite TYPE differs (%s vs %s) — a volatile column is excused its "+
			"VALUE, never its type", at, bt)
	}
	af, aerr := strconv.ParseFloat(av, 64)
	bf, berr := strconv.ParseFloat(bv, 64)
	if aerr != nil || berr != nil {
		return false, "not a number, so the +/- window cannot apply"
	}
	if d := af - bf; d > volatileWindowSecs || d < -volatileWindowSecs {
		return false, fmt.Sprintf("%.3fs apart, outside the +/-%.0fs window", d, volatileWindowSecs)
	}
	return true, ""
}

// compareDeltas is requirement (b): the RESULTING ROWS must match. It compares the rows PHP left
// behind with the rows Go left behind, forgiving only the volatile columns and only within their
// window. Returns "" when the two engines wrote the same rows.
func compareDeltas(php, gd []deltaRow) string {
	if len(php) != len(gd) {
		return fmt.Sprintf("the two engines wrote a DIFFERENT NUMBER OF ROWS: php=%d go=%d\n"+
			"  php wrote:\n%s\n  go wrote:\n%s", len(php), len(gd), renderDelta(php), renderDelta(gd))
	}
	var problems []string
	for i := range php {
		p, g := php[i], gd[i]
		if p.table != g.table || p.rowid != g.rowid || p.kind != g.kind {
			problems = append(problems, fmt.Sprintf("  row %d: php wrote %s[rowid %d] %s but go wrote %s[rowid %d] %s",
				i, p.table, p.rowid, p.kind, g.table, g.rowid, g.kind))
			continue
		}
		if len(p.cells) != len(g.cells) {
			problems = append(problems, fmt.Sprintf("  %s[rowid %d]: column count differs", p.table, p.rowid))
			continue
		}
		for c := range p.cells {
			col := p.cols[c]
			if p.cells[c] == g.cells[c] {
				continue
			}
			if _, excluded := volatileColumns[col]; excluded {
				if ok, why := volatileCellCompatible(p.cells[c], g.cells[c]); ok {
					continue
				} else {
					problems = append(problems, fmt.Sprintf(
						"  %s[rowid %d].%s (a VOLATILE column, but still not compatible: %s)\n"+
							"      php: %s\n      go : %s", p.table, p.rowid, col, why, p.cells[c], g.cells[c]))
					continue
				}
			}
			problems = append(problems, fmt.Sprintf(
				"  %s[rowid %d].%s DIFFERS\n      php: %s\n      go : %s",
				p.table, p.rowid, col, p.cells[c], g.cells[c]))
		}
	}
	if len(problems) == 0 {
		return ""
	}
	return "the two engines wrote DIFFERENT ROWS:\n" + strings.Join(problems, "\n")
}

func renderDelta(d []deltaRow) string {
	if len(d) == 0 {
		return "    (nothing)"
	}
	out := make([]string, len(d))
	for i, r := range d {
		out[i] = "    " + r.String()
	}
	return strings.Join(out, "\n")
}

// summariseDelta is the one-line "what this route wrote" for the test log.
func summariseDelta(d []deltaRow) string {
	if len(d) == 0 {
		return "no rows"
	}
	counts := map[string]int{}
	var order []string
	for _, r := range d {
		k := r.table + " " + r.kind
		if counts[k] == 0 {
			order = append(order, k)
		}
		counts[k]++
	}
	parts := make([]string, len(order))
	for i, k := range order {
		parts[i] = fmt.Sprintf("%d %s", counts[k], k)
	}
	return strings.Join(parts, ", ")
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Driving the two engines.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// phpServer is the ephemeral `php -S` running phpShimSource.
type phpServer struct {
	cmd  *exec.Cmd
	base string
	log  *bytes.Buffer
}

// startPHPServer writes the shim into dir and boots `php -S 127.0.0.1:<free port> <shim>`.
func startPHPServer(php, boot, dir string) (*phpServer, error) {
	shim := filepath.Join(dir, "equiv_router.php")
	if err := os.WriteFile(shim, []byte(phpShimSource), 0o600); err != nil {
		return nil, err
	}
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return nil, err
	}
	port := l.Addr().(*net.TCPAddr).Port
	l.Close()

	cmd := exec.Command(php, "-S", fmt.Sprintf("127.0.0.1:%d", port), shim)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), "EQUIV_BOOT="+boot)
	log := &bytes.Buffer{}
	cmd.Stdout = log
	cmd.Stderr = log
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	s := &phpServer{cmd: cmd, base: fmt.Sprintf("http://127.0.0.1:%d/", port), log: log}

	deadline := time.Now().Add(15 * time.Second)
	for time.Now().Before(deadline) {
		c, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", port), 200*time.Millisecond)
		if err == nil {
			c.Close()
			return s, nil
		}
		if cmd.Process == nil || cmd.ProcessState != nil {
			break
		}
		time.Sleep(25 * time.Millisecond)
	}
	s.stop()
	return nil, fmt.Errorf("the ephemeral php server never came up on port %d; php said:\n%s", port, log.String())
}

func (s *phpServer) stop() {
	if s == nil || s.cmd == nil || s.cmd.Process == nil {
		return
	}
	_ = s.cmd.Process.Kill()
	_ = s.cmd.Wait()
}

// call drives one route through the real congruency_rest_route(), against the scratch db named in
// the X-Equiv-Db header. body is the raw request body, which rest.php reads from php://input.
func (s *phpServer) call(route, method, dbPath, body string) (int, []byte, error) {
	var rdr io.Reader
	if body != "" {
		rdr = strings.NewReader(body)
	}
	req, err := http.NewRequest(method, s.base+"?route="+route, rdr)
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("X-Equiv-Db", dbPath)
	req.Header.Set("Content-Type", "application/json")
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()
	out, err := io.ReadAll(resp.Body)
	return resp.StatusCode, out, err
}

// goWriteRoute runs one route through the Go engine against its own scratch fork.
//
// A FRESH DB handle per route is not incidental: db.go pins one sqlite connection per Open() because
// PDO::lastInsertId() is a property of one connection, and rest.php opens a new PDO per request. A
// handle reused across routes would report the PREVIOUS route's rowid in this route's reply — the
// exact bug db.go's note 4 warns about. The shim opens a fresh PDO per request for the same reason.
//
// The error path mirrors the shim's catch, which mirrors congruency_rest_dispatch()'s: 500 and a
// PRETTY {"error": msg}.
func goWriteRoute(dbPath, route, method string, input map[string]any) (int, []byte, error) {
	d, err := Open(dbPath)
	if err != nil {
		return 0, nil, err
	}
	defer d.Close()
	reply, err := d.RunRoute(route, method, input, AllowAll{})
	if err != nil {
		body, encErr := phpJSONEncode(Obj{{"error", err.Error()}}, jsonPretty|jsonUnescapedSlashes)
		if encErr != nil {
			return 0, nil, encErr
		}
		return 500, append(body, '\n'), nil
	}
	return reply.Status, reply.Body, nil
}

// resolveWriteParam turns a declared input value into the concrete value that goes on the wire,
// swapping a seedRef for the id the seed actually allocated.
func resolveWriteParam(v any, ids seedIDs) (any, error) {
	switch r := v.(type) {
	case seedRef:
		switch r {
		case refTicketA:
			return ids.ticketA, nil
		case refTicketB:
			return ids.ticketB, nil
		}
		return nil, fmt.Errorf("unknown seed reference %q", string(r))
	}
	return v, nil
}

// buildWriteBody assembles the JSON request body for a route FROM THE ROUTE'S OWN ROW: it walks the
// params the row declares and takes the value writeRouteInputs supplies for each. A param the row
// declares but the inputs do not supply is an ERROR, not a silently-NULL bind — that is how a param
// added to a route row gets caught instead of quietly going unproven.
//
// The body is encoded with phpJSONEncode (db.go's PHP-faithful encoder), so the bytes PHP's
// json_decode() sees are the bytes this test intends.
func buildWriteBody(route string, decl map[string]string, in writeRouteInput, ids seedIDs) (string, error) {
	names := make([]string, 0, len(decl))
	for k := range decl {
		names = append(names, k)
	}
	sort.Strings(names)

	// (a) every declared param must have a value.
	var missing []string
	for _, n := range names {
		if _, ok := in.params[n]; !ok {
			missing = append(missing, n)
		}
	}
	// (b) every supplied value must be a param the row declares.
	var extra []string
	for k := range in.params {
		if _, ok := decl[k]; !ok {
			extra = append(extra, k)
		}
	}
	sort.Strings(extra)
	if len(missing) > 0 || len(extra) > 0 {
		return "", fmt.Errorf("writeRouteInputs[%q] does not match the route's declared params.\n"+
			"  declared by the api_routes row but not supplied here: %v\n"+
			"  supplied here but not declared by the row:             %v\n"+
			"  the row declares: %v\n"+
			"Routes are DATA: if the row changed, this input must change with it — a param left "+
			"unsupplied would bind NULL and silently prove nothing.", route, missing, extra, names)
	}

	obj := make(Obj, 0, len(names))
	for _, n := range names {
		v, err := resolveWriteParam(in.params[n], ids)
		if err != nil {
			return "", fmt.Errorf("route %s param %s: %w", route, n, err)
		}
		obj = append(obj, Field{n, v})
	}
	b, err := phpJSONEncode(obj, jsonUnescapedSlashes)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

// goInputFor reproduces the input map rest.php assembles before congruency_rest_route binds anything:
//
//	$input = $_GET;                                              // so 'route' IS in the map
//	if (POST|PUT|PATCH|DELETE) { $input = array_merge($input, json_decode(php://input, true)); }
//
// The body is decoded with db.go's jsonUnmarshalObject, which types numbers the way PHP's
// json_decode does (integral -> int, fractional -> float) — so both engines see not just the same
// keys but the same PHP value types. Body keys win over $_GET, as array_merge does.
func goInputFor(route, body string) (map[string]any, error) {
	input := map[string]any{"route": route}
	if body == "" {
		return input, nil
	}
	var decoded map[string]any
	if err := jsonUnmarshalObject(body, &decoded); err != nil {
		return nil, err
	}
	for k, v := range decoded {
		input[k] = v
	}
	return input, nil
}

// postRoutesFromDB reads the write surface FROM THE TABLE: every route whose method column names
// POST. Routes are data, so the list of routes to prove is data too.
func postRoutesFromDB(d *sql.DB) ([]string, error) {
	rows, err := d.Query(`SELECT name, method FROM api_routes ORDER BY name`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var name string
		var method sql.NullString
		if err := rows.Scan(&name, &method); err != nil {
			return nil, err
		}
		m := strings.ToUpper(method.String)
		if m == "" {
			m = "GET" // rest.php: strtoupper((string)$def['method'] ?: 'GET')
		}
		for _, part := range strings.Split(m, ",") {
			if strings.TrimSpace(part) == "POST" {
				out = append(out, name)
				break
			}
		}
	}
	return out, rows.Err()
}

// routeRow reads one api_routes row's method/params, the way the engine does.
func routeRow(d *sql.DB, name string) (method string, params map[string]string, err error) {
	var m, p sql.NullString
	err = d.QueryRow(`SELECT method, params FROM api_routes WHERE name = ?`, name).Scan(&m, &p)
	if err != nil {
		return "", nil, err
	}
	return m.String, declaredParams(p.String), nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PART 2 — the write sweep itself.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// writeHarness is everything a write subtest needs, built once.
type writeHarness struct {
	php      *phpServer
	seedPath string
	shape    []tableShape
	seedFP   map[string]map[int64]string
	ids      seedIDs
	tmp      string
}

// newWriteHarness does steps 1 and 2 of the discipline in the file header: snapshot the live db
// (immutable=1 + VACUUM INTO), then seed ONE db that every route forks from.
func newWriteHarness(t *testing.T, live, php, boot string) (*writeHarness, string) {
	tmp := t.TempDir()

	snap := filepath.Join(tmp, "snapshot.sqlite")
	if err := snapshotLiveDB(live, snap); err != nil {
		return nil, fmt.Sprintf("cannot snapshot the live state db: %v", err)
	}

	seed := filepath.Join(tmp, "seed.sqlite")
	if err := copyFile(snap, seed); err != nil {
		return nil, fmt.Sprintf("cannot fork the snapshot into a seed: %v", err)
	}
	ids, err := seedScratchDB(seed)
	if err != nil {
		return nil, fmt.Sprintf("cannot seed the scratch db: %v", err)
	}

	sd, err := sql.Open("sqlite", "file:"+seed+"?immutable=1")
	if err != nil {
		return nil, fmt.Sprintf("cannot reopen the seed: %v", err)
	}
	defer sd.Close()
	shape, err := dbShape(sd)
	if err != nil {
		return nil, fmt.Sprintf("cannot read the seed's shape: %v", err)
	}
	seedFP, err := scanRowHashes(sd, shape)
	if err != nil {
		return nil, fmt.Sprintf("cannot fingerprint the seed: %v", err)
	}

	srv, err := startPHPServer(php, boot, tmp)
	if err != nil {
		return nil, fmt.Sprintf("cannot start the ephemeral php server: %v", err)
	}
	t.Cleanup(srv.stop)

	return &writeHarness{php: srv, seedPath: seed, shape: shape, seedFP: seedFP, ids: ids, tmp: tmp}, ""
}

// fork makes one route's private scratch db from the seed.
func (h *writeHarness) fork(name string) (string, error) {
	p := filepath.Join(h.tmp, name+".sqlite")
	if err := copyFile(h.seedPath, p); err != nil {
		return "", err
	}
	return p, nil
}

// deltaOf reads back what an engine left behind in its fork.
func (h *writeHarness) deltaOf(path string) ([]deltaRow, error) {
	d, err := sql.Open("sqlite", "file:"+path+"?immutable=1")
	if err != nil {
		return nil, err
	}
	defer d.Close()
	return scanDelta(d, h.shape, h.seedFP)
}

// runWriteSweep is #451: prove all 24 POST routes on response bytes AND resulting rows.
func runWriteSweep(t *testing.T) {
	live, why := resolveLiveDB()
	if why != "" {
		t.Skip("NAMED SKIP (whole write sweep): " + why)
	}
	php, why := resolvePHP()
	if why != "" {
		t.Skip("NAMED SKIP (whole write sweep): " + why)
	}
	boot, why := resolveBoot()
	if why != "" {
		t.Skip("NAMED SKIP (whole write sweep): " + why)
	}

	before, err := captureLiveDirState(live)
	if err != nil {
		t.Skipf("NAMED SKIP (whole write sweep): cannot stat the live state db %s: %v", live, err)
	}
	t.Cleanup(func() { assertLiveDBUntouched(t, live, before) })

	h, why := newWriteHarness(t, live, php, boot)
	if why != "" {
		t.Skip("NAMED SKIP (whole write sweep): " + why)
	}

	t.Logf("live state db (snapshotted, never written): %s", live)
	t.Logf("php engine: %s driving %s/rest.php (ephemeral server at %s)", php, boot, h.php.base)
	t.Logf("go engine: db.go RunRoute, in-process")
	t.Logf("seed: %s (probe ticket A=%d with a crew, ticket B=%d, agent %q registered); "+
		"every route forks TWO byte-identical scratch dbs from it",
		h.seedPath, h.ids.ticketA, h.ids.ticketB, seededAgentID)

	// The volatile-column exclusions, enumerated in the output as the ticket requires.
	cols := make([]string, 0, len(volatileColumns))
	for c := range volatileColumns {
		cols = append(cols, c)
	}
	sort.Strings(cols)
	for _, c := range cols {
		t.Logf("VOLATILE COLUMN EXCLUDED FROM ROW EQUALITY: %q — %s. It is still required to have the "+
			"SAME sqlite type on both sides and to be within %.0fs.", c, volatileColumns[c], volatileWindowSecs)
	}
	t.Logf("AUTOINCREMENT ids are NOT excluded: both forks come from ONE seed, so both carry the same " +
		"sqlite_sequence and must allocate the SAME id. Comparing them is stronger than excluding them.")

	// Routes are data: read the write surface from the table, and hold the inputs to it.
	sd, err := sql.Open("sqlite", "file:"+h.seedPath+"?immutable=1")
	if err != nil {
		t.Fatalf("cannot open the seed to read api_routes: %v", err)
	}
	defer sd.Close()

	declared, err := postRoutesFromDB(sd)
	if err != nil {
		t.Fatalf("cannot read the POST routes from api_routes: %v", err)
	}
	assertCoverage(t, declared)

	// Before any write proof is believed: prove the PHP side of it is the real engine, and prove the
	// volatile-column exclusion is a window rather than a hole.
	t.Run("_shim_fidelity", func(t *testing.T) { runShimFidelity(t, h) })
	t.Run("_volatile_exclusion_is_bounded", runVolatileExclusionBounds)

	var proven, skipped, attempted []string
	for _, route := range declared {
		route := route
		t.Run(route, func(t *testing.T) {
			// attempted is what actually ran: a `-run .../<one route>` filter silently drops the
			// others, and the spine check below must not read that as a failure.
			attempted = append(attempted, route)
			in, ok := writeRouteInputs[route]
			if !ok { // assertCoverage already failed; keep the subtest honest anyway.
				t.Fatalf("no input declared for POST route %q", route)
			}
			if in.skip != "" {
				skipped = append(skipped, route)
				t.Skipf("NAMED SKIP: %s", in.skip)
			}

			method, decl, err := routeRow(sd, route)
			if err != nil {
				t.Fatalf("cannot read the api_routes row: %v", err)
			}
			body, err := buildWriteBody(route, decl, in, h.ids)
			if err != nil {
				t.Fatalf("%v", err)
			}
			if in.precondition != "" {
				t.Logf("PRECONDITION: %s", in.precondition)
			}
			t.Logf("row: method=%q params=%v", method, decl)
			t.Logf("body: %s", body)

			phpDB, err := h.fork(route + ".php")
			if err != nil {
				t.Fatalf("cannot fork the php scratch db: %v", err)
			}
			goDB, err := h.fork(route + ".go")
			if err != nil {
				t.Fatalf("cannot fork the go scratch db: %v", err)
			}

			pStatus, pBody, err := h.php.call(route, "POST", phpDB, body)
			if err != nil {
				t.Fatalf("the php engine could not be driven: %v\nphp server log:\n%s", err, h.php.log.String())
			}
			input, err := goInputFor(route, body)
			if err != nil {
				t.Fatalf("cannot assemble the go input: %v", err)
			}
			gStatus, gBody, err := goWriteRoute(goDB, route, "POST", input)
			if err != nil {
				t.Fatalf("the go engine could not be driven: %v", err)
			}

			// (a) the RESPONSE must match.
			if gStatus != pStatus {
				t.Errorf("STATUS MISMATCH: go=%d php=%d\n  go body : %q\n  php body: %q",
					gStatus, pStatus, gBody, pBody)
			}
			if !bytes.Equal(gBody, pBody) {
				t.Errorf("RESPONSE BYTE MISMATCH (go=%dB php=%dB):\n%s", len(gBody), len(pBody),
					unifiedish(gBody, pBody))
			}

			// (b) the RESULTING ROWS must match. This is the half a response comparison cannot do,
			// and the half #279 needed: identical JSON over different rows is the failure mode.
			pDelta, err := h.deltaOf(phpDB)
			if err != nil {
				t.Fatalf("cannot read back the php scratch db: %v", err)
			}
			gDelta, err := h.deltaOf(goDB)
			if err != nil {
				t.Fatalf("cannot read back the go scratch db: %v", err)
			}
			if problem := compareDeltas(pDelta, gDelta); problem != "" {
				t.Errorf("ROW MISMATCH for %s — the response bytes matched but the engines wrote "+
					"different rows. This is the #279 class.\n%s", route, problem)
			}

			if t.Failed() {
				return
			}
			proven = append(proven, route)
			t.Logf("PROVEN: response identical (%d, %dB) AND resulting rows identical (%s)",
				pStatus, len(pBody), summariseDelta(pDelta))
			t.Logf("rows written (identical on both engines, volatile columns aside):\n%s", renderDelta(pDelta))
		})
	}

	t.Run("_279_governance_guard", func(t *testing.T) { runGovernanceGuard279(t, h) })

	assertSpineProven(t, proven, attempted)

	named := "none"
	if len(skipped) > 0 {
		named = strings.Join(skipped, ", ")
	}
	t.Logf("WRITE SUMMARY: %d/%d POST routes PROVEN (response bytes AND resulting rows identical, "+
		"Go vs PHP, from the same pristine snapshot); %d skipped with a NAMED reason (%s); "+
		"0 unnamed skips (assertCoverage above forbids them).",
		len(proven), len(declared), len(skipped), named)
}

// runVolatileExclusionBounds proves the ts/updated exclusion is a NARROW WINDOW, not a blanket hole.
//
// "Exclude the timestamps" is the easiest place for a differential to quietly stop measuring: once a
// column is excluded, ANY divergence in it is forgiven forever, and the test still prints green. So
// the exclusion here forgives exactly one thing — the exact second two engines stamped — and this
// subtest pins the boundary with cases that MUST still be rejected.
//
// The other half of the same worry (that a NON-volatile column might be silently forgiven) is not
// checkable from a table of strings; it was checked by MUTATION instead, and these are the measured
// numbers. Binding every string param through strings.ToUpper in a COPY of db.go (the repo untouched)
// makes Go write different rows while leaving the {route,affected,rowid} response byte-identical —
// the #279 shape exactly. Result: 22 of the 24 routes fail, and 21 of those are caught by the ROW
// DIFF ALONE, with the response bytes identical. The response check alone would have caught ONE
// (ticket.assign, whose INSERT OR IGNORE then reports affected=0). The two routes that do not fail
// are no-ops for that mutation, not blind spots: process_status binds only "ACTIVE", which is already
// uppercase, and telemetry.record short-circuits and writes nothing at all.
//
// MEASURED BLIND SPOT, recorded here rather than left for the reader to discover: binding an int
// param as sqlite INTEGER instead of TEXT (breaking db.go's note 1, where PDO's PARAM_STR makes every
// bound value TEXT) is NOT caught by this sweep. It is not a gap in the diff — sqlite's column
// affinity coerces TEXT '459' to INTEGER 459 on the way into an INTEGER column, so both engines
// genuinely store the same cell and genuinely return the same bytes. The divergence only becomes
// observable where no affinity coerces (db.go's note 1 gives `WHERE (id+0) = :id`), and no route in
// api_routes is written that way today. If one ever is, this sweep will start catching it; until
// then, this test cannot speak for that property and does not pretend to.
func runVolatileExclusionBounds(t *testing.T) {
	for _, c := range []struct {
		name     string
		php, gov string
		want     bool
	}{
		{"identical stamps", "real:1784179630.0", "real:1784179630.0", true},
		{"one second apart — the ONLY thing the exclusion exists to forgive",
			"real:1784179630.0", "real:1784179631.0", true},
		{"the sqlite TYPE differs — a port writing text where PHP writes real MUST still fail",
			"real:1784179630.0", "text:'1784179630'", false},
		{"integer vs real is a type divergence too", "integer:1784179630", "real:1784179630.0", false},
		{"a wild value inside the same type is NOT forgiven",
			"real:1784179630.0", "real:1784190000.0", false},
		{"one engine wrote no stamp at all", "null:NULL", "real:1784179630.0", false},
	} {
		got, why := volatileCellCompatible(c.php, c.gov)
		if got != c.want {
			t.Errorf("volatileCellCompatible(%q, %q) = %v (%s), want %v — %s",
				c.php, c.gov, got, why, c.want, c.name)
		}
	}
	t.Logf("VOLATILE EXCLUSION IS BOUNDED: an excluded column is forgiven ONLY a value within "+
		"%.0fs of the other engine's, and never a difference in sqlite type.", volatileWindowSecs)
}

// runShimFidelity answers the only real objection to PART 2's golden: "your PHP side is a shim you
// wrote, not the server."
//
// PART 1 measures the Go engine against the LIVE rest.php over the live db and finds the GET routes
// byte-identical. This re-measures the Go engine against the SHIM's rest.php over the seed and
// requires the same byte-identity. Both comparisons have the Go engine as their fixed point, so
// agreeing with it on all 38 GET routes is agreement with each other: the shim is a front door onto
// the engine the live server runs, not a second implementation of it.
//
// It is also the strictly BETTER-CONDITIONED half of the two. PART 1 fights live writers and has to
// skip a route as VOLATILE when the db moves inside its window; here both engines read one frozen
// seed, so there is nothing to skip and nothing to forgive.
//
// Both engines read the SAME fork (a GET route is a SELECT and writes nothing) — and rather than
// assume that, the subtest ends by asserting the fork's delta against the seed is empty, so a GET
// route that ever started writing would be caught here too.
func runShimFidelity(t *testing.T, h *writeHarness) {
	fork, err := h.fork("_shim_fidelity")
	if err != nil {
		t.Fatalf("cannot fork a scratch db: %v", err)
	}
	d, err := Open(fork)
	if err != nil {
		t.Fatalf("cannot open the scratch db with the Go engine: %v", err)
	}
	defer d.Close()

	var identical, documented []string
	for _, route := range getRoutes {
		pStatus, pBody, err := h.php.call(route, "GET", fork, "")
		if err != nil {
			t.Errorf("%s: the shim could not be driven: %v\nphp server log:\n%s", route, err, h.php.log.String())
			continue
		}
		gStatus, gBody := goRoute(d, route)
		if bytes.Equal(gBody, pBody) {
			identical = append(identical, route)
			if gStatus != pStatus {
				t.Errorf("%s: bytes match but status differs: go=%d shim=%d", route, gStatus, pStatus)
			}
			continue
		}
		if knownDriverMsgDiff[route] && isErrorEnvelope(gBody) && isErrorEnvelope(pBody) {
			documented = append(documented, route)
			continue
		}
		t.Errorf("SHIM FIDELITY BROKEN for %s (go=%dB shim=%dB, status go=%d shim=%d):\n%s\n"+
			"The write proofs use this shim as their PHP golden, so this must hold before any of them "+
			"is believed.", route, len(gBody), len(pBody), gStatus, pStatus, unifiedish(gBody, pBody))
	}

	delta, err := h.deltaOf(fork)
	if err != nil {
		t.Fatalf("cannot read back the scratch db: %v", err)
	}
	if len(delta) != 0 {
		t.Errorf("a GET route WROTE to the db (the read sweep is supposed to be read-only):\n%s",
			renderDelta(delta))
	}

	if t.Failed() {
		return
	}
	t.Logf("SHIM FIDELITY PROVEN: %d/%d GET routes byte-identical between the shim's rest.php and the "+
		"Go engine over one frozen seed (%d documented driver-msg diffs: %s), and the %d GET routes "+
		"wrote zero rows. The shim is the same engine the live server runs.",
		len(identical), len(getRoutes), len(documented), strings.Join(documented, ","), len(getRoutes))
}

// runGovernanceGuard279 drives the #279 FAILURE on purpose — the one the sweep above is careful to
// satisfy — and proves the two engines REFUSE it identically.
//
// #279 shipped a pair_loop change that ran process_status ACTIVE before ticket.assign. The
// tg_tickets_active_needs_agent trigger ABORTs exactly that, so every new dispatch died with HTTP
// 500 until it was reverted. Proving the happy path (process_status above, on a ticket WITH a crew)
// is only half the story: an engine that quietly SUCCEEDED where PHP aborts would be a far worse
// divergence than one that returns different bytes, because it would write a row the governance
// spine forbids. So this drives process_status ACTIVE at probe ticket B, which has NO crew.
//
// What is asserted, and what is not:
//
//   - both engines answer 500 with an {"error": ...} envelope — asserted;
//   - both messages carry the TRIGGER's own text, which is sqlite's, not the driver's — asserted,
//     and read from the trigger's SQL in sqlite_master rather than copied here, so it cannot rot;
//   - both scratch dbs are left with ZERO rows changed: the ABORT means the forbidden write never
//     landed on either engine — asserted, and it is the real point of this test;
//   - the two messages are not byte-identical, and cannot be: PDO says "SQLSTATE[HY000]: General
//     error: 19 <text>" and go-sqlite says its own thing. That is db.go's documented
//     unreproducible-by-design driver-message class (knownDriverMsgDiff), so the envelope, the
//     status, the trigger text and the resulting rows are compared, and the driver's prefix is not.
func runGovernanceGuard279(t *testing.T, h *writeHarness) {
	const route = "process_status"

	trigger, err := triggerAbortText(h.seedPath, "tg_tickets_active_needs_agent")
	if err != nil {
		t.Fatalf("cannot read the trigger's own message out of sqlite_master: %v", err)
	}
	t.Logf("the trigger under test (tg_tickets_active_needs_agent) raises: %q", trigger)

	body, err := phpJSONEncode(Obj{{"id", h.ids.ticketB}, {"status", "ACTIVE"}}, jsonUnescapedSlashes)
	if err != nil {
		t.Fatalf("cannot encode the body: %v", err)
	}
	t.Logf("driving the #279 failure: %s on probe ticket B (%d), which has NO crew. body: %s",
		route, h.ids.ticketB, body)

	phpDB, err := h.fork("_279.php")
	if err != nil {
		t.Fatalf("cannot fork the php scratch db: %v", err)
	}
	goDB, err := h.fork("_279.go")
	if err != nil {
		t.Fatalf("cannot fork the go scratch db: %v", err)
	}

	pStatus, pBody, err := h.php.call(route, "POST", phpDB, string(body))
	if err != nil {
		t.Fatalf("the php engine could not be driven: %v\nphp server log:\n%s", err, h.php.log.String())
	}
	input, err := goInputFor(route, string(body))
	if err != nil {
		t.Fatalf("cannot assemble the go input: %v", err)
	}
	gStatus, gBody, err := goWriteRoute(goDB, route, "POST", input)
	if err != nil {
		t.Fatalf("the go engine could not be driven: %v", err)
	}

	// Both must REFUSE. An engine that succeeds here writes a row the spine forbids.
	if pStatus != 500 {
		t.Errorf("php did NOT refuse the #279 write: status %d, body %s", pStatus, pBody)
	}
	if gStatus != 500 {
		t.Errorf("go did NOT refuse the #279 write: status %d, body %s. An engine that succeeds where "+
			"PHP aborts is a WORSE divergence than different bytes — it writes a row the governance "+
			"spine forbids.", gStatus, gBody)
	}
	for _, c := range []struct {
		who  string
		body []byte
	}{{"php", pBody}, {"go", gBody}} {
		if !isErrorEnvelope(c.body) {
			t.Errorf("%s did not answer an {\"error\": ...} envelope: %s", c.who, c.body)
			continue
		}
		if !bytes.Contains(c.body, []byte(trigger)) {
			t.Errorf("%s's 500 does not carry the trigger's own message.\n  want to contain: %q\n  got: %s",
				c.who, trigger, c.body)
		}
	}

	// The real assertion: the forbidden write landed on NEITHER engine.
	pDelta, err := h.deltaOf(phpDB)
	if err != nil {
		t.Fatalf("cannot read back the php scratch db: %v", err)
	}
	gDelta, err := h.deltaOf(goDB)
	if err != nil {
		t.Fatalf("cannot read back the go scratch db: %v", err)
	}
	if len(pDelta) != 0 {
		t.Errorf("php ABORTed but still wrote rows:\n%s", renderDelta(pDelta))
	}
	if len(gDelta) != 0 {
		t.Errorf("go ABORTed but still wrote rows:\n%s", renderDelta(gDelta))
	}
	if problem := compareDeltas(pDelta, gDelta); problem != "" {
		t.Errorf("the two engines left different rows behind after the abort:\n%s", problem)
	}

	if t.Failed() {
		return
	}
	t.Logf("PROVEN (the #279 class): both engines REFUSE process_status=ACTIVE on a crew-less ticket " +
		"with a 500 carrying the trigger's own message, and BOTH leave the db with zero rows changed.")
	t.Logf("the driver prefixes differ by design and are NOT compared (db.go's documented "+
		"PDO-vs-go-sqlite message class):\n  php: %s  go : %s", firstLineOfError(pBody), firstLineOfError(gBody))
}

// triggerAbortText pulls a trigger's RAISE(ABORT, '...') message out of its own SQL in
// sqlite_master, so the expected text is read from the schema under test rather than copied into
// this file where it could rot away from the migration that defines it.
func triggerAbortText(dbPath, trigger string) (string, error) {
	d, err := sql.Open("sqlite", "file:"+dbPath+"?immutable=1")
	if err != nil {
		return "", err
	}
	defer d.Close()
	var ddl string
	if err := d.QueryRow(
		`SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?`, trigger).Scan(&ddl); err != nil {
		return "", fmt.Errorf("trigger %s: %w", trigger, err)
	}
	_, rest, ok := strings.Cut(ddl, "RAISE(ABORT,")
	if !ok {
		return "", fmt.Errorf("trigger %s does not RAISE(ABORT, ...): %s", trigger, ddl)
	}
	open := strings.Index(rest, "'")
	if open < 0 {
		return "", fmt.Errorf("trigger %s has no quoted abort message: %s", trigger, ddl)
	}
	rest = rest[open+1:]
	close := strings.Index(rest, "'")
	if close < 0 {
		return "", fmt.Errorf("trigger %s has an unterminated abort message: %s", trigger, ddl)
	}
	return rest[:close], nil
}

// firstLineOfError pulls the message out of an {"error": "..."} envelope for a one-line log.
func firstLineOfError(body []byte) string {
	for _, line := range strings.Split(string(body), "\n") {
		if strings.Contains(line, `"error"`) {
			return strings.TrimSpace(line) + "\n"
		}
	}
	return strings.TrimSpace(string(body)) + "\n"
}

// assertCoverage is the "no silent skips" gate. It requires writeRouteInputs to name EXACTLY the
// POST routes api_routes declares — a new POST row cannot be silently uncovered, and an input for a
// route that no longer exists cannot rot unnoticed.
func assertCoverage(t *testing.T, declared []string) {
	have := map[string]bool{}
	for _, r := range declared {
		have[r] = true
	}
	var uncovered []string
	for _, r := range declared {
		if _, ok := writeRouteInputs[r]; !ok {
			uncovered = append(uncovered, r)
		}
	}
	var stale []string
	for r := range writeRouteInputs {
		if !have[r] {
			stale = append(stale, r)
		}
	}
	sort.Strings(uncovered)
	sort.Strings(stale)
	if len(uncovered) > 0 {
		t.Errorf("UNCOVERED POST ROUTES (%d): %v. api_routes declares them and this test does not "+
			"drive them — that is exactly the blanket skip #451 exists to remove. Add an entry to "+
			"writeRouteInputs (with a NAMED skip reason if it genuinely cannot be driven).",
			len(uncovered), uncovered)
	}
	if len(stale) > 0 {
		t.Errorf("STALE INPUTS (%d): %v. writeRouteInputs names routes api_routes no longer declares "+
			"as POST.", len(stale), stale)
	}
	t.Logf("write surface (read from api_routes, not hard-coded): %d POST routes: %s",
		len(declared), strings.Join(declared, ", "))
}

// assertSpineProven refuses to let the four governance-spine routes fall out of the PROVEN set. The
// ticket names them because they are what #279 broke; a named skip is not acceptable for these.
//
// It judges only the spine routes this run ATTEMPTED. A `-run .../<one route>` filter drops the
// others before their subtest body ever executes, and reporting "the spine is not proven" because
// the operator asked for one route would be a false alarm — the check would then be crying wolf on
// exactly the runs where it has nothing to say. The acceptance command
// (`go test . -run TestRouteEquivalence`) attempts all 24, so the full assertion holds there.
func assertSpineProven(t *testing.T, proven, attempted []string) {
	got := map[string]bool{}
	for _, r := range proven {
		got[r] = true
	}
	tried := map[string]bool{}
	for _, r := range attempted {
		tried[r] = true
	}
	var missing, notRun []string
	for _, r := range spineRoutes {
		switch {
		case got[r]:
		case !tried[r]:
			notRun = append(notRun, r)
		default:
			missing = append(missing, r)
		}
	}
	if len(missing) > 0 {
		t.Errorf("THE GOVERNANCE SPINE IS NOT PROVEN: %v. These are what the dispatch machinery "+
			"itself runs and what #279 broke; they must be PROVEN, not skipped or failed.", missing)
		return
	}
	if len(notRun) > 0 {
		t.Logf("SPINE: not judged this run — %v were filtered out by -run, so this run cannot speak "+
			"for them. Run `go test . -run TestRouteEquivalence` for the full assertion.", notRun)
		return
	}
	t.Logf("SPINE PROVEN: %s", strings.Join(spineRoutes, ", "))
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The entry point.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// TestRouteEquivalence is the whole sweep: the GET half against the live rest.php, and the write half
// against throwaway scratch dbs. The two halves are guarded independently, so the write proofs still
// run when the live server is down (and vice versa).
func TestRouteEquivalence(t *testing.T) {
	t.Run("read_GET_routes", runGetSweep)
	t.Run("write_POST_routes", runWriteSweep)
}
