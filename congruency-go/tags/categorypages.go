package tags

// categorypages.go — ticket #255, unit go-port:tags:tag:CategoryPages.
//
// The Go port of ONE tag: invocators/tags/dev/CategoryPages.php — browse pages by category. It is
// an ADD-A-FILE leaf in the sense #281 established (engine.go:1293-1321): this file holds the tag's
// type, its constructor, its GetDocument, its helpers and its self-registration, and it changes
// NOTHING in engine.go. Adding it moves PortedTags() from 12 names to 13; that is the whole
// footprint.
//
// TWO CONSEQUENCES OF TOUCHING NOTHING CENTRAL, both read off this checkout this session, because
// each looks like a contradiction until you see why it is not:
//
//   - engine.go:194-198's "NOT PORTED (35)" list STILL NAMES CategoryPages, and this file cannot fix
//     it — the deliverable is this file alone. That list is not the authority and says so in place:
//     "PortedTags(), which is the authority; this list is a copy" (engine.go:191-192). It has been
//     stale since #247 and #248 landed, both of which it also still lists as unported. Trust
//     PortedTags(); the copy rots BY DESIGN, and the alternative — every tag ticket editing
//     engine.go — is precisely the collision #281 removed.
//   - engine.go's SelfCheck STAYS GREEN with a 13th tag registered. Its registry invariants are
//     deliberately additive-safe: the ported set is asserted as a SUBSET, the count as a FLOOR never
//     an equality, and the negatives are names that can never be legitimately registered at all
//     (engine.go:4363-4391). This registration is the exact case that design anticipates, so nothing
//     central needs an edit here either.
//
// THE CONTRACT is engine.go's contract: byte-identical HTML against the same DB. THE PHP IS THE
// SPEC — everything below that looks quirky is quirky because CategoryPages.php is, and where the
// two disagree THIS file is wrong.
//
// ── WHAT THE TAG IS, AND ITS TWO BRANCHES ───────────────────────────────────────────────────────
//
// A category is a page tag. A page is tagged by an `annotations` row whose `tag` is the category
// name and whose `target` is "page:<DocumentID>" (written by TagPageHandler). CategoryPages shows
// ONE category at a time, and picks which one from the tag argument, else ?category=:
//
//	$cat === ''  -> THE INDEX: every Categories row, its page count, and a link that drills in.
//	$cat !== ''  -> THE DRILL-IN: every page tagged with that category, as links to ?page=<DocumentID>.
//
// It is invoked as <<<CategoryPages>>> or <<<CategoryPages(specifications)>>>. It reads only.
//
// ── THE DOCBLOCK ON THE PHP IS WRONG. DO NOT PORT IT ────────────────────────────────────────────
//
// Read this before you conclude this port is missing a join. CategoryPages.php:11-12 says the tag
// "lists every Document linked to it via the Page_Categories join table". THERE IS NO
// Page_Categories TABLE, and the tag's SQL never mentions one — both queries read `annotations`.
// The sibling tag says so in as many words: "There is no Page_Categories join table — the link
// lives in `annotations`" (CategoryBrowse.php:13-14). So the PHP's own docblock describes a schema
// that does not exist, while the PHP's CODE reads the schema that does.
//
// That is a defect in a COMMENT, not in behaviour: the rendered bytes are produced by the code, so
// porting the code faithfully IS porting the contract, and there is nothing here to file a bug
// against (the ticket's "if the PHP is genuinely defective, file a separate bug ticket and port the
// defect faithfully" is about behaviour; a stale comment emits no bytes). It is flagged here only
// because a reader who checks this port against that docblock rather than against the SQL will
// think a join is missing.
//
// ── THE GALLERY RENDERS THE INDEX, AND IT IS NOT SELF-FILTERED ──────────────────────────────────
//
// ?page=tags&tag=CategoryPages constructs the tag as `new CategoryPages(null)` (TagList.php:67), so
// $this->category is '' — and this tag reads ?category=, NOT ?tag=, so the gallery's own ?tag=
// parameter does NOT feed back into it. The gallery therefore renders THE INDEX, in full.
//
// This is worth stating because the sibling port Annotations does the opposite: it reads ?tag= as
// its own row filter, so ?page=tags&tag=Annotations self-filters to an empty result
// (annotations.go:26-34). CategoryPages does not have that shape. Both facts are read off the two
// sources, not assumed from the URL.
//
// ── THREE QUIRKS THAT A "CLEANER" PORT WOULD SILENTLY BREAK ─────────────────────────────────────
//
//  1. THE DESCRIPTION TEST IS PHP TRUTHINESS, NOT A NULL/EMPTY CHECK (CategoryPages.php:45). The
//     PHP writes `$r['description'] ? " &mdash; " . esc(...) : ""`, so a description of the single
//     character "0" is FALSY and renders NOTHING — no em-dash, no text. Its sibling CategoryBrowse
//     tests `!== null && !== ''` on the same column (CategoryBrowse.php:63) and WOULD render "0".
//     The two tags genuinely disagree on that one input; each port matches its own source. See
//     catPagesDescription.
//
//  2. THE TITLE TEST IS STRICT IDENTITY (CategoryPages.php:58): `$r['Title'] !== null && $r['Title']
//     !== ''`. Identity, not equality — so an INTEGER Title of 0 satisfies it (0 !== '' is true,
//     the types differ) and renders "0", where a loose test would fall back to the DocumentID.
//     sqlite is dynamically typed, so an integer Title is storable. See catPagesTitleSet.
//
//  3. THE INDEX HAS NO EMPTY STATE. With zero Categories rows the loop never runs and the PHP
//     returns "<ul>" . "</ul>" — a literal, empty "<ul></ul>". There is no "No categories yet."
//     branch here (CategoryBrowse.php:94 has one; this tag does not). Reproducing the bare
//     "<ul></ul>" is the port; adding an empty state would be a divergence.
//
// ── DEPENDENCY AND DEGRADATION (the ticket asks for this explicitly) ────────────────────────────
//
// The dependency is three tables in CONGRUENCY_SQLITE — Categories, annotations and Documents —
// which is the class of dependency tools/tag_selfcheck.py checks ("SQL TABLES — every table name
// after FROM/JOIN ... verified against CONGRUENCY_SQLITE"). Unlike Annotations and ApiReference,
// this tag PROBES FOR NOTHING: there is no sqlite_master check and no "table missing" branch. It
// has exactly two degradation steps, and both are reproduced:
//
//	!defined('CONGRUENCY_SQLITE')  -> "<p>CategoryPages: no DB.</p>"                  (:32)
//	any \Throwable                 -> "<div class='cy-form-error'>CategoryPages error: …</div>"  (:62-64)
//
// So a MISSING TABLE degrades through the second arm: PDO throws (ERRMODE_EXCEPTION, :26) and the
// catch renders the error div. Go's database/sql returns an error instead of throwing, so each
// queryRows error is routed to throwableHTML — same branch, different mechanism. catchThrowable
// still guards the deferred path for a real panic.
//
// TWO INHERITED DIVERGENCES INSIDE THAT ERROR ARM. Neither is a decision this file makes and
// neither is reachable from this unit's gate (which runs both engines against the same, present
// db), but both are real and are stated rather than quietly widened:
//
//   - THE MESSAGE TEXT. PHP renders `get_class($e) . ': ' . $e->getMessage()` — e.g. "PDOException:
//     SQLSTATE[HY000]: General error: 1 no such table: Categories". A Go error has no class and its
//     text comes from a different driver, so throwableHTML emits the message alone (engine.go:1708-
//     1710 documents this for every ported tag). The div, its class and its "CategoryPages error: "
//     prefix are identical; the message inside it is not.
//   - THE MISSING DB FILE. PHP's `new PDO('sqlite:'.$path)` is READ-WRITE and CREATES an empty db
//     when the path is absent; the first query then throws "no such table: Categories" and the PHP
//     renders the error div. openDB refuses to create anything (engine.go's divergence 2), so the
//     same input renders the error div with "database not found: <path>" instead. Both are error
//     divs; the message differs. Re-litigating #226's package-wide open policy is out of scope for
//     a port-ONE-tag ticket, so this file follows the policy its siblings follow
//     (engine.go:1607-1610, annotations.go:47-56).
//
// A db that exists but is corrupt or unreadable is the throwing path in BOTH engines, and both
// render the error div.
//
// ── ESCAPING: htmlspecialchars, NEVER urlencode ─────────────────────────────────────────────────
//
// Every DB-derived byte goes through esc() — the htmlspecialchars($s, ENT_QUOTES) recursion guard
// that keeps a stored "<<<Tag>>>" from re-entering execute_all_tags (engine.go's file header,
// mechanism 2). Note the hrefs: CategoryPages.php:44 builds "?page=pages&category=" . esc($r['name'])
// — it ESCAPES, it does NOT urlencode, exactly as its sibling does (CategoryBrowse.php:61). A
// category named "R&D" therefore renders href='?page=pages&category=R&amp;D' with no percent-
// encoding anywhere. Reaching for phpURLEncode here would be tidier, more correct as HTML, and
// WRONG — it would diverge on the first category whose name is not [A-Za-z0-9-_.].
//
// ── WHAT WAS AND WAS NOT RUN (read this before trusting a claim above) ──────────────────────────
//
// THIS FILE WAS NEVER COMPILED, AND THIS UNIT'S GATE WAS NEVER RUN. Both statements are absolute;
// nothing below softens them.
//
// The gate the ticket specifies is a byte-diff of two live servers over the same db. NEITHER SIDE
// of it can be produced in this worktree, and the reasons were re-checked this session, not
// inherited:
//
//   - NO PHP. The ticket permits exactly one php — "the repo php at tooling/congruencey-harness/php/
//     php" — and THAT PATH DOES NOT EXIST here: the directory holds only AutoLoader.php,
//     Constants_patched.php, README.md, router.php, serve, shim.php and telemetry.php. It is
//     PROVISIONED, not committed — .gitignore:10 lists "/tooling/congruencey-harness/php/". (Whether
//     some other php sits on PATH was NOT established: `command -v php` is itself refused by the
//     harness. It would be moot — that php is not the one the ticket permits.)
//   - NO DB. CONGRUENCY_SQLITE is <app>/../state/congruency.sqlite = checkouts/current/state/
//     congruency.sqlite (configure.php:42). checkouts/current/state/ exists and holds only
//     README.md, STATE.json, component.json, manifest.json and state.lock; no *.sqlite exists
//     anywhere under the repo root (searched this session). It is gitignored too —
//     .gitignore:7 "*.sqlite", :11 "/checkouts/current/state/congruency.sqlite".
//   - NO SERVERS, NO NETWORK. curl to 127.0.0.1:8899 and :8900 is refused by the harness, so the
//     two-server diff cannot be issued at all.
//   - NO GO TOOLCHAIN. `go version`, and therefore `go build`, `go vet`, `gofmt` and `go test`, are
//     refused by the harness with "This command requires approval", and there is no one to approve
//     them. The obvious workaround — shelling out to go from the python that IS permitted — was
//     deliberately not taken: routing around a permission gate is not a measurement.
//
// So "renders IDENTICAL HTML to the PHP" is, for this file, a claim DERIVED BY PORTING THE SOURCE
// LINE BY LINE. It is not a measured result and it is not reported as one.
//
// WHAT WAS ACTUALLY RUN, with python3 (the one toolchain permitted here) — this is narrow, and its
// limits are stated with it. A line-by-line PYTHON TRANSLITERATION of the PHP source above (same
// branches, same helpers, same literals, same order) and a second transliteration of THIS Go file
// were run against a SYNTHETIC sqlite db — synthetic, and its schema RECONSTRUCTED rather than read,
// because the live db is absent: Categories(`key`,name,description) comes from
// NewCategoryHandler.php:40-42's INSERT, annotations(id,tag,target,note,ts) from this tag's and
// Annotations.php's SQL, and Documents(DocumentID,Title,...) from this tag's SQL plus DocumentDAO's
// join (engine.go:1087-1099). A column this tag never reads could differ from the live db and this
// would not know it; every column it DOES read is exercised, over 15 inputs covering every branch
// and every quirk above: the index over 0, 1 and 5 categories;
// the "0" description, a NULL description and an empty-string description; the &-in-name escaping
// path; the drill-in from the tag argument and from ?category=; the argument-beats-?category=
// precedence; a trimmed argument; a spaces-only ?category=; the untagged category; a category with
// no pages and one that does not exist; an empty Title, a NULL Title and an integer Title of 0; and
// a stored "<<<TicketList>>>" coming back escaped and inert in BOTH a Title and a description. All
// 15 agreed byte for byte, and the two SQL statements below executed unmodified against real sqlite
// — which is what proves the backtick-quoted GROUP BY c.`key` is accepted, that the LEFT JOIN gives
// an untagged category COUNT(a.id) = 0 rather than 1, and that the ON-clause LIKE 'page:%' keeps a
// "ticket:12"/"source:<hash>" annotation carrying the same tag out of both the count and the list.
//
// WHAT THAT DOES AND DOES NOT ESTABLISH. It establishes that the ALGORITHM encoded here matches the
// PHP SOURCE branch for branch, and that its SQL is valid SQLite. It does NOT establish that this
// Go file compiles; it does NOT establish that Go's own primitives behave as the transliteration
// assumed; and — because there is no php binary here — it does NOT compare against the PHP's own
// bytes, only against a reading of the PHP's source. That reading is the weakest link and it is
// named as such. THE FIRST THINGS TO DO WITH THIS FILE, in order:
//
//	cd congruency-go && go build ./... && go vet ./... && gofmt -l .
//	go test ./tags/ -run TestTagEquivalence/CategoryPages -v      # needs the live PHP on 8899
//
// The second command IS this unit's gate and needs no edit anywhere to include this tag: #282's
// harness sweeps Scan()'s names and measures any that IsPorted(), so the Register call below is
// exactly what flips CategoryPages from "no Go port yet — SKIP" to a measured byte-diff.
//
// WHY NOT THE TICKET'S LITERAL GATE, EVEN ONCE php AND THE DB ARE BACK. Neither leg of the
// two-server diff can come out empty, for reasons that are not this unit's. The ticket instructs
// that this be said on the ticket rather than settled around ("if you cannot make a diff here run
// against THIS unit, say so on the ticket"), so it is said here too, precisely:
//
//   - LEG 1, ?page=tags&tag=CategoryPages. 8900 DOES run this tag: #280 wired the page seam to the
//     real engine, and ?page=tags is the ONE page surface that is not a seam (server.go:45-52). But
//     the PHP wraps every tag render in ~6.2 KB of CMS chrome (nav/head/style from
//     Controller::control()) that the Go frame deliberately does not forge (server.go:62-66). So the
//     RAW page diff is non-empty by that constant, with or without this file.
//   - LEG 2, ?page=pages. Worse: ?page=tags is the only exception, so every other page key — this
//     one included — is answered by the generic table-list CATALOG SEAM, which never runs the tag
//     engine at all (server.go:40-43). <<<CategoryPages>>> is therefore never substituted on 8900's
//     ?page=pages, and that diff would be IDENTICALLY non-empty with this file deleted — the
//     ticket's own definition of a gate that does not exercise the unit.
//
// The gate that DOES change exactly when this file changes is the per-tag byte-diff above. It is
// not a weaker substitute for leg 1: #282's harness cuts the chrome away and compares THIS TAG's
// bytes, slicing the PHP page on the document template's own tail (measured via an Unknown-tag
// probe, equivalence_test.go:69-73,163-165) — i.e. it is leg 1 with the constant that defeats it
// removed.

import (
	"database/sql"
	"strconv"
)

// init self-registers the tag. This is the whole wiring step (#281; engine.go:1293-1307).
func init() {
	Register("CategoryPages", func(e *Engine, a *TagArguments) Tag { return newCategoryPagesTag(e, a) })
}

// CategoryPagesTag is CategoryPages (CategoryPages.php:16).
type CategoryPagesTag struct {
	e        *Engine
	category string
}

// newCategoryPagesTag is CategoryPages::__construct (CategoryPages.php:19-21):
//
//	$this->category = (isset($arguments) && method_exists($arguments,'top')) ? $arguments->top() : '';
//
// A nil *TagArguments is the PHP's NULL — the standalone/gallery shape TagList.php:67 passes — and
// `isset(NULL)` is FALSE, so the category stays ''. Top() on a *TagArguments with no arguments is
// PHP's end([]) === false cast to '' (engine.go:737-742), so <<<CategoryPages>>> and
// <<<CategoryPages()>>> both land on '' too.
func newCategoryPagesTag(e *Engine, args *TagArguments) *CategoryPagesTag {
	c := &CategoryPagesTag{e: e}
	if args != nil {
		c.category = args.Top()
	}
	return c
}

// GetDocument is CategoryPages::get_document() (CategoryPages.php:30-65).
//
// The whole body is the PHP's try block; catchThrowable is its `catch (\Throwable $e)` arm (:62-64).
func (t *CategoryPagesTag) GetDocument() (out string) {
	defer catchThrowable(&out, "CategoryPages")

	// if (!defined('CONGRUENCY_SQLITE')) — :32
	if t.e.cfg.SQLite == "" {
		return "<p>CategoryPages: no DB.</p>"
	}
	// PHP reaches its catch through `new PDO(...)` throwing (:25-26); an unopenable db lands on the
	// same branch here. See the header for the one input (db file ABSENT) where the two messages
	// inside the div differ.
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return throwableHTML("CategoryPages", err)
	}
	defer db.Close()

	// :35-36 — the category comes from the tag argument, else the ?category= URL param. The argument
	// WINS: ?category= is consulted only when the argument trimmed to ''. getIsset is
	// `isset($_GET['category'])`; trim('') is '', so a key that is absent and a key that is
	// present-but-empty both leave $cat at '' — the index branch.
	cat := phpTrim(t.category)
	if cat == "" {
		if v, ok := t.e.getIsset("category"); ok {
			cat = phpTrim(v)
		}
	}

	if cat == "" { // :38 — no arg -> index of all categories with page counts
		return t.index(db)
	}
	return t.pages(db, cat)
}

// index is CategoryPages.php:39-47 — every category, its page count, and a link that drills in.
//
// THE COUNT IS A LEFT JOIN, NOT A CORRELATED SUBQUERY (its sibling uses the latter,
// CategoryBrowse.php:90-92). COUNT(a.id) counts NON-NULL a.id, so a category with no annotations
// rows counts 0 rather than 1 — which is the whole reason the PHP counts a COLUMN and not (*).
//
// GROUP BY is on c.`key`, the Categories primary key (NewCategoryHandler.php:40-42 inserts it as
// max+1), NOT on c.name. Two categories that somehow share a name therefore stay TWO rows. The
// backticks are MySQL-style identifier quoting, which sqlite accepts; they are kept verbatim
// because the PHP is the spec and this SQL is what it runs.
//
// There is no empty state: with no rows this returns the literal "<ul></ul>". See the header.
func (t *CategoryPagesTag) index(db *sql.DB) string {
	rows, err := queryRows(db, "SELECT c.name, c.description, COUNT(a.id) AS n\n"+
		"                        FROM Categories c LEFT JOIN annotations a ON a.tag=c.name AND a.target LIKE 'page:%'\n"+
		"                        GROUP BY c.`key` ORDER BY c.name")
	if err != nil {
		return throwableHTML("CategoryPages", err)
	}
	out := "<ul>" // :42
	for _, r := range rows {
		// :44-45. esc(), NOT urlencode() — see the header. (int)$r['n'] is toInt.
		out += "<li><a href='?page=pages&category=" + esc(r["name"]) + "'>" + esc(r["name"]) +
			"</a> (" + strconv.FormatInt(toInt(r["n"]), 10) + ")" + catPagesDescription(r["description"]) + "</li>"
	}
	return out + "</ul>" // :47
}

// pages is CategoryPages.php:50-61 — every page tagged with one category, as links.
//
// The join reproduces the sibling's documented rule exactly (CategoryBrowse.php:41-42): 'page:' is
// 5 characters and sqlite's substr is 1-INDEXED, so substr(a.target, 6) is the DocumentID. The
// `LIKE 'page:%'` is what keeps a "ticket:12" or "source:<hash>" annotation carrying the same tag
// out of the result — without it, substr(target,6) would still produce a string and could collide
// with a real DocumentID.
func (t *CategoryPagesTag) pages(db *sql.DB, cat string) string {
	rows, err := queryRows(db, "SELECT d.DocumentID, d.Title FROM annotations a\n"+
		"                    JOIN Documents d ON d.DocumentID=substr(a.target, 6)\n"+
		"                    WHERE a.tag=? AND a.target LIKE 'page:%' ORDER BY d.DocumentID", cat)
	if err != nil {
		return throwableHTML("CategoryPages", err)
	}
	// if (!$rows) — :55. An empty result set is falsy in PHP. Note this branch does NOT get the
	// "<ul>" wrapper: it is a <p>, and it is the tag's whole output.
	if len(rows) == 0 {
		return "<p>No pages tagged <code>" + esc(cat) + "</code> yet.</p>"
	}
	out := "<ul>" // :56
	for _, r := range rows {
		// $title = ($r['Title'] !== null && $r['Title'] !== '') ? $r['Title'] : $r['DocumentID'];  — :58
		title := r["Title"]
		if !catPagesTitleSet(title) {
			title = r["DocumentID"]
		}
		out += "<li><a href='?page=" + esc(r["DocumentID"]) + "'>" + esc(title) + "</a></li>" // :59
	}
	return out + "</ul>" // :61
}

// catPagesDescription is the description clause of CategoryPages.php:45:
//
//	($r['description'] ? " &mdash; " . self::esc($r['description']) : "")
//
// The test is PHP TRUTHINESS on the raw column value, which is why this calls annTruthy
// (annotations.go:355 — PHP counts NULL, "", "0", 0 and 0.0 as FALSE) rather than a nil-or-empty
// check. A description of "0" emits NOTHING AT ALL, em-dash included. See the header for why this
// tag and CategoryBrowse genuinely differ on that input.
func catPagesDescription(description any) string {
	if !annTruthy(description) {
		return ""
	}
	return " &mdash; " + esc(description)
}

// catPagesTitleSet is `$r['Title'] !== null && $r['Title'] !== ''` (CategoryPages.php:58).
//
// Both tests are STRICT (!==), so this is not "is the string empty". `$v !== ''` is false ONLY when
// $v is a string that is empty; an integer 0, a float 0.0 and the string "0" all PASS it and render
// as themselves. Testing phpString(v) == "" instead would agree on every value sqlite can actually
// return here — but only by accident, and it would silently invert on a boolean false, so the
// identity test is written out rather than approximated.
func catPagesTitleSet(v any) bool {
	if v == nil { // $v !== null
		return false
	}
	if s, ok := v.(string); ok && s == "" { // $v !== ''
		return false
	}
	return true
}
