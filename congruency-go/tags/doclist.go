package tags

// doclist.go — ticket #312, unit go-port:tags:tag:DocList.
//
// The Go port of ONE tag: invocators/tags/dev/DocList.php — the CMS browsing its own documentation.
// The app serves it standalone at ?page=tags&tag=DocList, and the `docs` page's stored template
// embeds <<<DocList>>> (the in-page substitution site named by this unit's ticket).
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. The PHP is the SPEC — where the two
// disagree THIS file is wrong, and "improving" the markup or the markdown subset here is a defect,
// not a fix. Several behaviours below are quirks; each is reproduced at the code that needs it and
// named in a comment, so that a later reader does not "correct" one back into a divergence.
//
// ── WHAT THIS FILE ADDS, AND WHAT IT DOES NOT TOUCH ─────────────────────────────────────────────
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers, and its self-registration (the init() below). Nothing in engine.go changes — the registry
// picks this tag up because Go runs every init() in a package before any other code in it
// (engine.go:1309-1314; Register at engine.go:1355, newTag at engine.go:1393). Every identifier this
// file defines is docList*-prefixed or DocList*-named, so it cannot collide with the sibling tag
// ports.
//
// It REUSES engine.go's audited PHP primitives rather than restating them: esc
// (htmlspecialchars($s, ENT_QUOTES), engine.go:599), phpString (PHP's (string) cast over a PDO row's
// native types — NULL becomes "", engine.go:497), phpTrim (trim()'s charlist " \t\n\r\0\x0B",
// engine.go:630), phpSubstr (BYTE-counting substr(), engine.go:483), toInt (PHP's (int) cast,
// engine.go:559), openDB/queryRows (PDO::query(...)->fetchAll(PDO::FETCH_ASSOC), engine.go:1173,1241)
// and catchThrowable (the catch(\Throwable) block, engine.go:1715).
//
// It deliberately does NOT reuse a sibling UNIT's helpers (annotations.go's annTruthy /
// annIdenticalString model the same two PHP rules): those files are other tickets' deliverables, and
// depending on them would couple this unit's bytes to edits made under another unit's authority.
// engine.go is the shared floor; a sibling tag file is not. Hence docListTruthy and
// docListIdenticalString below.
//
// ── SIBLING TAGS THAT LOOK LIKE THIS ONE AND ARE NOT ────────────────────────────────────────────
//
// RepoDocs.php carries a markdown()/inline() pair that is character-identical to DocList's, and
// SourceList.php carries the same ADMIN_GATED constant. They are DIFFERENT tags with DIFFERENT
// tables, and two of their details actually differ:
//
//   - RepoDocs keys its markdown branch on kind === 'md' (RepoDocs.php:84); DocList keys its on
//     kind === 'markdown' (DocList.php:85). The vocabularies come from different writers —
//     tools/ingest_self.py's LANG map (:39) writes "markdown"/"text" into doc_blobs.kind.
//   - RepoDocs reads repo_docs; DocList reads doc_blobs/doc_refs.
//
// So the markdown helpers here are docList*-prefixed and MUST NOT be merged with a future RepoDocs
// port's. If they are ever unified, it has to be a deliberate ticket that proves both tags' bytes,
// not a drive-by dedup.
//
// ── THE DEPENDENCY, AND HOW IT DEGRADES (the ticket's "degrade IDENTICALLY") ────────────────────
//
// tools/tag_selfcheck.py's three dependency kinds (its docstring, "WHAT IT CHECKS") resolve for this
// tag to exactly one: SQL TABLES against CONGRUENCY_SQLITE — doc_refs and doc_blobs, created by
// tools/ingest_self.py:45-46 as
//
//	doc_blobs(hash TEXT PRIMARY KEY, kind TEXT, bytes INTEGER, body TEXT)
//	doc_refs (hash TEXT, path TEXT, commit_sha TEXT, ts REAL, is_current INTEGER DEFAULT 0)
//
// No getenv/external db, no repos.forge_remote. The four degradation states, in the order
// GetDocument can reach them:
//
//	CONGRUENCY_SQLITE undefined -> "<p>DocList: no DB.</p>"                       (DocList.php:36)
//	a query throws              -> "<div class='cy-form-error'>DocList error: …</div>"  (:43)
//	tables present but EMPTY    -> the index intro + an EMPTY <ul> (NOT an empty-state
//	                               sentence — DocList.php:51-56 has no `if (!$rows)` arm,
//	                               unlike RepoDocs.php:55. See docListIndex.)
//	?doc=<unknown hash>         -> "<p>No such doc blob <code>…</code>. …</p>"     (:63)
//
// THE MISSING-TABLE CASE IS THE ONE THAT THROWS, and that is a deliberate PHP choice: DocList sets
// PDO::ERRMODE_EXCEPTION (:38), so a missing doc_refs raises PDOException and lands in the catch —
// it does NOT degrade silently. (Contrast the store DAOs, which set ERRMODE_SILENT and return "";
// see categoryview.go's header. Reading this tag's degradation off that one would be wrong.)
//
// ── WHAT IS NOT BYTE-REPRODUCIBLE, STATED PLAINLY (the catch arm only) ──────────────────────────
//
// PHP's catch renders self::esc($e->getMessage()) (:43) — for a missing table, PDO's
// "SQLSTATE[HY000]: General error: 1 no such table: doc_refs". A Go database/sql error has no
// SQLSTATE text, so docListError emits the Go driver's message inside the IDENTICAL
// "<div class='cy-form-error'>DocList error: …</div>" frame. The FRAME is byte-identical; the
// message inside it is not, and is not claimed to be. This is the package's standing, documented
// limitation (annotatehandler.go:134-142), not a new one, and it is unreachable on any gate surface
// whose db actually has the two tables.
//
// One related PHP behaviour is worth naming because it decides WHICH branch a missing db file takes:
// PHP's `new PDO('sqlite:<path>')` CREATES an empty file when the path does not exist (engine.go's
// header, divergence 2), so PHP proceeds and then throws on the missing TABLE. openDB instead
// returns an error for an absent file (engine.go:1177-1179). Both land in the catch arm and emit the
// same frame — the branch agrees, only the message inside differs, as above.
//
// ── THE GATE — WHAT THE TICKET ASKS FOR, WHAT IS RUNNABLE HERE, AND WHAT WAS RUN ────────────────
//
// The ticket's gate is two byte-diffs, PHP:8899 vs Go:8900, over the same db. NEITHER CAN BE RUN
// FROM THIS WORKTREE, and both are additionally confounded on their own terms. Stating this rather
// than settling on a green-looking diff is what the ticket asks for — "if you cannot make a diff
// here run against THIS unit, say so on the ticket rather than settling on a diff that would be
// empty even with the unit unimplemented".
//
// WHY IT CANNOT BE RUN HERE. This worktree has no PHP and no database, and both absences are by
// design, not accident: tooling/congruencey-harness/.gitignore ignores `php/` and `*.sqlite`, so the
// static PHP 8.3 binary the harness documents at php/php (its README, "Pieces") and the seeded
// congruency.sqlite are both untracked. Checked this session: no `php` on PATH and no php binary,
// .sqlite or .db file anywhere in the tree. equivalence_test.go's header records this same wall as
// the reason #226 landed 10 tags "ported-not-measured" (:9-13). The live server's db, at
// checkouts/current/state/congruency.sqlite under the MAIN checkout, is outside this worktree.
//
// WHY BOTH DIFFS ARE CONFOUNDED EVEN WITH THE SERVERS UP — each would be exactly as non-empty with
// this file deleted, so neither measures this unit:
//
//	diff 1  ?page=tags&tag=DocList   The PHP returns a FULL CMS page; the Go server does not
//	                                 reproduce the page frame and says so itself (server.go:39-43,
//	                                 62-66: "NOT claimed: that the page's BYTES match PHP … larger
//	                                 by a constant ~6.2 KB of CMS chrome"). The tag's own bytes are a
//	                                 SLICE of that page (equivalence_test.go:28-33).
//	diff 2  ?page=docs               server.go's handlePage routes EVERY page key except "tags" to
//	                                 handleCatalogPage, the table-list seam that never invokes the
//	                                 tag engine (server.go:727-735, 831-833). So ?page=docs on the Go
//	                                 server cannot reach DocList at all. Wiring it is an edit to
//	                                 server.go, which this ticket forbids ("touch nothing else").
//
// THE REAL GATE, which exists precisely because of diff 1's confound, is #282's harness:
//
//	cd congruency-go && go test ./tags/ -run TestTagEquivalence/DocList -v
//
// It cuts the tag's own bytes out of the live PHP page with TagList.php's own anchors and compares
// them to RenderTag's, with a stability sandwich against concurrent writers. It needs the live 8899
// and the shared state db; absent either it SKIPS (its four guards, :115-120). It requires NO edit
// to run this tag — it sweeps Scan(TAGS_DIR) and measures whatever IsPorted reports, so registering
// DocList in the init() below is the whole wiring. That is the command to run on a host that has the
// server, and it is the measurement this unit's claim should ultimately rest on.
//
// THIS GO CODE WAS NOT COMPILED OR EXECUTED, AND THAT IS A REAL GAP IN THIS DELIVERABLE. It must be
// said plainly rather than left for the reader to discover. The sandbox this file was written in
// permits no `go` invocation at all — `go build`, `go vet`, `go test` and even `go version` and
// `gofmt` are each refused before they start. So the usual floor ("RUN your own work before
// reporting done") could not be met here: the Go below is reviewed, not run, and a compile error or
// a runtime panic in it would be a live defect that no step in this session could have caught. The
// FIRST thing to do with this file is:
//
//	cd congruency-go && go build ./... && go vet ./tags/
//
// WHAT WAS ACTUALLY RUN THIS SESSION — one thing, and it tests my READING OF THE PHP, not the Go:
//
//	A Python transliteration of DocList.php's markdown()/inline(), with PCRE's \s spelled out
//	explicitly (as it is in the Go below) and PHP's trim() charlist modelled exactly. Two runs:
//
//	  - A 14-case quirk suite. It CONFIRMED, as behaviour rather than as my assertion, each quirk
//	    documented at docListMarkdown and docListInline: the indented ``` inside a fence closes it;
//	    consecutive 4-space lines emit SEPARATE <pre><code> blocks; a 4-space-only line emits an
//	    EMPTY block instead of ending the paragraph; a form-feed-only line is NOT blank and becomes
//	    paragraph text; "#Foo" and "####### x" are paragraphs, not headings; "<<<TitleTag>>>" comes
//	    out "&lt;&lt;&lt;TitleTag&gt;&gt;&gt;"; `mysql_*` survives the italic pass; "**a** and **b**"
//	    makes two <strong>s; "* item" is not an <em>; an unclosed fence still emits its block.
//	  - The real corpus this tag would serve through markdown(): the 10 .md files under the app root,
//	    which are exactly the blobs ingest_self.py stores with kind='markdown' (its LANG map, :39).
//	    All 10 rendered without error and between them exercised every structural branch — heading
//	    10, para 10, pre 4, code-span 10, bold 9, em 5, link 1 — and 4 of them carry a literal
//	    <<<Tag>>> that stayed escaped, so the escape-first guard is load-bearing on real data rather
//	    than a theoretical concern. (The 5 doc/*.txt blobs are kind='text' and DocList renders them
//	    through the <pre> arm, never markdown(); they were pushed through markdown() as extra input
//	    and also survived, but that is a stress test of a path they cannot take in production.)
//
//	It is NOT the PHP interpreter (no PHP exists here to run), it is NOT this file's Go, and it is
//	NOT the gate. It raises confidence that the SPEC ENCODED BELOW is the spec DocList.php actually
//	implements; it says nothing about whether the Go transcribes it correctly.
//
// SO, PLAINLY: this unit is PORTED and its spec is CHECKED, but the Go is UNBUILT and the tag is
// NOT byte-measured against PHP. The gate is UNMET. The two commands that would move it — the build
// above, then the #282 harness — are both named here, and both need a host this session did not
// have.

import (
	"database/sql"
	"regexp"
	"strconv"
	"strings"
)

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there,
// and TestTagEquivalence starts measuring this tag with no edit either.
func init() {
	Register("DocList", func(e *Engine, a *TagArguments) Tag { return &DocListTag{e: e, args: a} })
}

// DocListTag is DocList (DocList.php:17-137).
//
// args mirrors the PHP constructor's $arguments (DocList.php:22), which the PHP stores in a private
// field and NEVER reads — the tag takes no TAG arguments (its inputs are $_GET), and the `docs`
// template invokes it bare as <<<DocList>>>. A nil *TagArguments (what TagList.php:67's
// `new $sel(null)` passes, the shape the ?page=tags&tag=DocList gate takes) is therefore stored and
// ignored, which is exactly what the PHP does with the NULL it is handed.
//
// UNLIKE CategoryView (categoryview.go), this constructor CANNOT throw on nil args: DocList.php:22
// only assigns the field, it never dereferences it. So the gallery render is not an error path — it
// runs the tag's real index query. There is no ctorThrew here and there must not be one.
type DocListTag struct {
	e    *Engine
	args *TagArguments
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The gate (DocList.php:19, 25-30) — dead code today, ported as dead code.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// docListAdminGated is `const ADMIN_GATED = false` (DocList.php:19), whose own comment reads
// "TEMP: browse without login while the browser is being finished; set true to re-gate".
// doc/CMS_ADDITIONS.md:101-102 documents the same state ("currently ungated (ADMIN_GATED=false)
// during shakeout"). SourceList.php:21 carries an independent copy of this constant; the two are
// separate units and neither reads the other.
//
// It is false, so docListGate's deny branch is UNREACHABLE — the render is never gated.
const docListAdminGated = false

// docListDenyHTML is gate()'s deny return (DocList.php:27), verbatim, including the "\n" between the
// sentence and the tag.
//
// The trailing "<<<Login>>>" is a LIVE tag invocation, not text: the deny string flows back through
// execute_all_tags, which substitutes the Login tag into it. That is the PHP's intent (an admin area
// that renders its own login form) and it is why this string is NOT escaped on the way out.
const docListDenyHTML = "<p><strong>Administrator area.</strong> Please log in to browse the documentation.</p>\n<<<Login>>>"

// docListGate is DocList::gate() (DocList.php:25-30):
//
//	if (self::ADMIN_GATED && (!class_exists('UserPrivilegeSet') || !UserPrivilegeSet::logged_in())) {
//	    return "<p><strong>Administrator area.</strong> …</p>\n<<<Login>>>";
//	}
//	return null;
//
// ok=false is the PHP's `return null`, which get_document() tests with `!== null` (:34).
//
// THE SECOND OPERAND HAS NO GO COUNTERPART, AND DOES NOT NEED ONE. PHP's `&&` short-circuits, so
// with ADMIN_GATED false the class_exists/logged_in probe is NEVER EVALUATED; Go's `&&` short-
// circuits identically, and a `if false` guard evaluates nothing at all. The tags package has no
// UserPrivilegeSet — the session probe lives on the SERVER side as Authorizer.LoggedIn
// (db.go:770-773, server.go:107, 381) and is not reachable from a tag. So flipping this constant to
// true is NOT a one-character change: it needs a real UserPrivilegeSet::logged_in() port threaded
// into the engine, and it would need its own ticket. Inventing one here to fill a dead branch would
// be guessing at bytes the PHP cannot currently emit.
func docListGate() (string, bool) {
	if docListAdminGated {
		return docListDenyHTML, true
	}
	return "", false
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PHP semantics this tag needs. Deliberately unit-local — see the file header.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// docListTruthy is PHP's truthiness test on a DB value — DocList.php:80's `$h['cur'] ? "*" : ""`,
// where cur is MAX(is_current) over doc_refs.
//
// It is NOT "not nil": PHP counts 0, 0.0, "", "0" and NULL as FALSE. is_current is an INTEGER column
// (ingest_self.py:46) whose 0 rows are exactly the non-current refs, so the 0-is-false arm is the one
// that carries the common case — a historical version gets NO "*".
func docListTruthy(v any) bool {
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

// docListIdenticalString is PHP's `$v === $s` where $s is a known string — DocList.php:81's
// `$h['hash'] === $hash` and :85's `$blob['kind'] === 'markdown'`.
//
// `===` requires the TYPES to match, so it is true only when $v is ALSO a string and equal. phpString
// would NOT do: it would coerce an int64 hash column to "123…" and report a match the PHP's `===`
// denies. Both columns are declared TEXT (ingest_self.py:45) so PDO hands back strings and the
// coercion never bites in practice — modelling `===` exactly is what keeps that a fact about the
// schema rather than an assumption in this file.
func docListIdenticalString(v any, s string) bool {
	got, ok := v.(string)
	return ok && got == s
}

// docListError is the catch(\Throwable) body (DocList.php:42-44):
//
//	return "<div class='cy-form-error'>DocList error: " . self::esc($e->getMessage()) . "</div>";
//
// It is spelled out rather than left to catchThrowable because the PHP reaches this branch by
// THROWING (PDO::ERRMODE_EXCEPTION, :38) where Go's database/sql returns an error — same branch,
// different mechanism. catchThrowable still guards the deferred path and produces the identical
// wrapper for a real panic. See the file header on what is and is not byte-reproducible here.
func docListError(err error) string {
	return "<div class='cy-form-error'>DocList error: " + esc(err.Error()) + "</div>"
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// GetDocument — DocList::get_document() (DocList.php:32-45).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// GetDocument is DocList::get_document() (DocList.php:32-45).
//
// The order below is the PHP's order and it is load-bearing: gate() runs OUTSIDE the try (:33-34),
// then the try opens the DB (:36-38) BEFORE it reads $_GET (:39). So an unopenable db yields the
// error div whether or not ?doc= was supplied — the doc parameter never gets a chance to matter.
//
// `$hash = isset($_GET['doc']) ? trim((string) $_GET['doc']) : ''` (:39) is getStr + phpTrim.
// getStr already collapses the ternary's two arms correctly: it returns "" for an unset key
// (engine.go:910-916), which is the same "" the else-arm supplies, and both then fail the `!== ''`
// test at :40 and fall through to the index. The isset/empty distinction that several other tags
// branch on (engine.go:918-921) therefore cannot be observed here — ?doc= and no ?doc at all render
// the identical index — and that is the PHP's behaviour, because trim("") is "".
//
// phpTrim, not strings.TrimSpace: PHP's trim() charlist is " \t\n\r\0\x0B" — it strips NUL and
// vertical tab but NOT form feed, and it does not touch Unicode spaces (engine.go:628-632). A
// ?doc=<hash>\f would keep its \f and miss the blob; TrimSpace would strip it and find one.
func (t *DocListTag) GetDocument() (out string) {
	defer catchThrowable(&out, "DocList")

	// :33-34 — the gate, outside the try. Dead while ADMIN_GATED is false.
	if deny, denied := docListGate(); denied {
		return deny
	}

	// :36 — !defined('CONGRUENCY_SQLITE'). The same mapping every sibling port uses
	// (apireference.go:91-93, engine.go:1742-1744).
	if t.e.cfg.SQLite == "" {
		return "<p>DocList: no DB.</p>"
	}

	// :37-38 — new PDO('sqlite:'.CONGRUENCY_SQLITE) + ERRMODE_EXCEPTION. PHP reaches its catch by
	// throwing out of the PDO constructor; an unopenable db lands on the same branch here.
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return docListError(err)
	}
	defer db.Close()

	// :39-41 — the one input this tag takes.
	hash := phpTrim(t.e.getStr("doc"))
	if hash != "" {
		return t.docListView(db, hash)
	}
	return t.docListIndex(db)
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// index — DocList::index($db) (DocList.php:47-57).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// docListIndex is DocList::index($db) (DocList.php:47-57) — the CURRENT docs, one <li> each. It is
// what BOTH gate surfaces render: ?page=tags&tag=DocList and a bare ?page=docs.
//
// THERE IS NO EMPTY-STATE ARM, AND ADDING ONE WOULD BE A DIVERGENCE. DocList.php:51-56 opens the
// intro <p> and the <ul>, loops, and closes the <ul> unconditionally — an empty doc_refs renders the
// intro plus "<ul class='doclist'>\n</ul>\n" with nothing between. The sibling RepoDocs DOES have
// such an arm ("No repo documentation ingested yet.", RepoDocs.php:55) and DocList pointedly does
// not; tag_selfcheck.py reports an empty backing table as WARN precisely because this renders clean
// and empty rather than saying anything.
//
// THE APOSTROPHE IN "The CMS's own documentation" IS A RAW BYTE. It is a literal ' inside a
// double-quoted PHP string (:51), not data, and htmlspecialchars is never called on it — so it
// emits as ' and NOT as &#039;. esc() here would be a byte diff on the very first line.
//
// Every DATA value, by contrast, is esc()'d exactly where the PHP esc()'s it (:53-54) — hash, path
// and kind are columns, and this render flows back through execute_all_tags, so a stored "<<<Tag>>>"
// must come back "&lt;&lt;&lt;Tag&gt;&gt;&gt;" and stay inert (engine.go's header, mechanism 2).
//
// `(int) $r['bytes']` (:54) is toInt, NOT esc: the PHP casts to int and interpolates the number, so
// no escaping happens and none is needed. bytes is an INTEGER column (ingest_self.py:45), so PDO
// hands back an int64 and the cast is identity on it; toInt models the cast rather than assuming the
// column's type (engine.go:558-579).
func (t *DocListTag) docListIndex(db *sql.DB) string {
	// :48-50 — one JOIN, ORDER BY r.path. The is_current=1 filter is what makes this "the CURRENT
	// docs" (ingest_self.py:216-218 clears the flag and re-sets it per ingest).
	rows, err := queryRows(db,
		"SELECT r.path, r.hash, b.kind, b.bytes FROM doc_refs r JOIN doc_blobs b ON b.hash=r.hash "+
			"WHERE r.is_current=1 ORDER BY r.path")
	if err != nil {
		return docListError(err)
	}

	var b strings.Builder
	// :51
	b.WriteString("<p>The CMS's own documentation, addressed by git blob hash.</p>\n<ul class='doclist'>\n")
	for _, r := range rows {
		// :53-54 — one <li> per row. The space after </a> and the "\n" after </li> are the PHP's.
		b.WriteString("<li><a href='?page=docs&doc=" + esc(r["hash"]) + "'>" + esc(r["path"]) + "</a> " +
			"<span style='color:#888;font-size:.85em'>" + esc(r["kind"]) + " &middot; " +
			strconv.FormatInt(toInt(r["bytes"]), 10) + " B</span></li>\n")
	}
	// :56
	b.WriteString("</ul>\n")
	return b.String()
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// view — DocList::view($db, $hash) (DocList.php:59-89).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// docListView is DocList::view($db, $hash) (DocList.php:59-89) — one doc, addressed by blob hash.
// Reached only via ?doc=<hash>, i.e. ?page=docs&doc=<hash> (the links docListIndex emits) — the
// gallery URL carries no doc parameter and so never lands here.
//
// THE THREE QUERIES ARE CHAINED THROUGH $path, AND THE CHAIN'S DEGENERATE CASE IS REAL (:65-72):
// the refs query can return NOTHING while the blob EXISTS — a blob whose every ref was deleted. Then
// `$refs ? $refs[0]['path'] : ''` yields "" (:68, PHP's empty-array-is-falsy), and the history query
// runs as `WHERE path=''`, which matches no row. The doc still renders: the head just carries an
// empty <strong></strong>, and count($hist) > 1 is false so no versions line appears. That is the
// PHP's behaviour and it is reproduced, not guarded against.
//
// `$blob['bytes']` is SELECTed (:60) and never read — an unused column, not an omission. It is
// selected here too: dropping it from the SQL could not change a rendered byte, but keeping the
// query text identical to the PHP's is the cheaper thing to verify.
func (t *DocListTag) docListView(db *sql.DB, hash string) string {
	// :60-62 — the blob. PHP prepares and binds; so does this. fetch() returns FALSE on no rows, so
	// `if (!$blob)` is exactly len == 0.
	blobs, err := queryRows(db, "SELECT kind, bytes, body FROM doc_blobs WHERE hash=?", hash)
	if err != nil {
		return docListError(err)
	}
	if len(blobs) == 0 {
		// :63 — the unknown-hash state. NO trailing newline; the PHP's string ends at "</p>".
		return "<p>No such doc blob <code>" + esc(hash) + "</code>. <a href='?page=docs'>&larr; index</a></p>"
	}
	blob := blobs[0]

	// :65-67 — every path this blob is (or was) mounted at; the FIRST is the one the head shows.
	refs, err := queryRows(db, "SELECT DISTINCT path, is_current FROM doc_refs WHERE hash=? ORDER BY path", hash)
	if err != nil {
		return docListError(err)
	}

	// :68 — `$path = $refs ? $refs[0]['path'] : '';`. PHP's empty-array-is-falsy supplies the STRING
	// '' as the default; otherwise $path keeps the column's NATIVE type. So it stays `any` here rather
	// than being flattened through phpString, and that is not fussiness — $path is re-BOUND as a query
	// parameter two lines down. A NULL path column binds as SQL NULL in PHP (matching no row, since
	// `path = NULL` is never true), where phpString would have bound ''. Both happen to render the
	// same today — ingest_self.py always writes a real path, and esc() maps NULL and '' alike to "" —
	// but modelling the VALUE rather than its string form is what keeps that a fact about the data
	// instead of a coincidence this file quietly leans on.
	var path any = ""
	if len(refs) > 0 {
		path = refs[0]["path"]
	}

	// :70-72 — every version of THAT path, newest first. GROUP BY hash collapses each version's
	// several refs (one per commit) to one row; MAX(is_current) is "any of them is current".
	hist, err := queryRows(db,
		"SELECT hash, MAX(ts) t, MAX(is_current) cur FROM doc_refs WHERE path=? GROUP BY hash ORDER BY t DESC", path)
	if err != nil {
		return docListError(err)
	}

	// :74-75 — the head. substr($hash,0,12) is phpSubstr: PHP's substr counts BYTES and this port
	// must too (engine.go:479-482). A hash shorter than 12 bytes yields the whole string on both
	// sides — phpSubstr clamps where a Go slice s[:12] would panic.
	head := "<p><a href='?page=docs'>&larr; index</a> &middot; <strong>" + esc(path) + "</strong> " +
		"<span style='color:#888'>(blob " + esc(phpSubstr(hash, 0, 12)) + ")</span></p>\n"

	verhtml := ""
	// :77 — the versions line appears ONLY when the path has MORE THAN ONE version. A doc with a
	// single version renders no line at all, not an empty one.
	if len(hist) > 1 {
		var v strings.Builder
		v.WriteString("<p style='font-size:.85em'>versions: ") // :78
		for _, h := range hist {
			// :80 — NOTE THE ORDER: esc() wraps ONLY the 9-byte hash prefix, and the "*" is
			// concatenated AFTER it. Escaping the assembled label would be the same bytes today
			// (hex digits and '*' are all esc-inert) but it is not what the PHP writes.
			lab := esc(phpSubstr(phpString(h["hash"]), 0, 9))
			if docListTruthy(h["cur"]) {
				lab += "*"
			}
			// :81 — the CURRENT selection is bold and unlinked; every other version is a link. Both
			// arms end with a trailing space, and that space is a rendered byte.
			if docListIdenticalString(h["hash"], hash) {
				v.WriteString("<strong>" + lab + "</strong> ")
			} else {
				v.WriteString("<a href='?page=docs&doc=" + esc(h["hash"]) + "'>" + lab + "</a> ")
			}
		}
		v.WriteString("</p>\n") // :83
		verhtml = v.String()
	}

	// :85-87 — markdown, or a <pre> of the escaped body. The key is `=== 'markdown'` (ingest_self.py's
	// LANG map, :39, writes "markdown" for .md and "text" for .txt), NOT RepoDocs' 'md'. Anything that
	// is not exactly the string "markdown" — including "text", NULL, or an int — takes the <pre> arm.
	var rendered string
	if docListIdenticalString(blob["kind"], "markdown") {
		rendered = docListMarkdown(blob["body"])
	} else {
		rendered = "<pre style='background:#f4f1e8;padding:.6rem;overflow:auto'>" + esc(blob["body"]) + "</pre>"
	}

	// :88
	return head + verhtml + "<div class='doc prose'>\n" + rendered + "</div>\n"
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The markdown subset — DocList::markdown/inline (DocList.php:91-136).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// docListPCRESpaceClass is PCRE's \s as a Go character-class BODY: [ \t\n\v\f\r].
//
// GO'S OWN \s IS THE WRONG SET AND USING IT WOULD BE A REAL BUG. Go's regexp \s is [\t\n\f\r ] — it
// does NOT include \v (0x0B). PHP 7.3+ runs PCRE2, whose \s DOES include \v (matching Perl 5.18+).
// engine.go already made and documented this call for the same reason (isPHPSpace, engine.go:624-626
// — "PCRE's \s = [ \t\n\r\f\v]"). So every \s in DocList.php's patterns is spelled out explicitly
// below, and none of them is Go's \s.
//
// This is also NOT phpTrim's charlist (" \t\n\r\0\x0B"), which strips NUL and NOT \f. The two sets
// genuinely differ and this file uses both — \s in the regexes, trim() at the blank-line test. See
// docListMarkdown's blank-line branch.
const docListPCRESpaceClass = " \\t\\n\\v\\f\\r"

var (
	// docListFenceRe is preg_match('/^\s*```/', $ln) (DocList.php:102) — an OPTIONALLY INDENTED
	// fence marker. Unanchored at the right, so a ```php info string matches and is discarded.
	docListFenceRe = regexp.MustCompile("^[" + docListPCRESpaceClass + "]*```")

	// docListHeadingRe is preg_match('/^(#{1,6})\s+(.*)$/', $ln, $m) (DocList.php:108).
	//
	// The \s+ is REQUIRED, so "#Foo" is a paragraph, not an h1. Seven or more #'s cannot match
	// either: #{1,6} takes six, \s+ then needs whitespace and finds '#', and every shorter backtrack
	// fails the same way — so "####### x" is a paragraph too.
	//
	// PCRE's `$` (without /D) also matches BEFORE a trailing newline where Go's `$` (without (?m))
	// matches only at end of text. The difference cannot bite here: markdown() explodes on "\n" after
	// deleting every "\r", so no line contains either byte. Same reason `.` excluding \n is moot.
	docListHeadingRe = regexp.MustCompile("^(#{1,6})[" + docListPCRESpaceClass + "]+(.*)$")

	// docListIndentRe is preg_match('/^    (.*)$/', $ln, $m) (DocList.php:111) — EXACTLY four
	// leading spaces (a fifth lands in $m[1]). Tabs do not match.
	docListIndentRe = regexp.MustCompile("^    (.*)$")

	// docListCodeRe is the `code` span of preg_replace_callback('/`([^`]+)`/', …) (DocList.php:126).
	// [^`]+ is greedy and the span cannot be empty, so "``" is left alone.
	docListCodeRe = regexp.MustCompile("`([^`]+)`")

	// docListBoldRe is preg_replace('/\*\*(.+?)\*\*/', …) (DocList.php:131) — NON-GREEDY, so
	// "**a** and **b**" makes two <strong>s rather than one spanning the middle.
	docListBoldRe = regexp.MustCompile(`\*\*(.+?)\*\*`)

	// docListItalicRe is preg_replace('/(^|[^*])\*([^*\s][^*]*)\*/', …) (DocList.php:132).
	//
	// Group 1 CONSUMES the preceding character (or matches empty at ^), which is why the replacement
	// puts $1 back. The [^*\s] first-char guard is what stops "* item" (a list bullet) becoming an
	// <em>, and stops the leftover single '*' of an odd run from opening one.
	docListItalicRe = regexp.MustCompile("(^|[^*])\\*([^*" + docListPCRESpaceClass + "][^*]*)\\*")

	// docListLinkRe is preg_replace('/\[([^\]]+)\]\(([^)\s]+)\)/', …) (DocList.php:133). The URL may
	// hold no whitespace and no ')', so "[a](b c)" and "[a]()" are left as text.
	docListLinkRe = regexp.MustCompile("\\[([^\\]]+)\\]\\(([^)" + docListPCRESpaceClass + "]+)\\)")
)

// docListMarkdown is DocList::markdown($text) (DocList.php:93-120) — the minimal, ESCAPE-FIRST
// markdown subset, whose own header (DocList.php:91-92) reads:
//
//	Minimal markdown subset. ESCAPE FIRST (so HTML and '<<<Tag>>>' examples stay literal), then apply:
//	#.. -> h1-h6, blank-line paragraphs, ``` / 4-space indent -> <pre><code>, `x` -> <code>, [t](u) -> <a>.
//
// ESCAPE FIRST IS THE WHOLE SECURITY MODEL AND THE ORDER IS NOT NEGOTIABLE (:94). htmlspecialchars
// runs ONCE, over the entire raw document, BEFORE any structure is recognised. Everything after that
// point manipulates already-escaped text, and the markup this function adds (<p>, <h1>, <pre>, <em>…)
// is therefore the ONLY live markup in the output. Two consequences a "cleaner" implementation would
// break:
//
//   - a doc containing "<<<TitleTag>>>" emits "&lt;&lt;&lt;TitleTag&gt;&gt;&gt;", which tagPattern
//     cannot match, so the tag engine does not re-parse it when this output flows back through
//     execute_all_tags (engine.go's header, mechanism 2). This is the documented reason DocList
//     renders docs at all: the docs describe tags.
//   - the fence/indent bodies are emitted RAW into <pre><code> (:104, :112) with NO further
//     escaping, and that is CORRECT — they were escaped at :94. Escaping them again would render
//     "&amp;lt;" as visible source text in every code block.
//
// str_replace("\r", "", …) (:95) deletes EVERY carriage return, not just the ones before a newline,
// so a lone CR is a deletion and not a line break. explode("\n") then yields lines that contain
// neither \r nor \n — which is what makes the PCRE-vs-Go `$` and `.` differences moot (see
// docListHeadingRe).
//
// THE FOUR QUIRKS, each reproduced deliberately:
//
//  1. THE FENCE CHECK PRECEDES THE inFence CHECK (:102 before :107), so an indented ``` INSIDE a
//     fence closes it. A fence body cannot contain a fence line, at any indent.
//  2. EACH 4-SPACE LINE IS ITS OWN <pre><code> BLOCK (:112) — consecutive indented lines are NOT
//     merged, so a 3-line indented listing emits three separate blocks. This is a real difference
//     from every standard markdown implementation, and it is the spec here.
//  3. A LINE OF EXACTLY FOUR SPACES matches the indent rule (with $m[1] === "") BEFORE the
//     blank-line test at :114 can see it, so it emits an EMPTY "<pre><code></code></pre>\n" rather
//     than closing a paragraph. Order is the reason: :111 runs first.
//  4. THE BLANK TEST IS trim(), NOT \s (:114). PHP's trim() strips NUL and \v but NOT \f — so a line
//     holding only a form feed is NOT blank, and it becomes paragraph text. phpTrim is that exact
//     charlist (engine.go:628-632); strings.TrimSpace would strip the \f and lose the quirk.
//
// The closure `$flush` (:97-100) inlines below. Its `if ($para)` is PHP's empty-array-is-falsy, so a
// flush with nothing buffered emits NOTHING — there are no empty <p></p> in the output. Its
// implode(" ", $para) is why inline() sees the JOINED paragraph, which the PHP's own comment at :98
// explains: "inline() on the JOINED paragraph so bold/italic/code spanning a wrapped line still
// match". Reproducing the join is therefore reproducing which inline spans match at all.
//
// An UNCLOSED fence at EOF still emits its block (:118) — the document is not truncated.
func docListMarkdown(text any) string {
	// :94 — the one escape, over the whole document. esc is htmlspecialchars($s, ENT_QUOTES) with
	// PHP's (string) cast in front of it (engine.go:599), which is exactly `htmlspecialchars((string)
	// $text, ENT_QUOTES)`. A NULL body escapes to "" on both sides.
	escd := esc(text)

	// :95
	lines := strings.Split(strings.ReplaceAll(escd, "\r", ""), "\n")

	// :96
	var out strings.Builder
	var para []string
	inFence := false
	code := ""

	// :97-100 — $flush.
	flush := func() {
		if len(para) > 0 {
			out.WriteString("<p>" + docListInline(strings.Join(para, " ")) + "</p>\n")
			para = nil
		}
	}

	for _, ln := range lines {
		// :102-106 — the fence toggle. The fence LINE itself is never emitted, on either edge.
		if docListFenceRe.MatchString(ln) {
			if !inFence {
				flush()
				inFence = true
				code = ""
			} else {
				out.WriteString("<pre><code>" + code + "</code></pre>\n")
				inFence = false
			}
			continue
		}
		// :107 — inside a fence every line is buffered raw, with its newline restored.
		if inFence {
			code += ln + "\n"
			continue
		}
		// :108-110 — the heading. strlen($m[1]) is the level, 1..6.
		if m := docListHeadingRe.FindStringSubmatch(ln); m != nil {
			flush()
			h := strconv.Itoa(len(m[1]))
			out.WriteString("<h" + h + ">" + docListInline(m[2]) + "</h" + h + ">\n")
			continue
		}
		// :111-113 — the indented code line. Quirks 2 and 3 live here.
		if m := docListIndentRe.FindStringSubmatch(ln); m != nil {
			flush()
			out.WriteString("<pre><code>" + m[1] + "</code></pre>\n")
			continue
		}
		// :114 — quirk 4.
		if phpTrim(ln) == "" {
			flush()
			continue
		}
		// :115 — buffered RAW; inline() is applied to the whole paragraph in flush.
		para = append(para, ln)
	}

	// :117-118
	flush()
	if inFence {
		out.WriteString("<pre><code>" + code + "</code></pre>\n")
	}
	return out.String()
}

// docListInline is DocList::inline($s) (DocList.php:122-136) — the inline spans, applied to a whole
// paragraph or to a heading's text.
//
// THE PLACEHOLDER DANCE IS THE POINT, and the PHP's own comment (:123-124) says why: "Protect inline
// code first: its contents may hold * (e.g. `mysql_*`) that would otherwise break the bold/italic
// passes. Swap each span for a placeholder, transform, then restore." So the order is fixed:
//
//	1. `code`  -> "\x01<n>\x01"      (:126-130)   n counts from 0
//	2. **bold**                       (:131)
//	3. *italic*                       (:132)
//	4. [text](url)                    (:133)
//	5. restore each placeholder       (:134)      in INSERTION order
//
// Running any pass out of order changes the output. Restoring before step 4, for instance, would let
// a link regex chew a URL out of a code span.
//
// THE PLACEHOLDER IS A RAW \x01 BYTE AND IT IS NOT ESCAPED — htmlspecialchars (which already ran, in
// markdown()) does not touch \x01. So a document that CONTAINS a literal \x01 can collide with a
// placeholder and corrupt this render. That is a genuine (if unreachable-in-practice) defect in the
// PHP, and it is ported faithfully: this code does the identical thing with the identical bytes, so
// both sides corrupt identically. Per the ticket, a defect in the PHP is ported, not fixed — "if the
// PHP is genuinely defective, file a separate bug ticket and port the defect faithfully".
//
// The counter cannot collide with ITSELF, though, and the trailing \x01 is what earns that: the key
// for n=1 ("\x01" "1" "\x01") is not a substring of the key for n=11 ("\x01" "11" "\x01"), because
// the closing delimiter must line up. So the naive str_replace loop at :134 is safe against its own
// keys, and this loop is too.
//
// $m[1] (the code span's contents) is inserted into <code>…</code> WITHOUT further escaping (:128) —
// correct, because markdown() escaped the whole document before inline() ever saw it.
func docListInline(s string) string {
	// :126-130 — step 1. keys preserves PHP's array INSERTION order, which is the order :134's
	// foreach restores in; a Go map alone would not, and the restore order is observable whenever one
	// span's text could contain another's key.
	codes := map[string]string{}
	var keys []string
	s = docListCodeRe.ReplaceAllStringFunc(s, func(m string) string {
		// count($codes) is read BEFORE the insert, so the first key is \x010\x01.
		k := "\x01" + strconv.Itoa(len(codes)) + "\x01"
		// The pattern is `([^`]+)` — one backtick each side — so $m[1] is the match minus its first
		// and last byte. ReplaceAllStringFunc hands over the whole match, hence the slice.
		codes[k] = "<code>" + m[1:len(m)-1] + "</code>"
		keys = append(keys, k)
		return k
	})

	// :131-133 — steps 2-4. ${1}/${2} rather than $1/$2: Go reads $1< as group "1" here, but the
	// braced form is the spelling that cannot be misread when a digit follows.
	s = docListBoldRe.ReplaceAllString(s, "<strong>${1}</strong>")
	s = docListItalicRe.ReplaceAllString(s, "${1}<em>${2}</em>")
	s = docListLinkRe.ReplaceAllString(s, `<a href="${2}">${1}</a>`)

	// :134 — step 5, in insertion order.
	for _, k := range keys {
		s = strings.ReplaceAll(s, k, codes[k])
	}
	return s
}
