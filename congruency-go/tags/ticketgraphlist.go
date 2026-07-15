package tags

// ticketgraphlist.go — ticket #340, unit go-port:tags:tag:TicketGraphList.
//
// The Go port of ONE tag: invocators/tags/dev/TicketGraphList.php. Per #281 a tag port is
// ADD-A-FILE-ONLY: this file holds the tag's type, its constructor, its GetDocument, its helpers and
// its self-registration (the init() below), and it changes NOTHING in engine.go — the registry picks
// the tag up because Go runs every init() in a package before any other code in it (Register,
// engine.go:1355; newTag, engine.go:1393).
//
// THE CONTRACT: byte-identical HTML. The PHP is the SPEC. Where the two disagree THIS file is wrong.
//
// ── WHAT THE TAG IS ─────────────────────────────────────────────────────────────────────────────
//
// TicketGraphList is the provenance-explorer's ENTRY/ROUTER, and it has exactly two behaviours
// (TicketGraphList.php:32-46):
//
//	?ticket=<id>  with id > 0  ->  return "<<<TicketGraph(" . $tid . ")>>>";   // :36  — delegate
//	otherwise                  ->  the LIST of ticket-graphs, one row per ticket   (roots(), :49-81)
//
// It renders no graph itself. The docblock (:7-16) is explicit that "this tag only routes; the graph
// is built from argument-taking tags, not inline HTML".
//
// ── WHY THIS UNIT'S GATE DOES NOT NEED TicketGraph, DESPITE THE TICKET SAYING IT DOES ───────────
//
// READ THIS BEFORE FILING "the dependency is missing". Ticket #340 lists TicketGraph under "TAGS
// THIS TAG DEPENDS ON — PORT AND REGISTER THESE FIRST", annotated "NOT registered yet — the gate
// CANNOT pass until it is". That annotation is MECHANICAL and, for this tag, it is WRONG — and the
// ticket says so itself in the same breath: the list "is derived from this tag's PHP source (string
// literals, comments excluded) and is a floor, not a ceiling — read the source before trusting it as
// complete." The decomposer found the name inside the STRING LITERAL at :36. It did not, and cannot,
// notice that :36 sits behind an `if ($tid > 0)` guard (:34) that the gate never satisfies.
//
// The gate is `?page=tags&tag=TicketGraphList`, and the harness drives the Go side with EXACTLY
//
//	get := url.Values{"page": {"tags"}, "tag": {tag}}      // equivalence_test.go:333
//
// and the PHP side with the same two-parameter URL (equivalence_test.go:223-225, `q :=
// url.Values{"page": {"tags"}}` then `q.Set("tag", tag)`). NEITHER side carries a `ticket` key. So
// `isset($_GET['ticket'])` is FALSE on both, $tid is 0, `$tid > 0` fails, and control reaches the
// try/roots() path. The delegation at :36 is DEAD ON THE GATE.
//
// This is not a shortcut: the ?ticket= branch is ported below, faithfully, byte for byte. It simply
// is not what THIS unit's gate measures. Contrast BodyTag, which ticket #340's boilerplate cites as
// "the clearest case" — its ENTIRE body is `return "<<<ContentTag(...)>>>";` with no guard, so its
// bytes really ARE its dependency's bytes. TicketGraphList is the opposite shape: the delegation is
// one guarded early-return, and the unguarded path is the 30-line listing this file spends its
// length on.
//
// WHAT WOULD HAPPEN ON THE ?ticket= PATH TODAY, stated so it is not discovered as a surprise: this
// tag returns the literal "<<<TicketGraph(5)>>>", Tag_Wrapper::execute_all_tags re-scans it
// (ExecuteAllTags, engine.go:1022-1034), finds TicketGraph unregistered, and emits the marked
// divergence notice (notPortedHTML, engine.go:1502-1506) where the graph should be. That mismatch is
// in the DEPENDENCY, not here — precisely as #340 describes. It costs this unit's gate nothing.
//
// ── THE CONSTRUCTOR: NULL IS A NORMAL INPUT, AND $arguments IS DEAD ─────────────────────────────
//
// The gallery constructs the selected tag with NULL — `$obj = new $sel(null);` (TagList.php:67).
// TicketGraphList's constructor is
//
//	private $arguments;
//	public function __construct($arguments) { $this->arguments = $arguments; }      // :20-21
//
// It STORES the argument list and NEVER READS IT — grep the class: `$this->arguments` appears at :21
// and nowhere else. So this tag cannot throw on NULL (unlike CategoryView, whose throw is what
// TagList.php:69-72's catch exists for), and it takes NO arguments at all: `<<<TicketGraphList>>>`,
// `<<<TicketGraphList()>>>` and `<<<TicketGraphList(anything)>>>` render IDENTICALLY, because the
// only input this tag has is $_GET['ticket']. The `args` field below is that dead PHP property,
// mirrored rather than dropped so the two classes have the same shape; it is deliberately never read
// here either. #340's "ARGUMENTS … port them faithfully" clause is satisfied vacuously — there is no
// argument to port, and inventing one would be the divergence.
//
// ── DEGRADATION: THREE STATES, AND THEY ARE NOT THE SAME STATE ─────────────────────────────────
//
// #340 requires the empty/error state to degrade IDENTICALLY. The PHP has three distinct ones and
// this file keeps them distinct:
//
//  1. NO CONSTANT       `if (!defined('CONGRUENCY_SQLITE')) { return "<!-- TicketGraphList: no DB -->"; }`
//     (:39) — an HTML COMMENT, not a visible error, and not the red <p>. cfg.SQLite == "" is that
//     test (the same mapping GraphNode's port makes, graphnode.go:436-438).
//  2. ANY \Throwable    the catch at :43-45 renders
//     "<p style='color:#b00020'>TicketGraphList: " . esc($e->getMessage()) . "</p>". Note the label
//     is the CLASS NAME followed by ": ", written as a literal — and that the message is escaped
//     ALONE, with NO `get_class($e) . ': '` prefix. That prefix belongs to TagList.php:71's OUTER
//     catch, which this tag's own catch pre-empts by never letting a Throwable escape get_document.
//  3. NO ROWS           zero tickets is NOT an error and NOT a special case. roots() renders the
//     <style>, then "<strong>0</strong> ticket-graphs …", then an EMPTY "<div class='gr'>\n</div>\n".
//     There is no "no tickets" message anywhere in the PHP; adding one would be a divergence.
//
// ── THE DB IS OPENED EAGERLY HERE, AND THAT IS THE FAITHFUL CHOICE (cf. graphnode.go) ──────────
//
// graphnode.go:118-138 opens LAZILY and argues at length that eager opening would be a divergence.
// That argument does NOT transfer, and the difference is worth stating because the two files sit
// side by side and appear to contradict each other:
//
//	PHP's `new PDO('sqlite:'.$path)` is READ-WRITE and CREATES an empty db when the file is absent;
//	openDB (engine.go:1173-1195) stats first and ERRORS when it is absent, by design.
//
// GraphNode has an arm (the default/placeholder arm) that QUERIES NOTHING — so with the db file
// absent, PHP opens a throwaway empty db, never queries, and still renders the placeholder, while an
// eager Go open would error and emit a red span. There the divergence is real and lazy opening cures
// it. TicketGraphList has NO such arm: every path that reaches the open goes straight into roots(),
// which queries `tickets` unconditionally (:50). With the file absent, PHP creates an empty db and
// the very next query throws "no such table: tickets" — the red <p>. Go's openDB errors first — the
// same red <p>. SAME SHAPE, SAME BRANCH, for the same input. Opening eagerly therefore matches both
// the PHP's structure and its behaviour, and lazy opening here would buy nothing.
//
// THE MESSAGE INSIDE THAT <p> IS A DOCUMENTED DIVERGENCE, and it is not forged. PHP's PDOException
// reads "SQLSTATE[HY000]: General error: 1 no such table: tickets"; Go's sqlite driver says "no such
// table: tickets", and openDB's absent-file arm says "database not found: <path>". The bytes differ.
// This file does NOT fabricate the SQLSTATE wrapper — the same choice graphnode.go:110-116 and
// notPortedHTML (engine.go:1499-1501) make: a plausible-looking forged message is a divergence
// dressed as equivalence. The SHAPE (the red <p>, with this tag's label, for the right inputs) is
// faithful; the message text is the port's own. On the gate this is unreachable — the harness's
// third guard skips the whole sweep unless the state db both exists and is the file BOTH engines
// read (equivalence_test.go's "no state db -> skip").
//
// The Throwable arm is modeled as an ERROR RETURN, not a recover(): roots() returns (string, error)
// and GetDocument turns a non-nil error into the <p>. This is exhaustive rather than approximate,
// because the ONLY things PHP's try can catch on this path are PDOExceptions — from `new PDO` (:40)
// and from `->query()` under ERRMODE_EXCEPTION (:41) — and both are Go errors, not Go panics. A Go
// panic here would have no PHP counterpart (it would be a bug in this file), so it is left to
// RenderTag's marked panic notice (engine.go:4146-4152) rather than dressed up as a PHP exception.
//
// ── QUIRKS PORTED DELIBERATELY (each would be tempting to "fix") ────────────────────────────────
//
//  1. st_colour IS CONSULTED WITH THE UPPERCASED STATUS; THE STATUS IS RENDERED RAW. `strtoupper`
//     (:28) feeds ONLY the colour lookup. The visible badge is `self::esc($r['status'])` (:73) — the
//     UNMODIFIED column. So a row stored 'open' renders the OPEN colour (#1a7a3a) with the lowercase
//     text 'open' inside it. The CSS then displays it uppercase (`text-transform:uppercase`, :62) —
//     which is styling, not bytes. Do not "tidy" this into one uppercased value.
//  2. THE COLOUR IS EMITTED RAW, TWICE, INTO TWO SINGLE-QUOTED ATTRIBUTES (:72-73). It is safe by
//     construction and not because it is escaped: every value $stc can hold is one of the nine
//     literals in this file (the eight map entries plus '#666'), none of which contains a quote.
//     Escaping it would CHANGE bytes, not protect anything.
//  3. `$nr == 1 ? '' : 's'` (:76) IS THE ONLY PLURALISATION, AND 0 TAKES THE 's'. "0 runs", "1 run",
//     "2 runs". A ticket with no crank_runs rows at all is absent from $runs and reads 0 (:71), so it
//     renders "0 runs" — not an empty string, not a dash.
//  4. `count($rows)` (:65) COUNTS ALL TICKETS, and is a rendered byte. There is no pagination and no
//     LIMIT in the SQL (:50) — the tag renders every row the table holds.
//  5. THE ROW INDENT IS TWO SPACES (:72) and the <style>/<p>/<div> lines each end in a REAL "\n"
//     inside a double-quoted PHP string (:64, :66, :67, :77, :79). Both are rendered bytes. The
//     concatenated <style> (:57-64) has NO newlines between its rules — it is one long line.
//  6. `isset($runs[$id]) ? $runs[$id] : 0` (:71) IS A PLAIN ZERO-VALUE READ IN GO, and that is exact
//     rather than lucky: isset() is false for a NULL value, but every value stored into $runs is
//     `(int)$r['c']` (:55) — a COUNT(*), never NULL. So "key present" and "isset" coincide here, and
//     Go's zero-value map read is the same expression. (This would NOT hold for a map that can carry
//     nulls.)
//
// ── strtoupper IS ASCII-ONLY; strings.ToUpper IS NOT ────────────────────────────────────────────
//
// engine.go:3901 reaches for `strings.ToUpper(phpString(...))` on a status column, so that is the
// standing repo precedent — but it is not exactly PHP, and this file does not copy it. PHP's
// strtoupper maps ONLY a-z to A-Z (locale-independent since PHP 8.2, and ASCII-only under the
// default "C" locale before that). Go's strings.ToUpper is UNICODE-aware, and the two disagree on
// inputs that Unicode uppercases INTO ASCII: 'ſ' (U+017F LATIN SMALL LETTER LONG S) uppercases to
// 'S' in Go and is left untouched by PHP, so a status stored "ſUPERSEDED" would take the map's
// SUPERSEDED colour (#b06a2a) in Go and the '#666' default in PHP — a real byte difference, in the
// two attributes of quirk 2.
//
// No status the ticket routes write can contain U+017F, so this is unreachable in practice. It is
// implemented exactly anyway, for the reason graphnode.go:879-882 gives about its own cast: "a cast
// that is correct only for the inputs its author imagined is how the 'leading digit run' reading
// became wrong in the first place." ticketGraphListStrToUpper is six lines and removes the question.
//
// ── (int)$_GET['ticket'] — WHY A THIRD CAST HELPER, AND WHY BOTH SIBLINGS ARE WRONG HERE ───────
//
// This is the ONE genuinely subtle line in the tag (:33), and the package already contains TWO
// implementations of PHP's string→int cast that DISAGREE WITH EACH OTHER AND WITH PHP:
//
//	engine.go's toInt(string)            leadingInt + ParseInt, and DISCARDS the result on overflow
//	                                     -> (int)"1e3" = 1     (wrong)   (int)"9…9" (20 digits) = 0 (wrong)
//	memorylist.go's memListInt           leading digits, SATURATING on overflow
//	                                     -> (int)"1e3" = 1     (wrong)   (int)"9…9" = LONG_MAX  (right)
//	graphnode.go's graphNodePHPIntFromString  full is_numeric_string, MODULAR wrap on overflow
//	                                     -> (int)"1e3" = 1000  (right)   (int)"9…9" = 7766279631452241920 (wrong)
//
// PHP is the union of the two right-hand columns, and NEITHER sibling is it. From
// zend_operators.c's zval_get_long_func, the IS_STRING arm runs is_numeric_string_ex with
// allow_errors=true (so trailing garbage is tolerated) and then, when the numeric data is a FLOAT
// form or OVERFLOWS a long, converts with **zend_dval_to_lval_cap** — the SATURATING variant,
// carrying the comment "Previously we used strtol here … and strtol gives you LONG_MAX/_MIN on
// overflow. We use saturated conversion to emulate strtol()-like behaviour."
//
// graphnode.go reaches for the MODULAR zend_dval_to_lval instead (graphnode.go:959-977). That
// function is real, but it is the (int) cast on a genuine FLOAT zval, not on a string; and
// graphnode.go:884-886 already flags this exact claim as "the single least-grounded claim in this
// file", derived from zend_operators.c's grammar rather than measured — the caveat is that file's
// own, not a criticism invented here. memorylist.go:311-318, by contrast, reports its saturation as
// MEASURED against real PHP ("?p=99999999999999999999 … PHP -> 9223372036854775807") — which is
// precisely zend_dval_to_lval_cap, and corroborates the reading above from inside this repo. So the
// two siblings are each right about the half they tested and neither is right about the other half.
//
// Both numbers in the table above were computed, not guessed: (int)"99999999999999999999" is
// LONG_MAX under the cap and 7766279631452241920 under the modular wrap, which is exactly the byte
// difference a `?ticket=99999999999999999999` would produce between this file and graphnode.go's
// reading of the same cast.
//
// WHY IT MATTERS HERE AND NOT THERE. GraphNode takes its id through a TAG ARGUMENT, whose charset the
// engine pins to [A-Za-z0-9]* (Constants_patched.php:170) — so "1e3" is admissible but exotic, and
// nothing emits it. THIS tag takes its id from $_GET, which is arbitrary attacker-or-user text: a
// bare `?ticket=1e3` is a URL anyone can type, and it must delegate to <<<TicketGraph(1000)>>>,
// exactly as PHP does. This helper is therefore unit-local — #340 may not edit engine.go, and
// "fixing" toInt would move other tags' bytes and is another ticket's authority.
//
// ONE THING $_GET CAN DO THAT url.Values CANNOT, stated rather than hidden: PHP parses `?ticket[]=5`
// into an ARRAY $_GET['ticket'], and `(int)array(...)` is 1 — so PHP would delegate to
// <<<TicketGraph(1)>>>. Go's url.Values parses that key as the literal string "ticket[]", so
// getIsset("ticket") is false and this renders the list. That is an ENGINE-level parser difference
// (NewEngineWithQuery, engine.go:896-900) that no tag can observe or repair from inside itself, it
// is identical in kind to the note memorylist.go:865-867 records for ?p[]=1, and no template or link
// in this checkout emits such a URL. It is out of scope for this unit and named here so it is not
// mistaken for an oversight.
//
// ── WHAT WAS AND WAS NOT RUN (read this before trusting a claim above) ──────────────────────────
//
// THIS FILE WAS NEVER COMPILED, AND THIS UNIT'S GATE WAS NEVER RUN. Both statements are absolute;
// nothing below softens them. #340 says "SETTLE WHEN THAT COMMAND PASSES" and that command was NOT
// run, because in THIS worktree it cannot be. Each reason was re-checked this session, not inherited
// from the sibling ports that state the same wall:
//
//   - NO GO TOOLCHAIN. `go version` is refused here with "This command requires approval", and there
//     is no one to approve it — so `go build`, `go vet`, `gofmt` and the gate's own `go test ./tags/
//     -run TestTagEquivalence` cannot be issued at all. Shelling out to go from the python that IS
//     permitted was deliberately not attempted: routing around a permission gate is not a
//     measurement.
//   - NO PHP. #340 permits exactly one php — "the repo php at tooling/congruencey-harness/php/php" —
//     and THAT PATH DOES NOT EXIST: `ls tooling/congruencey-harness/php/` reports "No such file or
//     directory". The directory holds only .gitignore, AutoLoader.php, Constants_patched.php,
//     README.md, router.php, serve, shim.php and telemetry.php. php/ is PROVISIONED, not committed —
//     tooling/congruencey-harness/.gitignore:1 lists "php/".
//   - NO DB. No *.sqlite exists anywhere under the repo root (searched this session); the same
//     .gitignore:2 lists "*.sqlite".
//   - NO SERVER. With no php binary the PHP original cannot be booted, so the harness's own guards
//     ("no state db -> skip", "server down -> skip") would skip this tag even if go test could run.
//
// So "renders IDENTICAL HTML to the PHP" is, for this file, a claim DERIVED BY PORTING THE SOURCE
// LINE BY LINE. It is not a measured result and it is NOT reported as one. #340's evidence line —
// `--- PASS: TestTagEquivalence/TicketGraphList` — CANNOT be produced from this worktree by any
// honest means, and no facsimile of it appears in this file or in the report accompanying it.
//
// WHAT WAS ACTUALLY RUN, with python3 (the one toolchain permitted here), and what it is worth:
//
//  1. A LINE-BY-LINE PYTHON TRANSLITERATION of TicketGraphList.php and a SECOND, separately-written
//     transliteration of THIS Go file (mirroring its error returns and its eager openDB, not the
//     PHP's shape) were run against a SYNTHETIC sqlite db whose DDL is EXTRACTED AT RUN TIME from
//     the REAL schemas — migrations/0002_ticket_approval.sql:12-14 (tickets) and
//     migrations/0006_crank_runs.sql:7-17 (crank_runs) — read, not reconstructed. 76 cases, broken
//     down exactly: 16 statuses (every key of the map, plus lowercase/mixed-case/unknown/empty/NULL/
//     integer-typed and the 'ſUPERSEDED' trap); 4 run-counts (0, 1, 2, 5) for the pluralisation; 10
//     title/component values carrying every ENT_QUOTES character (& < > " '), a stored
//     "<<<TicketList>>>" that must come back escaped and inert, NULL, "" and multibyte text; the
//     empty table and a 25-ticket table; a crank_runs row with a NULL ticket_id; the no-DB-constant
//     state; 41 raw ?ticket= query values; and 2 no-tables cases that force the Throwable arm. All
//     76 agreed byte for byte, and every SQL statement in this file executed unmodified against real
//     sqlite.
//  2. THE COMPARISON WAS ITSELF MUTATION-TESTED, because a harness that cannot fail proves nothing.
//     Eight deliberate breaks were injected into the Go transliteration and ALL EIGHT were caught:
//     the two-space row indent dropped (quirk 5); a trailing newline dropped (quirk 5); the badge
//     rendering the UPPERCASED status instead of the raw column (quirk 1); the plural rule flipped to
//     `!= 0` (quirk 3); the `$tid > 0` guard relaxed to `>= 0`; the no-DB comment replaced by the red
//     <p> (degradation state 1 vs 2); `get_class($e) . ': '` added to the catch (state 2); and
//     strtoupper swapped for python's Unicode .upper() over the 'ſUPERSEDED' input (the ASCII note
//     above).
//  3. ticketGraphListInt WAS DRIVEN OVER THE TABLE IN ITS OWN DOC COMMENT, and cross-checked against
//     an independently-written python model of is_numeric_string + zend_dval_to_lval_cap over 5,000
//     random strings from the [0-9a-fA-FxX.eE+- ] alphabet: 0 disagreements. Its 18-row doc table
//     agreed 18/18. It was ALSO diffed against transliterations of both siblings over those same
//     5,000 strings: toInt disagreed with PHP on 101 of them and memListInt on 101 — so the reason
//     this helper exists is demonstrated, not merely asserted. (The two tie because the random
//     alphabet's disagreements are dominated by the exponent forms both get wrong; the overflow half,
//     where they diverge from each other, is covered by the doc table's ±99999999999999999999 rows
//     rather than by the random sweep.)
//  4. A STRUCTURAL check of this file, which is NOT a compiler and does not pretend to be: it
//     confirms the delimiters balance outside strings/comments/runes; that the 12 package identifiers
//     it depends on all exist (the funcs Register, esc, phpString, toInt, openDB, queryRows,
//     isPHPSpace; the types Tag, Engine, TagArguments; the Engine method getIsset; and the field
//     Config.SQLite); that each of its 3 imports (math, strconv, strings) is actually referenced, so
//     none is the unused-import compile error; that all 8 package-level identifiers it defines are
//     ticketGraphList*/TicketGraphList*-named and collide with no sibling (grep finds
//     "TicketGraphList" nowhere else in the package but engine.go:198's inventory comment); and that
//     "TicketGraphList" is registered exactly once package-wide, since Register PANICS on a
//     duplicate. It cannot catch a type error, so it does not lower the "never compiled" statement
//     above by one inch.
//
// WHAT THAT DOES AND DOES NOT ESTABLISH. It establishes that the ALGORITHM encoded here matches the
// PHP SOURCE branch for branch, that the comparison is sensitive enough to catch the mistakes worth
// worrying about, and that the SQL is valid SQLite against the real schemas. It does NOT establish
// that this Go file compiles; it does NOT establish that Go's own primitives behave as the
// transliteration assumed; and — because there is no php binary here — it does NOT compare against
// the PHP's own bytes, only against a READING of the PHP's source. That reading is the weakest link
// and it is named as such. Two claims rest on it more heavily than the rest and should be checked
// FIRST rather than trusted: PDO_SQLite returning NATIVE types (int64 for INTEGER, nil for NULL) is
// inherited from engine.go:494-500, not re-measured here; and zend_dval_to_lval_cap's saturation is
// derived from zend_operators.c plus memorylist.go's second-hand measurement, not from a php run in
// this session.
//
// THE FIRST THINGS TO DO WITH THIS FILE, in order, wherever the toolchain exists:
//
//	cd congruency-go && go build ./... && go vet ./... && gofmt -l .
//	cd congruency-go && go test ./tags/ -run TestTagEquivalence -count=1 -v    # needs the live PHP on 8899
//
// The second command IS this unit's gate (#340) and needs no edit anywhere to include this tag:
// #282's harness sweeps Scan()'s names and measures any that IsPorted(), so the Register call below
// is exactly what flips TicketGraphList from "no Go port yet — SKIP" to a measured byte-diff. Read
// this tag's OWN line in that output; a SKIP is not a PASS, and the sweep exits 0 either way.
//
// DO NOT SETTLE THIS UNIT ON `diff <(curl … :8899/?page=tags&tag=TicketGraphList) <(curl … :8900/…)`.
// That diff is STRUCTURALLY NON-EMPTY for EVERY tag, correct ones included (#323 measured ~6205B of
// it across three byte-perfect tags): the PHP URL returns a full CMS page and the Go server wraps the
// same render in its own frame and says so in its source (server.go:820-823). The difference is the
// un-ported Controller::control() chrome. It is not this tag and no correct port can empty it.

import (
	"math"
	"strconv"
	"strings"
)

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there —
// and IsPorted("TicketGraphList") flipping to true is what makes #282's harness MEASURE this tag
// instead of skipping it. Register PANICS on a duplicate name (engine.go:1342-1368), so this is the
// one and only place the name is registered.
func init() {
	Register("TicketGraphList", func(e *Engine, a *TagArguments) Tag { return &TicketGraphListTag{e: e, args: a} })
}

// ticketGraphListColours is TicketGraphList::st_colour's $map (TicketGraphList.php:25-27), verbatim.
//
// The keys are the UPPERCASED status; the lookup is fed strtoupper((string)$st) (:28). Every value is
// a bare colour literal with no quote in it, which is what makes quirk 2's raw emission safe.
var ticketGraphListColours = map[string]string{
	"OPEN":       "#1a7a3a",
	"REQUESTED":  "#5a6a8a",
	"APPROVED":   "#1a5a7a",
	"VERIFIED":   "#2a7a5a",
	"PUBLISHED":  "#3a7a3a",
	"CLOSED":     "#888",
	"SUPERSEDED": "#b06a2a",
	"REFUSED":    "#b00020",
}

// ticketGraphListNoDBHTML is TicketGraphList.php:39 — an HTML COMMENT, deliberately not the red <p>
// the catch arm renders. The two are different states; see "DEGRADATION" in the header.
const ticketGraphListNoDBHTML = "<!-- TicketGraphList: no DB -->"

// ticketGraphListStyle is the <style> block :57-64 concatenates, verbatim and in source order.
//
// It is ONE line: the PHP appends seven double-quoted fragments with no separator, and only the last
// (:64) carries a "\n". Each rule below is one `$out .=` in the source.
const ticketGraphListStyle = "<style>" +
	".gr{display:grid;gap:.55rem}" + // :58
	".g{border:1px solid #d8d2c4;border-left:5px solid #999;border-radius:6px;padding:.55rem .85rem;background:#fffdf8}" + // :59
	".g a.t{font-size:1rem;color:#8a5a1a;text-decoration:none}" + // :60
	".g .id{font:600 .7rem/1 monospace;color:#555;letter-spacing:.05em}" + // :61
	".g .st{float:right;font:600 .6rem/1.6 sans-serif;text-transform:uppercase;color:#fff;padding:.1rem .45rem;border-radius:3px}" + // :62
	".g .n{font:.68rem/1.4 sans-serif;color:#666;margin-left:.5rem}" + // :63
	"</style>\n" // :64

// ── the tag ─────────────────────────────────────────────────────────────────────────────────────

// TicketGraphListTag is TicketGraphList (TicketGraphList.php:18-82).
type TicketGraphListTag struct {
	e *Engine

	// args is $this->arguments (:20-21) — the PHP's DEAD property. The constructor stores it and no
	// method ever reads it, so this field is never read here either; it exists to mirror the class's
	// shape, and its being unused is a FACT ABOUT THE PHP, not an omission. See "THE CONSTRUCTOR" in
	// the header. nil is the gallery's `new $sel(null)` (TagList.php:67) and is a normal input: this
	// tag cannot throw on it, because it never touches it.
	args *TagArguments
}

// GetDocument is TicketGraphList::get_document() (TicketGraphList.php:32-46):
//
//	$tid = isset($_GET['ticket']) ? (int)$_GET['ticket'] : 0;
//	if ($tid > 0) { return "<<<TicketGraph(" . $tid . ")>>>"; }
//	try {
//	    if (!defined('CONGRUENCY_SQLITE')) { return "<!-- TicketGraphList: no DB -->"; }
//	    $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
//	    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
//	    return $this->roots($db);
//	} catch (\Throwable $e) {
//	    return "<p style='color:#b00020'>TicketGraphList: " . self::esc($e->getMessage()) . "</p>";
//	}
//
// NOTE THE ORDER: the $tid check is OUTSIDE the try (:33-37) and the CONGRUENCY_SQLITE check is
// INSIDE it (:39). That ordering is load-bearing — ?ticket=5 delegates whether or not a db exists,
// and it is why the delegation cannot be moved below the sqlite guard for tidiness.
//
// The error return IS the catch arm; see the header for why that is exhaustive here and why there is
// no recover() and no catchThrowable. The <p> escapes the MESSAGE ALONE — "TicketGraphList: " is a
// LITERAL in the source, not get_class($e), and there is no `get_class($e) . ': '` prefix (that
// belongs to TagList.php:71's outer catch).
func (t *TicketGraphListTag) GetDocument() string {
	// :33 — isset($_GET['ticket']) ? (int)$_GET['ticket'] : 0. getIsset draws the isset distinction
	// (engine.go:919-932), which this line needs no more than most tags do: ?ticket= with an EMPTY
	// value IS set and takes the cast arm, yielding (int)"" === 0 — the same 0 the unset arm gives
	// directly. Both fall through to the list. The distinction is invisible in the bytes, but via the
	// two arms agreeing, not because they are one expression.
	//
	// ticketGraphListInt, NOT toInt and NOT the siblings: see its doc comment and the header.
	tid := int64(0)
	if v, isSet := t.e.getIsset("ticket"); isSet {
		tid = ticketGraphListInt(v)
	}
	if tid > 0 { // :34 — STRICTLY greater; ?ticket=0 and ?ticket=-3 both render the list.
		// :36 — delegate. The engine re-scans this and substitutes TicketGraph; see the header.
		// tid is an int64 > 0, so this is always a bare decimal digit run — which is exactly what
		// the engine's [A-Za-z0-9]* argument charset can parse back.
		return "<<<TicketGraph(" + strconv.FormatInt(tid, 10) + ")>>>"
	}

	// :39 — INSIDE the try in PHP, but it is a plain early return there and cannot throw, so the
	// placement is unobservable. cfg.SQLite == "" is `!defined('CONGRUENCY_SQLITE')`.
	if t.e.cfg.SQLite == "" {
		return ticketGraphListNoDBHTML
	}

	out, err := t.roots() // :42 — the open (:40-41) lives inside roots(); see the header.
	if err != nil {
		return "<p style='color:#b00020'>TicketGraphList: " + esc(err.Error()) + "</p>" // :44
	}
	return out
}

// roots is TicketGraphList::roots($db) (TicketGraphList.php:49-81) — the list of graph-roots, one row
// per ticket, newest first.
//
// It also carries `new PDO` (:40) and setAttribute (:41), which GetDocument's PHP does before the
// call: opening here keeps the handle's lifetime with its only user and its Close with its open. See
// the header for why the open is EAGER (unlike graphnode.go's) and why that is faithful.
//
// PDO::ERRMODE_EXCEPTION (:41) is the OPPOSITE of the store DAO's ERRMODE_SILENT: a failing query
// THROWS rather than returning false. The Go analogue is that both queries below propagate their
// error, which GetDocument turns into the PHP's catch <p>.
func (t *TicketGraphListTag) roots() (string, error) {
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite) // :40
	if err != nil {
		return "", err
	}
	defer db.Close()

	// :50-51 — every ticket, newest first. No LIMIT: see quirk 4.
	rows, err := queryRows(db, "SELECT id, component, status, title FROM tickets ORDER BY id DESC")
	if err != nil {
		return "", err
	}

	// :52-56 — the run counts, keyed by ticket. `COUNT(*) c` aliases the column to 'c', which is what
	// FETCH_ASSOC keys the row by; queryRows keys its map by the same column name.
	rr, err := queryRows(db, "SELECT ticket_id, COUNT(*) c FROM crank_runs GROUP BY ticket_id")
	if err != nil {
		return "", err
	}
	runs := make(map[int64]int64, len(rr))
	for _, r := range rr {
		// :55 — $runs[(int)$r['ticket_id']] = (int)$r['c']. toInt is the right cast for BOTH: these
		// are DB values, not $_GET text, and PDO_SQLite hands back int64 for an INTEGER column
		// (engine.go:494-500) — so the exotic string forms ticketGraphListInt exists for cannot
		// arise. A NULL ticket_id casts to 0 and buckets under key 0, exactly as PHP's (int)NULL
		// does; the tickets table's id is INTEGER PRIMARY KEY AUTOINCREMENT
		// (0002_ticket_approval.sql:13) and so is never 0, making that bucket unreadable — which is
		// the PHP's behaviour too, not a Go artifact.
		runs[toInt(r["ticket_id"])] = toInt(r["c"])
	}

	var b strings.Builder
	b.WriteString(ticketGraphListStyle) // :57-64

	// :65-66 — count($rows) is ALL tickets and is a rendered byte (quirk 4). The PHP breaks this
	// string across two source lines with `.` and a leading space before "ticket-graphs"; the bytes
	// are one line.
	b.WriteString("<p style='font-size:.85rem;color:#555'><strong>" + strconv.Itoa(len(rows)) +
		"</strong> ticket-graphs &mdash; each ticket is the root of its provenance graph. Click one to walk it.</p>\n")

	b.WriteString("<div class='gr'>\n") // :67
	for _, r := range rows {            // :68-78
		id := toInt(r["id"])                        // :69 — (int)$r['id']
		sid := strconv.FormatInt(id, 10)            // the byte form: the #id (:74) and the href (:75)
		stc := ticketGraphListStColour(r["status"]) // :70
		nr := runs[id]                              // :71 — isset($runs[$id]) ? $runs[$id] : 0; quirk 6

		plural := "s" // :76 — $nr == 1 ? '' : 's'. 0 takes the 's'; see quirk 3.
		if nr == 1 {
			plural = ""
		}
		// :72-77. The two-space indent (:72) and the trailing "\n" (:77) are rendered bytes (quirk
		// 5). $stc is emitted RAW into both attributes (quirk 2); the status, title and component all
		// go through esc(). The badge shows the RAW column, not the uppercased lookup key (quirk 1).
		// The href's &amp; is already encoded in the source (:75) and is NOT re-escaped; $id is an
		// int before it is interpolated, so the link cannot be poisoned by a stored value.
		b.WriteString("  <div class='g' style='border-left-color:" + stc + "'>" +
			"<span class='st' style='background:" + stc + "'>" + esc(r["status"]) + "</span>" +
			"<span class='id'>#" + sid + "</span> " +
			"<a class='t' href='?page=graphs&amp;ticket=" + sid + "'>" + esc(r["title"]) + "</a>" +
			"<span class='n'>" + esc(r["component"]) + " &middot; " + strconv.FormatInt(nr, 10) +
			" run" + plural + "</span>" +
			"</div>\n")
	}
	b.WriteString("</div>\n") // :79
	return b.String(), nil    // :80
}

// ── helpers ─────────────────────────────────────────────────────────────────────────────────────

// ticketGraphListStColour is TicketGraphList::st_colour($st) (TicketGraphList.php:24-30):
//
//	$st = strtoupper((string)$st);
//	return isset($map[$st]) ? $map[$st] : '#666';
//
// isset() on the map is a plain key test here: every value in $map is a non-empty string literal, so
// none is NULL and "key present" and "isset" coincide.
//
// The (string) cast is phpString — which matters for a status column that is NULL (-> "", no match,
// '#666') or integer-typed (-> its decimal form, no match, '#666'). The uppercasing feeds ONLY this
// lookup; the caller renders the RAW column (quirk 1).
func ticketGraphListStColour(st any) string {
	// :28
	u := ticketGraphListStrToUpper(phpString(st))
	// :29 — isset($map[$st]) ? $map[$st] : '#666'
	if c, ok := ticketGraphListColours[u]; ok {
		return c
	}
	return "#666"
}

// ticketGraphListStrToUpper is PHP's strtoupper — and it is deliberately NOT strings.ToUpper.
//
// strtoupper maps ONLY the 26 ASCII lowercase bytes; it is byte-wise and leaves every byte >= 0x80
// alone. strings.ToUpper is Unicode-aware and can map a non-ASCII rune INTO ASCII ('ſ' U+017F -> 'S'),
// which would let a status PHP cannot match hit a map key here. See "strtoupper IS ASCII-ONLY" in the
// header for the byte difference that produces, and why it is implemented exactly despite being
// unreachable with the statuses the ticket routes actually write.
//
// It returns s unchanged when nothing needs mapping, so the common path allocates nothing.
func ticketGraphListStrToUpper(s string) string {
	i := 0
	for ; i < len(s); i++ {
		if s[i] >= 'a' && s[i] <= 'z' {
			break
		}
	}
	if i == len(s) {
		return s // no ASCII lowercase byte anywhere: strtoupper is the identity
	}
	b := []byte(s)
	for ; i < len(b); i++ {
		if b[i] >= 'a' && b[i] <= 'z' {
			b[i] -= 'a' - 'A'
		}
	}
	return string(b)
}

// ticketGraphListInt is PHP's `(int)` cast applied to a STRING — the cast TicketGraphList.php:33
// makes on $_GET['ticket'], whose value is always a string on this path.
//
// It is deliberately NOT engine.go's toInt, NOT memorylist.go's memListInt and NOT graphnode.go's
// graphNodePHPIntFromString. All three disagree with PHP on inputs a URL can carry; the header
// tabulates exactly how and why, and why the fix cannot be made centrally from this ticket.
//
// THE GRAMMAR (zend_operators.c, zval_get_long_func's IS_STRING arm): run is_numeric_string_ex over
// the leading numeric data with allow_errors=true; if there is none, the cast is 0. If the data is an
// integer form that fits a long, return it. Otherwise — a FLOAT form (a fraction or a complete
// exponent) or an OVERFLOWING integer form — convert the double with zend_dval_to_lval_cap, which
// SATURATES at LONG_MAX/LONG_MIN and answers 0 for a non-finite value.
//
//	"340"                    -> 340        ""  / "abc"  -> 0      (no leading numeric data at all)
//	"007"                    -> 7          "12abc"      -> 12     (trailing garbage is allowed)
//	" 5"                     -> 5          "5 "         -> 5      (leading WS skipped; trailing is garbage)
//	"+5"                     -> 5          "-3"         -> -3     (then $tid > 0 sends -3 to the list)
//	"1e3"                    -> 1000       "1e"         -> 1      (an exponent with no digits is garbage)
//	"1.9"                    -> 1          ".5"         -> 0      (double form, truncated toward zero)
//	"0x1A"                   -> 0          "1."         -> 1      (no hex in a numeric string)
//	"99999999999999999999"   -> 9223372036854775807     (SATURATES — this is the cap, not a wrap)
//	"-99999999999999999999"  -> -9223372036854775808
//	"1e400"                  -> 0          (INF is not finite -> cap returns 0)
//
// EVERY LINE OF THAT TABLE IS REACHABLE: $_GET is arbitrary user text and each is a URL someone can
// type. That is the whole reason this helper is exact rather than approximate — contrast graphnode.go,
// whose id arrives through the engine's [A-Za-z0-9]* argument charset.
//
// NOT VERIFIED AGAINST php IN THIS SESSION: there is no php binary in this worktree (see the header),
// so the table is derived from zend_operators.c's grammar and cross-checked against a python model,
// not measured. The saturation half of it is corroborated by memorylist.go:311-318, which reports the
// same behaviour as MEASURED against real PHP.
func ticketGraphListInt(s string) int64 {
	i, n := 0, len(s)
	// is_numeric_string skips leading " \t\n\r\v\f" and ONLY those. isPHPSpace (engine.go:624-626) is
	// already that exact set, so this reuses it rather than restating it; strings.TrimSpace would also
	// strip UNICODE spaces and would read ?ticket=<NBSP>5 as 5 where PHP reads 0.
	for i < n && isPHPSpace(s[i]) {
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
	if i < n && s[i] == '.' { // a fractional part forces the double path — including a bare "1."
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
			return v // IS_LONG: is_numeric_string's lval, returned as-is
		}
		// ParseInt only fails here on OVERFLOW — lit is a well-formed [+-]?[0-9]+ by construction.
		// ZEND_STRTOL overflows too, so is_numeric_string reports IS_DOUBLE and the cast falls
		// through to the same cap the float forms take. THIS is where the saturation happens.
	}
	// lit is well-formed for ParseFloat by construction (Go accepts a trailing '.'), so the only
	// possible error is ErrRange — and on ErrRange Go still returns ±Inf (overflow) or 0 (underflow),
	// which cap turns into 0 and 0: exactly what PHP's zend_strtod + cap produce. So the error is
	// correctly ignored rather than folded into a 0 return of its own.
	f, _ := strconv.ParseFloat(lit, 64)
	return ticketGraphListDvalToLvalCap(f)
}

// ticketGraphListDvalToLvalCap is zend_dval_to_lval_cap (Zend/zend_operators.h) — the SATURATING
// double->long conversion the string (int) cast reaches for:
//
//	if (!zend_finite(d) || zend_isnan(d)) return 0;
//	if (!ZEND_DOUBLE_FITS_LONG(d))       return d > 0 ? ZEND_LONG_MAX : ZEND_LONG_MIN;
//	return (zend_long)d;
//
// IT IS NOT zend_dval_to_lval, the MODULAR variant graphnode.go:959-977 ports. That one is real, but
// it is the cast on a genuine float zval; the STRING arm calls the _cap variant, carrying the comment
// "strtol gives you LONG_MAX/_MIN on overflow. We use saturated conversion to emulate strtol()-like
// behaviour." Using the modular one here would answer 7766279631452241920 for ?ticket=1e20 where PHP
// answers 9223372036854775807 — a different <<<TicketGraph(N)>>>, i.e. different bytes.
//
// It is also not a plain int64(f): Go's float->int conversion is UNDEFINED for out-of-range values
// and is free to produce anything, which is exactly the range the cap exists to define.
func ticketGraphListDvalToLvalCap(f float64) int64 {
	if math.IsNaN(f) || math.IsInf(f, 0) { // !zend_finite || zend_isnan -> 0
		return 0
	}
	// ZEND_DOUBLE_FITS_LONG: the bounds are the exactly-representable doubles adjacent to the int64
	// range, so the comparison is exact rather than rounded.
	if f >= -9.2233720368547758e18 && f < 9.2233720368547758e18 {
		return int64(f) // truncation toward zero
	}
	if f > 0 {
		return math.MaxInt64 // ZEND_LONG_MAX
	}
	return math.MinInt64 // ZEND_LONG_MIN
}
