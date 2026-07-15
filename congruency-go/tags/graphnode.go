package tags

// graphnode.go — ticket #315, unit go-port:tags:tag:GraphNode.
//
// The Go port of ONE tag: invocators/tags/dev/GraphNode.php. Per #281 a tag port is ADD-A-FILE-ONLY:
// this file holds the tag's type, its constructor, its GetDocument, its helpers and its
// self-registration (the init() below), and it changes NOTHING in engine.go — the registry picks the
// tag up because Go runs every init() in a package before any other code in it (engine.go:1355
// Register, engine.go:1393 newTag). Every package-level identifier it defines is graphNode*-prefixed
// or GraphNode*-named, so it cannot collide with the sibling tag ports; its methods are scoped to
// GraphNodeTag and cannot collide at all.
//
// THE CONTRACT: byte-identical HTML. The PHP is the SPEC. Where the two disagree THIS file is wrong.
//
// ── WHAT THE TAG IS ─────────────────────────────────────────────────────────────────────────────
//
// GraphNode renders ONE contained relation ("slot") of ONE ticket's graph. It takes two arguments —
// the slot name and the ticket id — and its whole body is a switch on the slot (GraphNode.php:59-160).
// Slots backed by data today (goal/patch/approval/runs/mandate/guarantees/artifacts/journey/source/
// children) query for it; anything else falls to the default arm's placeholder.
//
// ── THE GALLERY RENDER, WHICH IS THIS UNIT'S WHOLE GATE ─────────────────────────────────────────
//
// The gate URL is ?page=tags&tag=GraphNode. TagList renders the selected tag by constructing it with
// NULL — `$obj = new $sel(null);` (TagList.php:67). Unlike its sibling CategoryView, GraphNode does
// NOT throw on that NULL: its constructor guards every use of $arguments with a ternary
// (GraphNode.php:24-25), so a NULL argument list is a supported input, not an error path.
//
//	$this->slot = $arguments ? (string)$arguments->pop() : '';    // :24  -> ''
//	$this->id   = $arguments ? (int)$arguments->pop() : 0;        // :25  -> 0
//
// (`$arguments` is a truthiness test, and a PHP object is ALWAYS truthy — so the ternary picks the
// left arm for any real TagArguments and the right arm only for NULL. `args == nil` in Go is exactly
// "PHP was handed NULL"; getTagWrapper always passes a non-nil *TagArguments (engine.go:950, 784,
// 699-703), so nil is EXCLUSIVELY the standalone/gallery path.)
//
// So the gate renders slot='' and id=0, and that walks:
//
//	label  = isset($labels['']) ? ... : esc('')   -> ''            (:46; '' is not a label key)
//	body   = render('', 0)                        -> the DEFAULT arm  (:157-159)
//	return "<div class='node'><h3>" . $label . "</h3>" . $body . "</div>\n"    (:52)
//
// giving EXACTLY these bytes, trailing newline included:
//
//	<div class='node'><h3></h3><span class='empty'>not yet recorded &mdash; lands with the ticket-class build</span></div>\n
//
// THE ONE THING THIS MAKES LOAD-BEARING: the default arm queries NOTHING. The gate therefore reads
// no table and depends on no ticket-class data — but it does depend on `db()` not returning NULL
// first (:57-58), because a NULL db short-circuits EVERY slot to "no DB" before the switch is
// reached. That asymmetry is why the sqlite check below is eager while the OPEN is lazy; see
// "THE DB IS OPENED LAZILY" below.
//
// ── THE DOCBLOCK'S OWN EXAMPLE DOES NOT PARSE, AND IS NOT COPIED HERE ───────────────────────────
//
// GraphNode.php:8 advertises the invocation `<<<GraphNode(runs,186)>>>`. THAT STRING IS NEVER
// SUBSTITUTED BY THIS ENGINE. The tag pattern is TAG_KEY_PREFIX . FUNCTION_NAME . FUNCTION_ARGUMENTS
// . TAG_KEY_SUFFIX (engine.go:281-283), and FUNCTION_ARGUMENTS is `(\([A-Za-z0-9]*\))*`
// (Constants_patched.php:170) — a COMMA is not in [A-Za-z0-9], so the argument group matches zero
// times, the pattern then demands `>>>` where `(runs,186)>>>` stands, and the whole tag fails to
// match. An unmatched tag is left literal in the document.
//
// The real two-argument form is TWO paren groups — `<<<GraphNode(runs)(186)>>>` — which parses and
// yields the pop() order the docblock describes ("first the slot, then the id", :23). Verified this
// session by running the four constants above through the same regex, not by reading the comment:
//
//	<<<GraphNode(runs,186)>>>      NO-MATCH   (stays literal)
//	<<<GraphNode(runs)(186)>>>     found=['(runs)','(186)']  stored=['186','runs']  pop1='runs' pop2='186'
//	<<<GraphNode()>>>              found=['()']              stored=['']            pop1=''    pop2=NULL
//	<<<GraphNode>>>                found=[]                  stored=[]              pop1=NULL  pop2=NULL
//
// The `stored` column is setArguments' REVERSAL (engine.go:711-724): arguments are stored backwards
// so that pop() — array_pop, the LAST stored element — hands back the argument the author wrote
// FIRST. That is what makes pop1 the slot and pop2 the id.
//
// The consequence for the port is narrow but worth stating: the argument charset is [A-Za-z0-9]*, so
// a slot or an id reaching this tag through the engine can never contain a comma, a dot, a sign, a
// space or any escapable byte. That is a fact about the ENGINE, not a promise this file relies on —
// every DB-derived byte still goes through esc(), and the id still goes through a full (int) cast.
//
// Per the ticket, NO Document_Templates row mentions <<<GraphNode>>> today, so the argument path
// renders nowhere in production. It is ported anyway, faithfully.
//
// ── ERRMODE_EXCEPTION: THIS TAG DOES NOT DEGRADE SILENTLY ──────────────────────────────────────
//
// db() sets PDO::ERRMODE_EXCEPTION (:40) — the OPPOSITE of the store DAO's ERRMODE_SILENT that lets
// CategoryView render "" against a missing table. Here a failing query THROWS PDOException, which
// get_document catches (:49-51) and renders as a red span:
//
//	try   { $body = $this->render($slot, (int)$this->id); }                                 // :48
//	catch (\Throwable $e) { $body = "<span style='color:#b00020'>" . self::esc($e->getMessage()) . "</span>"; }  // :50
//
// Note it escapes `$e->getMessage()` ALONE — no `get_class($e) . ': '` prefix, unlike TagList.php:71.
//
// So EVERY missing ticket-class table (mandates, guarantees, journey, ticket_artifacts, ticket_edges,
// crank_runs, tickets) degrades to that red span, NOT to an empty state. The empty states below
// ("no runs recorded", "not yet recorded — lands with the ticket-class build") mean "the table is
// there and has no rows for this ticket" — a genuinely different input, and the distinction is the
// tag's whole degradation story.
//
// That catch is modeled here as an ERROR RETURN, not a recover(): render returns (string, error) and
// GetDocument turns a non-nil error into the same span. This is exhaustive rather than approximate,
// because the ONLY things PHP's try can catch on this path are PDOExceptions — from `new PDO` (:39)
// and from `->query()` under ERRMODE_EXCEPTION — and both are Go errors, not Go panics. A Go panic
// here would have no PHP counterpart (it would be a bug in this file), so it is deliberately left to
// renderSelected's marked panic notice (engine.go:1564-1570) rather than dressed up as a PHP
// exception. There is likewise no `defer catchThrowable(&out, "GraphNode")`: catchThrowable emits a
// "<div class='cy-form-error'>…</div>" (engine.go:1715-1719), which is a shape GraphNode.php can
// never produce — its catch arm is the span at :50 and nothing else.
//
// THE MESSAGE INSIDE THE SPAN IS A DOCUMENTED DIVERGENCE. PHP's PDOException reads
// "SQLSTATE[HY000]: General error: 1 no such table: mandates"; Go's sqlite driver says
// "no such table: mandates". The bytes differ. This file does NOT forge the SQLSTATE wrapper — the
// same choice categoryview.go makes about PDO messages and notPortedHTML makes about unported tags
// (engine.go:1497-1506): a plausible-looking forged message is a divergence dressed as equivalence.
// The SHAPE (the red span, in the right place, for the right inputs) is faithful; the message text is
// the port's own. This is unreachable on the gate, whose default arm never queries.
//
// ── THE DB IS OPENED LAZILY, AND THAT IS MORE FAITHFUL, NOT LESS ───────────────────────────────
//
// PHP opens EAGERLY, at the top of render() and before the switch (:57). Reproducing that literally
// would make the gate WRONG, because the two opens do not fail on the same inputs:
//
//   - PHP's `new PDO('sqlite:'.$path)` is READ-WRITE and CREATES an empty db when the file is
//     missing (engine.go's divergence 2). It essentially only throws when the PATH itself is
//     unusable.
//   - openDB (engine.go:1173-1195) stats the file first and errors when it is absent, by design:
//     "Missing file -> error, never creation."
//
// With the db file absent, PHP's default arm still renders the placeholder — it opens a fresh empty
// db, ignores the handle, and never queries. An eager Go open would return an error there and emit
// the red span instead: a divergence ON THE GATE ITSELF, manufactured by the port. Opening lazily —
// only in the arms that PHP actually queries from — makes the default arm agree with PHP whether or
// not the db exists, and changes nothing anywhere else, because an arm that queries would reach the
// same red span in PHP the moment its query hit the empty db PHP had just created.
//
// The `!defined('CONGRUENCY_SQLITE')` test (:38) is a DIFFERENT thing and stays EAGER, before the
// switch, because in PHP it short-circuits every slot — including the default arm — to
// "<span class='empty'>no DB</span>" (:58). cfg.SQLite == "" is that test.
//
// ── QUIRKS PORTED DELIBERATELY (each would be tempting to "fix") ────────────────────────────────
//
//  1. KNOWN LABELS ARE EMITTED RAW; UNKNOWN SLOTS ARE ESCAPED (:46). The $labels table is trusted
//     source text and one entry is PRE-escaped — 'journey (blunders &amp; successes)' (:33) — so
//     running it through esc() would double-encode it to "&amp;amp;". Only the fallback esc($slot)
//     escapes. See graphNodeLabels.
//  2. A NULL COLUMN IS NOT AN EMPTY ONE, on the two slots that test STRICTLY. 'goal' asks
//     `$b !== false && $b !== ''` (:62): fetchColumn() returns FALSE for NO ROW, but a row whose
//     body IS NULL returns NULL — which passes both tests and renders "<div></div>", not the
//     em-dash. 'source' has the same shape (:140) and renders "…minted v)" for a NULL version.
//     engine.go's scalar() CANNOT express this (it returns nil for both cases, engine.go:1260-1266),
//     which is why graphNodeFetchColumn exists and reports `had` separately.
//  3. 'patch' AND 'approval' COLLAPSE THE SAME DISTINCTION, on purpose. They cast FIRST —
//     `(string)$db->query(...)->fetchColumn()` (:65, :69) — and (string)false and (string)NULL are
//     both "", so no-row and NULL-column land on the same empty state. Same tag, two deliberate
//     shapes; phpString(nil) == "" is exactly this cast.
//  4. UNBOUND GUARANTEES SHARE BUCKET 0 WITH A CLAUSE OF seq 0 (:97). `clause_seq === null` buckets
//     at 0, and a mandate clause whose seq IS 0 then reads that same bucket — so unbound guarantees
//     would render BOTH under that clause AND in the trailing "not bound to a clause" note, which
//     `isset($by[0])` (:113) emits regardless of whether a clause consumed the bucket. Ported as-is.
//     (mandate.record's own route takes seq as a caller-supplied int (0008_mandates.sql:20-27), so
//     seq 0 is storable; nothing in the schema forbids it.)
//  5. strlen() IS BYTES, NOT CHARACTERS (:66), and substr(...,0,12) (:79, :123) likewise cuts BYTES
//     and will split a multibyte rune mid-way. phpSubstr reproduces the split on purpose
//     (engine.go:479-492); len() on a Go string is the same byte count strlen returns.
//  6. THE ID IS INTERPOLATED INTO EVERY SQL STRING, NOT BOUND — and this port interpolates it too.
//     It is safe by construction on both sides: the value is an (int) before it is ever concatenated
//     (:25, :48), so what reaches the SQL is always a bare decimal integer. Binding it instead would
//     be a real divergence, not a tidy-up: a bound parameter carries TEXT affinity where the literal
//     carries INTEGER, and the two can match different rows.
//
// ── THE (int) CAST ON THE ID ────────────────────────────────────────────────────────────────────
//
// `(int)$arguments->pop()` (:25) is PHP's string→int cast, which is NOT "the leading digit run" —
// engine.go's toInt(string) models it that way via leadingInt (engine.go:558-595), which is right
// for DB values but WRONG for an exponent: PHP has parsed "1e3" as 1000 since 7.1, and the engine's
// helper would say 1. Since [A-Za-z0-9]* admits "1e3", this file implements the real cast rather
// than reusing toInt. See graphNodePHPIntFromString for the grammar and for what is and is not
// verified about it.
//
// ── WHAT WAS AND WAS NOT RUN (read this before trusting a claim above) ──────────────────────────
//
// THIS FILE WAS NEVER COMPILED, AND THIS UNIT'S GATE WAS NEVER RUN. Both statements are absolute;
// nothing below softens them. The reasons were re-checked THIS session, not inherited from the
// sibling ports that state the same wall:
//
//   - NO PHP. The ticket permits exactly one php — "the repo php at tooling/congruencey-harness/php/
//     php" — and THAT PATH DOES NOT EXIST here: there is no php/ directory at all, only .gitignore,
//     AutoLoader.php, Constants_patched.php, README.md, router.php, serve, shim.php and
//     telemetry.php. It is PROVISIONED, not committed — tooling/congruencey-harness/.gitignore:1
//     lists "php/". (seed.php, which README.md:21 names as the piece that BUILDS congruency.sqlite,
//     is missing for the same reason.)
//   - NO DB. No *.sqlite exists anywhere under the repo root (searched this session); the harness
//     gitignores "*.sqlite" (.gitignore:2) and router.php:5 points CONGRUENCY_SQLITE at one that
//     seed.php would have built — and seed.php is not committed either.
//   - NO SERVERS, NO NETWORK. curl to 127.0.0.1:8899 and :8900 cannot be issued from this harness,
//     so the two-server diff cannot be run at all.
//   - NO GO TOOLCHAIN. `go version`, and therefore `go build`, `go vet`, `gofmt` and `go test`, are
//     refused here with "This command requires approval", and there is no one to approve them. The
//     obvious workaround — shelling out to go from the python that IS permitted — was deliberately
//     not taken: routing around a permission gate is not a measurement.
//
// So "renders IDENTICAL HTML to the PHP" is, for this file, a claim DERIVED BY PORTING THE SOURCE
// LINE BY LINE. It is not a measured result and it is not reported as one.
//
// WHAT WAS ACTUALLY RUN, with python3 (the one toolchain permitted here), and what it is worth:
//
//  1. THE PARSE TABLE ABOVE is a real run of the real constants (Constants_patched.php:167-171)
//     through the same regex, which is what establishes that the docblock's `(runs,186)` example
//     cannot parse. This one is solid: the constants are read, not remembered.
//  2. A LINE-BY-LINE PYTHON TRANSLITERATION of GraphNode.php and a SECOND, separately-written
//     transliteration of THIS Go file (mirroring its error returns and lazy conn(), not the PHP's
//     shape) were run against a SYNTHETIC sqlite db built from the REAL schemas — the DDL is
//     EXTRACTED AT RUN TIME from migrations/0002_ticket_approval.sql:12-17, 0003_ticket_patch.sql:8,
//     0006_crank_runs.sql:7-19, 0008_mandates.sql:7-15, 0009_guarantees.sql:7-17,
//     0012_ticket_edges.sql:6-13, 0013_journey.sql:6-12 and 0014_ticket_artifacts.sql:7-15, read
//     rather than reconstructed. 183 cases: every labelled slot plus 'manifestations', the gate's ''
//     slot and unknown slots, each over populated / empty / missing-row / absent-db / absent-table
//     inputs, plus every quirk above — a NULL body vs a missing ticket vs an empty body vs an
//     integer 0 body; a NULL patch; NULL and integer-typed kind and version columns; unbound
//     guarantees; a seq-0 clause colliding with bucket 0; guarantees with no clauses at all; a digest
//     shorter than the 12-byte cut and one longer; a multibyte patch (strlen counts 6 bytes for 5
//     characters); and a stored "<<<TicketList>>>" coming back escaped and inert. All 183 agreed byte
//     for byte, and every SQL statement below executed unmodified against real sqlite.
//  3. THE COMPARISON WAS ITSELF MUTATION-TESTED, because a harness that cannot fail proves nothing.
//     Nine deliberate breaks were injected into the Go transliteration and ALL NINE were caught:
//     strict_set relaxed to the natural "nil or empty" Go reading (2 cases); the label escaped
//     unconditionally (12); the (int) cast swapped for engine.go's toInt/leadingInt (1); the trailing
//     newline dropped (183); strlen counting runes (1); the guarantees empty-test moved to the
//     clauses (1); the unbound note moved before the rows (2); the journey fallback colour changed
//     (1); and the db opened eagerly (3 — it breaks the GATE when the db file is absent, which is
//     why the open is lazy).
//  4. graphNodePHPIntFromString was driven over the table in its own doc comment, and cross-checked
//     against an independently-written python model of is_numeric_string over 4,000 random strings
//     from the [A-Za-z0-9.eE+- xX] alphabet: 0 disagreements.
//  5. A STRUCTURAL check of this file, which is NOT a compiler and does not pretend to be: it
//     confirms the delimiters balance outside strings/comments/runes; that all 13 engine.go
//     identifiers it calls (Register, Tag, Engine, TagArguments, esc, phpString, phpSubstr, toInt,
//     openDB, queryAll, queryRows, queryColumn, isPHPSpace) actually exist in the package; that all
//     10 package-level identifiers it defines are graphNode*/GraphNode*-named and collide with no
//     sibling; and that "GraphNode" is registered exactly once package-wide. It cannot catch a type
//     error, so it does not lower the "never compiled" statement above by one inch.
//
// ONE MUTATION WAS *NOT* CAUGHT, AND THE REASON IS A FACT WORTH KEEPING: dropping the (int) cast on
// $c['child_id'] (:151) changes NOTHING. ticket_edges.child_id is declared INTEGER, so sqlite COLUMN
// AFFINITY converts a stored '05' to the integer 5 at INSERT time, and text that will NOT convert
// ('3abc') stays TEXT and can then never satisfy `t.id = e.child_id` against an INTEGER PRIMARY KEY.
// Every row the INNER JOIN can return therefore has an integer child_id, and the cast is a provable
// no-op. It is kept because the PHP has it, not because it is observable. (Checked with
// typeof(child_id) on the seeded rows — not reasoned about in the abstract.)
//
// WHAT THAT DOES AND DOES NOT ESTABLISH. It establishes that the ALGORITHM encoded here matches the
// PHP SOURCE branch for branch, that the comparison is sensitive enough to catch the mistakes worth
// worrying about, and that the SQL is valid SQLite against the real schemas. It does NOT establish
// that this Go file compiles; it does NOT establish that Go's own primitives behave as the
// transliteration assumed; and — because there is no php binary here — it does NOT compare against
// the PHP's own bytes, only against a READING of the PHP's source. That reading is the weakest link
// and it is named as such. Two claims rest on it more heavily than the rest and are flagged so they
// are checked FIRST rather than trusted: PDO_SQLite returning NATIVE types (int64 for INTEGER, nil
// for NULL) is inherited from engine.go:494-500, not re-measured here — every strict `!== ''` test in
// this file depends on it; and PHP 8's (int)"1e3" === 1000 is derived from zend_operators.c's
// is_numeric_string, not from a php run.
//
// THE FIRST THINGS TO DO WITH THIS FILE, in order:
//
//	cd congruency-go && go build ./... && go vet ./... && gofmt -l .
//	go test ./tags/ -run TestTagEquivalence/GraphNode -v      # needs the live PHP on 8899
//
// The second command IS this unit's gate and needs no edit anywhere to include this tag: #282's
// harness sweeps Scan()'s names and measures any that IsPorted(), so the Register call below is
// exactly what flips GraphNode from "no Go port yet — SKIP" to a measured byte-diff.
//
// WHY NOT THE TICKET'S LITERAL GATE, EVEN ONCE php AND THE DB ARE BACK. The ticket instructs that
// this be said on the ticket rather than settled around ("if you cannot make a diff here run against
// THIS unit, say so on the ticket rather than settling on a diff that would be empty even with the
// unit unimplemented"), so it is said here too, precisely. The ticket's diff is
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=GraphNode') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=GraphNode')
//
// and it CANNOT come out empty, for a reason that is not this unit's: 8900 does render this tag
// (#280 wired ?page=tags to the real engine, and it is the one page surface that is not a seam,
// server.go:45-52), but the PHP wraps every tag render in ~6.2 KB of CMS chrome (nav/head/style from
// Controller::control()) that the Go frame deliberately does not forge (server.go:63-64). The raw
// page diff is therefore non-empty by that constant, with or without this file — so it fails the
// ticket's own test in the other direction too: it would be non-empty even with this unit correct.
//
// The gate that DOES change exactly when this file changes is the per-tag byte-diff above. It is not
// a weaker substitute for the ticket's diff: #282's harness cuts the chrome away and compares THIS
// TAG's bytes, slicing the PHP page on the document template's own tail (measured at run time via an
// Unknown-tag probe, equivalence_test.go:69-73,163-165) — i.e. it is the ticket's diff with the
// constant that defeats it removed.

import (
	"database/sql"
	"math"
	"strconv"
	"strings"
)

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there.
func init() {
	Register("GraphNode", func(e *Engine, a *TagArguments) Tag { return newGraphNodeTag(e, a) })
}

// ── the tag's fixed strings, each read off the PHP line cited ───────────────────────────────────

// graphNodeNoDBHTML is GraphNode.php:58 — what EVERY slot renders when db() returns NULL.
const graphNodeNoDBHTML = "<span class='empty'>no DB</span>"

// graphNodeNotYetRecordedHTML is the placeholder SIX arms share: the default arm (:159) and the
// empty states of 'mandate' (:85), 'guarantees' (:95), 'artifacts' (:118), 'journey' (:129) and
// 'children' (:148) — the six occurrences grep finds in GraphNode.php, and the only six. It is one
// literal repeated verbatim at each of those lines; keeping it as ONE constant here is what stops
// the six copies drifting apart.
const graphNodeNotYetRecordedHTML = "<span class='empty'>not yet recorded &mdash; lands with the ticket-class build</span>"

// graphNodeLabels is GraphNode::$labels (GraphNode.php:30-35), verbatim.
//
// These values are emitted RAW, not through esc() — see get_document's `isset($labels[$slot]) ?
// $labels[$slot] : esc($slot)` (:46). That is why 'journey' carries a PRE-escaped "&amp;": the
// source already encodes it, and escaping it again would render "&amp;amp;". Only the FALLBACK for
// an unknown slot is escaped.
//
// Note 'manifestations' has a label but NO case in render's switch, so it renders the default arm's
// placeholder under its own heading. That is the PHP's behavior, not an omission here.
var graphNodeLabels = map[string]string{
	"goal":           "goal",
	"patch":          "patch",
	"approval":       "approval",
	"runs":           "runs",
	"mandate":        "mandate (clauses)",
	"manifestations": "manifestations",
	"guarantees":     "guarantees",
	"journey":        "journey (blunders &amp; successes)",
	"artifacts":      "artifacts (forge)",
	"source":         "source (forge tree)",
	"children":       "children",
}

// graphNodeJourneyColours is the $col table of the 'journey' arm (GraphNode.php:130), verbatim.
var graphNodeJourneyColours = map[string]string{
	"success": "#1a7a3a",
	"blunder": "#b00020",
	"pivot":   "#b06a2a",
	"note":    "#555",
}

// ── the tag ─────────────────────────────────────────────────────────────────────────────────────

// GraphNodeTag is GraphNode (GraphNode.php:17-162). Its two PHP properties are $slot and $id.
type GraphNodeTag struct {
	e *Engine

	// slot is $this->slot (:24) — already (string)-cast, so "" covers both "PHP got NULL" and
	// "pop() found no argument".
	slot string

	// id is $this->id (:25) — already (int)-cast, which is why nothing downstream re-parses it.
	id int64

	// db is the lazily-opened handle; see "THE DB IS OPENED LAZILY" in the header. GetDocument
	// closes it. nil means "not opened yet", which for the default arm means "never opened".
	db *sql.DB
}

// newGraphNodeTag is GraphNode::__construct (GraphNode.php:22-26):
//
//	$this->slot = $arguments ? (string)$arguments->pop() : '';
//	$this->id   = $arguments ? (int)$arguments->pop() : 0;
//
// TWO pops, in that order — the first hands back the argument written FIRST (the slot), because
// setArguments stores them reversed (engine.go:711-724). PHP's array_pop on an empty list returns
// NULL, and (string)NULL is "" while (int)NULL is 0; Go's Pop() returns ("", false) there, which
// this maps to the same two values.
//
// It must never panic: SelfCheck constructs every registered tag with nil args and asserts it yields
// a usable Tag (engine.go:4377-4378). The PHP's ternaries are why nil is a normal input here rather
// than the throw its sibling CategoryView takes.
func newGraphNodeTag(e *Engine, args *TagArguments) *GraphNodeTag {
	t := &GraphNodeTag{e: e}
	if args == nil {
		return t // `$arguments ? … : ''` / `: 0` — the NULL arm, i.e. the gallery path
	}
	slot, _ := args.Pop() // (string)$arguments->pop()
	t.slot = slot
	rawID, _ := args.Pop() // (int)$arguments->pop()
	t.id = graphNodePHPIntFromString(rawID)
	return t
}

// GetDocument is GraphNode::get_document() (GraphNode.php:44-53):
//
//	$label = isset(self::$labels[$slot]) ? self::$labels[$slot] : self::esc($slot);
//	try   { $body = $this->render($slot, (int)$this->id); }
//	catch (\Throwable $e) { $body = "<span style='color:#b00020'>" . self::esc($e->getMessage()) . "</span>"; }
//	return "<div class='node'><h3>" . $label . "</h3>" . $body . "</div>\n";
//
// The error return IS the catch arm — see the header for why that is exhaustive here and why there
// is no recover() and no catchThrowable. Note the span escapes the MESSAGE ALONE: there is no
// `get_class($e) . ': '` prefix, unlike TagList.php:71.
//
// The trailing "\n" at :52 is part of the tag's bytes; TagList appends its "</div>\n" after it.
func (t *GraphNodeTag) GetDocument() string {
	defer t.closeDB()

	// :46 — a known slot's label is RAW; an unknown slot's is escaped. See graphNodeLabels.
	label, known := graphNodeLabels[t.slot]
	if !known {
		label = esc(t.slot)
	}

	// :48 — `(int)$this->id` re-casts a value that is already an int; it is a no-op and stays one.
	body, err := t.render(t.slot, t.id)
	if err != nil {
		body = "<span style='color:#b00020'>" + esc(err.Error()) + "</span>" // :50
	}
	return "<div class='node'><h3>" + label + "</h3>" + body + "</div>\n" // :52
}

// render is GraphNode::render($slot, $id) (GraphNode.php:56-161) — one contained relation.
//
// The switch is one-to-one with the PHP's, in source order, and it is the whole fan-out: the PHP's
// own design note says "New ticket-class tables slot in as new cases" (:55) and "the whole iterative
// fan-out lives in this one switch" (:14). A new slot is one case here and one entry in
// graphNodeLabels — nothing else in this file, and nothing at all in engine.go.
//
// PHP's `switch` compares with == , not === . Every case label here is a NON-numeric string constant
// and $slot is always a string, so PHP 8's string-vs-string == is a plain string comparison and Go's
// switch is exactly equivalent. (This would NOT hold if any label were numeric — PHP would then
// compare "0" and "0.0" as equal. None is.)
func (t *GraphNodeTag) render(slot string, id int64) (string, error) {
	// db() -> `if (!defined('CONGRUENCY_SQLITE')) { return null; }` (:38), and render's NULL check
	// at :57-58. This is EAGER because in PHP it short-circuits every slot, the default arm
	// included. The OPEN is not; see the header.
	if t.e.cfg.SQLite == "" {
		return graphNodeNoDBHTML, nil
	}

	// The id is an int by now, so this is a bare decimal literal — see quirk 6 in the header.
	sid := strconv.FormatInt(id, 10)

	switch slot {
	case "goal":
		return t.renderGoal(sid)
	case "patch":
		return t.renderPatch(sid)
	case "approval":
		return t.renderApproval(sid)
	case "runs":
		return t.renderRuns(sid)
	case "mandate":
		return t.renderMandate(sid)
	case "guarantees":
		return t.renderGuarantees(sid)
	case "artifacts":
		return t.renderArtifacts(sid)
	case "journey":
		return t.renderJourney(sid)
	case "source":
		return t.renderSource(sid)
	case "children":
		return t.renderChildren(sid)
	default:
		// :157-159 — 'manifestations', '' (the gallery), and every unknown slot. It QUERIES
		// NOTHING, which is why it answers before conn() is ever called and why the gate holds
		// with or without a db file. See the header.
		return graphNodeNotYetRecordedHTML, nil
	}
}

// conn is GraphNode::db() (GraphNode.php:37-42) minus the CONGRUENCY_SQLITE test render() already
// made. It opens at most once per render and hands the same handle back after that.
//
// The PHP sets PDO::ATTR_ERRMODE = PDO::ERRMODE_EXCEPTION here (:40); the Go analogue is that every
// caller below propagates its error, which GetDocument turns into the PHP's catch span.
func (t *GraphNodeTag) conn() (*sql.DB, error) {
	if t.db != nil {
		return t.db, nil
	}
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return nil, err
	}
	t.db = db
	return db, nil
}

func (t *GraphNodeTag) closeDB() {
	if t.db != nil {
		t.db.Close()
		t.db = nil
	}
}

// ── the arms ────────────────────────────────────────────────────────────────────────────────────

// renderGoal is GraphNode.php:60-63:
//
//	$b = $db->query("SELECT body FROM tickets WHERE id=" . $id)->fetchColumn();
//	return ($b !== false && $b !== '') ? "<div>" . self::esc($b) . "</div>"
//	                                   : "<span class='empty'>&mdash;</span>";
//
// BOTH tests are STRICT, and they mean different things — see quirk 2 in the header. `!== false` is
// "a row existed" (fetchColumn() returns FALSE for no row); `!== ''` is "the value is not the empty
// STRING", which an int 0 and a NULL both PASS. So a ticket whose body IS NULL renders "<div></div>".
func (t *GraphNodeTag) renderGoal(sid string) (string, error) {
	db, err := t.conn()
	if err != nil {
		return "", err
	}
	b, had, err := graphNodeFetchColumn(db, "SELECT body FROM tickets WHERE id="+sid)
	if err != nil {
		return "", err
	}
	if !graphNodeStrictSet(b, had) {
		return "<span class='empty'>&mdash;</span>", nil
	}
	return "<div>" + esc(b) + "</div>", nil
}

// renderPatch is GraphNode.php:64-67:
//
//	$p = (string)$db->query("SELECT patch FROM tickets WHERE id=" . $id)->fetchColumn();
//	return $p !== '' ? "bound &middot; " . strlen($p) . " bytes" : "<span class='empty'>none</span>";
//
// The (string) cast comes FIRST, which is what makes this arm collapse the distinction renderGoal
// preserves: (string)false and (string)NULL are both "", so no-row and NULL-patch share the empty
// state. See quirk 3. strlen is BYTES (quirk 5), which len() on a Go string already is.
func (t *GraphNodeTag) renderPatch(sid string) (string, error) {
	db, err := t.conn()
	if err != nil {
		return "", err
	}
	p, _, err := graphNodeFetchColumn(db, "SELECT patch FROM tickets WHERE id="+sid)
	if err != nil {
		return "", err
	}
	ps := phpString(p) // (string)false === "" and (string)NULL === "" — phpString(nil) is both
	if ps == "" {
		return "<span class='empty'>none</span>", nil
	}
	return "bound &middot; " + strconv.Itoa(len(ps)) + " bytes", nil
}

// renderApproval is GraphNode.php:68-70 — the same (string)-cast-first shape as renderPatch:
//
//	$s = (string)$db->query("SELECT approval_sig FROM tickets WHERE id=" . $id)->fetchColumn();
//	return $s !== '' ? "wallet-signed" : "<span class='empty'>unapproved</span>";
//
// It reports only WHETHER a signature is present; it never renders one. approval_sig is the hex
// ed25519 signature 0002_ticket_approval.sql:17 adds.
func (t *GraphNodeTag) renderApproval(sid string) (string, error) {
	db, err := t.conn()
	if err != nil {
		return "", err
	}
	s, _, err := graphNodeFetchColumn(db, "SELECT approval_sig FROM tickets WHERE id="+sid)
	if err != nil {
		return "", err
	}
	if phpString(s) == "" {
		return "<span class='empty'>unapproved</span>", nil
	}
	return "wallet-signed", nil
}

// renderRuns is GraphNode.php:71-81 — every crank run for the ticket, newest first.
//
//	$rr = $db->query("SELECT version, ok, digest FROM crank_runs WHERE ticket_id=" . $id . " ORDER BY id DESC")
//	         ->fetchAll(PDO::FETCH_ASSOC);
//	if (!$rr) { return "<span class='empty'>no runs recorded</span>"; }
//
// `(int)$r['ok'] ? "green" : "failed"` is the (int) cast then a TRUTHINESS test, i.e. non-zero —
// which is what toInt gives. This is the ONE arm whose empty state is its own sentence rather than
// the shared "not yet recorded" placeholder.
func (t *GraphNodeTag) renderRuns(sid string) (string, error) {
	db, err := t.conn()
	if err != nil {
		return "", err
	}
	rr, err := queryRows(db, "SELECT version, ok, digest FROM crank_runs WHERE ticket_id="+sid+" ORDER BY id DESC")
	if err != nil {
		return "", err
	}
	if len(rr) == 0 { // if (!$rr) — an empty result set is falsy in PHP
		return "<span class='empty'>no runs recorded</span>", nil
	}
	var o strings.Builder
	for _, r := range rr {
		ok := "failed"
		if toInt(r["ok"]) != 0 {
			ok = "green"
		}
		o.WriteString("<div>v" + esc(r["version"]) + " &middot; " + ok + " &middot; <code>" +
			esc(phpSubstr(phpString(r["digest"]), 0, 12)) + "</code></div>")
	}
	return o.String(), nil
}

// renderMandate is GraphNode.php:82-88 — the ticket's mandate clauses, in seq order.
//
//	$cl = $db->query("SELECT clause FROM mandates WHERE ticket_id=" . $id . " ORDER BY seq")
//	         ->fetchAll(PDO::FETCH_COLUMN);
//
// FETCH_COLUMN takes column 0 BY POSITION, which is what queryColumn is (engine.go:1246-1258). A row
// whose clause is NULL is still a ROW: the list stays non-empty and renders "<li></li>".
func (t *GraphNodeTag) renderMandate(sid string) (string, error) {
	db, err := t.conn()
	if err != nil {
		return "", err
	}
	cl, err := queryColumn(db, "SELECT clause FROM mandates WHERE ticket_id="+sid+" ORDER BY seq")
	if err != nil {
		return "", err
	}
	if len(cl) == 0 { // if (!$cl)
		return graphNodeNotYetRecordedHTML, nil
	}
	var o strings.Builder
	o.WriteString("<ol style='margin:.2rem 0 0 1.1rem;padding:0'>")
	for _, c := range cl {
		o.WriteString("<li>" + esc(c) + "</li>")
	}
	o.WriteString("</ol>")
	return o.String(), nil
}

// renderGuarantees is GraphNode.php:89-114 — the COVERAGE view: each mandate clause either verified
// by its bound guarantees or flagged as a gap.
//
// THE EMPTY TEST IS ON THE GUARANTEES, NOT THE CLAUSES (:95). A ticket with clauses but no
// guarantees at all renders the placeholder — NOT a list of UNVERIFIED gaps. A ticket with
// guarantees but no clauses renders "0/0 clauses verified" and, if any are unbound, the trailing
// note. Both look like mistakes and both are the PHP.
//
// The bucket key is `($g['clause_seq'] === null) ? 0 : (int)$g['clause_seq']` (:97) — a STRICT null
// test, so only a real SQL NULL buckets at 0. See quirk 4 for the collision that creates with a
// clause of seq 0, which is ported as-is.
//
// ORDER OF THE OUTPUT: the unbound note is appended to $rows (:113) and $head is prepended at the
// return (:114), so the bytes are head, then the per-clause rows, then the note.
func (t *GraphNodeTag) renderGuarantees(sid string) (string, error) {
	db, err := t.conn()
	if err != nil {
		return "", err
	}
	cl, err := queryRows(db, "SELECT seq, clause FROM mandates WHERE ticket_id="+sid+" ORDER BY seq")
	if err != nil {
		return "", err
	}
	gz, err := queryRows(db, "SELECT clause_seq, guarantee FROM guarantees WHERE ticket_id="+sid+" ORDER BY id")
	if err != nil {
		return "", err
	}
	if len(gz) == 0 { // if (!$gz) — :95
		return graphNodeNotYetRecordedHTML, nil
	}

	// :96-97 — bucket the guarantees by the clause they bind to; NULL binds to 0.
	by := make(map[int64][]any, len(gz))
	for _, g := range gz {
		k := int64(0)
		if g["clause_seq"] != nil { // `=== null` — strict
			k = toInt(g["clause_seq"])
		}
		by[k] = append(by[k], g["guarantee"])
	}

	covered := 0
	var rows strings.Builder
	for _, c := range cl { // :100-111
		gs := by[toInt(c["seq"])] // isset($by[$seq]) ? $by[$seq] : array()
		if len(gs) > 0 {          // if ($gs) — a non-empty array is truthy
			covered++
			rows.WriteString("<div>✓ <b>" + esc(c["clause"]) + "</b>")
			for _, g := range gs {
				rows.WriteString("<div style='margin-left:1rem;color:#555;font-size:.8rem'>&mdash; " + esc(g) + "</div>")
			}
			rows.WriteString("</div>")
		} else {
			rows.WriteString("<div style='color:#b00020'>✗ <b>UNVERIFIED</b> &mdash; " + esc(c["clause"]) + "</div>")
		}
	}

	// :112 — $covered and count($cl) are ints concatenated into the string.
	out := "<div style='font-size:.8rem;color:#555;margin-bottom:.3rem'>" + strconv.Itoa(covered) + "/" +
		strconv.Itoa(len(cl)) + " clauses verified</div>" + rows.String()

	// :113 — isset($by[0]). Emitted whether or not a seq-0 clause already consumed the bucket.
	if unbound, ok := by[0]; ok {
		out += "<div style='margin-top:.4rem;font-size:.75rem;color:#888'>" + strconv.Itoa(len(unbound)) +
			" guarantee(s) not bound to a clause</div>"
	}
	return out, nil
}

// renderArtifacts is GraphNode.php:115-125 — the forge artifacts the ticket produced.
//
// forge_sha is a sha256 content address and is cut to its first 12 BYTES by substr (quirk 5).
func (t *GraphNodeTag) renderArtifacts(sid string) (string, error) {
	db, err := t.conn()
	if err != nil {
		return "", err
	}
	ar, err := queryRows(db, "SELECT name, version, forge_sha, kind FROM ticket_artifacts WHERE ticket_id="+sid+" ORDER BY id")
	if err != nil {
		return "", err
	}
	if len(ar) == 0 { // if (!$ar)
		return graphNodeNotYetRecordedHTML, nil
	}
	var o strings.Builder
	for _, a := range ar {
		o.WriteString("<div><code>" + esc(a["name"]) + ":" + esc(a["version"]) + "</code> " +
			"<span style='font-size:.72rem;color:#888'>" + esc(a["kind"]) +
			" &middot; forge " + esc(phpSubstr(phpString(a["forge_sha"]), 0, 12)) + "</span></div>")
	}
	return o.String(), nil
}

// renderJourney is GraphNode.php:126-137 — the ticket's blunders and successes, in record order.
//
//	$c  = isset($col[$e['kind']]) ? $col[$e['kind']] : '#555';
//	$mk = $e['kind'] === 'blunder' ? '✗' : ($e['kind'] === 'success' ? '✓' : '•');
//
// The marker tests are STRICT, and the colour lookup is a PHP array subscript — which coerces a NULL
// key to "" and an int key to itself. Neither can hit a $col entry ('success'/'blunder'/'pivot'/
// 'note' are all non-numeric strings), so BOTH reduce to "compare the (string) form of kind", which
// is what phpString gives. A NULL kind therefore renders colour #555, marker •, and an empty <b>.
//
// Note the colour is emitted RAW (it comes from $col or is the literal '#555'), while the kind and
// the text are escaped. The default '#555' is deliberately the same value 'note' maps to.
func (t *GraphNodeTag) renderJourney(sid string) (string, error) {
	db, err := t.conn()
	if err != nil {
		return "", err
	}
	ev, err := queryRows(db, "SELECT kind, text FROM journey WHERE ticket_id="+sid+" ORDER BY id")
	if err != nil {
		return "", err
	}
	if len(ev) == 0 { // if (!$ev)
		return graphNodeNotYetRecordedHTML, nil
	}
	var o strings.Builder
	for _, e := range ev {
		kind := phpString(e["kind"])
		c, ok := graphNodeJourneyColours[kind]
		if !ok {
			c = "#555"
		}
		mk := "•" // •
		switch kind {
		case "blunder":
			mk = "✗" // ✗
		case "success":
			mk = "✓" // ✓
		}
		o.WriteString("<div style='color:" + c + "'>" + mk + " <b>" + esc(e["kind"]) + "</b> &mdash; " +
			esc(e["text"]) + "</div>")
	}
	return o.String(), nil
}

// renderSource is GraphNode.php:138-143 — a link into the forge tree, labelled by the newest version
// this ticket minted.
//
//	$v = $db->query("SELECT version FROM crank_runs WHERE ticket_id=" . $id . " ORDER BY id DESC")->fetchColumn();
//	$lbl = ($v !== false && $v !== '') ? "browse congruency source (this ticket minted v" . self::esc($v) . ")"
//	                                   : "browse congruency source (forge-parked tree)";
//
// Same strict pair as renderGoal (quirk 2): a run row whose version is NULL passes both tests and
// renders "…minted v)" with nothing after the v. The link itself is a fixed literal — the ?repo= is
// hardcoded to congruency and the &amp; is already encoded in the source, so it is NOT re-escaped.
//
// This arm renders a link even when the tag's own db has no such ticket at all; only the LABEL varies.
func (t *GraphNodeTag) renderSource(sid string) (string, error) {
	db, err := t.conn()
	if err != nil {
		return "", err
	}
	v, had, err := graphNodeFetchColumn(db, "SELECT version FROM crank_runs WHERE ticket_id="+sid+" ORDER BY id DESC")
	if err != nil {
		return "", err
	}
	lbl := "browse congruency source (forge-parked tree)"
	if graphNodeStrictSet(v, had) {
		lbl = "browse congruency source (this ticket minted v" + esc(v) + ")"
	}
	return "<div>&mdash; <a href='?page=tree&amp;repo=congruency'>" + lbl + "</a></div>", nil
}

// renderChildren is GraphNode.php:144-156 — the ticket's owned child tickets, newest first.
//
// The JOIN is what makes an edge whose child_id has no tickets row vanish entirely rather than
// render a blank entry — an INNER join, the same shape 0012_ticket_edges.sql:28-30's children.list
// route uses (that route also selects t.component; this tag does not). $cid is an (int) before it is
// interpolated into the href, so the link cannot be poisoned by a stored value; the title/kind/status
// all go through esc(). Note the (int) is a provable no-op here — see the header's note on sqlite
// column affinity — and is kept only because the PHP has it.
func (t *GraphNodeTag) renderChildren(sid string) (string, error) {
	db, err := t.conn()
	if err != nil {
		return "", err
	}
	ch, err := queryRows(db, "SELECT e.child_id, e.kind, t.title, t.status FROM ticket_edges e "+
		"JOIN tickets t ON t.id = e.child_id WHERE e.parent_id="+sid+" ORDER BY e.child_id DESC")
	if err != nil {
		return "", err
	}
	if len(ch) == 0 { // if (!$ch)
		return graphNodeNotYetRecordedHTML, nil
	}
	var o strings.Builder
	for _, c := range ch {
		cid := strconv.FormatInt(toInt(c["child_id"]), 10) // (int)$c['child_id']
		o.WriteString("<div>&mdash; <a href='?page=graphs&amp;ticket=" + cid + "'>#" + cid + " " +
			esc(c["title"]) + "</a> <span style='font-size:.72rem;color:#888'>(" +
			esc(c["kind"]) + " &middot; " + esc(c["status"]) + ")</span></div>")
	}
	return o.String(), nil
}

// ── helpers ─────────────────────────────────────────────────────────────────────────────────────

// graphNodeFetchColumn is PDO::query($sql)->fetchColumn() — column 0 of row 0 — reporting whether a
// row existed AT ALL as a separate result.
//
// engine.go's scalar() (engine.go:1260-1266) cannot be used here: it returns nil both for "no rows"
// and for "one row whose cell is NULL", and GraphNode's 'goal' (:62) and 'source' (:140) arms test
// `$x !== false && $x !== ''`, which distinguishes exactly those two. had=false is PHP's FALSE.
//
// The error is propagated rather than swallowed because db() runs in ERRMODE_EXCEPTION (:40) — a
// failing query THROWS, and GetDocument's catch is what renders it.
func graphNodeFetchColumn(db *sql.DB, query string) (any, bool, error) {
	cols, rows, err := queryAll(db, query)
	if err != nil {
		return nil, false, err
	}
	if len(rows) == 0 || len(cols) == 0 {
		return nil, false, nil // fetchColumn() === false
	}
	return rows[0][cols[0]], true, nil
}

// graphNodeStrictSet is `$x !== false && $x !== ''` — the pair of STRICT tests 'goal' (:62) and
// 'source' (:140) guard their populated branch with, where $x came from fetchColumn().
//
//	had == false                 -> $x === false     -> the empty branch  (no such row)
//	v is the string ""           -> $x === ''        -> the empty branch  (empty cell)
//	v is nil (SQL NULL)          -> passes BOTH      -> the POPULATED branch, rendering esc(NULL) = ""
//	v is int64(0) / float64(0)   -> passes BOTH      -> the POPULATED branch, rendering "0"
//
// The last two are the point: `!== ''` is a type-AND-value test, so only a genuine empty STRING
// takes the empty branch. Writing this as "is v nil or empty" would be the natural Go reading and
// would diverge on a NULL body and on an integer 0 alike. See quirk 2 in the header.
func graphNodeStrictSet(v any, had bool) bool {
	if !had {
		return false // $x !== false
	}
	s, isString := v.(string)
	return !(isString && s == "") // $x !== ''
}

// graphNodePHPIntFromString is PHP's `(int)` cast applied to a string — the cast GraphNode.php:25
// makes on the id argument.
//
// WHY NOT engine.go's toInt: toInt(string) is leadingInt, "the leading run of digits"
// (engine.go:558-595). That is right for the DB values it was written for and WRONG for an exponent.
// PHP does not scan digits; it runs is_numeric_string over the leading numeric data and, when that
// data is a FLOAT form, converts through a double (zend_operators.c, zval_get_long_func):
//
//	"186"    -> 186          "" / "abc" -> 0        (no leading numeric data at all)
//	"007"    -> 7            "12abc"    -> 12       (trailing garbage is allowed by the cast)
//	"1e3"    -> 1000         "1e"       -> 1        (an exponent with no digits is not an exponent)
//	"0x1A"   -> 0            "1.9"      -> 1        (double form, truncated toward zero)
//
// The engine can only ever deliver [A-Za-z0-9]* here (see the header's parse table), so the sign,
// the '.' and the leading-whitespace clauses below are UNREACHABLE through a tag invocation. They
// are implemented anyway, because a cast that is correct only for the inputs its author imagined is
// how the "leading digit run" reading became wrong in the first place.
//
// NOT VERIFIED HERE: there is no php binary in this worktree, so the table above is derived from
// zend_operators.c's grammar, not measured. It is the single least-grounded claim in this file, and
// it sits on a path no template exercises.
func graphNodePHPIntFromString(s string) int64 {
	i, n := 0, len(s)
	for i < n && isPHPSpace(s[i]) { // ZEND_IS_WHITESPACE — is_numeric_string skips leading WS
		i++
	}
	start := i
	if i < n && (s[i] == '+' || s[i] == '-') {
		i++
	}

	intDigits := 0
	for i < n && s[i] >= '0' && s[i] <= '9' {
		i++
		intDigits++
	}

	// is_numeric_string requires a digit after the optional sign, or a '.' followed by a digit.
	// Anything else is not numeric data and the cast is 0.
	if intDigits == 0 && !(i+1 < n && s[i] == '.' && s[i+1] >= '0' && s[i+1] <= '9') {
		return 0
	}

	isDouble := false
	if i < n && s[i] == '.' { // a fractional part forces the double path
		j := i + 1
		for j < n && s[j] >= '0' && s[j] <= '9' {
			j++
		}
		isDouble = true
		i = j
	}
	if i < n && (s[i] == 'e' || s[i] == 'E') { // so does an exponent — but only a COMPLETE one
		j := i + 1
		if j < n && (s[j] == '+' || s[j] == '-') {
			j++
		}
		expDigits := 0
		for j < n && s[j] >= '0' && s[j] <= '9' {
			j++
			expDigits++
		}
		if expDigits > 0 { // "1e" keeps the 'e' as trailing garbage and stays an int
			isDouble = true
			i = j
		}
	}

	lit := s[start:i]
	if !isDouble {
		if v, err := strconv.ParseInt(lit, 10, 64); err == nil {
			return v
		}
		// ParseInt only fails here on OVERFLOW — lit is a well-formed [+-]?[0-9]+ by construction.
		// ZEND_STRTOL overflows too, so is_numeric_string reports IS_DOUBLE and the cast falls
		// through to the same double path an exponent takes.
	}
	f, err := strconv.ParseFloat(lit, 64)
	if err != nil {
		return 0
	}
	return graphNodeDvalToLval(f)
}

// graphNodeDvalToLval is zend_dval_to_lval (Zend/zend_operators.h) — PHP's double→int conversion,
// which the (int) cast reaches for any float-form or overflowing numeric string.
//
// It is NOT a plain Go int64(f): PHP defines the out-of-range case as a MODULAR wrap into
// [-2^63, 2^63), while Go's float→int conversion is undefined for out-of-range values and is free to
// produce anything. NaN and the infinities are 0.
//
// Reachable only from graphNodePHPIntFromString, and within it only from an id like "1e3" or a digit
// run too long for an int64 — both of which [A-Za-z0-9]* admits.
func graphNodeDvalToLval(f float64) int64 {
	if math.IsNaN(f) || math.IsInf(f, 0) {
		return 0
	}
	if f >= -9.2233720368547758e18 && f < 9.2233720368547758e18 {
		return int64(f) // ZEND_DOUBLE_FITS_LONG — truncation toward zero
	}
	// zend_dval_to_lval_slow: fmod into [0, 2^64), then fold the top half negative.
	const twoPow64 = 18446744073709551616.0 // 2^64
	const twoPow63 = 9223372036854775808.0  // 2^63
	dmod := math.Mod(f, twoPow64)
	if dmod < 0 {
		dmod += twoPow64
	}
	if dmod >= twoPow63 {
		dmod -= twoPow64
	}
	return int64(dmod)
}
