package tags

// pagelist.go — ticket #324, unit go-port:tags:tag:PageList.
//
// The Go port of ONE tag: invocators/tags/dev/PageList.php — every page in the CMS as a hyperlink.
// The app serves it standalone at ?page=tags&tag=PageList, and the `pages` page's stored template
// embeds <<<PageList>>> (the in-page substitution site named by this unit's ticket;
// doc/CMS_ADDITIONS.md:24 documents the same pair — "`<<<PageList>>>` | `?page=pages` | index of
// every page").
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. The PHP is the SPEC — where the two
// disagree THIS file is wrong, and "improving" the markup or the null-handling here is a defect, not
// a fix. Two behaviours below are quirks; each is reproduced at the code that needs it and named in a
// comment, so a later reader does not "correct" one back into a divergence.
//
// ── WHAT THIS FILE ADDS, AND WHAT IT DOES NOT TOUCH ─────────────────────────────────────────────
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers, and its self-registration (the init() below). Nothing in engine.go changes — the registry
// picks this tag up because Go runs every init() in a package before any other code in it
// (engine.go:1309-1314; Register at engine.go:1355, newTag at engine.go:1393). Every identifier this
// file defines is pageList*-prefixed or PageList*-named, so it cannot collide with the sibling tag
// ports. Checked this session: no other file in the package defines any pageList*/PageList*
// identifier — the only pre-existing occurrence of the string "PageList" in congruency-go is
// engine.go:196's COVERAGE comment.
//
// (engine.go's COVERAGE header still lists PageList under "NOT PORTED (35)". That list is a
// hand-maintained COPY; its own text names PortedTags() as "the authority" (engine.go:189-192), and
// PortedTags is registry-derived (engine.go:1406-1415), so it answers correctly the moment this
// file's init() runs. Correcting the copy means editing engine.go, which this ticket forbids ("touch
// nothing else") — the same stale-copy state #312, #316 and #319 left behind for DocList, Login and
// MemoryList. It is a comment, not behaviour.)
//
// It REUSES engine.go's audited PHP primitives rather than restating them: esc
// (htmlspecialchars((string)$s, ENT_QUOTES), engine.go:599), openDB/queryRows
// (PDO::query(...)->fetchAll(PDO::FETCH_ASSOC), engine.go:1173,1241) and catchThrowable
// (engine.go:1715).
//
// It deliberately does NOT reuse a sibling UNIT's helpers — doclist.go's docListTruthy models the
// same PHP truthiness rule this tag needs at :37, and memorylist.go's memListIsEmptyString models
// the same strict `!== ''`. Those files are other tickets' deliverables, and depending on them would
// couple this unit's bytes to edits made under another unit's authority. engine.go is the shared
// floor; a sibling tag file is not. Hence pageListTruthy and pageListIsEmptyString below.
//
// ── THE TWO PHP RULES THAT DECIDE THIS TAG'S BYTES, AND WHY THEY ARE NOT THE SAME RULE ──────────
//
// PageList.php makes two per-row decisions, ONE LINE APART, using TWO DIFFERENT PHP comparison
// rules. Reading either off the other is the single easiest way to mis-port this tag:
//
//	:34  $title = ($r['Title'] !== null && $r['Title'] !== '') ? $r['Title'] : $id;   STRICT (!==)
//	:37  if ($r['Description']) { ... }                                               TRUTHY
//
// So a Title of "0" IS used as the link text (it is neither null nor the empty string), while a
// Description of "0" emits NO <p> at all (the string "0" is falsy in PHP). A port that used
// truthiness for both would drop a "0" title back to the DocumentID; one that used strictness for
// both would render a "0" description paragraph the PHP never emits. Both are rendered bytes, both
// are pinned by the quirk suite, and both are why pageListTruthy and pageListIsEmptyString are
// separate functions rather than one "is it empty" helper.
//
// ── THE DEPENDENCY, AND HOW IT DEGRADES (the ticket's "degrade IDENTICALLY") ────────────────────
//
// tools/tag_selfcheck.py's three dependency kinds (its docstring, "WHAT IT CHECKS") resolve for this
// tag to exactly one: (2) SQL TABLES against CONGRUENCY_SQLITE — a single table, `Documents`,
// created by every page migration as
//
//	Documents(DocumentID TEXT PRIMARY KEY, TemplateID INTEGER, Title TEXT, Description TEXT,
//	          ContentID INTEGER)                          (e.g. migrations/0023_bug_catalog.sql:68-74)
//
// No getenv/external db (kind 1) and no repos.forge_remote (kind 3) — this tag's SQL names no other
// table, so tag_selfcheck derives exactly that one dependency from it. The three degradation states,
// in the order GetDocument can reach them:
//
//	CONGRUENCY_SQLITE undefined -> "<p>PageList: no DB.</p>"                        (PageList.php:22)
//	the open or the query throws -> "<div class='cy-form-error'>PageList error: …</div>"      (:43)
//	table present but EMPTY      -> "<strong>0</strong> pages" + an EMPTY <ul> (NOT an
//	                                empty-state sentence — :31-40 has no `if (!$rows)` arm.
//	                                See GetDocument.)
//
// THE MISSING-TABLE CASE IS THE ONE THAT THROWS, and that is a deliberate PHP choice: PageList sets
// PDO::ERRMODE_EXCEPTION (:24), so a missing Documents raises PDOException and lands in the catch —
// it does NOT degrade silently. (Contrast MemoryList, whose DB arm swallows every throw because it
// is one optional source of two — memorylist.go:76-90. Reading this tag's degradation off that one
// would be wrong.) In practice the table is never absent and never empty: the migrations seed it
// with the page rows, which is why tag_selfcheck's empty-table WARN list names repo_docs/repos/
// code_blobs and not Documents.
//
// ── WHAT IS NOT BYTE-REPRODUCIBLE, STATED PLAINLY (the catch arm only) ──────────────────────────
//
// PHP's catch renders self::esc(get_class($e) . ': ' . $e->getMessage()) (:43) — for a missing table,
// "PDOException: SQLSTATE[HY000]: General error: 1 no such table: Documents".
//
// NOTE THE get_class PREFIX. It is NOT optional decoration and it is NOT what every sibling does:
// DocList's and TreeView's catches print getMessage() ALONE (doclist.go:304-306, engine.go:1747-1748)
// while PageList's and MemoryList's print "Class: message" (memorylist.go:362-368). Borrowing a
// sibling's frame here would be a byte diff on the error path.
//
// pageListError reproduces the CLASS exactly and the message not at all, and the reason it can do the
// first is that the class is DETERMINATE here: every throw reachable inside PageList's try comes out
// of PDO — the constructor (:23), setAttribute (:24), query or fetchAll (:25) — and PDO with
// ERRMODE_EXCEPTION throws PDOException, as does `new PDO` on an unopenable DSN regardless of errmode.
// The string-building at :26-40 cannot throw (the columns are TEXT, so no array reaches esc()). So
// "PDOException" is not a guess about which of several classes it might be; it is the only one this
// arm can carry. THAT STRING IS READ OFF PDO's DOCUMENTED SEMANTICS, NOT MEASURED HERE: no php binary
// exists in this worktree to run it against (see "THE GATE"), and it is flagged again at
// pageListError rather than hidden.
//
// The MESSAGE inside is a Go database/sql error, which has no SQLSTATE text, so the FRAME and the
// class are byte-identical and the message is not, and is not claimed to be. This is the package's
// standing, documented limitation (annotatehandler.go:134-142), not a new one, and it is unreachable
// on any gate surface whose db actually has the Documents table.
//
// One related PHP behaviour is worth naming because it decides WHICH branch a missing db file takes:
// PHP's `new PDO('sqlite:<path>')` CREATES an empty file when the path does not exist (engine.go's
// header, divergence 2), so PHP proceeds and then throws on the missing TABLE. openDB instead returns
// an error for an absent file (engine.go:1177-1179). Both land in the catch arm and emit the same
// frame with the same class — the branch agrees, only the message inside differs, as above.
//
// The deferred catchThrowable guards a Go panic and emits the "<div class='cy-form-error'>PageList
// error: …</div>" frame WITHOUT the class prefix, because a Go panic has no exception class. That is
// the same standing limitation and it only fires when something is already broken.
//
// ── THE GATE — WHAT THE TICKET ASKS FOR, WHAT IS RUNNABLE HERE, AND WHAT WAS RUN ────────────────
//
// The ticket's gate is two byte-diffs, PHP:8899 vs Go:8900, over the same db:
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=PageList') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=PageList')
//	for p in pages; do
//	  diff <(curl -s "http://127.0.0.1:8899/?page=$p") <(curl -s "http://127.0.0.1:8900/?page=$p") \
//	    || echo "DIVERGES: $p"; done
//
// NEITHER CAN BE RUN FROM THIS WORKTREE, and both are additionally confounded on their own terms.
// Stating this rather than settling on a green-looking diff is what the ticket asks for — "if you
// cannot make a diff here run against THIS unit, say so on the ticket rather than settling on a diff
// that would be empty even with the unit unimplemented".
//
// WHY IT CANNOT BE RUN HERE — three independent walls, each checked this session:
//
//	NO PHP.  The ticket names tooling/congruencey-harness/php/php as allowed. That path does not
//	         exist — the whole php/ directory is absent — and `php` is not on PATH. It is
//	         PROVISIONED, not committed, BY DESIGN: provision_php.py's docstring opens "The mono ships
//	         NO binaries (they don't belong in git); instead this python recipe places a php binary
//	         into <mono>/<paths.php> (default tooling/congruencey-harness/php/php)"
//	         (provision_php.py:4-6), and .gitignore:10 ignores that directory outright.
//	NO DB.   Both engines must read the SAME congruency.sqlite (configure.php:42 puts it at
//	         checkouts/current/state/congruency.sqlite — "state is a sibling of the app root", as its
//	         own inline comment says). That file is git-ignored too (.gitignore:11, plus *.sqlite at
//	         .gitignore:7), and a find for *.sqlite and *.db across the whole worktree returns
//	         NOTHING. Without the shared db there is no "same database" for a diff to be over — and
//	         for THIS tag the db is not incidental: Documents IS its entire input.
//	NO GO.   A `go` binary exists at /opt/homebrew/bin/go — unlike the earlier tags in this layer,
//	         whose headers record it as absent — but every invocation of it is refused by this
//	         session's permission layer before it starts. `go build ./...` was attempted twice,
//	         plainly and with the sandbox override, and `gofmt -l` once; all three were denied. So the
//	         :8900 side of every diff above cannot be built, let alone served. The binary existing and
//	         being unrunnable are easy to confuse, hence the detail: do not conclude from `which go`
//	         that this file was compiled.
//
// WHY BOTH DIFFS ARE CONFOUNDED EVEN WITH THE SERVERS UP — each would be exactly as non-empty with
// this file deleted, so neither measures this unit:
//
//	diff 1  ?page=tags&tag=PageList   The PHP returns a FULL CMS page; the Go server does not
//	                                  reproduce the page frame and says so itself (server.go:39-43,
//	                                  62-66: "NOT claimed: that the page's BYTES match PHP … larger by
//	                                  a constant ~6.2 KB of CMS chrome"). The tag's own bytes are a
//	                                  SLICE of that page (equivalence_test.go:28-33).
//	diff 2  ?page=pages               server.go's handlePage routes EVERY page key except "tags" to
//	                                  handleCatalogPage, the table-list seam that never invokes the
//	                                  tag engine (server.go:727-735, 831-833). So ?page=pages on the Go
//	                                  server cannot reach PageList at all. Wiring it is an edit to
//	                                  server.go, which this ticket forbids ("touch nothing else").
//
// THE REAL GATE, which exists precisely because of diff 1's confound, is #282's harness — and #323
// settled that this, not diff 1, is where a tag-unit gate belongs:
//
//	cd congruency-go && go test ./tags/ -run TestTagEquivalence/PageList -v
//
// It cuts the tag's own bytes out of the live PHP page with TagList.php's own anchors and compares
// them to RenderTag's, with a stability sandwich against concurrent writers. It needs the live 8899
// and the shared state db; absent either it SKIPS (its four guards, equivalence_test.go:115-120). It
// requires NO edit to run this tag — it sweeps Scan(TAGS_DIR) and measures whatever IsPorted reports,
// so registering PageList in the init() below is the whole wiring. That is the command to run on a
// host that has the server, and it is the measurement this unit's claim should ultimately rest on.
//
// ONE CAVEAT SPECIFIC TO THIS TAG, which whoever runs that harness must know: PageList reads the
// Documents table, which the pair_loop agents and the migrations both write. It is therefore VOLATILE
// in exactly the way the harness's php1/go/php2 sandwich exists to absorb — a page added between the
// two PHP fetches reports VOLATILE, not a divergence. That is a data difference, not an engine
// difference (#227's header).
//
// THIS GO CODE WAS NOT COMPILED OR EXECUTED, AND THAT IS A REAL GAP IN THIS DELIVERABLE. It must be
// said plainly rather than left for the reader to discover. The usual floor ("RUN your own work
// before reporting done") could not be met here: the Go below is reviewed, not run, and a compile
// error or a runtime panic in it would be a live defect that no step in this session could have
// caught. The FIRST thing to do with this file is:
//
//	cd congruency-go && go build ./... && go vet ./tags/
//
// WHAT WAS ACTUALLY RUN THIS SESSION — three things, and NONE of them EXECUTES this file's Go:
//
//  1. A Python transliteration of PageList.php's get_document(), modelling PHP's truthiness, the two
//     strict (!==) guards, the (string) casts esc() performs, and count(). A 25-case quirk suite over
//     it passed 25/25 and CONFIRMED, as behaviour rather than as my assertion, each quirk documented
//     below:
//
//	the two rules that disagree  a Title of "0" IS the link text, while a Description of "0"
//	                             emits NO <p> and leaves "</span></li>" butted together.
//	the Title fallback (strict)  NULL and "" fall back to the DocumentID; " " (one space), "X"
//	                             and the int 0 do NOT.
//	the Description test (truthy) NULL, "" and the int 0 emit no <p>; " " and "00" do emit one.
//	the empty state              0 rows render "<strong>0</strong> pages" and an EMPTY <ul>,
//	                             with no sentence; 3 rows count 3.
//	the escape/recursion guard   a stored "<<<PageList>>>" in EITHER a Title or a Description
//	                             comes back "&lt;&lt;&lt;PageList&gt;&gt;&gt;" with no raw "<<<"
//	                             surviving; "it's" escapes to "&#039;" (PHP's spelling, not Go's
//	                             html pkg's "&#39;"); "a&b" to "a&amp;b".
//	degradation                  the no-DB sentence exactly; the class-prefixed error div
//	                             exactly; and the error MESSAGE is esc'd, so a "<b>" inside it
//	                             cannot re-trigger the engine.
//	the <li> shape               exactly two leading spaces, and no space after "</a>".
//
//  2. A MECHANICAL LITERAL DIFF of the markup — the highest byte-risk part of any port and the one
//     thing eyeballing reliably misses. It extracts every string literal from PageList.php and from
//     the non-comment lines of THIS file and compares them: all of the PHP's markup literals appear
//     here VERBATIM, including the four concatenated <style> fragments, the two leading spaces on the
//     <li>, and every "\n". The one literal Go must split around strconv — :30's interpolated
//     "<strong>" . count($rows) . "</strong> pages" — is reconstructed with concrete values and
//     compared to the PHP's concatenation of the SAME values. All byte-identical.
//
//  3. A DIFFERENTIAL FUZZ of the two renders. Checks 1 and 2 both test my reading of the PHP; this
//     one tests THE TRANSCRIPTION — it writes the tag out twice from two different sources (one from
//     PageList.php line by line, one from THIS file's GetDocument statement by statement, mirroring
//     pageListTruthy/pageListIsEmptyString/esc) and diffs the bytes. Over 20,000 random row-sets of
//     0-4 rows drawn from a 26-value corpus (NULL, "", "0", "00", " ", ints, floats, bools, "it's",
//     "a&b", "<b>", "<<<PageList>>>", embedded newlines, "café", …) and then EXHAUSTIVELY over all
//     7,436 single-row (DocumentID × Title × Description) combinations of that corpus: 20000/20000
//     and 7436/7436 byte-identical.
//
//     ITS WEAKNESS, STATED RATHER THAN LEFT TO BE FOUND: the go-derived side is hand-transliterated
//     from the Go by the same author, so a MISREADING of the Go could be duplicated on both sides.
//     It catches a swapped concatenation, a dropped space, or a truthy-vs-strict mix-up; it is not a
//     substitute for `go build`, and it does not execute one line of the Go below.
//
// None of the three is the PHP interpreter (no PHP exists here to run), none EXECUTES this file's Go,
// and none is the gate. Checks 1 and 2 raise confidence that the SPEC ENCODED BELOW is the spec
// PageList.php actually implements; check 3 raises confidence that the Go expresses that spec. All
// three are silent on whether the Go COMPILES.
//
// SO, PLAINLY: this unit is PORTED and its spec is CHECKED, but the Go is UNBUILT and the tag is NOT
// byte-measured against PHP. The gate is UNMET. The two commands that would move it — the build
// above, then the #282 harness — are both named here, and both need a host this session did not have.

import (
	"strconv"
	"strings"
)

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there, and
// TestTagEquivalence starts measuring this tag with no edit either.
func init() {
	Register("PageList", func(e *Engine, a *TagArguments) Tag { return &PageListTag{e: e, args: a} })
}

// PageListTag is PageList (PageList.php:14-46).
//
// args mirrors the PHP constructor's $arguments (:17), which the PHP stores in a private field and
// NEVER reads — the tag takes no TAG arguments and no $_GET either (it is the only ported tag with NO
// input at all beyond the DB), and the `pages` template invokes it bare as <<<PageList>>>. A nil
// *TagArguments (what TagList.php:67's `new $sel(null)` passes, the shape the ?page=tags&tag=PageList
// gate takes) is therefore stored and ignored, which is exactly what the PHP does with the NULL it is
// handed.
//
// Like DocList and MemoryList, and unlike CategoryView, this constructor CANNOT throw on nil args:
// :17 only assigns the field, it never dereferences it. So the gallery render is not an error path —
// it runs the tag's real query. There is no ctorThrew here and there must not be one.
type PageListTag struct {
	e    *Engine
	args *TagArguments
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PHP semantics this tag needs. Deliberately unit-local — see the file header.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// pageListTruthy is PHP's truthiness test on a DB value — PageList.php:37's `if ($r['Description'])`.
//
// IT IS NOT "not nil" AND IT IS NOT "not empty": PHP counts 0, 0.0, "", "0" and NULL as FALSE. The
// "0"-is-false arm is the one that carries this tag's sharpest quirk — a page whose Description is
// literally the one-character string "0" emits NO description <p> — and Description is a TEXT column,
// so "0" is exactly the shape that value takes. The numeric arms are here because sqlite is
// dynamically typed and will hand back an int64 for an INTEGER stored in a TEXT column.
//
// Contrast pageListIsEmptyString below, which models :34's STRICT test on the very next line. They
// are different rules and they disagree on "0"; see the file header.
func pageListTruthy(v any) bool {
	switch x := v.(type) {
	case nil:
		return false
	case bool:
		return x
	case int:
		return x != 0
	case int32:
		return x != 0
	case int64:
		return x != 0
	case float32:
		return x != 0
	case float64:
		return x != 0
	case string:
		return x != "" && x != "0"
	case []byte:
		s := string(x)
		return s != "" && s != "0"
	default:
		return true // every object is truthy in PHP
	}
}

// pageListIsEmptyString is PHP's `$v === ''` — the second half of :34's guard.
//
// `===` requires the TYPES to match, so it is true only when $v is ALSO a string and is empty. An
// int 0 and a float 0.0 both FAIL this test and therefore pass :34's guard, so a Title of 0 renders
// as "0" and does NOT fall back to the DocumentID — the opposite of what :37's truthiness would say
// about the same value. That is pinned by the quirk suite precisely because it reads backwards.
//
// phpString would NOT do here: it would coerce an int64 0 to "0" and report an empty-string match the
// PHP's `===` denies.
func pageListIsEmptyString(v any) bool {
	s, ok := v.(string)
	return ok && s == ""
}

// pageListError is the catch(\Throwable) body (PageList.php:42-44):
//
//	return "<div class='cy-form-error'>PageList error: "
//	     . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</div>";
//
// The class is passed in rather than hardcoded at the call sites so that the "Class: message" shape —
// the thing that distinguishes this catch from DocList's getMessage()-only one — lives in exactly one
// place. Every caller passes "PDOException", because that is the only class this arm can carry; the
// file header sets out why that is determinate rather than a guess, and that it is read off PDO's
// documented semantics rather than measured (there is no php here to measure it with).
//
// It is spelled out rather than left to catchThrowable because the PHP reaches this branch by
// THROWING (PDO::ERRMODE_EXCEPTION, :24) where Go's database/sql returns an error — same branch,
// different mechanism. catchThrowable still guards the deferred path and produces the same wrapper
// for a real panic, minus the class prefix a Go panic does not have.
func pageListError(class, message string) string {
	return "<div class='cy-form-error'>PageList error: " + esc(class+": "+message) + "</div>"
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// GetDocument — PageList::get_document() (PageList.php:20-45).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// GetDocument is PageList::get_document() (PageList.php:20-45) — every row of Documents as a link.
//
// THERE IS NO EMPTY-STATE ARM, AND ADDING ONE WOULD BE A DIVERGENCE. :30-40 writes the count line,
// opens the <ul>, loops, and closes the <ul> unconditionally — an empty Documents renders
// "<strong>0</strong> pages" and then "<ul class='pglist'>\n</ul>\n" with nothing between, and no
// sentence. The sibling RepoDocs DOES have such an arm (RepoDocs.php:55) and PageList, like DocList,
// pointedly does not.
//
// The whole body is the PHP's try (:21) and the order is the PHP's order: the defined() check (:22)
// precedes the open (:23), which precedes the query (:25). This tag reads NO $_GET at all, so there
// is no input to interleave with any of it.
func (t *PageListTag) GetDocument() (out string) {
	defer catchThrowable(&out, "PageList")

	// :22 — !defined('CONGRUENCY_SQLITE'). The same mapping every sibling port uses
	// (doclist.go:338, engine.go:1742-1744).
	if t.e.cfg.SQLite == "" {
		return "<p>PageList: no DB.</p>"
	}

	// :23-24 — new PDO('sqlite:'.CONGRUENCY_SQLITE) + ERRMODE_EXCEPTION. PHP reaches its catch by
	// throwing out of the PDO constructor; an unopenable db lands on the same branch here. See the
	// file header on why the class is PDOException and the message is not reproducible.
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return pageListError("PDOException", err.Error())
	}
	defer db.Close()

	// :25 — the query, verbatim, ORDER BY included.
	//
	// ORDER BY DocumentID is sqlite's default BINARY collation on a TEXT PRIMARY KEY — a BYTE
	// ordering, not a locale-aware one. Both engines run the same SQL over the same file, so both see
	// the same order; the port must not "help" by sorting in Go, which would apply a different rule.
	rows, err := queryRows(db, "SELECT DocumentID, Title, Description FROM Documents ORDER BY DocumentID")
	if err != nil {
		return pageListError("PDOException", err.Error())
	}

	var b strings.Builder

	// :26-29 — the <style> block, verbatim across its four concatenated fragments. The trailing "\n"
	// is inside the PHP's double-quoted string and is a rendered byte.
	b.WriteString("<style>.pglist{display:grid;gap:.5rem;list-style:none;padding:0}" +
		".pglist li{border:1px solid #d8d2c4;border-left:5px solid #8a5a1a;border-radius:6px;padding:.5rem .8rem;background:#fffdf8}" +
		".pglist a{font-size:1.05rem}.pglist .id{font:.72rem/1 monospace;color:#777;margin-left:.4rem}" +
		".pglist p{margin:.2rem 0 0;font-size:.85rem;color:#555}</style>\n")

	// :30 — count($rows) is an INT concatenated into the string, so it is NOT escaped and must not be:
	// strconv, not esc.
	b.WriteString("<p style='font-size:.85rem;color:#555'><strong>" + strconv.Itoa(len(rows)) +
		"</strong> pages</p>\n")

	// :31
	b.WriteString("<ul class='pglist'>\n")

	for _, r := range rows {
		// :33 — $id = $r['DocumentID']. NOT cast: the column's NATIVE value flows on and esc() does
		// the (string) cast at each of the two points that emit it (:35, :36). DocumentID is the TEXT
		// PRIMARY KEY, so it is a string in practice and can be neither NULL nor absent.
		id := r["DocumentID"]

		// :34 — $title = ($r['Title'] !== null && $r['Title'] !== '') ? $r['Title'] : $id;
		//
		// BOTH tests are STRICT, and $title keeps whichever NATIVE value wins — it is not flattened
		// to a string here, because esc() at :35 is what casts it. Only NULL and the actual empty
		// string fall back to the id: a Title of "0", of " " (one space), or of the int 0 is KEPT.
		// Do not rewrite this as a truthiness test; :37 one line down is the truthy one, and they
		// disagree. See the file header.
		title := id
		if r["Title"] != nil && !pageListIsEmptyString(r["Title"]) {
			title = r["Title"]
		}

		// :35-36 — the two leading spaces are the PHP's indentation and are rendered bytes. There is
		// no space between the </a> and the <span>.
		//
		// EVERY value is escaped exactly where the PHP escapes it. This render flows back through
		// execute_all_tags, so a stored "<<<PageList>>>" — a page Title or Description that names a
		// tag, which this CMS's own documentation pages plausibly hold — must come back
		// "&lt;&lt;&lt;PageList&gt;&gt;&gt;" and stay inert (engine.go's header, mechanism 2). Do not
		// remove an esc() call.
		b.WriteString("  <li><a href='?page=" + esc(id) + "'>" + esc(title) + "</a>" +
			"<span class='id'>?page=" + esc(id) + "</span>")

		// :37 — `if ($r['Description'])` is TRUTHY, not strict: NULL, "" and the string "0" each emit
		// NO <p> at all. Note there is no whitespace around this <p> — it butts directly against the
		// </span> before it and the </li> after it.
		if pageListTruthy(r["Description"]) {
			b.WriteString("<p>" + esc(r["Description"]) + "</p>")
		}

		// :38
		b.WriteString("</li>\n")
	}

	// :40
	b.WriteString("</ul>\n")
	return b.String() // :41
}
