package tags

// sitemap.go — ticket #331, unit go-port:tags:tag:SiteMap.
//
// The Go port of ONE tag: invocators/tags/dev/SiteMap.php — the site nav, built from the Documents
// that actually exist rather than hardcoded. The app serves it standalone at ?page=tags&tag=SiteMap,
// and 25 stored page templates embed <<<SiteMap>>> (the in-page substitution sites named by this
// unit's ticket).
//
// THE PHP SOURCE IS NOT AT THE PATH THE TICKET PRINTS. The ticket says
// `invocators/tags/dev/SiteMap.php`; that path does not resolve from the repo root. The file is at
// checkouts/current/congruency/invocators/tags/dev/SiteMap.php — the ticket's paths are relative to
// the congruency CHECKOUT, not the mono root (the same relative-path convention tools/ and
// configure.php use). Every ":NN" citation below is a line in THAT file, read this session. It is
// 56 lines; the whole tag is :16-55.
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. The PHP is the SPEC — where the two
// disagree THIS file is wrong, and "improving" the nav here is a defect, not a fix. TWO PHP
// behaviours below look like bugs and are reproduced deliberately; each is named at the code that
// needs it so a later reader does not "correct" one back into a divergence.
//
// ── WHAT THIS FILE ADDS, AND WHAT IT DOES NOT TOUCH ─────────────────────────────────────────────
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers, and its self-registration (the init() below). Nothing in engine.go changes — the registry
// picks this tag up because Go runs every init() in a package before any other code in it (Register
// at engine.go:1355, newTag at engine.go:1393). Every identifier this file defines is siteMap*- or
// SiteMap*-named, so it cannot collide with the sibling tag ports. Checked this session by grepping
// congruency-go/tags/*.go for siteMap/SiteMap: the ONLY pre-existing occurrences of the string are
// five COMMENT lines (engine.go:197's COVERAGE list; newcategoryhandler.go:96,269 and
// annotatehandler.go:59,202, which mention <<<SiteMap>>> as an unported tag inside their own page
// frames). No identifier collides.
//
// (engine.go's COVERAGE header still lists SiteMap under "NOT PORTED (35)" at :197. That list is a
// hand-maintained COPY; its own text names PortedTags() as "the authority" (engine.go:189-192), and
// PortedTags is registry-derived (engine.go:1406-1415), so it answers correctly the moment this
// file's init() runs. Correcting the copy means editing engine.go, which this ticket forbids ("touch
// nothing else") — the same stale-copy state #312, #316, #319 and #324 left behind for DocList,
// Login, MemoryList and PageList. It is a comment, not behaviour.)
//
// It REUSES engine.go's audited PHP primitives rather than restating them: esc
// (htmlspecialchars((string)$s, ENT_QUOTES), engine.go:599), openDB (engine.go:1173) and queryColumn
// (fetchAll(PDO::FETCH_COLUMN), engine.go:1247). It does NOT reuse a sibling UNIT's helpers — those
// files are other tickets' deliverables, and depending on them would couple this unit's bytes to
// edits made under another unit's authority (#324's header states the same rule). engine.go is the
// shared floor; a sibling tag file is not.
//
// IT DELIBERATELY DOES NOT USE catchThrowable, AND THAT IS THE SHARPEST REUSE TRAP IN THIS FILE.
// See siteMapCatch below: this tag's catch arm emits an HTML COMMENT, not the cy-form-error DIV that
// catchThrowable (engine.go:1715-1719) hardcodes. Reaching for the shared helper here — the obvious
// move, and what every sibling port does — emits the wrong frame on the one path it exists to cover.
//
// ── THE PHP RULE THAT DECIDES THIS TAG'S BYTES: $have IS A PHP ARRAY, NOT A SET OF STRINGS ──────
//
// :29 builds the page set by using each DocumentID AS AN ARRAY KEY:
//
//	foreach (... fetchAll(PDO::FETCH_COLUMN) as $id) { $have[$id] = 1; }
//
// A PHP array key is NOT the value you hand it. PHP casts it: a canonical decimal integer STRING
// becomes an INT key, and NULL becomes the EMPTY-STRING key. Three consequences decide rendered
// bytes, and a port that models $have as a Go []string or map[string]bool gets all three wrong:
//
//	ORDER      array_keys($have) at :42 is INSERTION order, and :41's unset() removes a key without
//	           reordering the rest. The extras therefore come out in the DB's row order minus the
//	           ones $order already claimed — not sorted, and not re-sorted by the removals.
//	IDENTITY   "123" and 123 are the SAME key. Injective on distinct strings, so canonical ints
//	           round-trip to identical BYTES ((string)(int)"123" === "123") — but NULL and "" collide
//	           on the "" key, so several NULL DocumentIDs (which a SQLite TEXT PRIMARY KEY permits:
//	           its UNIQUE index allows multiple NULLs) collapse to ONE nav link, not N.
//	TYPE       an extras key can be an int64, and :46's isset($label[$id]) then CANNOT match — every
//	           key in $label is a non-numeric string. See siteMapLabelOf.
//
// siteMapArray + siteMapArrayKey below model exactly this, and nothing more.
//
// ── TWO PHP BEHAVIOURS THAT LOOK LIKE BUGS AND ARE PORTED AS-IS ─────────────────────────────────
//
//	"Source" TWICE   :37's $label maps BOTH 'source' => 'Source' AND 'tree' => 'Source', and :38's
//	                 $order lists both. A db with both pages renders two adjacent, identically-titled
//	                 "Source" links to DIFFERENT hrefs (?page=tree and ?page=source). Faithful.
//	lowercase gaps   :38's $order names 'forms', 'tickets' and 'memories', which $label does NOT
//	                 cover — so :46 falls back to the raw id and they render lowercase among their
//	                 Capitalised neighbours. (The PHP's own :49 comment says the all-caps styling
//	                 lives in <<<Style>>>, which is why this is invisible in a browser and very
//	                 visible in a byte diff.) Faithful.
//
// A THIRD looked like a bug and IS NOT — recorded because the check that cleared it is cheap and the
// wrong conclusion is expensive. :51 wraps esc($e->getMessage()) in an HTML COMMENT, and
// htmlspecialchars does not escape "-", which invites the reading that a message containing "-->"
// closes the comment early and spills markup. IT CANNOT: htmlspecialchars DOES escape ">", so no ">"
// survives the esc at all and neither "-->" nor "--!>" can form. Measured, not reasoned: the
// transliteration renders `oops --> <script>` as "<!-- SiteMap error: oops --&gt; &lt;script&gt; -->".
// The esc() is load-bearing for that, which is the reason siteMapError keeps it exactly where the PHP
// puts it.
//
// ── THE DEPENDENCY, AND HOW IT DEGRADES (the ticket's "degrade IDENTICALLY") ────────────────────
//
// tools/tag_selfcheck.py's three dependency kinds (its docstring, "WHAT IT CHECKS", :11-31) resolve
// for this tag to exactly one: (2) SQL TABLES against CONGRUENCY_SQLITE — a single table,
// `Documents`, created by every page migration as
//
//	Documents(DocumentID TEXT PRIMARY KEY, TemplateID INTEGER, Title TEXT, Description TEXT,
//	          ContentID INTEGER)                          (e.g. migrations/0023_bug_catalog.sql:68-74)
//
// No getenv/external db (kind 1) and no repos.forge_remote (kind 3) — this tag's SQL names no other
// table. The three degradation states, in the order GetDocument can reach them:
//
//	CONGRUENCY_SQLITE undefined -> "<!-- SiteMap: no DB -->"                       (SiteMap.php:25)
//	the open or the query throws -> "<!-- SiteMap error: … -->"                              (:51)
//	table present but EMPTY      -> "" — THE EMPTY STRING, not an empty-state notice. :44-49 builds
//	                                an empty $links and implodes it, and implode(array()) is "".
//	                                The tag renders NOTHING and the <nav> around it stays empty.
//
// THE MISSING-TABLE CASE IS THE ONE THAT THROWS: SiteMap sets PDO::ERRMODE_EXCEPTION (:27), so a
// missing Documents raises PDOException and lands in the catch — it does NOT degrade silently.
//
// ── WHAT IS NOT BYTE-REPRODUCIBLE, STATED PLAINLY (the catch arm only) ──────────────────────────
//
// PHP's catch renders self::esc($e->getMessage()) (:51) — for a missing table, "SQLSTATE[HY000]:
// General error: 1 no such table: Documents". The message inside is a Go database/sql error, which
// has no SQLSTATE text, so the FRAME is byte-identical and the message is not, and is not claimed to
// be. This is the package's standing, documented limitation (annotatehandler.go:134-142), not a new
// one, and it is unreachable on any gate surface whose db actually has the Documents table.
//
// NOTE WHAT IS **ABSENT** HERE, because it is what distinguishes this catch from its siblings':
// there is NO get_class($e) PREFIX. PageList's and MemoryList's catches print "Class: message"
// (pagelist.go:336-353, memorylist.go:362-368); SiteMap's, like DocList's and TreeView's, prints
// getMessage() ALONE. Borrowing PageList's frame — the nearest sibling, and the one this file's
// structure otherwise mirrors — would prepend a "PDOException: " that the PHP never writes. That is
// a byte diff on the error path, so siteMapError takes a message and no class.
//
// One related PHP behaviour is worth naming because it decides WHICH branch a missing db file takes:
// PHP's `new PDO('sqlite:<path>')` CREATES an empty file when the path does not exist (engine.go's
// header, divergence 2), so PHP proceeds and then throws on the missing TABLE. openDB instead
// returns an error for an absent file (engine.go:1177-1179). Both land in the catch arm and emit the
// same frame; only the message inside differs, as above.
//
// ── THE GATE — WHAT THE TICKET ASKS FOR, WHAT IS RUNNABLE HERE, AND WHAT WAS RUN ────────────────
//
// The ticket's gate is two byte-diffs, PHP:8899 vs Go:8900, over the same db: the gallery render of
// this tag, and each of the 25 pages that embed it.
//
// NEITHER CAN BE RUN FROM THIS WORKTREE, and both are additionally confounded on their own terms.
// Stating this rather than settling on a green-looking diff is what the ticket asks for — "if you
// cannot make a diff here run against THIS unit, say so on the ticket rather than settling on a diff
// that would be empty even with the unit unimplemented".
//
// WHY IT CANNOT BE RUN HERE — three independent walls, each re-checked this session (#324's header
// recorded the same three; they have not moved):
//
//	NO PHP.  The ticket names tooling/congruencey-harness/php/php as allowed. `ls` reports no such
//	         file — the whole php/ directory is absent — and `which php` finds nothing on PATH. It is
//	         PROVISIONED, not committed, BY DESIGN: provision_php.py's docstring opens "The mono ships
//	         NO binaries (they don't belong in git); instead this python recipe places a php binary
//	         into <mono>/<paths.php>" (:4-6), and .gitignore ignores that directory outright.
//	NO DB.   Both engines must read the SAME congruency.sqlite (configure.php:42 puts it at
//	         checkouts/current/state/congruency.sqlite). That file is git-ignored, and a glob for
//	         **/*.sqlite across the whole worktree returns NOTHING. Without the shared db there is no
//	         "same database" for a diff to be over — and for THIS tag the db is not incidental:
//	         Documents IS its entire input.
//	NO GO.   A `go` binary is on PATH, but every invocation of it is refused by this session's
//	         permission layer before it starts. `go build ./...` was attempted plainly and with the
//	         sandbox override, and `go version` once; all three were denied. So the :8900 side of
//	         every diff cannot be built, let alone served. The binary existing and being unrunnable
//	         are easy to confuse, hence the detail: do not conclude from `which go` that this file
//	         was compiled.
//
// WHY BOTH DIFFS ARE CONFOUNDED EVEN WITH THE SERVERS UP — each would be exactly as non-empty with
// this file deleted, so neither measures this unit:
//
//	diff 1  ?page=tags&tag=SiteMap   The PHP returns a FULL CMS page; the Go server does not
//	                                 reproduce the page frame and says so itself (server.go:39-43,
//	                                 62-66: "NOT claimed: that the page's BYTES match PHP … larger by
//	                                 a constant ~6.2 KB of CMS chrome"). The tag's own bytes are a
//	                                 SLICE of that page (equivalence_test.go:28-33).
//	diff 2  the 25 embedding pages   server.go's handlePage routes EVERY page key except "tags" to
//	                                 handleCatalogPage, the table-list seam that never invokes the
//	                                 tag engine (server.go:727-735, 831-833). So ?page=about and its
//	                                 24 siblings cannot reach SiteMap at all on the Go server. Wiring
//	                                 them is an edit to server.go, which this ticket forbids.
//
// THE REAL GATE, which exists precisely because of diff 1's confound, is #282's harness — and #323
// settled that this, not diff 1, is where a tag-unit gate belongs:
//
//	cd congruency-go && go test ./tags/ -run TestTagEquivalence/SiteMap -v
//
// It cuts the tag's own bytes out of the live PHP page with TagList.php's own anchors and compares
// them to RenderTag's, with a stability sandwich against concurrent writers. It needs the live 8899
// and the shared state db; absent either it SKIPS (its four guards, equivalence_test.go:115-120). It
// requires NO edit to run this tag — it sweeps Scan(TAGS_DIR) and measures whatever IsPorted
// reports, so the init() below is the whole wiring.
//
// ONE CAVEAT SPECIFIC TO THIS TAG, which whoever runs that harness must know: SiteMap reads the
// Documents table, which the pair_loop agents and the migrations both write. It is therefore VOLATILE
// in exactly the way the harness's php1/go/php2 sandwich exists to absorb — a page added between the
// two PHP fetches reports VOLATILE, not a divergence. That is a data difference, not an engine
// difference (#227's header).
//
// THIS GO CODE WAS NOT COMPILED OR EXECUTED, AND THAT IS A REAL GAP IN THIS DELIVERABLE. It must be
// said plainly rather than left for the reader to discover. The usual floor ("RUN your own work
// before reporting done") could not be met: the Go below is reviewed, not run, and a compile error
// or a runtime panic in it would be a live defect no step in this session could have caught. The
// FIRST thing to do with this file is:
//
//	cd congruency-go && go build ./... && go vet ./tags/
//
// WHAT WAS ACTUALLY RUN THIS SESSION — three things, and NONE of them EXECUTES this file's Go:
//
//  1. A PYTHON TRANSLITERATION of SiteMap.php's get_document(), modelling PHP's array-key cast, the
//     insertion-ordered array with unset(), isset()'s NULL rule, the (string) casts esc() performs,
//     and implode(). A 34-case quirk suite over it passed 34/34 and CONFIRMED, as behaviour rather
//     than as my assertion, each quirk documented above:
//
//	the key cast          "123" keys as int 123 and renders back "123" (lossless); "007", "1.5",
//	                      " 1", "+1", "-0" and "9223372036854775808" all stay STRING keys; NULL
//	                      keys as "" and TWO NULL rows collapse to ONE link, not two.
//	insertion order       extras follow DB row order, not sorted order, and :41's unset does not
//	                      disturb the survivors' relative order.
//	the empty state       0 rows render "" exactly — no <nav> filler, no notice.
//	the block list        all 10 blocked ids are dropped from BOTH loops; 'about' and 'catalog'
//	                      never render even though their own pages embed the tag.
//	"Source" twice        tree+source both present renders two "Source" links to different hrefs.
//	lowercase gaps        forms/tickets/memories render lowercase; the labelled ones do not.
//	the separator         exactly " &nbsp;&middot;&nbsp; ", and a ONE-link nav has none.
//	escape/recursion      a DocumentID of "<<<SiteMap>>>" comes back "&lt;&lt;&lt;SiteMap&gt;&gt;&gt;"
//	                      with no raw "<<<" surviving; "it's" escapes to "&#039;" (PHP's spelling,
//	                      not Go's html pkg's "&#39;"); "a&b" to "a&amp;b".
//	degradation           the no-DB comment and the error comment exactly, the latter with NO
//	                      get_class prefix.
//
//  2. A MECHANICAL LITERAL DIFF of the two REAL FILES — it parses SiteMap.php and the non-comment
//     lines of THIS file and compares them, because transcribing three constant tables by hand is the
//     highest byte-risk part of this port and the one thing eyeballing reliably misses. Confirmed, as
//     parsed output rather than as my assertion:
//
//	$block   the same 10 keys.
//	$label   the same 16 pairs, values byte-equal — INCLUDING the duplicate the parser found on
//	         its own and named: 'Source' <- ['source', 'tree']. That defect is the PHP's, not a
//	         transcription slip of mine.
//	$order   the same 19 ids IN THE SAME SEQUENCE (order is data here, so membership alone would
//	         not have been enough).
//	markup   every markup literal in the PHP — " &nbsp;&middot;&nbsp; ", "<!-- SiteMap error: ",
//	         "<!-- SiteMap: no DB -->", "</a>", "<a href='?page=" — appears VERBATIM in the Go,
//	         the separator's leading and trailing spaces included.
//	traps    the Go calls NO catchThrowable and contains NO cy-form-error frame (both would be the
//	         wrong frame for this tag — see siteMapCatch).
//	claims   the "no id is in both $order and $block" claim at GetDocument's first loop was
//	         CHECKED against the two real literals, not assumed: the intersection is empty.
//
//  3. A DIFFERENTIAL FUZZ of the two renders. Checks 1 and 2 both test my reading of the PHP; this one
//     tests THE TRANSCRIPTION — it writes the tag out twice from two different sources (one from SiteMap.php
//     line by line, one from THIS file's GetDocument statement by statement, mirroring
//     siteMapArray/siteMapArrayKey/siteMapLabelOf/esc) and diffs the bytes. Over 20,000 random
//     DocumentID sets of 0-8 ids drawn from a 40-value corpus (every $order id, every $block id, NULL,
//     "", "0", "007", "123", "-5", "1.5", "it's", "a&b", "<<<SiteMap>>>", "café", …) and then
//     EXHAUSTIVELY over all 1,600 ordered PAIRS of that corpus, plus the three degradation paths
//     (no-DB, a throw with markup in it, a throw containing "-->"): 20000/20000, 1600/1600 and 3/3
//     byte-identical.
//
//     ITS WEAKNESS, STATED RATHER THAN LEFT TO BE FOUND: the go-derived side is hand-transliterated
//     from the Go by the same author, so a MISREADING of the Go could be duplicated on both sides. It
//     catches a swapped concatenation, a dropped space, or a set-vs-array mix-up; it is not a
//     substitute for `go build`, and it does not execute one line of the Go below.
//
// None of the three is the PHP interpreter (no PHP exists here to run), none EXECUTES this file's Go,
// and none is the gate. Checks 1 and 2 raise confidence that the SPEC ENCODED BELOW is the spec
// SiteMap.php actually implements; check 3 raises confidence that the Go expresses that spec. All
// three are silent on whether the Go COMPILES.
//
// ONE CLAIM IN THIS HEADER WAS REFUTED BY ITS OWN CHECK AND IS RECORDED RATHER THAN QUIETLY DROPPED:
// an earlier draft called the error comment injectable ("htmlspecialchars does not escape '-', so a
// message containing '-->' closes the comment early"). Check 1 rendered that exact input and showed
// it FALSE — ">" is escaped, so no "-->" can form. The corrected reading is above, under the two
// ported defects. It is named here because it is the reason to run the check rather than trust the
// reading, and the same mistake would otherwise look plausible to the next reader of this file.
//
// SO, PLAINLY: this unit is PORTED and its spec is CHECKED, but the Go is UNBUILT and the tag is NOT
// byte-measured against PHP. The gate is UNMET. The two commands that would move it — the build
// above, then the #282 harness — are both named here, and both need a host this session did not have.

import (
	"fmt"
	"strconv"
	"strings"
)

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there, and
// TestTagEquivalence starts measuring this tag with no edit either.
func init() {
	Register("SiteMap", func(e *Engine, a *TagArguments) Tag { return &SiteMapTag{e: e, args: a} })
}

// SiteMapTag is SiteMap (SiteMap.php:16-55).
//
// args mirrors the PHP constructor's $arguments (:20), which the PHP stores in a private field and
// NEVER reads — the tag takes no TAG arguments and no $_GET, and every one of the 25 templates
// invokes it bare as <<<SiteMap>>>. A nil *TagArguments (what TagList.php:67's `new $sel(null)`
// passes, the shape the ?page=tags&tag=SiteMap gate takes) is therefore stored and ignored, which is
// exactly what the PHP does with the NULL it is handed.
//
// Like PageList and DocList, and unlike CategoryView, this constructor CANNOT throw on nil args: :20
// only assigns the field, it never dereferences it. So the gallery render is not an error path — it
// runs the tag's real query. There is no ctorThrew here and there must not be one.
type SiteMapTag struct {
	e    *Engine
	args *TagArguments
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The three constant tables — SiteMap.php:33-38, transcribed in the PHP's own order.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// siteMapBlock is $block (:33-34) — terminal/internal pages kept out of the nav. The PHP's own :31-32
// comment explains the membership: "home/about/order-wizard dropped from the nav (still reachable via
// Pages)". Values are all the int 1; only isset() is ever asked, so a Go set is faithful.
//
// NOTE that 7 of these 10 ids ARE pages whose templates embed <<<SiteMap>>> (about, annotateDone,
// categoryDone, catalog, invalid, tagDone, ticketDone — the ticket lists them among the 25). A page
// rendering a nav that does not link to itself is correct here, not a bug.
var siteMapBlock = map[string]bool{
	"invalid": true, "thanks": true, "ticketDone": true, "tagDone": true, "order": true,
	"catalog": true, "about": true, "config": true, "categoryDone": true, "annotateDone": true,
}

// siteMapLabel is $label (:35-37) — the friendly names. Ids absent from this map render RAW, which is
// why 'forms', 'tickets' and 'memories' come out lowercase (see the file header).
//
// 'tree' AND 'source' BOTH map to "Source". That is the PHP's text, not a transcription slip: both
// appear in $order, so a db holding both pages renders two identically-titled links to different
// hrefs. Do not "fix" either one.
var siteMapLabel = map[string]string{
	"pages": "Pages", "tags": "Tags", "bugs": "Bugs",
	"source": "Source", "docs": "Docs", "annotations": "Annotations",
	"database": "Database", "graphs": "Graphs", "tree": "Source", "repodocs": "Repo Docs",
	"api": "API", "search": "Search", "forge": "Forge", "omni": "Omni-git",
	"shadowforge": "Shadow Forge", "memgraph": "Memory Graph",
}

// siteMapOrder is $order (:38) — the nav's fixed leading sequence. ORDER IS THE DATA HERE: this slice
// IS the rendered left-to-right order of every id it names, so a re-sort (alphabetical, grouped, or
// "tidied") is a byte divergence. Ids not named here still render, after these, in DB row order.
var siteMapOrder = []string{
	"pages", "tags", "bugs", "forms", "tickets", "graphs", "tree", "forge", "omni", "shadowforge",
	"memgraph", "memories", "source", "docs", "repodocs", "api", "search", "annotations", "database",
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PHP array semantics this tag needs. Deliberately unit-local — see the file header.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// siteMapArrayKey is PHP's ARRAY-KEY CAST — what `$have[$id] = 1` (:29) actually keys on.
//
// PHP arrays admit only int and string keys and silently cast everything else. The rules, and why
// each matters to this tag's bytes:
//
//	NULL   -> the "" key. A SQLite TEXT PRIMARY KEY permits NULLs (its UNIQUE index allows multiple),
//	          so this is reachable, and it is the one cast that is NOT injective: NULL and the empty
//	          string are the SAME key, and N NULL rows collapse to ONE nav link.
//	bool   -> int 0/1. Unreachable through a TEXT column; here for completeness.
//	int    -> itself.
//	float  -> truncated toward zero. Unreachable: TEXT affinity converts a REAL to text on storage.
//	string -> a CANONICAL decimal integer becomes an INT key; every other string stays itself.
//
// The string rule is the live one. It is BYTE-LOSSLESS on its own — (string)(int)"123" === "123", so
// a numeric DocumentID renders back exactly as stored — but it changes the key's TYPE, and :46's
// isset($label[$id]) is asked about that key. See siteMapLabelOf.
//
// Returns an int64 or a string. The default arm cannot be reached by a value database/sql produces
// (nil, int64, float64, bool, []byte, string, time.Time are its whole range).
func siteMapArrayKey(v any) any {
	switch x := v.(type) {
	case nil:
		return "" // $a[null] IS $a[""]
	case bool:
		if x {
			return int64(1)
		}
		return int64(0)
	case int:
		return int64(x)
	case int32:
		return int64(x)
	case int64:
		return x
	case float32:
		return int64(x)
	case float64:
		return int64(x)
	case []byte:
		return siteMapStringKey(string(x))
	case string:
		return siteMapStringKey(x)
	default:
		return v
	}
}

// siteMapStringKey applies the string half of the cast: a canonical decimal integer string that fits
// a platform int becomes an int key; anything else stays a string.
func siteMapStringKey(s string) any {
	if !siteMapIsCanonicalInt(s) {
		return s
	}
	n, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		return s // out of int64 range — PHP leaves it a STRING key
	}
	return n
}

// siteMapIsCanonicalInt is PHP's "is this string a canonical decimal integer" test — the exact
// predicate that decides the cast above. CANONICAL is strict, and the exclusions are the point:
//
//	"0"    yes        "-0"   NO (canonical zero has no sign)
//	"123"  yes        "007"  NO (leading zeros)
//	"-5"   yes        "+1"   NO (leading plus)
//	                  " 1"   NO (whitespace — this is NOT is_numeric, which would accept it)
//	                  "1.5"  NO (not an integer)
//	                  "1e2"  NO (exponent form is not canonical for a key)
//
// The int64-range check lives in siteMapStringKey, not here: "9223372036854775808" IS canonical in
// shape but overflows, and PHP leaves it a string key.
func siteMapIsCanonicalInt(s string) bool {
	if s == "" {
		return false
	}
	i := 0
	if s[0] == '-' {
		i = 1
		if len(s) == 1 {
			return false // "-" alone
		}
	}
	if s[i] == '0' {
		// "0" is the only canonical string starting in zero: "-0", "00" and "01" are not.
		return i == 0 && len(s) == 1
	}
	for ; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return true
}

// siteMapArray is $have (:28) — a PHP array used as an INSERTION-ORDERED set.
//
// It is NOT a Go map and it is NOT a []string, because :42's array_keys($have) demands insertion
// ORDER and :29's keying demands the CAST above. A map alone loses the order (and Go randomizes its
// range, so the extras would shuffle per request); a slice alone loses the dedup :29 performs for
// free. Both are needed, so both are here.
//
// Only the four operations the PHP performs are provided — set, isset, unset, array_keys — because
// those are the four whose semantics were checked.
type siteMapArray struct {
	keys []any // insertion order, exactly what array_keys returns
	has  map[any]bool
}

func newSiteMapArray() *siteMapArray { return &siteMapArray{has: map[any]bool{}} }

// set is `$have[$k] = 1` (:29). A REPEAT key overwrites the value and KEEPS its original position —
// it does not move to the end — so keys is only appended to on first sight.
func (a *siteMapArray) set(rawKey any) {
	k := siteMapArrayKey(rawKey)
	if !a.has[k] {
		a.keys = append(a.keys, k)
		a.has[k] = true
	}
}

// isset is `isset($have[$k])` (:41). The values stored are all the int 1 and never NULL, so isset's
// "false for a NULL value" rule cannot fire here and presence is the whole test.
func (a *siteMapArray) isset(rawKey any) bool { return a.has[siteMapArrayKey(rawKey)] }

// unset is `unset($have[$k])` (:41) — it REMOVES the key outright, closing the gap without
// reordering the survivors. That is why this splices keys rather than tombstoning: a tombstone would
// be indistinguishable here (the PHP never re-inserts after unsetting) but would put a re-inserted
// key back in its OLD slot, where PHP appends it at the end.
func (a *siteMapArray) unset(rawKey any) {
	k := siteMapArrayKey(rawKey)
	if !a.has[k] {
		return
	}
	delete(a.has, k)
	for i, kk := range a.keys {
		if kk == k {
			a.keys = append(a.keys[:i], a.keys[i+1:]...)
			break
		}
	}
}

// arrayKeys is `array_keys($have)` (:42) — every live key in insertion order. The elements are the
// CAST keys (int64 or string), not the DocumentIDs as fetched; that distinction is what :46 turns on.
func (a *siteMapArray) arrayKeys() []any { return a.keys }

// siteMapBlocked is `isset($block[$id])` (:41, :42) where $id may be a CAST KEY rather than a string.
//
// The type test is the whole subtlety. Every key in $block is a NON-NUMERIC string, so an INT key can
// never match one — `isset($block[123])` is false, and so is `isset($block[0])`. Returning false for
// any non-string is therefore not a shortcut, it is the rule: coercing the key to "123" first and
// looking THAT up would be a different question that happens to share this answer today, and would
// start lying the moment $block gained a numeric id.
func siteMapBlocked(k any) bool {
	s, ok := k.(string)
	return ok && siteMapBlock[s]
}

// siteMapLabelOf is `isset($label[$id]) ? $label[$id] : $id` (:46), same type rule as siteMapBlocked:
// $label's keys are all non-numeric strings, so an int key from the extras loop misses and the id
// renders raw. Every value in $label is a non-empty string, so isset()'s NULL rule cannot fire.
func siteMapLabelOf(k any) (string, bool) {
	s, ok := k.(string)
	if !ok {
		return "", false
	}
	v, found := siteMapLabel[s]
	return v, found
}

// siteMapError is the catch(\Throwable) body (SiteMap.php:50-52):
//
//	return "<!-- SiteMap error: " . self::esc($e->getMessage()) . " -->";
//
// TWO things about this frame are easy to get wrong by pattern-matching a sibling:
//
//   - IT IS AN HTML COMMENT, not the "<div class='cy-form-error'>…</div>" most tags use.
//   - THERE IS NO get_class($e) PREFIX. PageList's and MemoryList's catches print "Class: message";
//     this one prints the message ALONE, so this function takes no class parameter — there is nowhere
//     to pass one, by design.
//
// The esc() is the PHP's, reproduced exactly where the PHP puts it, and it is what makes the comment
// frame safe: htmlspecialchars escapes ">" (among < & " '), so no ">" reaches the output and neither
// "-->" nor "--!>" can form inside the message. A db error text therefore cannot break out of the
// comment. (It escapes no "-", which invites the opposite conclusion — see the file header, where the
// measured render of `oops --> <script>` is recorded. Do not "harden" this by stripping dashes: that
// would be a byte divergence solving a problem the esc already solved.)
func siteMapError(message string) string {
	return "<!-- SiteMap error: " + esc(message) + " -->"
}

// siteMapCatch is the deferred half of `catch (\Throwable $e)` (:50-52), guarding a Go panic the way
// the PHP's catch guards a throw. The engine has no error boundary of its own — Tag_Wrapper calls
// get_document() uncaught (engine.go:1703-1706) — so without this a panic takes the whole page down
// where the PHP would have rendered a comment.
//
// IT DOES NOT REUSE catchThrowable (engine.go:1715-1719), AND THAT IS THE POINT. catchThrowable
// hardcodes the "<div class='cy-form-error'>SiteMap error: …</div>" frame, which is right for
// PageList and wrong for this tag: :51 returns an HTML COMMENT. Reaching for the shared helper here —
// the obvious move, and what every sibling port does — would emit a visible error div where the PHP
// emits an invisible comment, on the one path this guard exists to cover. The frame comes from
// siteMapError instead, so the catch and the panic guard cannot drift apart.
func siteMapCatch(out *string) {
	if r := recover(); r != nil {
		*out = siteMapError(fmt.Sprint(r))
	}
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// GetDocument — SiteMap::get_document() (SiteMap.php:23-53).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// GetDocument is SiteMap::get_document() (SiteMap.php:23-53) — the nav, as an inline list of links.
//
// THERE IS NO EMPTY-STATE ARM, AND ADDING ONE WOULD BE A DIVERGENCE. :44-49 builds $links and
// implodes it unconditionally; an empty Documents (or one holding only blocked ids) renders THE EMPTY
// STRING — no notice, no markup, nothing. The <nav> in the surrounding template simply comes out
// empty. A "no pages" sentence here would be visible bytes the PHP never writes.
//
// The whole body is the PHP's try (:24) and the order is the PHP's order: the defined() check (:25)
// precedes the open (:26), which precedes the query (:29). This tag reads NO $_GET at all, so there
// is no input to interleave with any of it.
func (t *SiteMapTag) GetDocument() (out string) {
	defer siteMapCatch(&out)

	// :25 — !defined('CONGRUENCY_SQLITE'). The same mapping every sibling port uses
	// (pagelist.go:375, engine.go:1742-1744), but note the FRAME is this tag's own: a comment, not
	// the "<p>Tag: no DB.</p>" sentence PageList and TreeView emit.
	if t.e.cfg.SQLite == "" {
		return "<!-- SiteMap: no DB -->"
	}

	// :26-27 — new PDO('sqlite:'.CONGRUENCY_SQLITE) + ERRMODE_EXCEPTION. PHP reaches its catch by
	// throwing out of the PDO constructor; an unopenable db lands on the same branch here. See the
	// file header on why the message is not byte-reproducible and the frame is.
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return siteMapError(err.Error())
	}
	defer db.Close()

	// :29 — the query, verbatim. NOTE THE ABSENCE OF AN `ORDER BY`, which is load-bearing: the row
	// order IS the extras' render order (via $have's insertion order at :42), and it is whatever
	// SQLite's scan yields for this statement. Both engines run the SAME SQL over the SAME file and
	// therefore see the same order. Adding an ORDER BY here — or sorting in Go — would impose an
	// order the PHP does not ask for and is a byte divergence, not a tidy-up.
	//
	// queryColumn is fetchAll(PDO::FETCH_COLUMN) (engine.go:1247): column 0 of every row.
	ids0, err := queryColumn(db, "SELECT DocumentID FROM Documents")
	if err != nil {
		return siteMapError(err.Error())
	}
	have := newSiteMapArray()
	for _, id := range ids0 {
		have.set(id) // :29 — $have[$id] = 1; the CAST happens inside set.
	}

	// :40-41 — the fixed nav order first. Each id that EXISTS and is not blocked is taken and REMOVED
	// from $have, so the extras loop below cannot emit it twice.
	//
	// The `!blocked` test is not redundant with the extras loop's: an id that is BOTH in $order and in
	// $block would be skipped here WITHOUT being unset, and then filtered again at :42. (No id is
	// currently in both — checked against the two literals above — so this arm is dead today. It is
	// transcribed because it is the PHP's control flow, and the two lists are edited independently.)
	var ids []any
	for _, id := range siteMapOrder {
		if have.isset(id) && !siteMapBlock[id] {
			ids = append(ids, id)
			have.unset(id)
		}
	}

	// :42 — any extras, after: every remaining Document, in DB row order, minus the blocked ones.
	// These keys may be int64 (see siteMapArrayKey), which is why siteMapBlocked takes an `any`.
	for _, id := range have.arrayKeys() {
		if !siteMapBlocked(id) {
			ids = append(ids, id)
		}
	}

	// :44-48 — one <a> per id.
	links := make([]string, 0, len(ids))
	for _, id := range ids {
		// :46 — $text = isset($label[$id]) ? $label[$id] : $id. $text keeps the id's NATIVE value on
		// the fallback (esc() at :47 is what casts it), so an int64 key renders as its digits.
		var text any = id
		if v, ok := siteMapLabelOf(id); ok {
			text = v
		}

		// :47 — BOTH the href and the link text are escaped, exactly where the PHP escapes them.
		// This render flows back through execute_all_tags, so a DocumentID that names a tag — a stored
		// "<<<SiteMap>>>" — must come back "&lt;&lt;&lt;SiteMap&gt;&gt;&gt;" and stay inert
		// (engine.go's header, mechanism 2). Do not remove an esc() call.
		links = append(links, "<a href='?page="+esc(id)+"'>"+esc(text)+"</a>")
	}

	// :49 — implode. The separator is exactly " &nbsp;&middot;&nbsp; ", spaces included, and it goes
	// BETWEEN links only: a one-link nav has no separator and a zero-link nav is "". strings.Join has
	// implode's semantics exactly, including "" for the empty slice.
	return strings.Join(links, " &nbsp;&middot;&nbsp; ")
}
