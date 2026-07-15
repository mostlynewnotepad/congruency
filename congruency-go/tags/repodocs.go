package tags

// repodocs.go — ticket #327, unit go-port:tags:tag:RepoDocs.
//
// The Go port of ONE tag: invocators/tags/dev/RepoDocs.php — the per-repo documentation browser
// (each repo's docs/ + README, ingested through the doc.record token route and served read-only).
// The app serves it standalone at ?page=tags&tag=RepoDocs, and the `repodocs` page's stored template
// embeds <<<RepoDocs>>> (the in-page substitution site named by this unit's ticket; the template is
// the Document_Templates row id 92 that migrations/0017_repo_docs.sql:68-81 installs, and the
// Documents row binding the slug is :83-85).
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. The PHP is the SPEC — where the two
// disagree THIS file is wrong, and "improving" the markup or the markdown subset here is a defect,
// not a fix. Several behaviours below are quirks; each is reproduced at the code that needs it and
// named in a comment, so a later reader does not "correct" one back into a divergence.
//
// ── WHAT THIS FILE ADDS, AND WHAT IT DOES NOT TOUCH ─────────────────────────────────────────────
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers, and its self-registration (the init() below). Nothing in engine.go changes — the registry
// picks this tag up because Go runs every init() in a package before any other code in it (Register
// at engine.go:1355, newTag at engine.go:1393). Every identifier this file defines is
// repoDocs*-prefixed or RepoDocs*-named, so it cannot collide with the sibling tag ports.
//
// (engine.go's COVERAGE header still lists RepoDocs under "NOT PORTED (35)", at engine.go:197. That
// list is a hand-maintained COPY; its own text names PortedTags() as "the authority"
// (engine.go:189-192), and PortedTags is registry-derived (engine.go:1406-1415), so it answers
// correctly the moment this file's init() runs. Correcting the copy means editing engine.go, which
// this ticket forbids ("touch nothing else") — the same stale-copy state #312, #316 and #319 left
// behind for DocList, Login and MemoryList. It is a comment, not behaviour.)
//
// It REUSES engine.go's audited PHP primitives rather than restating them: esc
// (htmlspecialchars($s, ENT_QUOTES), engine.go:599), phpString (PHP's (string) cast over a PDO row's
// native types — NULL becomes "", engine.go:497), phpURLEncode (PHP's urlencode(), RFC1738,
// engine.go:458), phpTrim (trim()'s charlist " \t\n\r\0\x0B", engine.go:630), openDB
// (engine.go:1173), queryRows (fetchAll(PDO::FETCH_ASSOC), engine.go:1241), queryColumn
// (fetchAll(PDO::FETCH_COLUMN), engine.go:1247), scalar (fetchColumn(), engine.go:1260) and
// catchThrowable (the catch(\Throwable) block, engine.go:1715).
//
// It deliberately does NOT reuse a sibling UNIT's helpers. doclist.go carries docListMarkdown /
// docListInline / docListTruthy / docListIdenticalString, which model the same PHP rules — but that
// file is another ticket's deliverable, and depending on it would couple this unit's bytes to edits
// made under another unit's authority. engine.go is the shared floor; a sibling tag file is not.
// Hence the repoDocs* copies below. doclist.go's own header states the same rule from the other
// side, and names this file as the one that must not merge with it.
//
// ── THE SIBLING THAT LOOKS LIKE THIS ONE AND IS NOT: DocList ────────────────────────────────────
//
// DocList.php and RepoDocs.php carry a markdown()/inline() pair that is identical MODULO COMMENTS —
// measured this session by brace-matching both functions out of both files and diffing: every
// difference is a `//` comment DocList carries and RepoDocs does not (three in markdown, one in
// inline). Not one token of executable code differs. (doclist.go's header calls the pair
// "character-identical"; that is true of the CODE and false of the bytes, which is why it was
// re-measured here rather than inherited.)
//
// The TAGS, however, are different tags with different tables, and three details actually differ:
//
//   - RepoDocs keys its markdown branch on kind === 'md' (RepoDocs.php:84); DocList keys its on
//     kind === 'markdown' (DocList.php:85). Different writers fill the two columns.
//   - RepoDocs reads repo_docs (migrations/0017_repo_docs.sql:9-16, written by
//     tools/ingest_repo_docs.py); DocList reads doc_blobs/doc_refs (tools/ingest_self.py).
//   - RepoDocs HAS an empty-state arm ("No repo documentation ingested yet.", RepoDocs.php:55);
//     DocList pointedly has none. RepoDocs also has NO ADMIN_GATED gate; DocList has one.
//
// So the markdown helpers here are repoDocs*-prefixed and MUST NOT be merged with DocList's. If they
// are ever unified, it has to be a deliberate ticket that proves both tags' bytes, not a drive-by
// dedup.
//
// ── THE DEPENDENCY, AND HOW IT DEGRADES (the ticket's "degrade IDENTICALLY") ────────────────────
//
// tools/tag_selfcheck.py's dependency kinds resolve for this tag to exactly one: a SQL TABLE against
// CONGRUENCY_SQLITE — repo_docs, created by migrations/0017_repo_docs.sql:9-16 as
//
//	repo_docs(id INTEGER PRIMARY KEY, ts INTEGER, repo TEXT, path TEXT, kind TEXT, body TEXT)
//
// No getenv, no external db, no disk read, no repos.forge_remote. tag_selfcheck.py names this tag by
// name as one of its two motivating cases (:6-7): "RepoDocs renders 'No repo documentation ingested
// yet' because its backing table `repo_docs` is empty. Neither is a PHP crash, so a render-only
// harness calls them clean." THAT IS THE LIVE STATE OF THE GATE SURFACE, and it is the single most
// important fact about measuring this unit — see THE GATE below.
//
// Every column is NULLable and none has a default, so NULL is reachable in every one of them. The
// degradation states, in the order GetDocument can reach them:
//
//	CONGRUENCY_SQLITE undefined  -> "<p>RepoDocs: no DB.</p>"                     (RepoDocs.php:31)
//	a query throws               -> "<div class='cy-form-error'>RepoDocs error: …</div>"     (:49)
//	repo_docs present but EMPTY  -> "<p>No repo documentation ingested yet.</p>"             (:55)
//	?repo=<undocumented>         -> "<p><strong>No such documented repo.</strong> …</p>"     (:42)
//	?doc=<unknown path>          -> the back-link + "<p>No such doc <code>…</code>.</p>"     (:83)
//	a repo row with NO docs      -> the back-link + "<p>(no docs)</p>"                       (:68)
//
// THE MISSING-TABLE CASE IS THE ONE THAT THROWS, and that is a deliberate PHP choice: RepoDocs sets
// PDO::ERRMODE_EXCEPTION (:33), so a missing repo_docs raises PDOException and lands in the catch —
// it does NOT degrade silently. (Contrast the store DAOs, which set ERRMODE_SILENT and return "";
// see categoryview.go's header. Reading this tag's degradation off that one would be wrong.)
//
// ── WHAT IS NOT BYTE-REPRODUCIBLE, STATED PLAINLY (the catch arm only) ──────────────────────────
//
// PHP's catch renders self::esc($e->getMessage()) (:49) — for a missing table, PDO's
// "SQLSTATE[HY000]: General error: 1 no such table: repo_docs". A Go database/sql error has no
// SQLSTATE text, so repoDocsError emits the Go driver's message inside the IDENTICAL
// "<div class='cy-form-error'>RepoDocs error: …</div>" frame. The FRAME is byte-identical; the
// message inside it is not, and is not claimed to be. This is the package's standing, documented
// limitation (annotatehandler.go:134-142), not a new one, and it is unreachable on any gate surface
// whose db actually has the table.
//
// One related PHP behaviour decides WHICH branch a missing db FILE takes: PHP's
// `new PDO('sqlite:<path>')` CREATES an empty file when the path does not exist (engine.go's header,
// divergence 2), so PHP proceeds and then throws on the missing TABLE. openDB instead returns an
// error for an absent file (engine.go:1177-1179). Both land in the catch arm and emit the same
// frame — the branch agrees, only the message inside differs, as above.
//
// ── THE GATE — WHAT THE TICKET ASKS FOR, WHAT IS RUNNABLE HERE, AND WHAT WAS RUN ────────────────
//
// The ticket's gate is two byte-diffs, PHP:8899 vs Go:8900, over the same db. NEITHER CAN BE RUN
// FROM THIS WORKTREE, and both are additionally confounded on their own terms. Stating this rather
// than settling on a green-looking diff is what the ticket asks for — "if you cannot make a diff
// here run against THIS unit, say so on the ticket rather than settling on a diff that would be
// empty even with the unit unimplemented".
//
// WHY IT CANNOT BE RUN HERE. Checked this session, not assumed: there is no `php` on PATH and no
// php binary anywhere in the tree (tooling/congruencey-harness/ holds only the .php sources —
// router.php, shim.php, AutoLoader.php, Constants_patched.php, telemetry.php, serve — and NO php/
// directory, because the harness's .gitignore ignores `php/`); no .sqlite or .db file exists in the
// worktree (`*.sqlite` is likewise gitignored); and neither `go` nor `curl` is permitted to run
// here, so even the build and the fetch are out of reach. equivalence_test.go's header records this
// same wall as the reason #226 landed 10 tags "ported-not-measured" (:9-13). The live server's db,
// at checkouts/current/state/congruency.sqlite under the MAIN checkout, is outside this worktree.
//
// WHY BOTH DIFFS ARE CONFOUNDED EVEN WITH THE SERVERS UP — each would be exactly as non-empty with
// this file deleted, so neither measures this unit:
//
//	diff 1  ?page=tags&tag=RepoDocs   The PHP returns a FULL CMS page; the Go server does not
//	                                  reproduce the page frame and says so itself (server.go:39-43,
//	                                  62-66: "NOT claimed: that the page's BYTES match PHP … larger
//	                                  by a constant ~6.2 KB of CMS chrome"). The tag's own bytes are
//	                                  a SLICE of that page (equivalence_test.go:28-33).
//	diff 2  ?page=repodocs            server.go's handlePage routes EVERY page key except "tags" to
//	                                  handleCatalogPage, the table-list seam that never invokes the
//	                                  tag engine (server.go:727-735, 831-833). So ?page=repodocs on
//	                                  the Go server cannot reach RepoDocs at all. Wiring it is an
//	                                  edit to server.go, which this ticket forbids.
//
// THE REAL GATE, which exists precisely because of diff 1's confound, is #282's harness — and #323
// settled that this, not the two curl-diffs, is how a tag unit is measured:
//
//	cd congruency-go && go test ./tags/ -run TestTagEquivalence/RepoDocs -v
//
// It cuts the tag's own bytes out of the live PHP page with TagList.php's own anchors and compares
// them to RenderTag's, with a stability sandwich against concurrent writers. It needs the live 8899
// and the shared state db; absent either it SKIPS (its four guards). It requires NO edit to run this
// tag — it sweeps Scan(TAGS_DIR) and measures whatever IsPorted reports, so registering RepoDocs in
// the init() below is the whole wiring.
//
// AND THE HARNESS IS WEAK ON THIS PARTICULAR TAG TODAY, WHICH MUST BE SAID BEFORE ANYONE READS A
// PASS AS PROOF. tag_selfcheck.py records repo_docs as EMPTY on the live db (:6-7). If that is still
// true when the harness runs, ?page=tags&tag=RepoDocs renders the :55 empty-state arm on BOTH sides
// and the comparison is a 44-byte string match — "<p>No repo documentation ingested yet.</p>". That
// is a REAL byte-equal result and it does exercise this unit (the arm is unreachable without it),
// but it exercises ONE of six branches and touches neither listDocs, nor view, nor the markdown
// subset, nor urlencode. A green TestTagEquivalence/RepoDocs on an empty table is NOT evidence that
// this port is byte-equivalent; it is evidence that its empty state is. Measuring the rest needs
// rows in repo_docs (tools/ingest_repo_docs.py is the writer) and a ?repo=/?doc= drive, which the
// gallery URL cannot express — TagList.php constructs the tag with `new $sel(null)` and the tag
// reads $_GET, so ?page=tags&tag=RepoDocs&repo=X&doc=Y DOES reach the inner branches on the PHP
// side, and RenderTag's `get url.Values` carries the same keys on the Go side. That is the drive an
// honest gate for this unit needs, and it is what the ticket's "drive each argument form" asks for.
//
// THIS GO CODE WAS NOT COMPILED OR EXECUTED, AND THAT IS A REAL GAP IN THIS DELIVERABLE. It must be
// said plainly rather than left for the reader to discover. `go` exists on this host but is not a
// permitted command in this session — `go build` was attempted and refused. So the usual floor
// ("RUN your own work before reporting done") could not be met: the Go below is reviewed, not run,
// and a compile error or a runtime panic in it would be a live defect that no step in this session
// could have caught. The FIRST thing to do with this file is:
//
//	cd congruency-go && go build ./... && go vet ./tags/
//
// WHAT WAS ACTUALLY RUN THIS SESSION — python3 only. It splits in two: a BEHAVIOURAL check of my
// reading of the PHP, and a STATIC audit of this file against the PHP. Neither is the Go running.
//
// (A) THE BEHAVIOURAL CHECK — it tests MY READING OF THE PHP, not the Go:
//
//	A Python transliteration of RepoDocs.php — all four methods plus markdown()/inline() — with
//	PCRE's \s spelled out explicitly (as it is in the Go below), PHP's trim() charlist, urlencode's
//	RFC1738 set and PHP's truthiness modelled exactly. Driven against a REAL sqlite repo_docs built
//	by executing migrations/0017_repo_docs.sql's own CREATE TABLE verbatim. Three runs:
//
//	  - A 20-case markdown quirk suite. It CONFIRMED, as behaviour rather than as my assertion, each
//	    quirk documented at repoDocsMarkdown and repoDocsInline: the indented ``` inside a fence
//	    closes it; consecutive 4-space lines emit SEPARATE <pre><code> blocks; a 4-space-only line
//	    emits an EMPTY block instead of ending the paragraph; a form-feed-only line is NOT blank and
//	    becomes paragraph text while a vertical-tab-only line IS blank; "#Foo" and "####### x" are
//	    paragraphs, not headings; "<<<TitleTag>>>" comes out "&lt;&lt;&lt;TitleTag&gt;&gt;&gt;";
//	    `mysql_*` survives the italic pass; "**a** and **b**" makes two <strong>s; "* item *" is not
//	    an <em>; "[a](b c)" stays text; a wrapped "**a\nb**" bolds across the join; a lone CR is
//	    deleted, not a break; a fence body is NOT double-escaped; "``" is left alone; and three blank
//	    lines emit nothing at all. One case corrected MY EXPECTATION, not the code, and it is the
//	    kind of thing this exercise exists to find: an unclosed fence over "```\nx\n" emits
//	    "<pre><code>x\n\n</code></pre>\n" — TWO newlines — because explode("\n") leaves a trailing
//	    empty element that the open fence buffers as its own line. The Go below reproduces that,
//	    because it reproduces the algorithm rather than my first guess at its output.
//	  - The real corpus: the 10 .md files under the app root, exactly the shape ingest_repo_docs.py
//	    stores with kind='md'. All 10 rendered without error and between them exercised every
//	    structural branch — heading 10, para 10, pre 4, code-span 10, bold 9, em 5, link 1 — and 4 of
//	    them carry a literal <<<Tag>>> that stayed escaped, so the escape-first guard is load-bearing
//	    on real data rather than a theoretical concern.
//	  - A branch drive of get_document/index/listDocs/view over seeded rows. It CONFIRMED the empty
//	    state, the deny state, the (no docs) state, the unknown-doc state, the ORDER BY id DESC
//	    newest-wins pick, the md-vs-<pre> split, NULL path/kind rendering as "", urlencode's
//	    '~'->%7E / ' '->'+' / '/'->%2F, that ?repo= and ?doc= EMPTY take the index and listDocs arms
//	    respectively, and both quirks named at repoDocsListDocs and repoDocsGetDocument: listDocs
//	    emits DUPLICATE <li>s for a path ingested twice (no DISTINCT), and a repo literally named "0"
//	    is DENIED though its rows exist (fetchColumn returns the string "0", which is falsy).
//
//	It is NOT the PHP interpreter (no PHP exists here to run), it is NOT this file's Go, and it is
//	NOT the gate. It raises confidence that the SPEC ENCODED BELOW is the spec RepoDocs.php actually
//	implements; it says nothing about whether the Go transcribes it correctly.
//
// (B) THE STATIC AUDIT — this addresses transcription, which (A) cannot. Byte-equivalence dies on a
// typo'd literal ('doclist' where the PHP wrote 'srclist', a dropped "\n", &middot for &middot;), and
// with no compiler and no server those typos are otherwise invisible. Both audits lex the Go and the
// PHP, skipping comments — which is load-bearing on the PHP side, because RepoDocs.php:19 writes
// "htmlspecialchars()'d", whose lone apostrophe opens a single-quote scan that swallows the real
// literals and flips the quote parity for the rest of the file. (My first run of the audit "failed"
// every literal for exactly that reason: the TOOL was broken, not this file.) Results:
//
//	  - LITERAL AUDIT. All 45 markup string literals in this file occur VERBATIM in RepoDocs.php's
//	    own literals — 42 directly, plus the 3 regex replacement templates, which live in PHP
//	    SINGLE-quoted strings and are identical modulo Go's braced ${1}/${2} for PHP's $1/$2. All 4
//	    SQL statements match the PHP verbatim. All 7 regexes were checked against the PCRE they port
//	    (each PCRE confirmed present in the PHP source) and each compiles.
//	  - SKELETON AUDIT. Per function, JOIN every string literal in source order and compare. This is
//	    what the literal audit cannot do: it proves ORDER, and that no fragment is dropped or emitted
//	    twice. index, listDocs and view each came out BYTE-IDENTICAL to their PHP counterparts — 271,
//	    299 and 307 bytes of joined literal. markdown/inline differ only where this file hoists the
//	    regexes to package-level vars (audited above) and concatenates the heading level where PHP
//	    interpolates "<h$h>"; every other byte of their skeletons matches.
//
//	A third check ran for the two things `go build` would catch that nothing else here would: no
//	identifier this file declares collides with a sibling's (14 top-level names, 0 collisions), and
//	Register("RepoDocs") has exactly ONE call site in the package — a second would PANIC during
//	package init (engine.go:1355) and take every render down, not just this tag's. Every engine.go
//	helper called here exists under that name, and all 4 imports are used.
//
//	The static audit still cannot see a type error, a nil deref, or a control-flow mistake. It sees
//	bytes and names.
//
// SO, PLAINLY: this unit is PORTED, its spec is CHECKED, and its literals and markup order are
// AUDITED against the PHP — but the Go is UNBUILT and the tag is NOT byte-measured against PHP. The
// gate is UNMET. The commands that would move it — the build above, then the #282 harness, and for
// anything past the empty-state arm a seeded repo_docs — are all named here, and each needs a host
// this session did not have.

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
	Register("RepoDocs", func(e *Engine, a *TagArguments) Tag { return &RepoDocsTag{e: e, args: a} })
}

// RepoDocsTag is RepoDocs (RepoDocs.php:22-134).
//
// args mirrors the PHP constructor's $arguments (RepoDocs.php:26), which the PHP stores in a private
// field and NEVER reads — the tag takes no TAG arguments (its inputs are $_GET['repo'] and
// $_GET['doc']), and the `repodocs` template invokes it bare as <<<RepoDocs>>>
// (migrations/0017_repo_docs.sql:79). A nil *TagArguments (what TagList.php:67's `new $sel(null)`
// passes, the shape the ?page=tags&tag=RepoDocs gate takes) is therefore stored and ignored, which is
// exactly what the PHP does with the NULL it is handed.
//
// UNLIKE CategoryView (categoryview.go), this constructor CANNOT throw on nil args: RepoDocs.php:26
// only assigns the field, it never dereferences it. So the gallery render is not an error path — it
// runs the tag's real index query. There is no ctorThrew here and there must not be one.
type RepoDocsTag struct {
	e    *Engine
	args *TagArguments
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PHP semantics this tag needs. Deliberately unit-local — see the file header.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// repoDocsTruthy is PHP's truthiness test on a DB value — RepoDocs.php:41's
// `if (!$rs->fetchColumn())`, the whitelist.
//
// It is NOT "not nil", and the difference is a REAL, REACHABLE QUIRK rather than pedantry. PDO's
// fetchColumn() returns FALSE when there is no row, and otherwise the COLUMN'S VALUE — here the repo
// name itself. PHP then tests that value for truthiness, not for existence. So a repo literally named
// "0" returns the string "0", which PHP counts as FALSE, and the tag answers "No such documented
// repo." for a repo whose rows plainly exist. Confirmed as behaviour in the branch drive named in the
// file header. That is a defect in the PHP; per the ticket it is ported, not fixed — "if the PHP is
// genuinely defective, file a separate bug ticket and port the defect faithfully".
//
// PHP counts 0, 0.0, "", "0" and NULL as FALSE. A repo named "" cannot reach here (the `$repo === ''`
// test at :36 takes the index arm first), and a NULL repo cannot match `repo=?` at all, so the string
// "0" is the arm that actually bites.
func repoDocsTruthy(v any) bool {
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

// repoDocsIdenticalString is PHP's `$v === $s` where $s is a known string — RepoDocs.php:84's
// `$row['kind'] === 'md'`.
//
// `===` requires the TYPES to match, so it is true only when $v is ALSO a string and equal. phpString
// would NOT do: it would coerce an int64 kind column to "1" and could report a match the PHP's `===`
// denies. kind is declared TEXT (migrations/0017_repo_docs.sql:14) so PDO hands back a string or nil
// and the coercion never bites in practice — modelling `===` exactly is what keeps that a fact about
// the schema rather than an assumption in this file. Anything that is not exactly the string "md" —
// including "text", "markdown", NULL, or an int — takes the <pre> arm.
//
// NOTE THE VOCABULARY: 'md', not DocList's 'markdown'. See the file header.
func repoDocsIdenticalString(v any, s string) bool {
	got, ok := v.(string)
	return ok && got == s
}

// repoDocsError is the catch(\Throwable) body (RepoDocs.php:48-50):
//
//	return "<div class='cy-form-error'>RepoDocs error: " . self::esc($e->getMessage()) . "</div>";
//
// It is spelled out rather than left to catchThrowable because the PHP reaches this branch by
// THROWING (PDO::ERRMODE_EXCEPTION, :33) where Go's database/sql returns an error — same branch,
// different mechanism. catchThrowable still guards the deferred path and produces the identical
// wrapper for a real panic. See the file header on what is and is not byte-reproducible here.
func repoDocsError(err error) string {
	return "<div class='cy-form-error'>RepoDocs error: " + esc(err.Error()) + "</div>"
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// GetDocument — RepoDocs::get_document() (RepoDocs.php:29-51).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// GetDocument is RepoDocs::get_document() (RepoDocs.php:29-51).
//
// THE ORDER BELOW IS THE PHP'S ORDER AND IT IS LOAD-BEARING. The try opens the DB (:31-33) BEFORE it
// reads $_GET (:35), so an unopenable db yields the error div whether or not ?repo=/?doc= were
// supplied — the parameters never get a chance to matter. And the WHITELIST (:39-43) runs BEFORE
// ?doc= is read (:45), so an undocumented repo yields "No such documented repo." even when ?doc= is
// present: the deny arm wins over the view arm, always.
//
// THERE IS NO GATE. DocList and SourceList open with an ADMIN_GATED check; RepoDocs has none, and
// inventing one here would be markup the PHP cannot emit.
//
// `$repo = isset($_GET['repo']) ? (string) $_GET['repo'] : ''` (:35) is getStr, with NO trim —
// and that is a real difference from DocList, which trims its one parameter (DocList.php:39). getStr
// collapses the ternary's two arms correctly: it returns "" for an unset key (engine.go:910-916),
// which is the same "" the else-arm supplies, and both then fail the `!== ''` test at :36 and fall
// through to the index. So the isset/empty distinction that several other tags branch on
// (engine.go:918-921) cannot be observed here — ?repo= and no ?repo at all render the identical
// index, which the branch drive confirmed. The same holds for ?doc= at :45-46, which falls through to
// listDocs. Because neither parameter is trimmed, "?repo=congruency " (with a trailing space) is a
// DIFFERENT repo than "congruency" and is denied; that is the PHP's behaviour and it is reproduced.
func (t *RepoDocsTag) GetDocument() (out string) {
	defer catchThrowable(&out, "RepoDocs")

	// :31 — !defined('CONGRUENCY_SQLITE'). The same mapping every sibling port uses
	// (apireference.go:91-93, engine.go:1742-1744).
	if t.e.cfg.SQLite == "" {
		return "<p>RepoDocs: no DB.</p>"
	}

	// :32-33 — new PDO('sqlite:'.CONGRUENCY_SQLITE) + ERRMODE_EXCEPTION. PHP reaches its catch by
	// throwing out of the PDO constructor; an unopenable db lands on the same branch here.
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return repoDocsError(err)
	}
	defer db.Close()

	// :35-36 — no ?repo means the index.
	repo := t.e.getStr("repo")
	if repo == "" {
		return t.repoDocsIndex(db)
	}

	// :38-43 — the whitelist. ONLY repos that actually have docs in the DB may be browsed, and the
	// check is a query against repo_docs, never a trust of ?repo=. scalar is fetchColumn()
	// (engine.go:1260): nil for no rows, which is PHP's FALSE. See repoDocsTruthy for the "0" quirk.
	//
	// SELECT DISTINCT is the PHP's (:39). It cannot change this answer — one row or fifty, only the
	// first column of the first row is read — but the query text is kept identical to the PHP's
	// because that is the cheaper thing to verify.
	found, err := scalar(db, "SELECT DISTINCT repo FROM repo_docs WHERE repo=?", repo)
	if err != nil {
		return repoDocsError(err)
	}
	if !repoDocsTruthy(found) {
		// :42 — NO trailing newline; the PHP's string ends at "</p>".
		return "<p><strong>No such documented repo.</strong> <a href='?page=repodocs'>&larr; repos</a></p>"
	}

	// :45-47
	doc := t.e.getStr("doc")
	if doc != "" {
		return t.repoDocsView(db, repo, doc)
	}
	return t.repoDocsListDocs(db, repo)
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// index — RepoDocs::index($db) (RepoDocs.php:53-61).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// repoDocsIndex is RepoDocs::index($db) (RepoDocs.php:53-61) — every repo that has docs, one <li>
// each. It is what BOTH gate surfaces render bare: ?page=tags&tag=RepoDocs and a bare ?page=repodocs.
//
// THIS IS THE ARM THE LIVE DB ACTUALLY TAKES. tag_selfcheck.py:6-7 names RepoDocs as its motivating
// case precisely because repo_docs is empty, so :55 fires and the whole render is one 44-byte
// sentence. See THE GATE in the file header for why that makes a green harness run weak evidence.
//
// `if (!$rows)` (:55) is PHP's empty-array-is-falsy, so the EMPTY-STATE ARM EXISTS HERE — unlike
// DocList, whose index has no such arm and renders an empty <ul> instead. Do not "harmonise" the two.
// queryColumn returns a nil slice for zero rows (engine.go:1247-1258), so len == 0 is the same test.
//
// THE APOSTROPHE IN "browse each one's" IS A RAW BYTE. It is a literal ' inside a double-quoted PHP
// string (:56), not data, and htmlspecialchars is never called on it — so it emits as ' and NOT as
// &#039;. esc() here would be a byte diff on the intro line.
//
// THE LIST CLASS IS 'srclist', NOT 'doclist' (:56). listDocs below uses 'doclist' (:69). The two
// differ in the PHP and they differ here.
//
// Every DATA value, by contrast, is esc()'d exactly where the PHP esc()'s it (:58) — and note the
// PHP escapes the URLENCODED name too, `self::esc(urlencode($name))`, which is not redundant: '&'
// survives urlencode only as %26, but a repo name is arbitrary TEXT and esc-ing the encoded form is
// what the PHP writes, so it is what this writes. This render flows back through execute_all_tags, so
// a stored "<<<Tag>>>" must come back "&lt;&lt;&lt;Tag&gt;&gt;&gt;" and stay inert (engine.go's
// header, mechanism 2).
//
// $name is a FETCH_COLUMN value with its native type, and repo is a NULLable TEXT column
// (migrations/0017_repo_docs.sql:12), so a NULL repo is reachable. PHP's urlencode(null) yields "" (a
// deprecation notice in 8.1+, but no output), and esc(null) yields "" — phpString models both, so a
// NULL repo renders an empty link exactly as the PHP does. Confirmed in the branch drive.
func (t *RepoDocsTag) repoDocsIndex(db *sql.DB) string {
	// :54 — PDO::query(...)->fetchAll(PDO::FETCH_COLUMN). No parameters, so query() not prepare().
	// The PHP has no try here; the exception propagates to get_document's catch, which is the same
	// frame repoDocsError emits.
	rows, err := queryColumn(db, "SELECT DISTINCT repo FROM repo_docs ORDER BY repo")
	if err != nil {
		return repoDocsError(err)
	}
	// :55
	if len(rows) == 0 {
		return "<p>No repo documentation ingested yet.</p>"
	}

	var b strings.Builder
	// :56
	b.WriteString("<p>Repos with ingested documentation &mdash; browse each one's <code>docs/</code>" +
		" and README.</p>\n<ul class='srclist'>\n")
	for _, name := range rows {
		// :58 — one <li> per repo. &#128218; is the PHP's books emoji entity, and the "\n" after
		// </li> is the PHP's.
		b.WriteString("<li>&#128218; <a href='?page=repodocs&repo=" + esc(phpURLEncode(phpString(name))) +
			"'>" + esc(name) + "</a></li>\n")
	}
	// :60
	b.WriteString("</ul>\n")
	return b.String()
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// listDocs — RepoDocs::listDocs($db, $repo) (RepoDocs.php:63-75).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// repoDocsListDocs is RepoDocs::listDocs($db, $repo) (RepoDocs.php:63-75) — one whitelisted repo's
// docs. Reached via ?repo=X with no ?doc=.
//
// THERE IS NO DISTINCT IN THIS QUERY (:64), AND THAT IS A VISIBLE QUIRK, NOT A TRANSCRIPTION SLIP.
// index() selects DISTINCT repo (:54); this selects `path, kind` plain. repo_docs is an APPEND log —
// doc.record INSERTs a new row per ingest (migrations/0017_repo_docs.sql:47-54, no ON CONFLICT), so
// a doc ingested three times has three rows and this list renders THREE IDENTICAL <li>s linking to
// the same ?doc=. view() then collapses them to the newest by `ORDER BY id DESC LIMIT 1`. So the
// list can show a path N times while the view shows one body. Confirmed in the branch drive (a
// README.md at ids 1 and 5 rendered twice). Adding DISTINCT would "fix" it into a divergence.
//
// `if (!$rows)` (:68) is PHP's empty-array-is-falsy. The arm is all but unreachable through
// get_document — the whitelist at :39-43 has just proven a row exists for this repo — but a
// concurrent DELETE between the two queries can empty it, and it is the PHP's code either way, so it
// is ported rather than reasoned away. NOTE ITS SHAPE: it returns the back-link PLUS "<p>(no docs)</p>"
// with NO <ul> and NO trailing newline.
//
// $repo is the $_GET string (a Go string), so urlencode/esc take it directly. $r['path'] and
// $r['kind'] are FETCH_ASSOC values with their native types and both columns are NULLable
// (migrations/0017_repo_docs.sql:13-14), hence phpString before phpURLEncode; esc does its own cast.
func (t *RepoDocsTag) repoDocsListDocs(db *sql.DB, repo string) string {
	// :64-66 — PHP prepares and binds; so does this.
	rows, err := queryRows(db, "SELECT path, kind FROM repo_docs WHERE repo=? ORDER BY path", repo)
	if err != nil {
		return repoDocsError(err)
	}

	// :67 — the back-link head, emitted before the empty test so both arms carry it.
	out := "<p><a href='?page=repodocs'>&larr; repos</a> &middot; <strong>" + esc(repo) + "</strong></p>\n"
	if len(rows) == 0 {
		// :68 — NO trailing newline; the PHP's string ends at "</p>".
		return out + "<p>(no docs)</p>"
	}

	var b strings.Builder
	b.WriteString(out)
	// :69
	b.WriteString("<ul class='doclist'>\n")
	for _, r := range rows {
		// :71-72 — one <li> per ROW (not per path; see the no-DISTINCT note above). &#128196; is the
		// PHP's page-facing-up emoji entity. The space after </a> and the "\n" after </li> are the
		// PHP's, and so is the fact that the <span> carries no escaping of its own beyond esc(kind).
		b.WriteString("<li>&#128196; <a href='?page=repodocs&repo=" + esc(phpURLEncode(repo)) +
			"&doc=" + esc(phpURLEncode(phpString(r["path"]))) + "'>" + esc(r["path"]) + "</a> " +
			"<span style='color:#888;font-size:.85em'>" + esc(r["kind"]) + "</span></li>\n")
	}
	// :74
	b.WriteString("</ul>\n")
	return b.String()
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// view — RepoDocs::view($db, $repo, $path) (RepoDocs.php:77-88).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// repoDocsView is RepoDocs::view($db, $repo, $path) (RepoDocs.php:77-88) — one doc's body. Reached
// only via ?repo=X&doc=P, i.e. the links repoDocsListDocs emits; the gallery URL carries no doc
// parameter and so never lands here unless one is appended.
//
// `ORDER BY id DESC LIMIT 1` (:79) IS THE NEWEST INGEST WINNING. repo_docs is an append log (see
// repoDocsListDocs), and id is INTEGER PRIMARY KEY (migrations/0017_repo_docs.sql:10), so it is the
// rowid alias and ascends with insertion. The PHP orders by id, NOT by the ts column that sits right
// there — ts is written as strftime('%s','now') (:50 of the migration), a whole-SECOND stamp, so two
// ingests inside one second tie under ts and would order arbitrarily; id cannot tie. Do not "improve"
// this to ORDER BY ts.
//
// `if (!$row)` (:83) — PDO::fetch() returns FALSE when there is no row, and otherwise an ARRAY. A
// found row is a non-empty array and therefore truthy even when every column in it is NULL, so !$row
// is exactly "no row" and len(rows) == 0 is the same test. (This is the one place the array-is-falsy
// rule does NOT bite, and it is worth naming because the two arms above it turn on the rule biting.)
//
// $path IS NOT WHITELISTED — only $repo is (:39-43). The PHP's header comment says "repo/path are
// validated against the DB (never trusted from ?repo=/?doc=)", and for path that is true only in the
// sense that a bad path finds no row; the raw ?doc= string is still interpolated into `back` at :82
// and into the not-found message at :83. It is esc()'d at both, so it is inert — but the claim to
// hold onto is the escaping, not a whitelist. Reproduce the escaping exactly and the distinction
// costs nothing.
func (t *RepoDocsTag) repoDocsView(db *sql.DB, repo, path string) string {
	// :79-81 — the newest body for this registered repo/path. PHP prepares and binds both.
	rows, err := queryRows(db,
		"SELECT body, kind FROM repo_docs WHERE repo=? AND path=? ORDER BY id DESC LIMIT 1", repo, path)
	if err != nil {
		return repoDocsError(err)
	}

	// :82 — the back-link head. Built BEFORE the not-found test so both arms carry it. Both $repo and
	// $path are $_GET strings here, so esc/phpURLEncode take them directly.
	back := "<p><a href='?page=repodocs&repo=" + esc(phpURLEncode(repo)) + "'>&larr; " + esc(repo) +
		" docs</a> &middot; <strong>" + esc(path) + "</strong></p>\n"
	if len(rows) == 0 {
		// :83 — NO trailing newline; the PHP's string ends at "</p>".
		return back + "<p>No such doc <code>" + esc(path) + "</code>.</p>"
	}
	row := rows[0]

	// :84-86 — markdown, or a <pre> of the escaped body. The key is `=== 'md'`, NOT DocList's
	// 'markdown' (see the file header). tools/ingest_repo_docs.py is the writer that fills the column.
	var rendered string
	if repoDocsIdenticalString(row["kind"], "md") {
		rendered = repoDocsMarkdown(row["body"])
	} else {
		rendered = "<pre style='background:#f4f1e8;padding:.6rem;overflow:auto'>" + esc(row["body"]) + "</pre>"
	}

	// :87
	return back + "<div class='doc prose'>\n" + rendered + "</div>\n"
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The markdown subset — RepoDocs::markdown/inline (RepoDocs.php:90-132).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// repoDocsPCRESpaceClass is PCRE's \s as a Go character-class BODY: [ \t\n\v\f\r].
//
// GO'S OWN \s IS THE WRONG SET AND USING IT WOULD BE A REAL BUG. Go's regexp \s is [\t\n\f\r ] — it
// does NOT include \v (0x0B). PHP 7.3+ runs PCRE2, whose \s DOES include \v (matching Perl 5.18+).
// engine.go already made and documented this call for the same reason (isPHPSpace, engine.go:624-626
// — "PCRE's \s = [ \t\n\r\f\v]"). So every \s in RepoDocs.php's patterns is spelled out explicitly
// below, and none of them is Go's \s.
//
// This is also NOT phpTrim's charlist (" \t\n\r\0\x0B"), which strips NUL and NOT \f. The two sets
// genuinely differ and this file uses both — \s in the regexes, trim() at the blank-line test. The
// quirk suite exercises both edges: a \f-only line is paragraph text, a \v-only line is blank.
const repoDocsPCRESpaceClass = " \\t\\n\\v\\f\\r"

var (
	// repoDocsFenceRe is preg_match('/^\s*```/', $ln) (RepoDocs.php:100) — an OPTIONALLY INDENTED
	// fence marker. Unanchored at the right, so a ```php info string matches and is discarded.
	repoDocsFenceRe = regexp.MustCompile("^[" + repoDocsPCRESpaceClass + "]*```")

	// repoDocsHeadingRe is preg_match('/^(#{1,6})\s+(.*)$/', $ln, $m) (RepoDocs.php:106).
	//
	// The \s+ is REQUIRED, so "#Foo" is a paragraph, not an h1. Seven or more #'s cannot match
	// either: #{1,6} takes six, \s+ then needs whitespace and finds '#', and every shorter backtrack
	// fails the same way — so "####### x" is a paragraph too. Both confirmed in the quirk suite.
	//
	// PCRE's `$` (without /D) also matches BEFORE a trailing newline where Go's `$` (without (?m))
	// matches only at end of text. The difference cannot bite here: markdown() explodes on "\n" after
	// deleting every "\r", so no line contains either byte. Same reason `.` excluding \n is moot.
	repoDocsHeadingRe = regexp.MustCompile("^(#{1,6})[" + repoDocsPCRESpaceClass + "]+(.*)$")

	// repoDocsIndentRe is preg_match('/^    (.*)$/', $ln, $m) (RepoDocs.php:109) — EXACTLY four
	// leading spaces (a fifth lands in $m[1]). Tabs do not match.
	repoDocsIndentRe = regexp.MustCompile("^    (.*)$")

	// repoDocsCodeRe is the `code` span of preg_replace_callback('/`([^`]+)`/', …) (RepoDocs.php:122).
	// [^`]+ is greedy and the span cannot be empty, so "``" is left alone.
	repoDocsCodeRe = regexp.MustCompile("`([^`]+)`")

	// repoDocsBoldRe is preg_replace('/\*\*(.+?)\*\*/', …) (RepoDocs.php:127) — NON-GREEDY, so
	// "**a** and **b**" makes two <strong>s rather than one spanning the middle.
	repoDocsBoldRe = regexp.MustCompile(`\*\*(.+?)\*\*`)

	// repoDocsItalicRe is preg_replace('/(^|[^*])\*([^*\s][^*]*)\*/', …) (RepoDocs.php:128).
	//
	// Group 1 CONSUMES the preceding character (or matches empty at ^), which is why the replacement
	// puts $1 back. The [^*\s] first-char guard is what stops "* item" (a list bullet) becoming an
	// <em>, and stops the leftover single '*' of an odd run from opening one.
	repoDocsItalicRe = regexp.MustCompile("(^|[^*])\\*([^*" + repoDocsPCRESpaceClass + "][^*]*)\\*")

	// repoDocsLinkRe is preg_replace('/\[([^\]]+)\]\(([^)\s]+)\)/', …) (RepoDocs.php:129). The URL may
	// hold no whitespace and no ')', so "[a](b c)" and "[a]()" are left as text.
	repoDocsLinkRe = regexp.MustCompile("\\[([^\\]]+)\\]\\(([^)" + repoDocsPCRESpaceClass + "]+)\\)")
)

// repoDocsMarkdown is RepoDocs::markdown($text) (RepoDocs.php:92-118) — the minimal, ESCAPE-FIRST
// markdown subset, whose own header (RepoDocs.php:90-91) reads:
//
//	Minimal markdown subset. ESCAPE FIRST (so HTML and '<<<Tag>>>' examples stay literal), then apply:
//	#.. -> h1-h6, blank-line paragraphs, ``` / 4-space indent -> <pre><code>, `x` -> <code>, [t](u) -> <a>.
//
// ESCAPE FIRST IS THE WHOLE SECURITY MODEL AND THE ORDER IS NOT NEGOTIABLE (:93). The class's own
// header states the invariant (:18-20): "ALL output is htmlspecialchars()'d before it flows back
// through execute_all_tags, so any literal <<<...>>> in a doc stays inert." htmlspecialchars runs
// ONCE, over the entire raw document, BEFORE any structure is recognised. Everything after that point
// manipulates already-escaped text, and the markup this function adds (<p>, <h1>, <pre>, <em>…) is
// therefore the ONLY live markup in the output. Two consequences a "cleaner" implementation would
// break:
//
//   - a doc containing "<<<TitleTag>>>" emits "&lt;&lt;&lt;TitleTag&gt;&gt;&gt;", which tagPattern
//     cannot match, so the tag engine does not re-parse it when this output flows back through
//     execute_all_tags (engine.go's header, mechanism 2). This is load-bearing on the REAL corpus,
//     not in theory: 4 of the 10 .md files under the app root carry a literal <<<Tag>>>, because the
//     docs describe tags.
//   - the fence/indent bodies are emitted RAW into <pre><code> (:102, :110) with NO further
//     escaping, and that is CORRECT — they were escaped at :93. Escaping them again would render
//     "&amp;lt;" as visible source text in every code block.
//
// str_replace("\r", "", …) (:94) deletes EVERY carriage return, not just the ones before a newline,
// so a lone CR is a deletion and not a line break. explode("\n") then yields lines that contain
// neither \r nor \n — which is what makes the PCRE-vs-Go `$` and `.` differences moot (see
// repoDocsHeadingRe).
//
// THE FIVE QUIRKS, each reproduced deliberately and each confirmed by the quirk suite:
//
//  1. THE FENCE CHECK PRECEDES THE inFence CHECK (:100 before :105), so an indented ``` INSIDE a
//     fence closes it. A fence body cannot contain a fence line, at any indent.
//  2. EACH 4-SPACE LINE IS ITS OWN <pre><code> BLOCK (:110) — consecutive indented lines are NOT
//     merged, so a 3-line indented listing emits three separate blocks. This is a real difference
//     from every standard markdown implementation, and it is the spec here.
//  3. A LINE OF EXACTLY FOUR SPACES matches the indent rule (with $m[1] === "") BEFORE the
//     blank-line test at :112 can see it, so it emits an EMPTY "<pre><code></code></pre>\n" rather
//     than closing a paragraph. Order is the reason: :109 runs first.
//  4. THE BLANK TEST IS trim(), NOT \s (:112). PHP's trim() strips NUL and \v but NOT \f — so a line
//     holding only a form feed is NOT blank and becomes paragraph text, while a line holding only a
//     vertical tab IS blank. phpTrim is that exact charlist (engine.go:628-632); strings.TrimSpace
//     would strip the \f and lose the quirk.
//  5. AN UNCLOSED FENCE AT EOF STILL EMITS ITS BLOCK (:116) — the document is not truncated — AND IT
//     CARRIES A TRAILING BLANK LINE. explode("\n") on a body ending "\n" leaves a final EMPTY element;
//     inside an open fence that element is buffered like any other line, so "```\nx\n" emits
//     "<pre><code>x\n\n</code></pre>\n" with TWO newlines. This one corrected my own expectation when
//     the suite ran; it falls out of the algorithm rather than being special-cased.
//
// The closure `$flush` (:96-98) inlines below. Its `if ($para)` is PHP's empty-array-is-falsy, so a
// flush with nothing buffered emits NOTHING — there are no empty <p></p> in the output. Its
// implode(" ", $para) is why inline() sees the JOINED paragraph, so bold/italic/code spanning a
// wrapped line still match — reproducing the join is reproducing which inline spans match at all.
// (DocList.php:98 carries a comment saying exactly that; RepoDocs.php has the identical code and no
// comment. See the file header on the comments-only difference.)
func repoDocsMarkdown(text any) string {
	// :93 — the one escape, over the whole document. esc is htmlspecialchars($s, ENT_QUOTES) with
	// PHP's (string) cast in front of it (engine.go:599), which is exactly `htmlspecialchars((string)
	// $text, ENT_QUOTES)`. A NULL body escapes to "" on both sides.
	escd := esc(text)

	// :94
	lines := strings.Split(strings.ReplaceAll(escd, "\r", ""), "\n")

	// :95
	var out strings.Builder
	var para []string
	inFence := false
	code := ""

	// :96-98 — $flush.
	flush := func() {
		if len(para) > 0 {
			out.WriteString("<p>" + repoDocsInline(strings.Join(para, " ")) + "</p>\n")
			para = nil
		}
	}

	for _, ln := range lines {
		// :100-104 — the fence toggle. The fence LINE itself is never emitted, on either edge.
		if repoDocsFenceRe.MatchString(ln) {
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
		// :105 — inside a fence every line is buffered raw, with its newline restored. Quirk 5's
		// trailing blank line arrives here.
		if inFence {
			code += ln + "\n"
			continue
		}
		// :106-108 — the heading. strlen($m[1]) is the level, 1..6.
		if m := repoDocsHeadingRe.FindStringSubmatch(ln); m != nil {
			flush()
			h := strconv.Itoa(len(m[1]))
			out.WriteString("<h" + h + ">" + repoDocsInline(m[2]) + "</h" + h + ">\n")
			continue
		}
		// :109-111 — the indented code line. Quirks 2 and 3 live here.
		if m := repoDocsIndentRe.FindStringSubmatch(ln); m != nil {
			flush()
			out.WriteString("<pre><code>" + m[1] + "</code></pre>\n")
			continue
		}
		// :112 — quirk 4.
		if phpTrim(ln) == "" {
			flush()
			continue
		}
		// :113 — buffered RAW; inline() is applied to the whole paragraph in flush.
		para = append(para, ln)
	}

	// :115-116
	flush()
	if inFence {
		out.WriteString("<pre><code>" + code + "</code></pre>\n")
	}
	return out.String()
}

// repoDocsInline is RepoDocs::inline($s) (RepoDocs.php:120-132) — the inline spans, applied to a
// whole paragraph or to a heading's text.
//
// THE PLACEHOLDER DANCE IS THE POINT: inline code is protected FIRST because its contents may hold a
// '*' (e.g. `mysql_*`) that would otherwise break the bold/italic passes. Each span is swapped for a
// placeholder, the transforms run, then the spans are restored. So the order is fixed:
//
//	1. `code`  -> "\x01<n>\x01"      (:122-126)   n counts from 0
//	2. **bold**                       (:127)
//	3. *italic*                       (:128)
//	4. [text](url)                    (:129)
//	5. restore each placeholder       (:130)      in INSERTION order
//
// Running any pass out of order changes the output. Restoring before step 4, for instance, would let
// a link regex chew a URL out of a code span. (DocList.php:123-124 carries a comment saying exactly
// this; RepoDocs.php has the identical code and no comment.)
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
// the closing delimiter must line up. So the naive str_replace loop at :130 is safe against its own
// keys, and this loop is too.
//
// $m[1] (the code span's contents) is inserted into <code>…</code> WITHOUT further escaping (:124) —
// correct, because markdown() escaped the whole document before inline() ever saw it.
func repoDocsInline(s string) string {
	// :122-126 — step 1. keys preserves PHP's array INSERTION order, which is the order :130's
	// foreach restores in; a Go map alone would not, and the restore order is observable whenever one
	// span's text could contain another's key.
	codes := map[string]string{}
	var keys []string
	s = repoDocsCodeRe.ReplaceAllStringFunc(s, func(m string) string {
		// count($codes) is read BEFORE the insert, so the first key is \x010\x01.
		k := "\x01" + strconv.Itoa(len(codes)) + "\x01"
		// The pattern is `([^`]+)` — one backtick each side — so $m[1] is the match minus its first
		// and last byte. ReplaceAllStringFunc hands over the whole match, hence the slice.
		codes[k] = "<code>" + m[1:len(m)-1] + "</code>"
		keys = append(keys, k)
		return k
	})

	// :127-129 — steps 2-4. ${1}/${2} rather than $1/$2: Go reads $1< as group "1" here, but the
	// braced form is the spelling that cannot be misread when a digit follows.
	s = repoDocsBoldRe.ReplaceAllString(s, "<strong>${1}</strong>")
	s = repoDocsItalicRe.ReplaceAllString(s, "${1}<em>${2}</em>")
	s = repoDocsLinkRe.ReplaceAllString(s, `<a href="${2}">${1}</a>`)

	// :130 — step 5, in insertion order.
	for _, k := range keys {
		s = strings.ReplaceAll(s, k, codes[k])
	}
	return s
}
