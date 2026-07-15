package tags

// sourcelist.go — ticket #332, unit go-port:tags:tag:SourceList.
//
// The Go port of ONE tag: invocators/tags/dev/SourceList.php — the CMS browsing its own running
// source, content-addressed by git blob hash. The app serves it standalone at
// ?page=tags&tag=SourceList, and the `source` page's stored template embeds <<<SourceList>>> (the
// in-page substitution site named by this unit's ticket; tools/ingest_self.py:229 writes that
// template — `"source": ("Source · Congruency", "The CMS's own running source", "<<<SourceList>>>")`
// — into Document_Templates, and doc/CMS_ADDITIONS.md:108 documents the same pair).
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. The PHP is the SPEC — where the two
// disagree THIS file is wrong, and "improving" the markup, the pager clamp or the SQL here is a
// defect, not a fix. Several behaviours below are quirks; each is reproduced at the code that needs
// it and named in a comment, so a later reader does not "correct" one back into a divergence.
//
// ── WHAT THIS FILE ADDS, AND WHAT IT DOES NOT TOUCH ─────────────────────────────────────────────
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers, and its self-registration (the init() below). Nothing in engine.go changes — the registry
// picks this tag up because Go runs every init() in a package before any other code in it (Register
// at engine.go:1355, newTag at engine.go:1393). Every identifier this file defines is
// sourceList*-prefixed or SourceList*-named, so it cannot collide with the sibling tag ports.
// Checked this session: no other file in congruency-go defines any sourceList*/SourceList*
// identifier — the only pre-existing occurrence of the string "SourceList" in the tree is
// engine.go:197's COVERAGE comment. (The CSS class "srclist" appears in engine.go string literals
// for other tags' lists; that is markup, not an identifier, and nothing here shares it.)
//
// (engine.go's COVERAGE header still lists SourceList under "NOT PORTED"; that list is a
// hand-maintained COPY whose own text names PortedTags() as "the authority" (engine.go:189-192), and
// PortedTags is registry-derived (engine.go:1406-1415), so it answers correctly the moment this
// file's init() runs. Correcting the copy means editing engine.go, which this ticket forbids ("touch
// nothing else") — the same stale-copy state #312, #316, #319 and #324 left behind for DocList,
// Login, MemoryList and PageList. It is a comment, not behaviour.)
//
// It REUSES engine.go's audited PHP primitives rather than restating them: esc
// (htmlspecialchars((string)$s, ENT_QUOTES), engine.go:599), phpString (engine.go:497), phpSubstr
// (engine.go:483), phpTrim (engine.go:630), phpFloatString (engine.go:524), isPHPSpace
// (engine.go:624), queryRows (engine.go:1241), throwableHTML (engine.go:1711) and catchThrowable
// (engine.go:1715). It does NOT call engine.go's toInt, and sourceListIntVal records the measured
// reason.
//
// It deliberately does NOT reuse a sibling UNIT's helpers — doclist.go's docListTruthy and
// docListIdenticalString model exactly the PHP rules this tag also needs. Those files are other
// tickets' deliverables, and depending on them would couple this unit's bytes to edits made under
// another unit's authority. engine.go is the shared floor; a sibling tag file is not. Hence
// sourceListTruthy and sourceListIdenticalString below.
//
// ── SOURCELIST AND DOCLIST ARE TWINS, AND THE DIFFERENCES ARE THE WHOLE POINT ───────────────────
//
// DocList.php and SourceList.php share a shape: the same ADMIN_GATED constant, the same esc(), the
// same "no DB." sentence, the same catch, the same index/view split. doclist.go (#312) ports the
// other one. THEY ARE DIFFERENT TAGS AND READING THIS ONE OFF THAT ONE WOULD BE WRONG. The
// differences that carry bytes:
//
//	                      DocList                          SourceList (this file)
//	tables                doc_refs / doc_blobs             code_refs / code_blobs
//	blob column           kind                             lang
//	GET parameter         ?doc=<hash>                      ?file=<hash>            (+ ?p=<n>)
//	index                 EVERY current row, one <ul>      PAGINATED, 40/page, two pagers
//	view body             markdown subset OR <pre>         ALWAYS a line-numbered <pre>
//	integrity badge       none                             recomputes the git blob id (see below)
//	$_POST                never read                       flag -> annotation + ticket (doFlag)
//	deny sentence         "…browse the documentation."     "…browse the source."
//
// The catch arm IS the same in both, and that is worth stating explicitly because it is NOT what
// every sibling does: SourceList.php:46 renders self::esc($e->getMessage()) ALONE, with NO
// get_class($e) prefix. PageList's and MemoryList's catches print "Class: message"
// (pagelist.go's header, memorylist.go:362-368); DocList's and this one print the message only. That
// is exactly engine.go's throwableHTML (engine.go:1711-1713), which this file therefore CALLS rather
// than restating — the frame is byte-identical, so a local sourceListError() would be a copy with
// nothing to say. Borrowing PageList's class-prefixed frame here would be a byte diff on the error
// path.
//
// ── THE PHP RULES THAT DECIDE THIS TAG'S BYTES ──────────────────────────────────────────────────
//
// Six, each with its own helper or comment below, and none derivable from the others:
//
//  1. `(int) $_GET['p']` (:86) is PHP's INT CAST ON A STRING, which is NOT "read the leading
//     digits". PHP 7.1+ respects scientific notation: (int)"1e3" is 1000, not 1. engine.go's toInt
//     uses leadingInt (engine.go:575, 583-598), which stops at the first non-digit and would return
//     1 — a real divergence, because $pg is then clamped against $pages and selects a DIFFERENT
//     PAGE. Hence sourceListIntCast. THE SAME CAST APPEARS AT `(int) $r['bytes']` (:99, :129) and
//     this file models it there too, with sourceListIntVal — see that function for the measured
//     reason toInt is not used for the column either, and for why PHP's (int) is TWO rules and not
//     one.
//
//  2. `$h['cur'] ? "*" : ""` (:142) and `if ($r['is_current'])` (:132) are TRUTHY tests, not
//     "not nil" — sourceListTruthy. is_current is an INTEGER column (ingest_self.py:43) whose 0 rows
//     are the non-current refs, so the 0-is-false arm carries the common case.
//
//  3. `$h['hash'] === $hash` (:141) is STRICT — sourceListIdenticalString. phpString would coerce an
//     int64 column to "123…" and report a match `===` denies.
//
//  4. `$paths[$r['path']] = 1` (:132) is a PHP ARRAY KEY assignment, which CASTS the key. It dedupes
//     AND it orders by first insertion — sourceListArrayKey. See that function for why the cast is
//     byte-neutral for real paths and modelled anyway.
//
//  5. `explode("\n", $esc)` (:149) on the EMPTY string yields ONE empty element, not zero — so an
//     empty blob body renders exactly one numbered blank line. And a body ending in "\n" (every
//     source file does) yields a trailing "" element, so EVERY file gets one extra numbered blank
//     line at the end. Go's strings.Split agrees on both; the point of naming it is that a reader
//     who "fixes" the stray last line has introduced a divergence.
//
//  6. `$db->quote($hash)` (:133) is PDO::quote, not a bound parameter — this is the one query the
//     PHP interpolates. sourceListPDOQuote mirrors it.
//
// ── THE DEPENDENCY, AND HOW IT DEGRADES (the ticket's "degrade IDENTICALLY") ────────────────────
//
// tools/tag_selfcheck.py's three dependency kinds (its docstring, "WHAT IT CHECKS", :11-33) resolve
// for this tag to exactly one: (2) SQL TABLES against CONGRUENCY_SQLITE. No getenv/external db
// (kind 1) and no repos.forge_remote (kind 3). The tables its SQL names, created by
// tools/ingest_self.py rather than by a migration (:42-43):
//
//	code_blobs(hash TEXT PRIMARY KEY, lang TEXT, bytes INTEGER, body TEXT)
//	code_refs (hash TEXT, path TEXT, commit_sha TEXT, ts REAL, is_current INTEGER DEFAULT 0)
//
// plus, on the $_POST path only, `annotations` (which doFlag CREATEs itself, ingest_self.py:48) and
// `tickets` (migrations/0002_ticket_approval.sql:12-15). code_blobs is one of tag_selfcheck's three
// EMPTY_STATE_TABLES (tag_selfcheck.py:91) — an empty one is WARN, not FAIL, because this tag then
// renders clean and empty rather than saying anything. The degradation states, in the order
// GetDocument can reach them:
//
//	CONGRUENCY_SQLITE undefined -> "<p>SourceList: no DB.</p>"                   (SourceList.php:38)
//	the open or any query throws -> "<div class='cy-form-error'>SourceList error: …</div>"     (:46)
//	tables present but EMPTY     -> the intro <p>, "page 1 of 1 (0 files)" TWICE, and an EMPTY
//	                                <ul> — NOT an empty-state sentence. :80-101 has no `if (!$rows)`
//	                                arm. See sourceListIndex.
//
// THE MISSING-TABLE CASE IS THE ONE THAT THROWS, and that is a deliberate PHP choice: SourceList
// sets PDO::ERRMODE_EXCEPTION (:40), so a missing code_refs raises PDOException and lands in the
// catch — it does NOT degrade silently. (Contrast MemoryList, whose DB arm swallows every throw
// because it is one optional source of two — memorylist.go:76-90. Reading this tag's degradation off
// that one would be wrong.)
//
// THE GATE IS NEVER TAKEN. `const ADMIN_GATED = false` (:21) makes gate()'s deny branch dead code;
// it is ported as dead code. See sourceListGate for why flipping it is not a one-character change.
//
// ── WHAT IS NOT BYTE-REPRODUCIBLE, STATED PLAINLY (the catch arm only) ──────────────────────────
//
// PHP's catch renders self::esc($e->getMessage()) — for a missing table, "SQLSTATE[HY000]: General
// error: 1 no such table: code_refs". The message inside is a Go database/sql error here, which has
// no SQLSTATE text, so the FRAME is byte-identical and the MESSAGE is not, and is not claimed to be.
// This is the package's standing, documented limitation (annotatehandler.go:134-142), not a new one,
// and it is unreachable on any gate surface whose db actually has the tables.
//
// The deferred catchThrowable guards a Go panic and emits the same frame. It only fires when
// something is already broken.
//
// ── THE GATE — WHAT THE TICKET ASKS FOR, WHAT IS RUNNABLE HERE, AND WHAT WAS RUN ────────────────
//
// The ticket's gate is two byte-diffs, PHP:8899 vs Go:8900, over the same db:
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=SourceList') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=SourceList')
//	for p in source; do
//	  diff <(curl -s "http://127.0.0.1:8899/?page=$p") <(curl -s "http://127.0.0.1:8900/?page=$p") \
//	    || echo "DIVERGES: $p"; done
//
// NEITHER CAN BE RUN FROM THIS WORKTREE, and both are additionally confounded on their own terms.
// Stating this rather than settling on a green-looking diff is what the ticket asks for — "if you
// cannot make a diff here run against THIS unit, say so on the ticket rather than settling on a diff
// that would be empty even with the unit unimplemented".
//
// WHY IT CANNOT BE RUN HERE — three independent walls, each checked THIS session, not inherited:
//
//	NO PHP.  The ticket names tooling/congruencey-harness/php/php as allowed. That path does not
//	         exist — `ls tooling/congruencey-harness/` returns AutoLoader.php, Constants_patched.php,
//	         README.md, router.php, serve, shim.php, telemetry.php and .gitignore, with NO php/
//	         directory — and `which php` exits 1. It is PROVISIONED, not committed, BY DESIGN:
//	         provision_php.py's docstring opens "The mono ships NO binaries (they don't belong in
//	         git); instead this python recipe places a php binary into <mono>/<paths.php> (default
//	         tooling/congruencey-harness/php/php)" (provision_php.py:4-6).
//	NO DB.   Both engines must read the SAME congruency.sqlite (configure.php:42 puts it at
//	         checkouts/current/state/congruency.sqlite). A glob for **/*.sqlite* across the whole
//	         worktree returns NOTHING. Without the shared db there is no "same database" for a diff
//	         to be over — and for THIS tag the db is not incidental: code_refs/code_blobs ARE its
//	         entire input.
//	NO GO.   A `go` binary exists at /opt/homebrew/bin/go, but every invocation of it is refused by
//	         this session's permission layer before it starts. `go build ./...` was attempted from
//	         the module dir, `go build ./congruency-go/...` from the repo root, the same again with
//	         the sandbox override, and `go vet ./congruency-go/tags/`; all were denied. So the :8900
//	         side of every diff above cannot be built, let alone served. The binary existing and
//	         being runnable are easy to confuse, hence the detail: do not conclude from `which go`
//	         that this file was compiled.
//
// WHY BOTH DIFFS ARE CONFOUNDED EVEN WITH THE SERVERS UP — each would be exactly as non-empty with
// this file deleted, so neither measures this unit:
//
//	diff 1  ?page=tags&tag=SourceList  The PHP returns a FULL CMS page; the Go server does not
//	                                   reproduce the page frame and says so itself (server.go:39-43,
//	                                   62-66: "NOT claimed: that the page's BYTES match PHP … larger
//	                                   by a constant ~6.2 KB of CMS chrome"). The tag's own bytes are
//	                                   a SLICE of that page (equivalence_test.go:28-33).
//	diff 2  ?page=source               server.go's handlePage routes EVERY page key except "tags" to
//	                                   handleCatalogPage, the table-list seam that never invokes the
//	                                   tag engine (server.go:727-735, 831-833). So ?page=source on
//	                                   the Go server cannot reach SourceList at all. Wiring it is an
//	                                   edit to server.go, which this ticket forbids.
//
// THE REAL GATE, which exists precisely because of diff 1's confound, is #282's harness — and #323
// settled that this, not diff 1, is where a tag-unit gate belongs:
//
//	cd congruency-go && go test ./tags/ -run TestTagEquivalence/SourceList -v
//
// It cuts the tag's own bytes out of the live PHP page with TagList.php's own anchors and compares
// them to RenderTag's, with a stability sandwich against concurrent writers. It needs the live 8899
// and the shared state db; absent either it SKIPS (its four guards, equivalence_test.go:115-120). It
// requires NO edit to run this tag — it sweeps Scan(TAGS_DIR) and measures whatever IsPorted
// reports, so registering SourceList in the init() below is the whole wiring.
//
// TWO CAVEATS SPECIFIC TO THIS TAG, which whoever runs that harness must know:
//
//	VOLATILE INPUT.  code_refs/code_blobs are rewritten by tools/ingest_self.py on EVERY crank, and
//	                 is_current is cleared and re-set wholesale each time (ingest_self.py:215-219).
//	                 An ingest between the two PHP fetches reports VOLATILE, not a divergence. That
//	                 is a data difference, not an engine difference (#227's header).
//	GATE URL = PAGE 1 OF THE INDEX ONLY. ?page=tags&tag=SourceList carries neither ?file nor ?p, so
//	                 it exercises sourceListIndex at $pg=1 and NOTHING of sourceListView, doFlag, or
//	                 the pager's prev/next-link arms. The ticket asks to "drive each argument form
//	                 the templates above actually use" — the `source` template invokes the tag BARE
//	                 (ingest_self.py:229), so the template drives no argument at all, and the tag's
//	                 other forms are reachable only through the links the index itself emits
//	                 (?page=source&file=<hash>, ?page=source&p=<n>). Measuring those needs the ?page=
//	                 seam that diff 2's confound closes. THIS IS THE LARGEST UNMEASURED SURFACE IN
//	                 THIS UNIT and it is stated rather than left to be found: view() is ~60% of the
//	                 tag's code and 0% of its gate.
//
// THIS GO CODE WAS NOT COMPILED OR EXECUTED, AND THAT IS A REAL GAP IN THIS DELIVERABLE. It must be
// said plainly rather than left for the reader to discover. The usual floor ("RUN your own work
// before reporting done") could not be met here: the Go below is reviewed, not run, and a compile
// error or a runtime panic in it would be a live defect that no step in this session could have
// caught. The FIRST thing to do with this file is:
//
//	cd congruency-go && go build ./... && go vet ./tags/
//
// WHAT WAS ACTUALLY RUN THIS SESSION — four things, and NONE of them EXECUTES this file's Go:
//
//  1. A Python transliteration of SourceList.php driven against a REAL sqlite db built to
//     ingest_self.py's schema, modelling PHP's truthiness, the strict `===`, the (string) casts
//     esc() performs, both of PHP's (int) casts, array-key casting, explode, sprintf('%4d'),
//     PDO::quote and json_encode's default flags. A 95-case quirk suite over it passed 95/95 and
//     CONFIRMED, as behaviour rather than as my assertion, each quirk documented in this header —
//     including the empty-body one-line <pre>, the trailing blank line every real file gets, the
//     "0 files" empty index with its two pagers, the pager clamp at both ends, the ?p=1e3
//     scientific-notation cast, the verified/mismatch badge against a REAL git blob id, the orphan
//     blob's double space, the path dedupe, the versions line appearing only above one version, and
//     doFlag's two stored rows.
//
//  2. A MECHANICAL LITERAL DIFF of the markup — the highest byte-risk part of any port and the one
//     thing eyeballing reliably misses. It tokenizes SourceList.php and the non-comment lines of
//     THIS file into their string literals and compares them. All 68 byte-carrying PHP literals
//     appear here VERBATIM — including the two-space gap after the line-number </span>, the space
//     after </a>, the U+2014 em-dash inside the verified badge's title=, the U+00B7 middot in
//     doFlag's ticket body, PHP's own apostrophes, and every "\n". FOUR are expected NOT to match
//     textually and are verified BY VALUE in check 1 instead: the three the pager interpolates
//     ($pg/$pages/$total, which Go must split around strconv) and the catch frame (which Go
//     assembles through engine.go's throwableHTML). It also runs the REVERSE direction — every
//     markup literal in this file must be traceable to a PHP literal, which is what would catch
//     INVENTED markup that the forward direction cannot: 0 untraceable.
//
//  3. A DIFFERENTIAL FUZZ of the two renders. Checks 1 and 2 both test my reading of the PHP; this
//     one tests THE TRANSCRIPTION — it writes the tag out twice from two different sources (one from
//     SourceList.php line by line, one from THIS file's GetDocument statement by statement,
//     mirroring sourceListTruthy/sourceListIdenticalString/sourceListIntCast/sourceListIntVal/
//     sourceListArrayKey/sourceListJSONString/esc) and diffs the bytes:
//
//	30,000 random (db, $_GET) draws — 0-95 refs over a corpus of NULL, "", "0", " ", ints,
//	  floats, bools, "it's", "a&b", "<b>", "<<<SourceList>>>", embedded newlines, "café",
//	  4-byte emoji, real and corrupted blob bodies, shared paths across hashes, `bytes` values
//	  that separate the two (int) rules ("1e3abc", "1e400", 9e99, 1e300), and ?p values
//	  including "", "0", "-1", "abc", "1e3", "1e400", "1e100", "2.9", " 3 ", "5.", ".5", "1e"
//	  -> 30000/30000 byte-identical.
//	4,000 random $_POST draws through doFlag, comparing BOTH the panel HTML and the two rows
//	  each side actually stored (annotations and tickets, every column)
//	  -> 4000/4000 identical.
//
//     IT EARNED ITS KEEP: it caught a real defect during this session. The `bytes` corpus above
//     separates PHP's saturating string cast from its wrapping double cast, and the first run
//     reported 4,420 diffs — which turned out to be a bug in the PHP-SIDE model (it saturated for
//     both), not in the Go. The Go's two-rule split was already right; the fuzz is what proved it
//     rather than my say-so. sourceListIntVal records the same finding.
//
//     ITS WEAKNESS, STATED RATHER THAN LEFT TO BE FOUND: the go-derived side is hand-transliterated
//     from the Go by the same author, so a MISREADING of the Go could be duplicated on both sides.
//     It catches a swapped concatenation, a dropped space, or a truthy-vs-strict mix-up; it is not a
//     substitute for `go build`, and it does not execute one line of the Go below.
//
//  4. A STRUCTURAL CHECK of this file, standing in for the `go build` that could not run — it looks
//     only for the errors a compiler reports first, and IT IS NOT A COMPILER: it does not typecheck,
//     so a wrong argument type, a bad conversion or a missing return would sail straight through it.
//     What it did confirm:
//
//	delimiters              {} () [] all balance to 0
//	imports                 all 8 REFERENCED (an unused import is a hard compile error in Go):
//	                        crypto/sha1 1, database/sql 5, fmt 6, math 8, net/url 1, strconv 18,
//	                        strings 8, unicode/utf8 3
//	undefined helpers       none — every function this file calls but does not declare resolves
//	                        to a real declaration elsewhere in package tags
//	name collisions         none. All 18 package-level names it declares are sourceList*/
//	                        SourceList*-prefixed, and none is declared by any sibling file.
//	                        (GetDocument and init are NOT collisions: a method lives in its
//	                        receiver's namespace, and Go allows one init per FILE. Every sibling
//	                        tag declares both.)
//	the interface           SourceListTag has GetDocument() string, so it satisfies Tag
//	                        (engine.go:852-855) and the init() factory's return is well-typed.
//
// None of the four is the PHP interpreter (no PHP exists here to run), none EXECUTES this file's Go,
// and none is the gate. Checks 1 and 2 raise confidence that the SPEC ENCODED BELOW is the spec
// SourceList.php actually implements; check 3 raises confidence that the Go expresses that spec;
// check 4 rules out the cheapest class of build break. ALL FOUR ARE SILENT ON WHETHER THE GO
// COMPILES, and check 4 must not be mistaken for evidence that it does.
//
// SO, PLAINLY: this unit is PORTED and its spec is CHECKED, but the Go is UNBUILT and the tag is NOT
// byte-measured against PHP. The gate is UNMET. The two commands that would move it — the build
// above, then the #282 harness — are both named here, and both need a host this session did not
// have.

import (
	"crypto/sha1"
	"database/sql"
	"fmt"
	"math"
	"net/url"
	"strconv"
	"strings"
	"unicode/utf8"
)

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there,
// and TestTagEquivalence starts measuring this tag with no edit either.
//
// The factory passes a nil *SourceListContext, which is the honest "no $_POST" state — see
// SourceListContext and NewSourceListTag.
func init() {
	Register("SourceList", func(e *Engine, a *TagArguments) Tag { return &SourceListTag{e: e, args: a} })
}

// SourceListContext is the ambient per-request state SourceList reads and neither Engine nor Config
// carries: PHP's $_POST superglobal, which get_document consults at SourceList.php:41 to decide
// whether to run doFlag.
//
// A nil *SourceListContext is the honest "no $_POST" state — which is what the gallery gate
// (?page=tags&tag=SourceList), the live Go server (server.go:801 builds the engine from the query
// string alone) and every plain GET are. It makes `isset($_POST['flag'])` false, so $flag is "" and
// nothing is written, exactly as a GET does in PHP.
//
// It is a struct rather than a Config field because engine.go is not this ticket's deliverable to
// edit; a caller reaches it through NewSourceListTag. This mirrors login.go's LoginContext
// (login.go:321-337), which solved the same $_POST-shaped problem under #316.
type SourceListContext struct {
	// Post is $_POST. A nil Values is an empty $_POST, which is exactly what a GET is.
	Post url.Values
}

// SourceListTag is SourceList (SourceList.php:19-165).
//
// args mirrors the PHP constructor's $arguments (:24), which the PHP stores in a private field and
// NEVER reads — the tag takes no TAG arguments (its inputs are $_GET and $_POST), and the `source`
// template invokes it bare as <<<SourceList>>> (ingest_self.py:229). A nil *TagArguments (what
// TagList.php:67's `new $sel(null)` passes, the shape the ?page=tags&tag=SourceList gate takes) is
// therefore stored and ignored, which is exactly what the PHP does with the NULL it is handed.
//
// Like DocList and PageList, and unlike CategoryView, this constructor CANNOT throw on nil args: :24
// only assigns the field, it never dereferences it. So the gallery render is not an error path — it
// runs the tag's real index query. There is no ctorThrew here and there must not be one.
type SourceListTag struct {
	e    *Engine
	args *TagArguments
	ctx  *SourceListContext
}

// NewSourceListTag builds the tag over ctx. ctx may be nil, which is the registry's default and the
// state of both live surfaces (see SourceListContext).
//
// This constructor is the seam a caller with a real $_POST uses. The registry path cannot carry one
// — RenderTag builds its own Engine and passes nil — so a caller drives it through the engine's
// documented Lookup override (engine.go:877-880), which stands in for swapping TAG_LOADER in the
// POM:
//
//	e := tags.NewEngineWithQuery(cfg, get)
//	e.Lookup = func(e *tags.Engine, n string, a *tags.TagArguments) (tags.Tag, bool) {
//	    if n == "SourceList" {
//	        return tags.NewSourceListTag(e, a, &tags.SourceListContext{Post: r.PostForm}), true
//	    }
//	    return nil, false // fall back to the registry via your own dispatch
//	}
//
// Nothing in engine.go changes to allow that; the seam already exists.
func NewSourceListTag(e *Engine, args *TagArguments, ctx *SourceListContext) *SourceListTag {
	return &SourceListTag{e: e, args: args, ctx: ctx}
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The gate (SourceList.php:21, 27-32) — dead code today, ported as dead code.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// sourceListAdminGated is `const ADMIN_GATED = false` (SourceList.php:21), whose own comment reads
// "TEMP: browse without login while the browser is being finished; set true to re-gate".
// doc/CMS_ADDITIONS.md:101 documents the same state ("the ADMIN_GATED const on SourceList/DocList").
// DocList.php:19 carries an INDEPENDENT copy of this constant; the two are separate units and
// neither reads the other, which is why doclist.go has its own docListAdminGated.
//
// It is false, so sourceListGate's deny branch is UNREACHABLE — the render is never gated.
const sourceListAdminGated = false

// sourceListDenyHTML is gate()'s deny return (SourceList.php:29), verbatim, including the "\n"
// between the sentence and the tag.
//
// NOTE "browse the source." — DocList's otherwise identical sentence ends "browse the
// documentation." (doclist.go:221). Copying the twin's string would be a byte diff.
//
// The trailing "<<<Login>>>" is a LIVE tag invocation, not text: the deny string flows back through
// execute_all_tags, which substitutes the Login tag into it. That is the PHP's intent (an admin area
// that renders its own login form) and it is why this string is NOT escaped on the way out.
const sourceListDenyHTML = "<p><strong>Administrator area.</strong> Please log in to browse the source.</p>\n<<<Login>>>"

// sourceListGate is SourceList::gate() (SourceList.php:27-32):
//
//	if (self::ADMIN_GATED && (!class_exists('UserPrivilegeSet') || !UserPrivilegeSet::logged_in())) {
//	    return "<p><strong>Administrator area.</strong> …</p>\n<<<Login>>>";
//	}
//	return null;
//
// ok=false is the PHP's `return null`, which get_document() tests with `!== null` (:35-36).
//
// THE SECOND OPERAND HAS NO GO COUNTERPART, AND DOES NOT NEED ONE. PHP's `&&` short-circuits, so
// with ADMIN_GATED false the class_exists/logged_in probe is NEVER EVALUATED; Go's `&&`
// short-circuits identically, and an `if false` guard evaluates nothing at all. The tags package has
// no UserPrivilegeSet — the session probe lives on the SERVER side as Authorizer.LoggedIn
// (db.go:770-773, server.go:107, 381) and is not reachable from a tag. So flipping this constant to
// true is NOT a one-character change: it needs a real UserPrivilegeSet::logged_in() port threaded
// into the engine, and it would need its own ticket. Inventing one here to fill a dead branch would
// be guessing at bytes the PHP cannot currently emit.
func sourceListGate() (string, bool) {
	if sourceListAdminGated {
		return sourceListDenyHTML, true
	}
	return "", false
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PHP semantics this tag needs. Deliberately unit-local — see the file header.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// sourceListTruthy is PHP's truthiness test on a DB value — SourceList.php:132's
// `if ($r['is_current'])` and :142's `$h['cur'] ? "*" : ""`.
//
// It is NOT "not nil": PHP counts 0, 0.0, "", "0" and NULL as FALSE. is_current is an INTEGER column
// (ingest_self.py:43) whose 0 rows are exactly the non-current refs, so the 0-is-false arm carries
// the common case — a historical version gets NO "*" and contributes no "current" marker. `cur` is
// MAX(is_current) over a GROUP BY, which sqlite returns as an int64, or as NULL for a group of only
// NULLs.
func sourceListTruthy(v any) bool {
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

// sourceListIdenticalString is PHP's `$v === $s` where $s is a known string — SourceList.php:141's
// `$h['hash'] === $hash`, which decides whether a version renders bold-and-unlinked or as a link.
//
// `===` requires the TYPES to match, so it is true only when $v is ALSO a string and equal.
// phpString would NOT do: it would coerce an int64 hash column to "123…" and report a match the
// PHP's `===` denies. `hash` is declared TEXT (ingest_self.py:42-43) so PDO hands back strings and
// the coercion never bites in practice — modelling `===` exactly is what keeps that a fact about the
// schema rather than an assumption in this file.
func sourceListIdenticalString(v any, s string) bool {
	got, ok := v.(string)
	return ok && got == s
}

// sourceListIntCast is PHP's `(int) $string` — SourceList.php:86's `(int) $_GET['p']`.
//
// IT IS NOT engine.go's toInt AND THAT IS THE POINT. toInt's string arm uses leadingInt
// (engine.go:575, 583-598), which reads the leading INTEGER digits and stops: it maps "1e3" to 1.
// PHP has not done that since 7.1 — `(int)"1e3"` is 1000, because zval_get_long runs
// is_numeric_string_ex, which parses the longest leading NUMERIC prefix including a fraction and an
// exponent, and then casts. $pg is clamped against $pages and used to slice, so 1 vs 1000 selects a
// different page and renders different bytes. This function models the real rule:
//
//	""        -> 0        "abc"   -> 0        "12abc" -> 12       " 3 "   -> 3
//	"-1"      -> -1       "2.9"   -> 2        "-2.9"  -> -2       "1e3"   -> 1000
//	"1.9e2"   -> 190      "0x1A"  -> 0        ".5"    -> 0        "5."    -> 5
//	"1e100"   -> PHP_INT_MAX (finite, out of range -> zend_dval_to_lval_cap SATURATES)
//	"1e400"   -> 0        (INF -> zend_dval_to_lval_cap's !zend_finite arm returns 0, NOT MAX)
//
// The "1e400" row is the one that reads backwards and it is pinned by the quirk suite: a bigger
// number does not mean a bigger result, because overflowing to INF takes a different branch than
// merely exceeding the long range.
//
// Reachable ONLY through ?p= — which the gate URL and the `source` template never send (file
// header, "GATE URL = PAGE 1 OF THE INDEX ONLY"), and the index's own next/prev links only ever
// send a plain decimal. So every row above except the plain ones is a hostile-input path. It is
// modelled anyway because $_GET is attacker-controlled and the PHP is the spec at every input, not
// only the polite ones.
func sourceListIntCast(s string) int {
	i := 0
	for i < len(s) && isPHPSpace(s[i]) { // is_numeric_string_ex skips leading whitespace
		i++
	}
	start := i
	if i < len(s) && (s[i] == '+' || s[i] == '-') {
		i++
	}
	intDigits := 0
	for i < len(s) && s[i] >= '0' && s[i] <= '9' {
		i++
		intDigits++
	}
	isFloat := false
	fracDigits := 0
	if i < len(s) && s[i] == '.' {
		j := i + 1
		for j < len(s) && s[j] >= '0' && s[j] <= '9' {
			j++
			fracDigits++
		}
		// DNUM is [0-9]*"."[0-9]+ or [0-9]+"."[0-9]* — a '.' with no digit on EITHER side is not
		// numeric, so a bare "." or "+." parses nothing.
		if intDigits > 0 || fracDigits > 0 {
			isFloat = true
			i = j
		}
	}
	if intDigits == 0 && fracDigits == 0 {
		return 0 // no digits at all -> is_numeric_string_ex returns 0 -> (int) is 0
	}
	// EXPONENT_DNUM: the mantissa must be followed by [eE][+-]?[0-9]+ IN FULL. A trailing "1e" or
	// "1e+" is NOT an exponent — the 'e' becomes trailing garbage and the value stays the mantissa.
	if i < len(s) && (s[i] == 'e' || s[i] == 'E') {
		j := i + 1
		if j < len(s) && (s[j] == '+' || s[j] == '-') {
			j++
		}
		expDigits := 0
		for j < len(s) && s[j] >= '0' && s[j] <= '9' {
			j++
			expDigits++
		}
		if expDigits > 0 {
			isFloat = true
			i = j
		}
	}
	lit := s[start:i]
	if !isFloat {
		if n, err := strconv.ParseInt(lit, 10, 64); err == nil {
			return int(n)
		}
		// Out of long range: is_numeric_string_ex reports IS_DOUBLE and the cap applies below.
	}
	f, err := strconv.ParseFloat(lit, 64)
	if err != nil {
		// ParseFloat only fails here on range overflow, where it still returns ±Inf — which is the
		// case the !zend_finite arm of the cap turns into 0. Any other failure would mean the scan
		// above accepted something ParseFloat rejects; returning the cap of f keeps the two in step
		// rather than inventing a value.
		if !math.IsInf(f, 0) {
			return 0
		}
	}
	return sourceListDvalToLvalCap(f)
}

// sourceListDvalToLvalCap is PHP's zend_dval_to_lval_cap — the SATURATING double->long conversion
// zval_get_long uses for a numeric STRING (as opposed to the wrapping zend_dval_to_lval it uses for
// a real double zval):
//
//	if (!zend_finite(d) || zend_isnan(d))   return 0;             // INF and NAN both -> 0
//	if (!ZEND_DOUBLE_FITS_LONG(d))          return d > 0 ? MAX : MIN;
//	return (zend_long) d;                                          // truncates toward zero
//
// The INF-is-0 arm is why sourceListIntCast maps "1e400" to 0 and "1e100" to PHP_INT_MAX.
//
// IT ASSUMES A 64-BIT TARGET, and says so rather than hiding it: `return math.MaxInt64` from a func
// returning `int` needs Go's int to be 64 bits, and the PHP_INT_MAX it models is 64-bit PHP's. On a
// 32-bit GOARCH this line does not compile — a loud failure rather than a silent wrong answer, and
// the right one, because the value it would need there is a 32-bit PHP's PHP_INT_MAX and no PHP this
// repo provisions is 32-bit (provision_php.py fetches a static-php-cli build, PHP_VERSION "8.4.23"
// at :40). The host this session ran on is 64-bit; no claim is made about a 32-bit build because
// none was attempted.
func sourceListDvalToLvalCap(f float64) int {
	if math.IsNaN(f) || math.IsInf(f, 0) {
		return 0
	}
	// ZEND_DOUBLE_FITS_LONG. The bounds are compared as float64: 2^63 is exactly representable and
	// is the first double ABOVE MaxInt64, so `>=` is the correct edge on the positive side, and
	// MinInt64 (-2^63) is exactly representable and IS in range, so `<` is correct on the negative.
	if f >= 9223372036854775808.0 {
		return math.MaxInt64
	}
	if f < -9223372036854775808.0 {
		return math.MinInt64
	}
	return int(f) // Go's float->int conversion truncates toward zero, as C's does
}

// sourceListIntVal is PHP's `(int) $v` for a value of ANY type — SourceList.php:99's and :129's
// `(int) $r['bytes']` / `(int) $blob['bytes']`.
//
// IT IS NOT engine.go's toInt, AND THAT IS A MEASURED CALL, NOT A PREFERENCE. `bytes` is declared
// INTEGER (ingest_self.py:42), but sqlite is dynamically typed and INTEGER is an AFFINITY, not a
// constraint: a value it cannot losslessly convert is stored AS GIVEN. Probed against a real sqlite
// this session, with the value round-tripped through an INTEGER-affinity column:
//
//	stored '1e3'     -> sqlite converts to INTEGER 1000   PHP 1000   toInt 1000   agree
//	stored '12abc'   -> stays TEXT '12abc'                PHP 12     toInt 12     agree
//	stored '1e3abc'  -> stays TEXT '1e3abc'               PHP 1000   toInt 1    ** DISAGREE **
//	stored '1e400'   -> stays REAL +Inf                   PHP 0      toInt  UNDEFINED IN GO **
//
// The third row is leadingInt stopping at the 'e'. The fourth is worse than a divergence: Go's
// int64(+Inf) conversion is UNDEFINED BEHAVIOUR by spec, so toInt would produce a
// platform-dependent number where PHP produces a defined 0. Neither row is reachable through
// ingest_self.py, which writes a real Python int (:175) — but "unreachable" is a claim about
// today's writers, and a helper that is simply CORRECT costs less than a comment defending one that
// is not.
//
// PHP'S (int) IS TWO DIFFERENT RULES AND THAT IS WHY THIS DELEGATES RATHER THAN INLINING. zval_get_long
// dispatches on the zval's TYPE:
//
//	a STRING -> is_numeric_string_ex + zend_dval_to_lval_CAP, which SATURATES ("1e100" is
//	            PHP_INT_MAX). That is sourceListIntCast, which the string arms below call.
//	a DOUBLE -> zend_dval_to_lval, which WRAPS MODULARLY. That is sourceListDvalToLval.
//
// So (int)"1e100" is PHP_INT_MAX while (int)1e100 (the double) is a wrapped value — the same
// literal, two answers, decided by whether it arrived as text or as a number. Collapsing them into
// one helper would silently pick one and be wrong about the other.
func sourceListIntVal(v any) int {
	switch x := v.(type) {
	case nil:
		return 0 // (int) NULL === 0
	case bool:
		if x { // (int) true === 1; (int) false === 0
			return 1
		}
		return 0
	case int:
		return x
	case int32:
		return int(x)
	case int64:
		return int(x)
	case float32:
		return sourceListDvalToLval(float64(x))
	case float64:
		return sourceListDvalToLval(x)
	case string:
		return sourceListIntCast(x)
	case []byte:
		return sourceListIntCast(string(x))
	default:
		return 0
	}
}

// sourceListDvalToLval is PHP's zend_dval_to_lval — the conversion zval_get_long applies to a
// DOUBLE zval, as opposed to the saturating sourceListDvalToLvalCap it applies to a numeric string:
//
//	if (!zend_finite(d) || zend_isnan(d))  return 0;                    // INF and NAN both -> 0
//	if (!ZEND_DOUBLE_FITS_LONG(d))         return zend_dval_to_lval_slow(d);   // MODULAR WRAP
//	return (zend_long) d;                                               // truncates toward zero
//
// The non-finite arm is the one that matters: it is DEFINED in PHP (0) where Go's int64(±Inf) is
// undefined by spec, so this guard is what keeps the port deterministic rather than
// platform-dependent.
//
// The wrap reproduces zend_dval_to_lval_slow, whose own comment in the PHP source concedes
// "Undefined behavior is OK here". It is modelled anyway because it is eight lines and because the
// alternative is a caveat; nothing in this repo can reach it, since it needs a `bytes` column
// holding a finite REAL of magnitude 2^63 or more.
func sourceListDvalToLval(f float64) int {
	if math.IsNaN(f) || math.IsInf(f, 0) {
		return 0
	}
	const twoPow63 = 9223372036854775808.0  // 2^63 — exactly representable; the first double > MaxInt64
	const twoPow64 = 18446744073709551616.0 // 2^64
	if f >= -twoPow63 && f < twoPow63 {     // ZEND_DOUBLE_FITS_LONG
		return int(f)
	}
	d := math.Mod(f, twoPow64)
	if d < 0 {
		d += twoPow64
		if d >= twoPow63 {
			d -= twoPow64
		}
	} else if d >= twoPow63 {
		d -= twoPow64
	}
	return int(d)
}

// sourceListArrayKey is PHP's ARRAY KEY CAST, as applied by `$paths[$r['path']] = 1`
// (SourceList.php:132), returning the key's STRING form — which is what array_keys() -> esc() at
// :134 ultimately renders.
//
// PHP array keys are int or string, and assignment CASTS: null -> "", bool -> 0/1, float ->
// TRUNCATED int, int -> int, and a string that is a CANONICAL decimal integer -> int. Two
// consequences this file depends on:
//
//	IDENTITY.  The cast decides what COLLIDES. A path of "5" and a path of the int 5 are the SAME
//	           key, so they dedupe to one entry. Deduping on the raw value would emit two.
//	BYTES.     The key's string form is what gets escaped. For a canonical integer string the
//	           int-cast ROUND-TRIPS ("123" -> 123 -> "123"), so it is byte-neutral — which is why
//	           this returns the string unchanged for that case rather than pretending to be clever.
//	           A float does NOT round-trip: 5.7 becomes key 5 and renders "5", where phpString(5.7)
//	           would render "5.7".
//
// path is a TEXT column (ingest_self.py:43) so string and nil are the only arms live traffic can
// reach, and no real path is numeric — the rest are modelled so that this stays a fact about the
// SCHEMA rather than an assumption this file leans on. The caller preserves FIRST-INSERTION order,
// which is what array_keys() returns.
//
// (PHP 8.1 emits E_DEPRECATED for the lossy float->int key. boot/router.php:11 sets
// `error_reporting(E_ALL & ~E_DEPRECATED)`, so it prints nothing and costs no byte.)
func sourceListArrayKey(v any) string {
	switch x := v.(type) {
	case nil:
		return "" // (string) NULL key === ""
	case bool:
		if x {
			return "1"
		}
		return "0"
	case string:
		return x
	case []byte:
		return string(x)
	case int:
		return strconv.Itoa(x)
	case int32:
		return strconv.FormatInt(int64(x), 10)
	case int64:
		return strconv.FormatInt(x, 10)
	case float32:
		// sourceListDvalToLval, NOT a bare int64(x): PHP casts a float KEY with the same
		// zend_dval_to_lval it uses for (int) (via zend_dval_to_lval_safe, which adds only the
		// silenced 8.1 deprecation), so INF keys to a DEFINED 0 where Go's int64(+Inf) is undefined.
		return strconv.Itoa(sourceListDvalToLval(float64(x)))
	case float64:
		return strconv.Itoa(sourceListDvalToLval(x))
	default:
		return phpString(v)
	}
}

// sourceListPDOQuote is PDO::quote($s) on the sqlite driver — SourceList.php:133's
// `$db->quote($hash)`, the ONE place this tag interpolates a value into SQL instead of binding it.
//
// pdo_sqlite_handle_quoter formats with sqlite3_snprintf's "%Q": wrap in single quotes, double every
// internal single quote. It escapes NOTHING else — sqlite has no backslash escape, so a backslash is
// a literal.
//
// ONE PDO QUIRK IS NOT MODELLED, AND IT CANNOT BE REACHED: "%Q" takes a C string, so a value
// containing a NUL byte is TRUNCATED at it, where this function keeps the whole string. It is
// unreachable twice over — $hash reaches here only AFTER the code_blobs lookup at :105-107 matched a
// row, so it is a stored blob hash (40 hex bytes), and it has already been through trim(), whose
// charlist includes "\0" (engine.go:628-632). Naming it is cheaper than leaving a reader to wonder
// whether it was considered.
func sourceListPDOQuote(s string) string {
	return "'" + strings.ReplaceAll(s, "'", "''") + "'"
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// $_POST — the twin of engine.go's $_GET readers, scoped to this tag's context.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// sourceListPostIsset is `isset($_POST[k])` plus the value — the $_POST twin of engine.go's getIsset
// (engine.go:923-932), and deliberately the same rule, because $_POST and $_GET are populated by the
// same PHP machinery and read by the same idiom.
//
// A key present with an EMPTY value IS still set in PHP (flag= makes isset($_POST['flag']) true with
// the value ""), and SourceList.php:41 branches on isset ALONE — it never tests the value — so
// `flag=` with an empty value DOES trigger doFlag. That is why this returns (value, ok) and the
// caller tests only ok.
//
// PHP takes the LAST value for a repeated scalar key (flag=1&flag=2 makes $_POST['flag'] the string
// "2", since each assignment overwrites), so this returns the last value, as PHP does.
//
// NOT MODELLED, deliberately, because it cannot reach this function: PHP's ARRAY post (flag[]=x)
// makes $_POST['flag'] an array. Go's url.Values keys that body under "flag[]", not "flag", so the
// branch is unreachable through this type rather than mis-rendered by it. Closing it would need a
// $_POST model richer than url.Values, which is the request layer's shape to choose, not this tag's
// (the same call login.go:375-392 made under #316).
func (t *SourceListTag) sourceListPostIsset(k string) (string, bool) {
	if t.ctx == nil || t.ctx.Post == nil {
		return "", false
	}
	vs, ok := t.ctx.Post[k]
	if !ok || len(vs) == 0 {
		return "", false
	}
	return vs[len(vs)-1], true
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The DB handle.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// sourceListOpenDB is `new PDO('sqlite:' . CONGRUENCY_SQLITE)` + setAttribute(ATTR_ERRMODE,
// ERRMODE_EXCEPTION) (SourceList.php:39-40).
//
// IT IS NOT engine.go's openDB, AND THE REASON IS FUNCTIONAL, NOT STYLISTIC. The PHP opens exactly
// ONE handle at :39 and uses it for BOTH the reads and — when $_POST carries a flag — doFlag's
// CREATE TABLE and two INSERTs (:61-71). openDB opens `mode=ro` (engine.go:1180), on which those
// writes would fail and land in the catch arm, rendering an error div where the PHP renders a green
// confirmation panel. So this handle is READ-WRITE, exactly as PDO's is, and it is ONE handle,
// exactly as the PHP's is — which is also what makes LastInsertId belong to the INSERT that just
// ran. annotatehandler.go:487-521 made the same call for the same reason under its own ticket; this
// is that precedent, not a new liberty.
//
// ERRMODE_EXCEPTION needs no counterpart: database/sql returns an error from every call already, and
// every caller turns it into the same cy-form-error div PHP's catch arm produces.
//
// NO os.Stat GUARD, deliberately, and this is the branch openDB would get WRONG here: PHP's
// `new PDO('sqlite:<path>')` CREATES an empty file when the path does not exist (engine.go's header,
// divergence 2) and then throws on the missing TABLE. openDB instead refuses an absent file up front
// (engine.go:1177-1179). Both land in the catch arm and emit the same frame, so no gate byte turns
// on it — but letting the driver create the file is what PDO does, and mirroring it keeps the two
// engines on the same branch for the same reason rather than by coincidence. The file creation is
// PDO's own side effect, it is what the PHP spec does, and it is unreachable whenever the db exists
// — which is every surface the ticket's gate touches.
//
// The sqlite driver is registered by engine.go's blank import of modernc.org/sqlite (engine.go:243),
// the same driver openDB uses — both handles speak to the same file through the same implementation.
func sourceListOpenDB(path string) (*sql.DB, error) {
	// PHP would build the DSN 'sqlite:' . CONGRUENCY_SQLITE. With the constant undefined it throws,
	// but get_document's `!defined('CONGRUENCY_SQLITE')` check (:38) fires FIRST and returns the "no
	// DB." sentence, so PHP never reaches this call with no path. GetDocument makes the same check in
	// the same order; this guard is the belt to that braces, reported through the same error return.
	if path == "" {
		return nil, fmt.Errorf("no database path configured (CONGRUENCY_SQLITE)")
	}
	db, err := sql.Open("sqlite", "file:"+path)
	if err != nil {
		return nil, err
	}
	// One connection, as PDO has one. It serializes doFlag's CREATE TABLE and INSERTs onto the same
	// sqlite connection, which is what makes LastInsertId belong to THIS insert — the same property
	// server.go:25-30 documents for its per-request PDO handle.
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, err
	}
	return db, nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// GetDocument — SourceList::get_document() (SourceList.php:34-48).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// GetDocument is SourceList::get_document() (SourceList.php:34-48).
//
// THE ORDER BELOW IS THE PHP'S ORDER AND IT IS LOAD-BEARING, in three separate ways:
//
//	gate() runs OUTSIDE the try (:35-36), so a deny would never be wrapped in the catch's div.
//	The defined() check (:38) precedes the open (:39), which precedes BOTH $_POST (:41) and
//	  $_GET (:42) — so an unopenable db yields the error div whether or not ?file= or a flag was
//	  supplied; neither input gets a chance to matter.
//	doFlag runs BEFORE $_GET['file'] is read (:41 then :42) and its panel is PREPENDED to whichever
//	  body follows (:43-44). A flag POST that also carries ?file= therefore renders panel-then-view.
//
// AND THE PREPEND IS ABANDONED ON A THROW. `return $flag . $this->view($db, $hash)` (:43) is one
// expression: if view() throws, the catch returns the error div ALONE — the successful flag panel is
// LOST, even though its two INSERTs already committed. That is the PHP's behaviour, reproduced here
// by returning throwableHTML without the flag, not guarded against.
//
// `$hash = isset($_GET['file']) ? trim((string) $_GET['file']) : ''` (:42) is getStr + phpTrim.
// getStr already collapses the ternary's two arms correctly: it returns "" for an unset key
// (engine.go:910-916), which is the same "" the else-arm supplies, and both then fail the `!== ''`
// test at :43 and fall through to the index. The isset/empty distinction that several other tags
// branch on (engine.go:918-921) therefore cannot be observed here — ?file= and no ?file at all
// render the identical index — and that is the PHP's behaviour, because trim("") is "".
//
// phpTrim, not strings.TrimSpace: PHP's trim() charlist is " \t\n\r\0\x0B" — it strips NUL and
// vertical tab but NOT form feed, and it does not touch Unicode spaces (engine.go:628-632). A
// ?file=<hash>\f would keep its \f and miss the blob; TrimSpace would strip it and find one.
func (t *SourceListTag) GetDocument() (out string) {
	defer catchThrowable(&out, "SourceList")

	// :35-36 — the gate, outside the try. Dead while ADMIN_GATED is false.
	if deny, denied := sourceListGate(); denied {
		return deny
	}

	// :38 — !defined('CONGRUENCY_SQLITE'). The same mapping every sibling port uses
	// (doclist.go:338, pagelist.go, engine.go:1742-1744).
	if t.e.cfg.SQLite == "" {
		return "<p>SourceList: no DB.</p>"
	}

	// :39-40 — the ONE read-write handle. See sourceListOpenDB.
	db, err := sourceListOpenDB(t.e.cfg.SQLite)
	if err != nil {
		return throwableHTML("SourceList", err)
	}
	defer db.Close()

	// :41 — $flag = (isset($_POST['flag']) && isset($_POST['flag_hash'])) ? $this->doFlag($db) : "";
	//
	// BOTH tests are isset ONLY — neither looks at the value — so `flag=&flag_hash=` (two empty
	// strings) DOES run doFlag, on the empty hash. Ported as written. With a nil context (the
	// registry default, every GET, and both live surfaces) this is false and $flag stays "".
	flag := ""
	if _, ok := t.sourceListPostIsset("flag"); ok {
		if _, ok := t.sourceListPostIsset("flag_hash"); ok {
			panel, err := t.sourceListDoFlag(db)
			if err != nil {
				return throwableHTML("SourceList", err)
			}
			flag = panel
		}
	}

	// :42 — the one $_GET this tag's top level reads. (index() reads ?p separately, at :86.)
	hash := phpTrim(t.e.getStr("file"))

	// :43
	if hash != "" {
		body, err := t.sourceListView(db, hash)
		if err != nil {
			return throwableHTML("SourceList", err)
		}
		return flag + body
	}

	// :44
	body, err := t.sourceListIndex(db)
	if err != nil {
		return throwableHTML("SourceList", err)
	}
	return flag + body
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// index — SourceList::index($db) (SourceList.php:80-102).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// sourceListIndex is SourceList::index($db) (SourceList.php:80-102) — the RUNNING source, 40 files
// to a page. It is what BOTH gate surfaces render: ?page=tags&tag=SourceList and a bare ?page=source.
//
// THERE IS NO EMPTY-STATE ARM, AND ADDING ONE WOULD BE A DIVERGENCE. :96-101 writes the intro, the
// pager, the <ul>, loops, and closes unconditionally — an empty code_refs renders the intro plus
// "page 1 of 1 (0 files)" TWICE (the pager is emitted above AND below the list) plus
// "<ul class='srclist'>\n</ul>\n" with nothing between, and no sentence. The sibling RepoDocs DOES
// have such an arm (RepoDocs.php:55) and SourceList, like DocList and PageList, pointedly does not;
// tag_selfcheck.py reports an empty code_blobs as WARN (tag_selfcheck.py:91) precisely because this
// renders clean and empty rather than saying anything.
//
// THE APOSTROPHE IN "The CMS's own running source" IS A RAW BYTE. It is a literal ' inside a
// double-quoted PHP string (:96), not data, and htmlspecialchars is never called on it — so it emits
// as ' and NOT as &#039;. esc() here would be a byte diff on the very first line.
//
// THE PAGER IS BUILT ONCE AND EMITTED TWICE, from the same variable (:90-94, used at :96 and :101).
// Both copies are therefore byte-identical by construction; building it twice in Go would invite the
// two to drift.
func (t *SourceListTag) sourceListIndex(db *sql.DB) (string, error) {
	// :81-83 — one JOIN, ORDER BY r.path. The is_current=1 filter is what makes this "the RUNNING
	// source" (ingest_self.py:215-219 clears the flag and re-sets it per ingest).
	//
	// ORDER BY r.path is sqlite's default BINARY collation on a TEXT column — a BYTE ordering, not a
	// locale-aware one. Both engines run the same SQL over the same file, so both see the same order;
	// the port must not "help" by sorting in Go, which would apply a different rule. It is also NOT a
	// total order here: two rows sharing a path (the same file at two commits, both current) tie, and
	// sqlite may return a tie in either order. That is a property of the PHP's own SQL, identical on
	// both sides, not something this port can or should fix.
	rows, err := queryRows(db,
		"SELECT r.path, r.hash, b.lang, b.bytes FROM code_refs r JOIN code_blobs b ON b.hash=r.hash "+
			"WHERE r.is_current=1 ORDER BY r.path")
	if err != nil {
		return "", err
	}

	// :84-85 — $total = count($rows); $per = 40; $pages = max(1, (int) ceil($total / $per));
	//
	// The PHP divides as FLOAT and ceil()s. This is the exact integer ceiling of the same division:
	// $total is a row count, so it is a non-negative int, and for those the two agree everywhere —
	// including $total = 0, where ceil(0/40) is 0.0 and max(1, 0) is 1. Integer math is also exact
	// where the float division would start rounding (above 2^53 rows), so this cannot drift the way
	// transcribing the float form could.
	total := len(rows)
	const per = 40
	pages := (total + per - 1) / per
	if pages < 1 {
		pages = 1
	}

	// :86 — $pg = isset($_GET['p']) ? (int) $_GET['p'] : 1;
	//
	// getIsset, not getStr, to model the ternary exactly. The two happen to agree here — an absent
	// ?p gives 1 directly, and a present-but-empty ?p= gives (int)"" = 0, which :87's clamp lifts to
	// 1 — but the ternary tests isset and so does this.
	pg := 1
	if v, ok := t.e.getIsset("p"); ok {
		pg = sourceListIntCast(v) // NOT toInt — see sourceListIntCast
	}
	// :87 — two SEQUENTIAL ifs, clamping both ends. Order is irrelevant to the result ($pages >= 1),
	// but it is the PHP's shape and costs nothing to keep.
	if pg < 1 {
		pg = 1
	}
	if pg > pages {
		pg = pages
	}

	// :88 — array_slice($rows, ($pg - 1) * $per, $per).
	//
	// The clamps below cannot fire given the clamp at :87 — pg <= pages means off <= total always,
	// and array_slice would return [] for an offset past the end anyway. They are here because a Go
	// slice expression PANICS where array_slice returns [], and a panic is a worse way to learn that
	// an invariant moved than an empty list is.
	off := (pg - 1) * per
	if off > total {
		off = total
	}
	end := off + per
	if end > total {
		end = total
	}
	slice := rows[off:end]

	// :90-94 — the pager. Every interpolated value is an INT, so none is escaped and none must be:
	// strconv, not esc. Note the exact spacing: a space before "page", "(N files)" wrapped in
	// spaces, and a trailing space before the next-link arm.
	var p strings.Builder
	p.WriteString("<div class='pager'>")
	if pg > 1 { // :91 — a real link back, or an INERT <span> on page 1. Both arms always render.
		p.WriteString("<a href='?page=source&p=" + strconv.Itoa(pg-1) + "'>&larr; prev</a>")
	} else {
		p.WriteString("<span>&larr; prev</span>")
	}
	// :92 — " page <strong>$pg</strong> of $pages ($total files) "
	p.WriteString(" page <strong>" + strconv.Itoa(pg) + "</strong> of " + strconv.Itoa(pages) +
		" (" + strconv.Itoa(total) + " files) ")
	if pg < pages { // :93
		p.WriteString("<a href='?page=source&p=" + strconv.Itoa(pg+1) + "'>next &rarr;</a>")
	} else {
		p.WriteString("<span>next &rarr;</span>")
	}
	p.WriteString("</div>\n") // :94
	pager := p.String()

	var b strings.Builder
	// :96 — intro + pager + the <ul>, in that order.
	b.WriteString("<p>The CMS's own running source, addressed by git blob hash.</p>\n")
	b.WriteString(pager)
	b.WriteString("<ul class='srclist'>\n")

	for _, r := range slice {
		// :98-99 — one <li> per row. The space after </a> and the "\n" after </li> are the PHP's;
		// there is no leading indent.
		//
		// EVERY value is escaped exactly where the PHP escapes it. This render flows back through
		// execute_all_tags, so a stored "<<<SourceList>>>" — and the source tree of a CMS whose tags
		// are named in its own docs certainly holds one — must come back
		// "&lt;&lt;&lt;SourceList&gt;&gt;&gt;" and stay inert (engine.go's header, mechanism 2). Do
		// not remove an esc() call.
		//
		// `(int) $r['bytes']` (:99) is a CAST, NOT esc: the PHP casts to int and interpolates the
		// number, so no escaping happens and none is needed. bytes is an INTEGER column
		// (ingest_self.py:42), so PDO hands back an int64 and the cast is identity on it —
		// sourceListIntVal models the cast rather than assuming the column's type, which is what
		// keeps that sentence a fact about the schema instead of a bet on it.
		b.WriteString("<li><a href='?page=source&file=" + esc(r["hash"]) + "'>" + esc(r["path"]) + "</a> " +
			"<span style='color:#888;font-size:.85em'>" + esc(r["lang"]) + " &middot; " +
			strconv.Itoa(sourceListIntVal(r["bytes"])) + " B</span></li>\n")
	}

	// :101 — close the list, then the SAME pager again.
	b.WriteString("</ul>\n")
	b.WriteString(pager)
	return b.String(), nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// view — SourceList::view($db, $hash) (SourceList.php:104-164).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// sourceListView is SourceList::view($db, $hash) (SourceList.php:104-164) — one blob, addressed by
// git blob hash. Reached only via ?file=<hash>, i.e. ?page=source&file=<hash> (the links
// sourceListIndex emits) — the gallery URL carries no file parameter and so never lands here. It is
// the largest unmeasured surface in this unit; see the file header.
//
// THE THREE QUERIES ARE CHAINED THROUGH $path, AND THE CHAIN'S DEGENERATE CASE IS REAL (:111-120):
// the refs query can return NOTHING while the blob EXISTS — a blob whose every ref was deleted. Then
// `$refs ? $refs[0]['path'] : ''` yields "" (:114, PHP's empty-array-is-falsy), and the history query
// runs as `WHERE path=''`, which matches no row. The blob still renders: the head carries an empty
// <strong></strong>, the refs line reads "path:  &middot; in 0 commit(s)" (note the DOUBLE space —
// implode over an empty list yields ""), and count($hist) > 1 is false so no versions line appears.
// That is the PHP's behaviour and it is reproduced, not guarded against.
//
// THE ASSEMBLY ORDER AT :163 IS NOT THE COMPUTATION ORDER. The pieces are computed head, refs, vers,
// form, code — but returned head . refhtml . verhtml . flagForm . code. They are separate strings
// precisely so the two orders can differ; keep them separate.
func (t *SourceListTag) sourceListView(db *sql.DB, hash string) (string, error) {
	// :105-107 — the blob. PHP prepares and binds; so does this. fetch() returns FALSE on no rows,
	// so `if (!$blob)` (:108) is exactly len == 0.
	blobs, err := queryRows(db, "SELECT lang, bytes, body FROM code_blobs WHERE hash=?", hash)
	if err != nil {
		return "", err
	}
	if len(blobs) == 0 {
		// :108 — the unknown-hash state. NO trailing newline; the PHP's string ends at "</p>".
		return "<p>No such source blob <code>" + esc(hash) + "</code>. <a href='?page=source'>&larr; index</a></p>", nil
	}
	blob := blobs[0]

	// :111-113 — every path/commit this blob is (or was) mounted at; the FIRST is the one the head
	// shows. DISTINCT is over the three selected columns TOGETHER, so one path at two commits is two
	// rows — which is exactly why :132's $paths array has to dedupe again by path alone.
	refs, err := queryRows(db, "SELECT DISTINCT path, commit_sha, is_current FROM code_refs WHERE hash=? ORDER BY path", hash)
	if err != nil {
		return "", err
	}

	// :114 — `$path = $refs ? $refs[0]['path'] : '';`. PHP's empty-array-is-falsy supplies the STRING
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

	// :117-119 — every version of THAT path, newest first. GROUP BY hash collapses each version's
	// several refs (one per commit) to one row; MAX(is_current) is "any of them is current", MAX(ts)
	// is the ordering key, and MIN(commit_sha) `c` is SELECTed and NEVER READ — an unused column, not
	// an omission. It is selected here too: dropping it could not change a rendered byte, but keeping
	// the query text identical to the PHP's is the cheaper thing to verify.
	hist, err := queryRows(db, "SELECT hash, MIN(commit_sha) c, MAX(ts) t, MAX(is_current) cur FROM code_refs "+
		"WHERE path=? GROUP BY hash ORDER BY t DESC", path)
	if err != nil {
		return "", err
	}

	// :124 — the live integrity check:
	//
	//	$computed = sha1("blob " . strlen((string) $blob['body']) . "\x00" . (string) $blob['body']);
	//
	// This is git's blob object id: sha1 over the header "blob <bytelen>\0" plus the raw body. THE
	// LENGTH IS IN BYTES, not runes — PHP's strlen counts bytes and Go's len() on a string does too,
	// so a body with any multibyte character hashes the same on both sides. Encoding it as runes
	// would silently break every non-ASCII file's badge.
	//
	// (string) $blob['body'] is phpString: a NULL body casts to "", which hashes to the git blob id
	// of the empty object — a real value, not an error.
	body := phpString(blob["body"])
	computed := fmt.Sprintf("%x", sha1.Sum([]byte("blob "+strconv.Itoa(len(body))+"\x00"+body)))

	// :125-127 — $badge = hash_equals((string) $hash, $computed) ? verified : mismatch.
	//
	// hash_equals is a CONSTANT-TIME string compare; for equal-length inputs it is ==, and for
	// different-length inputs it returns false without comparing. Go's == agrees on the RESULT for
	// every input, which is all that decides a byte here. (The timing property protects a secret
	// comparison; $hash is a public content address read out of the URL, so there is no secret to
	// leak and nothing is lost by ==.) $hash is already a string, so the (string) cast is identity.
	//
	// Both arms are single-quoted PHP strings, so their contents are literal — note the U+2014 EM
	// DASH inside the verified badge's title=, which is a raw byte and not "&mdash;".
	badge := " &middot; <span style='color:#b00020' title='body does NOT match its stored hash'>&#10007; hash mismatch</span>"
	if hash == computed {
		badge = " &middot; <span style='color:#1a7a3a' title='body hashes to its git blob id — content-addressing verified'>&#10003; verified</span>"
	}

	// :128-129 — the head. substr($hash,0,12) is phpSubstr: PHP's substr counts BYTES and this port
	// must too (engine.go:479-482). A hash shorter than 12 bytes yields the whole string on both
	// sides — phpSubstr clamps where a Go slice s[:12] would panic.
	head := "<p><a href='?page=source'>&larr; index</a> &middot; <strong>" + esc(path) + "</strong> " +
		"<span style='color:#888'>(" + esc(blob["lang"]) + " &middot; " + strconv.Itoa(sourceListIntVal(blob["bytes"])) +
		" B &middot; blob " + esc(phpSubstr(hash, 0, 12)) + ")</span>" + badge + "</p>\n"

	// :131-132 — $paths[$r['path']] = 1 (a dedupe that PRESERVES FIRST-INSERTION ORDER, which is what
	// array_keys returns) and the is_current OR-fold, in ONE pass, as the PHP does them.
	//
	// The refs are already ORDER BY path, so first-insertion order is path order — but the PHP's
	// contract is insertion order and that is what this reproduces; leaning on the ORDER BY would be
	// reading the data's shape instead of the code's.
	var pathKeys []string
	seenPath := make(map[string]bool, len(refs))
	isCur := false
	for _, r := range refs {
		k := sourceListArrayKey(r["path"]) // see sourceListArrayKey: the cast decides what collides
		if !seenPath[k] {
			seenPath[k] = true
			pathKeys = append(pathKeys, k)
		}
		if sourceListTruthy(r["is_current"]) { // :132 — truthy, not "not nil"
			isCur = true
		}
	}

	// :133 — count($db->query("SELECT commit_sha FROM code_refs WHERE hash=" . $db->quote($hash))->fetchAll())
	//
	// THE ONLY INTERPOLATED QUERY IN THIS TAG, and it is interpolated in the PHP too — so the port
	// interpolates, through the same PDO::quote rule (sourceListPDOQuote). Rewriting it as a bound
	// parameter would be safe, would be a different SQL string, and would be exactly the kind of
	// "improvement" the ticket forbids.
	//
	// NOTE IT IS NOT DISTINCT and it does NOT reuse $refs: it counts EVERY code_refs row for this
	// hash (one per commit, across all paths), where $refs is DISTINCT over (path, commit_sha,
	// is_current). The two counts genuinely differ, and the label the count feeds says "commit(s)".
	commitRows, err := queryRows(db, "SELECT commit_sha FROM code_refs WHERE hash="+sourceListPDOQuote(hash))
	if err != nil {
		return "", err
	}
	ncommits := len(commitRows)

	// :134-135 — implode(", ", array_map('self::esc', array_keys($paths))).
	//
	// esc() is applied PER KEY and the ", " separator is joined AFTER, so the separator itself is
	// never escaped. Over an EMPTY $paths this yields "", leaving "path: " immediately followed by
	// " &middot;" — the double space named in this function's doc comment.
	//
	// ('self::esc' as a string callable is deprecated in PHP 8.2+ and boot/router.php:11 sets
	// error_reporting(E_ALL & ~E_DEPRECATED), so the notice prints nothing and costs no byte.)
	escaped := make([]string, 0, len(pathKeys))
	for _, k := range pathKeys {
		escaped = append(escaped, esc(k))
	}
	refhtml := "<p style='font-size:.85em;color:#666'>path: " + strings.Join(escaped, ", ") +
		" &middot; in " + strconv.Itoa(ncommits) + " commit(s)"
	if isCur { // :135 — the ternary emits NOTHING, not an empty span, when no ref is current.
		refhtml += " &middot; <em>current</em>"
	}
	refhtml += "</p>\n"

	// :137-146 — the versions line, which appears ONLY when the path has MORE THAN ONE version. A
	// file with a single version renders no line at all, not an empty one.
	verhtml := ""
	if len(hist) > 1 {
		var v strings.Builder
		v.WriteString("<p style='font-size:.85em'>versions of this file: ") // :139
		for _, h := range hist {
			// :142 — NOTE THE ORDER: esc() wraps ONLY the 9-byte hash prefix, and the "*" is
			// concatenated AFTER it. Escaping the assembled label would be the same bytes today
			// (hex digits and '*' are all esc-inert) but it is not what the PHP writes.
			lab := esc(phpSubstr(phpString(h["hash"]), 0, 9))
			if sourceListTruthy(h["cur"]) {
				lab += "*"
			}
			// :141, :143 — the CURRENT selection is bold and unlinked; every other version is a
			// link. Both arms end with a trailing space, and that space is a rendered byte. The
			// selection test is STRICT (===), not ==; see sourceListIdenticalString.
			if sourceListIdenticalString(h["hash"], hash) {
				v.WriteString("<strong>" + lab + "</strong> ")
			} else {
				v.WriteString("<a href='?page=source&file=" + esc(h["hash"]) + "'>" + lab + "</a> ")
			}
		}
		v.WriteString("</p>\n") // :145
		verhtml = v.String()
	}

	// :148-155 — the line-numbered <pre>. ESCAPE FIRST, THEN SPLIT, and that order is not
	// interchangeable: the PHP escapes the WHOLE body once (:148) and explodes the ESCAPED string
	// (:149). Splitting first and escaping per line would be the same bytes here only because
	// htmlspecialchars neither produces nor consumes a "\n" — the PHP's order is cheaper to verify
	// than that argument is, so it is the order kept.
	//
	// explode("\n", "") yields ONE empty element, so an EMPTY body renders exactly one numbered blank
	// line ("   1  \n"), not zero lines. And a body ending in "\n" — every source file does — yields
	// a trailing "" element, so every real file gets ONE EXTRA numbered blank line at the end.
	// strings.Split agrees with explode on both. Neither is a bug to fix.
	escBody := esc(blob["body"])
	lines := strings.Split(escBody, "\n")
	var c strings.Builder
	c.WriteString("<pre style='background:#f4f1e8;border:1px solid #d8d2c4;padding:.6rem;overflow:auto;font-size:.82rem;line-height:1.4'>")
	for i, ln := range lines {
		// :153 — sprintf('%4d', $n++): right-aligned, SPACE-padded, minimum width 4; a line number
		// of 10000+ simply widens. Go's %4d is the same rule. NOTE THE TWO SPACES between the
		// closing </span> and the line's text, and the "\n" that ends every line INCLUDING the last.
		c.WriteString("<span style='color:#b0a890;user-select:none'>" + fmt.Sprintf("%4d", i+1) + "</span>  " + ln + "\n")
	}
	c.WriteString("</pre>\n") // :155

	// :157-161 — the flag form. It POSTs back to the same URL, which is the ONLY way doFlag is ever
	// reached. The submit button's name is `flag` and the hidden field is `flag_hash` — the two keys
	// get_document's :41 isset-tests, which is why a click arrives as a flag POST.
	//
	// style='width:55%' is a literal '%' in a PHP string, not a format directive — this is a
	// concatenation, not a printf. Keep it out of any Sprintf.
	flagForm := "<form method='POST' style='margin:.5rem 0;font-size:.9rem'>" +
		"<input type='hidden' name='flag_hash' value='" + esc(hash) + "'>" +
		"<input type='hidden' name='flag_path' value='" + esc(path) + "'>" +
		"<input type='text' name='flag_note' placeholder='why flag this? (optional)' style='width:55%'> " +
		"<input type='submit' name='flag' value='&#9873; flag for follow-up'></form>\n"

	// :163 — the assembly order, which is NOT the computation order above.
	return head + refhtml + verhtml + flagForm + c.String(), nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// doFlag — SourceList::doFlag($db) (SourceList.php:54-78). THE WRITE PATH.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// sourceListDoFlag is SourceList::doFlag($db) (SourceList.php:54-78) — flag a source blob for
// follow-up.
//
// WHAT IT IS. Two writes, in order, and the second depends on the first:
//
//	1. an `annotations` row — the abstract backing, a `tag` ('flag') applied to an opaque `target`
//	   ref ("source:<hash>"), the shape the PHP's own comment at :50-53 describes as letting
//	   "anything be tagged with anything" (the #132 unify-tagging idea);
//	2. a `tickets` row — a `refactor` follow-up PROJECTION, linked back to the annotation by id
//	   through its meta.
//
// NO GATE REQUEST REACHES IT. It runs only when $_POST carries both `flag` and `flag_hash` (:41),
// and the only caller that can supply a $_POST is one that builds the tag through NewSourceListTag
// with a non-nil context. The registry factory passes nil; RenderTag builds its own Engine and
// passes nil; every GET has no $_POST. So the ticket's diffs, the #282 harness and the live Go
// server all take the `flag = ""` arm and this function is never entered. It is ported because the
// PHP has it, not because anything here runs it — and it is the part of this unit with the least
// measurement behind it, which is said here rather than left to be discovered.
//
// PDO BINDS EVERY PARAMETER AS A STRING. PDOStatement::execute($array) treats all values as
// PDO::PARAM_STR, so $now — a float from microtime(true) — goes in through PHP's float->string cast,
// which uses the `precision` ini (default 14), NOT serialize_precision. phpFloatString is exactly
// that cast (engine.go:524-547). The ts columns are REAL, so sqlite's column affinity converts the
// string back to a float on the way in — on both sides, identically, because both sides send the
// same string. annotatehandler.go:427-430 made the same call under its own ticket.
//
// The values it writes are DB CONTENT, not rendered bytes: only $id, $path and the 12-byte hash
// prefix reach the returned panel. They are still modelled exactly, because a port that stores
// different rows than the PHP has not ported the tag — it has ported the tag's HTML.
func (t *SourceListTag) sourceListDoFlag(db *sql.DB) (string, error) {
	// :55 — trim((string) $_POST['flag_hash']), read with NO isset guard. Safe: get_document's :41
	// already isset-tested this exact key, which is the only way control arrives here.
	rawHash, _ := t.sourceListPostIsset("flag_hash")
	hash := phpTrim(rawHash)

	// :56-57 — these two ARE isset-guarded, so an absent key is '' rather than a NULL-cast warning.
	path := ""
	if v, ok := t.sourceListPostIsset("flag_path"); ok {
		path = phpTrim(v)
	}
	note := ""
	if v, ok := t.sourceListPostIsset("flag_note"); ok {
		note = phpTrim(v)
	}

	// :58 — microtime(true): the current unix time in SECONDS as a float, to microsecond resolution.
	// It reads the engine's clock seam (Config.Now, engine.go:334-335, 375-379) rather than time.Now
	// directly, so a caller driving this path can pin the instant; a nil Now is time.Now, the live
	// path. Bound as a STRING — see this function's doc comment.
	now := phpFloatString(float64(t.e.cfg.now().UnixNano()) / 1e9)

	// :61 — $db->exec("CREATE TABLE IF NOT EXISTS annotations (...)"), verbatim. The tag makes its
	// own table rather than depending on a migration, which is why it works against a db that never
	// had one. The column list matches ingest_self.py:48's annotations schema exactly.
	if _, err := db.Exec("CREATE TABLE IF NOT EXISTS annotations (id INTEGER PRIMARY KEY AUTOINCREMENT, tag TEXT, target TEXT, note TEXT, ts REAL, meta TEXT)"); err != nil {
		return "", err
	}

	// :62-63 — the annotation. NOTE 'flag' IS A SQL LITERAL IN THE PHP'S QUERY TEXT, not a bound
	// parameter: the statement is `VALUES ('flag',?,?,?,?)` with FOUR placeholders, not five.
	an, err := db.Exec("INSERT INTO annotations (tag,target,note,ts,meta) VALUES ('flag',?,?,?,?)",
		"source:"+hash, note, now, sourceListJSONPath(path))
	if err != nil {
		return "", err
	}
	// :64 — $aid = (int) $db->lastInsertId();
	aid, err := an.LastInsertId()
	if err != nil {
		return "", err
	}

	// :67 — $title = "Source flag: " . $path;
	title := "Source flag: " + path

	// :68 — $body = ($note !== '' ? $note . "\n\n" : "") . "flagged source blob "
	//              . substr($hash, 0, 12) . " \u{00b7} " . $path;
	//
	// The `!== ''` is STRICT, but $note is already a string (trim() returns one), so it is plain
	// string equality here — no sourceListIsEmptyString helper is needed or wanted.
	//
	// "\u{00b7}" is a PHP 7+ unicode escape inside a double-quoted string: it is the CHARACTER U+00B7
	// MIDDLE DOT (bytes 0xC2 0xB7), not the six literal characters. Go's "·" is the same
	// character. This is DB content and is NOT escaped — no htmlspecialchars anywhere on this line.
	body := ""
	if note != "" {
		body = note + "\n\n"
	}
	body += "flagged source blob " + phpSubstr(hash, 0, 12) + " · " + path

	// :69 — the meta, linking the ticket back to the annotation just written.
	meta := sourceListJSONMeta(aid, "source:"+hash, path)

	// :70-71 — the follow-up ticket. 'OPEN' is a SQL literal in the query text (as 'flag' was above),
	// so this statement has SEVEN placeholders for eight columns. The tickets schema is
	// migrations/0002_ticket_approval.sql:12-15.
	st, err := db.Exec("INSERT INTO tickets (ts,updated,component,title,severity,status,body,meta) VALUES (?,?,?,?,?,'OPEN',?,?)",
		now, now, "refactor", title, "low", body, meta)
	if err != nil {
		return "", err
	}
	// :72 — $id = (int) $db->lastInsertId();
	id, err := st.LastInsertId()
	if err != nil {
		return "", err
	}

	// :74-77 — the green panel. Byte-for-byte the PHP's concatenation, in its order, including the
	// trailing "\n" after </div> — which is what separates the panel from the index or view that
	// GetDocument appends after it.
	//
	// $id is an INT interpolated into the string (:76), so it is NOT escaped and must not be:
	// strconv, not esc. $path and the hash prefix ARE esc()'d, exactly where the PHP esc()'s them.
	return "<div style='border:1px solid #1a7a3a;border-left:5px solid #1a7a3a;background:#f3fbf5;padding:.5rem .8rem;margin:.5rem 0'>" +
		"&#9873; Flagged for follow-up &mdash; annotation <code>flag &rarr; source:" + esc(phpSubstr(hash, 0, 12)) +
		"</code>, <strong>ticket #" + strconv.FormatInt(id, 10) + "</strong> (" + esc(path) +
		"). <a href='?page=tickets'>see the backlog &rarr;</a></div>\n", nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// json_encode — SourceList.php:63 and :69. DB content only; no rendered byte turns on it.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// sourceListJSONString is PHP's json_encode() applied to a single STRING, with the DEFAULT flags —
// the encoder SourceList.php:63 and :69 reach through json_encode(array(...)).
//
// PHP'S DEFAULTS ARE NOT GO'S AND encoding/json COULD NOT BE USED HERE. The three differences, each
// of which changes stored bytes:
//
//	SLASHES.    PHP escapes "/" as "\/" unless JSON_UNESCAPED_SLASHES is passed. It is not passed.
//	            EVERY path in code_refs contains a slash, so this is the COMMON case, not an edge:
//	            "tools/x.py" stores as "tools\/x.py".
//	NON-ASCII.  PHP escapes every non-ASCII rune as \uXXXX (UTF-16, lowercase hex, surrogate PAIRS
//	            above the BMP) unless JSON_UNESCAPED_UNICODE is passed. It is not passed. Go emits
//	            the raw UTF-8 instead.
//	HTML.       Go's encoding/json escapes <, > and & to </>/& by default. PHP does
//	            NOT (that is JSON_HEX_TAG/JSON_HEX_AMP, unpassed), so they stay literal.
//
// ok=false is json_encode returning FALSE, which it does for INVALID UTF-8 (the default has no
// JSON_INVALID_UTF8_SUBSTITUTE). The callers below then bind (string) false === "", which is PHP's
// own behaviour for that input — a silently empty meta column, not an error. Reachable only if a
// path or note is not valid UTF-8; ingest_self.py writes real repo paths, and a $_POST body is
// whatever the client sent.
func sourceListJSONString(s string) (string, bool) {
	var b strings.Builder
	b.WriteByte('"')
	for i := 0; i < len(s); {
		c := s[i]
		if c < utf8.RuneSelf {
			switch c {
			case '"':
				b.WriteString(`\"`)
			case '\\':
				b.WriteString(`\\`)
			case '/':
				b.WriteString(`\/`)
			case '\b':
				b.WriteString(`\b`)
			case '\f':
				b.WriteString(`\f`)
			case '\n':
				b.WriteString(`\n`)
			case '\r':
				b.WriteString(`\r`)
			case '\t':
				b.WriteString(`\t`)
			default:
				if c < 0x20 {
					// PHP spells the remaining control characters \u00XX with LOWERCASE hex.
					b.WriteString(fmt.Sprintf(`\u%04x`, c))
				} else {
					b.WriteByte(c)
				}
			}
			i++
			continue
		}
		r, size := utf8.DecodeRuneInString(s[i:])
		if r == utf8.RuneError && size <= 1 {
			return "", false // invalid UTF-8 -> json_encode returns false
		}
		if r > 0xFFFF {
			// PHP emits a UTF-16 SURROGATE PAIR for an astral rune (an emoji in a note reaches
			// this): U+1F600 becomes "😀", not "ὠ0".
			r -= 0x10000
			b.WriteString(fmt.Sprintf(`\u%04x\u%04x`, 0xD800+(r>>10), 0xDC00+(r&0x3FF)))
		} else {
			b.WriteString(fmt.Sprintf(`\u%04x`, r))
		}
		i += size
	}
	b.WriteByte('"')
	return b.String(), true
}

// sourceListJSONPath is json_encode(array('path' => $path)) (SourceList.php:63) — the annotation's
// meta column.
//
// PHP encodes a string-keyed array as a JSON OBJECT, and the key is encoded by the same rules as a
// value; 'path' is plain ASCII with nothing to escape, so it is spelled as the literal it always
// produces. "" is (string) false — see sourceListJSONString.
func sourceListJSONPath(path string) string {
	v, ok := sourceListJSONString(path)
	if !ok {
		return ""
	}
	return `{"path":` + v + `}`
}

// sourceListJSONMeta is json_encode(array('source' => 'source-flag', 'annotation' => $aid,
// 'target' => "source:" . $hash, 'path' => $path)) (SourceList.php:69) — the ticket's meta column.
//
// KEY ORDER IS INSERTION ORDER. PHP arrays are ordered maps and json_encode walks them in insertion
// order, so the four pairs come out source, annotation, target, path — exactly as written at :69.
// Go's encoding/json sorts a map's keys alphabetically (annotation, path, source, target), which is
// another reason it could not be used here.
//
// $aid is an INT, so it is encoded as a JSON NUMBER — unquoted. It comes from `(int)
// $db->lastInsertId()` (:64), and the two literal strings hold no character PHP's default flags
// escape, so they are spelled as the literals they always produce.
func sourceListJSONMeta(aid int64, target, path string) string {
	t, ok := sourceListJSONString(target)
	if !ok {
		return ""
	}
	p, ok := sourceListJSONString(path)
	if !ok {
		return ""
	}
	return `{"source":"source-flag","annotation":` + strconv.FormatInt(aid, 10) +
		`,"target":` + t + `,"path":` + p + `}`
}
