package tags

// ticketgraph.go — ticket #339, unit go-port:tags:tag:TicketGraph.
//
// The Go port of ONE tag: invocators/tags/dev/TicketGraph.php. Per #281 a tag port is
// ADD-A-FILE-ONLY: this file holds the tag's type, its constructor, its GetDocument, its helpers and
// its self-registration (the init() below), and it changes NOTHING in engine.go — the registry picks
// the tag up because Go runs every init() in a package before any other code in it (Register,
// engine.go:1355; newTag, engine.go:1393). Every package-level identifier it defines is
// ticketGraph*-prefixed or TicketGraph*-named, so it cannot collide with the sibling tag ports; its
// methods are scoped to TicketGraphTag and cannot collide at all.
//
// THE CONTRACT: byte-identical HTML. The PHP is the SPEC. Where the two disagree THIS file is wrong.
//
// ── WHAT THE TAG IS ─────────────────────────────────────────────────────────────────────────────
//
// TicketGraph renders ONE ticket's provenance graph. It takes the ticket id as a TAG ARGUMENT — not
// from $_GET — so it renders standalone (TicketGraph.php:10-11). Its body is short and has exactly
// four exits (TicketGraph.php:47-73):
//
//	1. no CONGRUENCY_SQLITE  -> the css + back-link, then an HTML COMMENT      (:52)
//	2. a PDO throw           -> the css + back-link, then a red error <p>       (:56-58)
//	3. no such ticket row    -> the css + back-link, then "No ticket #N."       (:59)
//	4. a ticket row          -> the header <div>, then ONE <<<GraphNode>>> per slot (:61-72)
//
// Exit 4 is the fan-out: the tag emits `<<<GraphNode(slot)(id)>>>` LITERALS and the engine re-scans
// its output and substitutes each one (ExecuteAllTags, engine.go:1022-1039). This file therefore
// emits the literals and expands NOTHING itself — that is the PHP's design ("the tag engine
// re-parses this output and executes each node tag", TicketGraph.php:12-13), and GraphNode is already
// registered in this package (graphnode.go:302-304), so those literals resolve.
//
// ── THE GALLERY RENDER, WHICH IS THIS UNIT'S WHOLE GATE ─────────────────────────────────────────
//
// The gate URL is ?page=tags&tag=TicketGraph. TagList renders the selected tag by constructing it
// with NULL — `$obj = new $sel(null);` (TagList.php:67). TicketGraph does NOT throw on that NULL: its
// constructor guards the argument with a ternary (TicketGraph.php:20), so a NULL argument list is a
// supported input, not an error path:
//
//	public function __construct($arguments) { $this->id = $arguments ? (int)$arguments->pop() : 0; }
//
// (`$arguments` is a truthiness test, and a PHP object is ALWAYS truthy — so the ternary picks the
// left arm for any real TagArguments and the right arm only for NULL. `args == nil` in Go is exactly
// "PHP was handed NULL"; getTagWrapper always passes a non-nil *TagArguments (engine.go:947-956), so
// nil is EXCLUSIVELY the standalone/gallery path.)
//
// So the gate renders id=0, and that walks to exit 3 — because `id INTEGER PRIMARY KEY AUTOINCREMENT`
// (migrations/0002_ticket_approval.sql:12-15) starts at 1 and AUTOINCREMENT never reuses or descends,
// so no tickets row has id 0 unless one was inserted by hand. The gate's bytes are therefore
//
//	css() + "<p><a href='?page=graphs'>&larr; all ticket-graphs</a></p>\n" + "<p class='empty'>No ticket #0.</p>"
//
// and NOT the fan-out. This matters more than it looks: see the next section.
//
// ── WHY THE GATE NEVER REACHES THE FAN-OUT, AND WHY THAT IS LOAD-BEARING ────────────────────────
//
// The two sides of the #282 harness reach this tag by DIFFERENT depths of the engine:
//
//   - PHP side: TagList calls `$obj->get_document()` DIRECTLY (TagList.php:68) — no re-scan there —
//     but TagList's whole return value is itself the output of a <<<TagList>>> invocation in the
//     ?page=tags document template, so execute_all_tags re-scans it and expands any tag it finds
//     INSIDE it. Nested <<<GraphNode(...)>>> literals would come back EXPANDED in the page's slice.
//   - GO side: the harness calls tags.RenderTag, which is `tag.GetDocument()` and nothing else
//     (engine.go:4147-4159) — no ExecuteAllTags, so nested literals would come back LITERAL.
//
// On exit 4 those two would differ, and the difference would be the harness's entry point rather
// than this port. On the gate they cannot: exit 3 emits no tag literal at all. The asymmetry is real
// but unreachable at id=0, so it is recorded here rather than worked around — inventing an
// ExecuteAllTags call inside GetDocument to "fix" it would make this tag expand its own children,
// which the PHP does not do, and would break exit 4 everywhere the engine drives it correctly.
//
// ── ERRMODE_EXCEPTION: THIS TAG DOES NOT DEGRADE SILENTLY ──────────────────────────────────────
//
// get_document sets PDO::ATTR_ERRMODE = PDO::ERRMODE_EXCEPTION (:54) — the OPPOSITE of the store
// DAO's ERRMODE_SILENT that lets CategoryView render "" against a missing table. A failing query
// THROWS, and the catch (:56-58) renders the red <p>:
//
//	catch (\Throwable $e) {
//	    return $out . "<p style='color:#b00020'>TicketGraph: " . self::esc($e->getMessage()) . "</p>";
//	}
//
// Note it escapes `$e->getMessage()` ALONE — no `get_class($e) . ': '` prefix, unlike TagList.php:71
// — and note the "TicketGraph: " prefix sits OUTSIDE esc(). So a missing `tickets` table degrades to
// that red <p>, NOT to "No ticket #N." — the empty state means "the table is there and has no such
// row", a genuinely different input, and the distinction is this tag's whole degradation story.
//
// That catch is modeled as an ERROR RETURN, not a recover(): fetchTicket returns (row, error) and
// GetDocument turns a non-nil error into the same <p>. This is exhaustive rather than approximate,
// because the ONLY things PHP's try can catch on this path are PDOExceptions — from `new PDO` (:53)
// and from `->query()` under ERRMODE_EXCEPTION (:55) — and both are Go errors, not Go panics. A Go
// panic here would have no PHP counterpart (it would be a bug in this file), so it is deliberately
// left to RenderTag's marked panic notice (engine.go:4149-4154) rather than dressed up as a PHP
// exception. There is likewise no `defer catchThrowable(&out, "TicketGraph")`: catchThrowable emits
// a "<div class='cy-form-error'>…</div>", a shape TicketGraph.php can never produce — its catch arm
// is the <p> at :57 and nothing else.
//
// THE MESSAGE INSIDE THE <p> IS A DOCUMENTED DIVERGENCE, on two counts, both unreachable on the gate
// (whose db exists — the harness SKIPS without it, equivalence_test.go:404-408):
//
//  1. TEXT. PHP's PDOException reads "SQLSTATE[HY000]: General error: 1 no such table: tickets";
//     Go's sqlite driver says "no such table: tickets". This file does NOT forge the SQLSTATE
//     wrapper — the same choice graphnode.go makes about PDO messages and unknownTagHTML makes about
//     unported tags (engine.go:987-993): a plausible-looking forged message is a divergence dressed
//     as equivalence. The SHAPE (the red <p>, in the right place, for the right inputs) is faithful;
//     the message text is the port's own.
//  2. WHICH INPUTS REACH IT. PHP's `new PDO('sqlite:'.$path)` is READ-WRITE and CREATES an empty db
//     when the file is missing; openDB stats first and errors ("Missing file -> error, never
//     creation", engine.go:1172-1179). The two still agree on the SHAPE for a missing file: PHP
//     creates an empty db, then :55's query hits "no such table: tickets" and throws into the same
//     catch. So both render the red <p>; only the text inside it differs, which is (1). Unlike
//     GraphNode — whose default arm queries nothing, forcing that port to open LAZILY — this tag
//     ALWAYS queries, so opening where the PHP opens is exact and no laziness is needed.
//
// ── QUIRKS PORTED DELIBERATELY (each would be tempting to "fix") ────────────────────────────────
//
//  1. `!$t` IS "NO ROW", NOT "NO DATA" (:59). fetch(PDO::FETCH_ASSOC) returns FALSE for no row, and
//     `!false` is true. A row of three NULLs is a NON-EMPTY array and is therefore TRUTHY, so it
//     takes the POPULATED branch and renders three empty esc()'d cells — not "No ticket #N.".
//     `row == nil` here is "fetch returned false" and nothing else.
//  2. THE ID IS INTERPOLATED INTO THE SQL, NOT BOUND — and this port interpolates it too. It is safe
//     by construction on both sides: the value is an (int) before it is ever concatenated (:20, :48),
//     so what reaches the SQL is always a bare decimal integer. Binding it instead would be a real
//     divergence, not a tidy-up: a bound parameter carries TEXT affinity where the literal carries
//     INTEGER, and the two can match different rows.
//  3. THE ID IS ECHOED RAW, NOT ESCAPED (:59, :64, :70). `"No ticket #" . $id`, `"#" . $id` and the
//     GraphNode argument all skip esc() while every DB-derived byte goes through it. That is SAFE and
//     is not sloppiness worth "fixing": $id is an int by then, so it can only ever be [-0-9]+.
//  4. THE STATUS COLOUR IS INTERPOLATED INTO AN ATTRIBUTE UNESCAPED (:62-63) — `style='...:$stc'`.
//     Also safe by construction: st_colour returns one of its own eight table literals or the '#666'
//     fallback, never anything caller-derived. Ported as-is.
//  5. 'manifestations' IS IN $slots BUT HAS NO GraphNode CASE (:24-25). It renders GraphNode's
//     default-arm placeholder under its own heading. That is the PHP's behavior — see
//     graphnode.go:325-326, which records the same fact from the other side — not an omission here.
//
// ── strtoupper IS ASCII-ONLY; strings.ToUpper IS NOT ────────────────────────────────────────────
//
// st_colour upper-cases the status before the table lookup (:31). PHP's strtoupper maps ONLY a-z: it
// is a byte function, and in the default C locale (nothing here calls setlocale) it leaves every
// non-ASCII byte alone — which is also what PHP 8.2+ does unconditionally. strings.ToUpper is
// Unicode-aware and does NOT agree: it maps U+017F LATIN SMALL LETTER LONG S to 'S', so a status of
// "ſUPERSEDED" would find the 'SUPERSEDED' key in Go and miss it in PHP, colouring the same ticket
// two different colours. ticketGraphStrToUpper is the byte-wise ASCII fold, which is exactly PHP's.
// (engine.go:3901 reaches for strings.ToUpper on a status; that is a different tag's line and this
// file does not touch it — but it is why this helper is spelled out rather than assumed.)
//
// ── WHAT WAS AND WAS NOT RUN (read this before trusting a claim above) ──────────────────────────
//
// THIS FILE WAS NEVER COMPILED, AND THIS UNIT'S GATE WAS NEVER RUN. Both statements are absolute;
// nothing below softens them. THE TICKET'S GATE IS THEREFORE NOT MET, and this file does not claim
// it is. The reasons were re-checked THIS session, not inherited from the sibling ports that state
// the same wall:
//
//   - NO GO TOOLCHAIN. `go` exists at /opt/homebrew/bin/go, but every invocation of it — `go
//     version`, and therefore `go build`, `go vet`, `gofmt` and the ticket's
//     `go test ./tags/ -run TestTagEquivalence -count=1 -v` — is refused by this harness with "This
//     command requires approval", and there is no one to approve it. The obvious workaround —
//     shelling out to go from the python that IS permitted — was deliberately not taken: routing
//     around a permission gate is not a measurement.
//   - NO PHP. The ticket permits exactly one php — "the repo php at tooling/congruencey-harness/php/
//     php" — and THAT PATH DOES NOT EXIST here: tooling/congruencey-harness/ holds only .gitignore,
//     AutoLoader.php, Constants_patched.php, README.md, router.php, serve, shim.php and
//     telemetry.php. It is PROVISIONED, not committed — tooling/congruencey-harness/.gitignore:1
//     lists "php/". So the PHP original cannot be booted and the gate's guard 4 (the live server,
//     equivalence_test.go:419-429) could not pass even with a toolchain.
//   - NO DB. No *.sqlite exists anywhere under the repo root (searched this session; .gitignore:2
//     ignores "*.sqlite"), so the gate's guard 2 (equivalence_test.go:404-408) would skip too.
//
// WHAT WAS ACTUALLY VERIFIED, mechanically, with the python that is permitted: every fixed byte
// string this file emits was extracted from THIS file and from TicketGraph.php independently and
// compared — the css() concatenation, the back-link, the no-DB comment, the error <p>, the empty <p>,
// the four header fragments, the GraphNode literal, the eleven $slots, and the eight st_colour
// entries with their '#666' fallback — thirteen comparisons, all matching. That is a transcription
// check, NOT the gate: it proves this file says what the PHP
// says, and says nothing about whether it COMPILES or whether the engine hands it what it expects.
// The gate remains unrun, and the ticket remains unsettled until someone can run it.

import (
	"strconv"
)

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there —
// and IsPorted("TicketGraph") flipping true is exactly what turns the harness's SKIP into a measured
// byte-diff (equivalence_test.go:456-461). Register is the registry's only writer and PANICS on a
// duplicate name (engine.go:1355-1368), so this is the ONE place TicketGraph is registered.
func init() {
	Register("TicketGraph", func(e *Engine, a *TagArguments) Tag { return newTicketGraphTag(e, a) })
}

// ── the tag's fixed strings, each read off the PHP line cited ───────────────────────────────────

// ticketGraphCSS is TicketGraph::css() (TicketGraph.php:35-45) — the seven rules and their <style>
// wrapper, verbatim, in source order. The trailing "\n" is inside the PHP's double-quoted
// "</style>\n" (:44) and is part of the tag's bytes.
const ticketGraphCSS = "<style>" +
	".g{border:1px solid #d8d2c4;border-left:5px solid #999;border-radius:6px;padding:.55rem .85rem;background:#fffdf8}" +
	".g .id{font:600 .7rem/1 monospace;color:#555;letter-spacing:.05em}" +
	".g .cm{font:.7rem/1 monospace;color:#8a5a1a}" +
	".g .st{float:right;font:600 .6rem/1.6 sans-serif;text-transform:uppercase;color:#fff;padding:.1rem .45rem;border-radius:3px}" +
	".node{border:1px solid #d8d2c4;border-radius:6px;padding:.5rem .8rem;margin:.4rem 0;background:#fffdf8}" +
	".node h3{margin:.1rem 0;font:600 .74rem sans-serif;text-transform:uppercase;letter-spacing:.04em;color:#555}" +
	".empty{color:#999;font-style:italic}" +
	"</style>\n"

// ticketGraphBackLink is TicketGraph.php:50 — emitted on EVERY exit, before any branch is chosen.
const ticketGraphBackLink = "<p><a href='?page=graphs'>&larr; all ticket-graphs</a></p>\n"

// ticketGraphNoDBHTML is TicketGraph.php:52 — an HTML COMMENT, not a visible state, and with NO
// trailing newline.
const ticketGraphNoDBHTML = "<!-- TicketGraph: no DB -->"

// ticketGraphSlots is TicketGraph::$slots (TicketGraph.php:24-25), verbatim and IN ORDER: the
// ordered slots the ticket-class aggregate contains, goal .. children. The order is the emit order at
// :69-71, so it is part of the bytes. 'manifestations' is here and has no GraphNode case — quirk 5.
var ticketGraphSlots = []string{
	"goal", "patch", "approval", "runs",
	"mandate", "manifestations", "guarantees", "journey", "artifacts", "source", "children",
}

// ticketGraphStatusColours is the $map of TicketGraph::st_colour (TicketGraph.php:28-30), verbatim.
// Every value is a non-empty string, so PHP's `isset($map[$st])` (:32) — which is false for a NULL
// value as well as for a missing key — is exactly Go's comma-ok lookup here.
var ticketGraphStatusColours = map[string]string{
	"OPEN":       "#1a7a3a",
	"REQUESTED":  "#5a6a8a",
	"APPROVED":   "#1a5a7a",
	"VERIFIED":   "#2a7a5a",
	"PUBLISHED":  "#3a7a3a",
	"CLOSED":     "#888",
	"SUPERSEDED": "#b06a2a",
	"REFUSED":    "#b00020",
}

// ticketGraphDefaultColour is st_colour's fallback (TicketGraph.php:32) — the colour of any status
// not in the table, the empty string and NULL included.
const ticketGraphDefaultColour = "#666"

// ── the tag ─────────────────────────────────────────────────────────────────────────────────────

// TicketGraphTag is TicketGraph (TicketGraph.php:17-74). Its one PHP property is $id.
type TicketGraphTag struct {
	e *Engine

	// id is $this->id (:20) — already (int)-cast, which is why nothing downstream re-parses it.
	id int64
}

// newTicketGraphTag is TicketGraph::__construct (TicketGraph.php:20):
//
//	public function __construct($arguments) { $this->id = $arguments ? (int)$arguments->pop() : 0; }
//
// ONE pop. It hands back the argument written FIRST, because setArguments stores them reversed
// (engine.go:711-722) — so <<<TicketGraph(186)>>> yields "186". PHP's array_pop on an empty list
// returns NULL and (int)NULL is 0; Go's Pop() returns ("", false) there, and the cast below maps ""
// to the same 0.
//
// It must never panic: SelfCheck constructs every registered tag with nil args and asserts it yields
// a usable Tag. The PHP's ternary is why nil is a normal input here rather than the throw its sibling
// CategoryView takes.
//
// THE CAST IS graphNodePHPIntFromString, NOT engine.go's toInt, and not a fresh copy of either.
// GraphNode.php:25 makes the IDENTICAL `(int)$arguments->pop()` cast on the IDENTICAL kind of value —
// an id argument off the same parser — so graphnode.go:887-948 is a port of the very cast this line
// needs, and reusing it is what stops two copies of PHP's string→int grammar drifting apart. toInt
// would be WRONG here: toInt(string) is "the leading run of digits" (engine.go:558-595, leadingInt),
// which is right for the DB values it was written for but says 1 for "1e3" where PHP has said 1000
// since 7.1 — and FUNCTION_ARGUMENTS is `(\([A-Za-z0-9]*\))*`, which admits "1e3". Reused, not
// edited: this ticket touches ticketgraph.go and nothing else.
func newTicketGraphTag(e *Engine, args *TagArguments) *TicketGraphTag {
	t := &TicketGraphTag{e: e}
	if args == nil {
		return t // `$arguments ? … : 0` — the NULL arm, i.e. the gallery path, leaving id 0
	}
	raw, _ := args.Pop() // (int)$arguments->pop()
	t.id = graphNodePHPIntFromString(raw)
	return t
}

// ticketGraphStrToUpper is strtoupper($s) — PHP's BYTE-wise, ASCII-only upper-case fold.
//
// NOT strings.ToUpper, which is Unicode-aware: see the "strtoupper IS ASCII-ONLY" section of the file
// header for the status that the two would colour differently. PHP maps a-z and leaves every other
// byte — every byte of a multibyte rune included — untouched, which is what this loop does.
func ticketGraphStrToUpper(s string) string {
	b := []byte(s)
	for i := 0; i < len(b); i++ {
		if b[i] >= 'a' && b[i] <= 'z' {
			b[i] -= 'a' - 'A'
		}
	}
	return string(b)
}

// ticketGraphStatusColour is TicketGraph::st_colour($st) (TicketGraph.php:27-33):
//
//	$st = strtoupper((string)$st);
//	return isset($map[$st]) ? $map[$st] : '#666';
//
// The (string) cast is phpString, so a NULL status becomes "" — not a key — and colours '#666'.
func ticketGraphStatusColour(st any) string {
	if c, ok := ticketGraphStatusColours[ticketGraphStrToUpper(phpString(st))]; ok {
		return c
	}
	return ticketGraphDefaultColour
}

// GetDocument is TicketGraph::get_document() (TicketGraph.php:47-73).
//
// The four exits are the header's four exits, in the PHP's order. Two structural details survive the
// port because each changes the bytes:
//
//   - `$out` is built BEFORE the try (:49-50), so the css and the back-link precede EVERY exit,
//     including the no-DB comment and the error <p>. Both `return $out . …` arms concatenate onto it.
//   - the `!defined('CONGRUENCY_SQLITE')` test sits INSIDE the try (:52) but is a plain `return`, not
//     a throw — so it is a branch here, not an error.
func (t *TicketGraphTag) GetDocument() string {
	id := t.id // :48 — `(int)$this->id` re-casts a value that is already an int; a no-op, and it stays one
	sid := strconv.FormatInt(id, 10)

	out := ticketGraphCSS      // :49
	out += ticketGraphBackLink // :50

	// :52 — `if (!defined('CONGRUENCY_SQLITE')) { return $out . "<!-- TicketGraph: no DB -->"; }`.
	// cfg.SQLite == "" is that test (the same reading graphnode.go:436-438 makes of GraphNode.php:38).
	if t.e.cfg.SQLite == "" {
		return out + ticketGraphNoDBHTML
	}

	row, err := t.fetchTicket(sid) // :53-55
	if err != nil {
		// :56-58 — the catch. "TicketGraph: " is OUTSIDE esc(); the message alone is escaped, with no
		// get_class($e) prefix. See the header for why an error return is the exhaustive model.
		return out + "<p style='color:#b00020'>TicketGraph: " + esc(err.Error()) + "</p>"
	}
	if row == nil {
		// :59 — `if (!$t)`. nil is "fetch() returned false", i.e. NO ROW, and nothing else; a row of
		// NULLs is truthy in PHP and falls through to the populated branch below. See quirk 1.
		// The id is echoed RAW (quirk 3): it is an int, so it can only be [-0-9]+.
		return out + "<p class='empty'>No ticket #" + sid + ".</p>"
	}

	stc := ticketGraphStatusColour(row["status"]) // :61

	// :62-65 — the graph-root header. $stc is interpolated into both attributes unescaped (quirk 4);
	// every DB-derived byte goes through esc().
	out += "<div class='g' style='border-left-color:" + stc + "'>"
	out += "<span class='st' style='background:" + stc + "'>" + esc(row["status"]) + "</span>"
	out += "<span class='id'>#" + sid + "</span> <span class='cm'>" + esc(row["component"]) + "</span>"
	out += "<h2 style='font-weight:normal;margin:.2rem 0'>" + esc(row["title"]) + "</h2></div>\n"

	// :69-71 — one node tag per slot, in $slots order. These are LITERALS: the engine re-scans this
	// return value and expands each one (ExecuteAllTags, engine.go:1022-1039). Congruency arguments
	// are CHAINED single parens, not comma-separated (:68) — `(slot)(id)`, which is what
	// FUNCTION_ARGUMENTS `(\([A-Za-z0-9]*\))*` matches; `(slot,id)` would not match at all and would
	// be left literal in the page.
	for _, slot := range ticketGraphSlots {
		out += "<<<GraphNode(" + slot + ")(" + sid + ")>>>\n"
	}
	return out // :72
}

// fetchTicket is the try block's DB work (TicketGraph.php:53-55):
//
//	$db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
//	$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
//	$t = $db->query("SELECT status, component, title FROM tickets WHERE id=" . $id)->fetch(PDO::FETCH_ASSOC);
//
// It returns (nil, nil) for fetch()'s FALSE — no such row — and (nil, err) for anything PHP would
// throw. ERRMODE_EXCEPTION has no Go analogue to set: it IS the error return, which GetDocument turns
// into the PHP's catch <p>.
//
// The open is EAGER, where the PHP opens. GraphNode's port defers its open because its default arm
// queries nothing and an eager open would manufacture a divergence on that tag's gate
// (graphnode.go:472-487); this tag has no such arm — every path that reaches here queries — so the
// PHP's own order is exact. The handle is closed on the way out; PHP leaves that to the GC.
func (t *TicketGraphTag) fetchTicket(sid string) (map[string]any, error) {
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite) // :53 — `new PDO`; see divergence 2 in the header
	if err != nil {
		return nil, err
	}
	defer db.Close()

	// :55 — the id is INTERPOLATED, not bound, and is safe by construction: it is an int before it is
	// concatenated, so this is always a bare decimal literal. See quirk 2 for why binding would be a
	// divergence rather than a tidy-up.
	rows, err := queryRows(db, "SELECT status, component, title FROM tickets WHERE id="+sid)
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, nil // fetch(PDO::FETCH_ASSOC) === false
	}
	return rows[0], nil // fetch() takes the FIRST row only
}
