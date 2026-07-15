package tags

// annotatehandler.go — ticket #246, unit go-port:tags:tag:AnnotateHandler.
//
// The Go port of ONE tag: invocators/tags/dev/AnnotateHandler.php. Nothing else. This file is the
// first of the per-tag files #281 built the init()-based registry for (engine.go:1290-1321): it adds
// its type, its GetDocument and its self-registration, and changes NOTHING in engine.go.
//
// THE CONTRACT, as everywhere in this package: byte-identical HTML. THE PHP IS THE SPEC — where the
// two disagree the Go is wrong, and a quirk below is a quirk because the PHP has it.
//
// ── WHAT THE PHP TAG IS ─────────────────────────────────────────────────────────────────────────
//
// AnnotateHandler is the handler half of the AnnotateForm pair — "the general front door to the
// tag->target layer" (AnnotateHandler.php:8-13). It reads the COMPLETED form out of the session's
// FORM_MANAGER, validates it, INSERTs one `annotations` row (tag -> target "kind:id"), resets the
// form, and reports what it wrote. It renders at ?page=tags&tag=AnnotateHandler (the gallery) and is
// substituted into the one page whose template embeds it: `annotateDone`.
//
// It is the only tag ported so far that WRITES. Everything unusual about this file follows from
// that one fact; see "THE WRITE PATH" below.
//
// ── THE FIVE BRANCHES, in the order get_document() takes them (AnnotateHandler.php:23-61) ───────
//
//	1. no pending form   kind=='' && id=='' && tag==''      -> "No pending annotation. Add one ->"
//	2. bad kind          kind not in {source,page,doc,ticket} -> "Rejected: <kind> is not a valid
//	                                                             target kind." + back()
//	3. missing id/tag    id=='' || tag==''                  -> "Rejected: a target id and a tag are
//	                                                            both required." + back()
//	4. the write         everything else                    -> INSERT, reset the form, the green
//	                                                            "Annotation #N added." panel
//	5. any \Throwable                                       -> the cy-form-error div
//
// Branch 1 is the one BOTH of this unit's gate surfaces take, and that is not an accident of the
// harness — it is the PHP's own steady state. bin/Initialize_POM.php:17-20 puts a FRESH FormManager
// in the POM on every request that lacks one, and FormManager::getResults returns NULL for a form
// that is not in its formsArray (FormManager.php:63-69). So a request with no prior AnnotateForm
// submission — every gate request — reaches get_document() with $res === NULL, hence kind/id/tag all
// '', hence branch 1. Measured against the live PHP on 127.0.0.1:8899 this session; see THE GATE.
//
// ── ARGUMENTS: this tag takes none, and that is a property of the PHP, not an omission here ─────
//
// AnnotateHandler.php:18-19 is the whole of its argument handling:
//
//	private $arguments;
//	public function __construct($arguments) { $this->arguments = $arguments; }
//
// $arguments is STORED AND NEVER READ — no method of the class touches it. So the two invocation
// shapes this unit's gate drives are identical in output by construction:
//
//	the gallery      `new AnnotateHandler(null)`      (TagList.php:67) -> args nil
//	the annotateDone `<<<AnnotateHandler>>>`          template          -> args empty
//
// The template's site was read out of the live db with the engine's own DAO join this session and is
// the BARE invocation, no parentheses:
//
//	Documents.DocumentID='annotateDone' -> Document_Templates.Content =
//	  "<!DOCTYPE html>\n<html>\n<head>\n<<<TitleTag>>>\n<<<Style>>>\n</head>\n<body>\n
//	   <nav><<<SiteMap>>></nav>\n<h1>Annotation added</h1>\n<<<AnnotateHandler>>>\n</body>\n</html>\n"
//
// The field is kept below anyway, unread, because the PHP keeps it: a port that dropped it would be
// a tidier class than the one it claims to reproduce.
//
// ── THE FORM_MANAGER SEAM: why this file declares two interfaces ────────────────────────────────
//
// The tag's input is `PersistentObjectManager::getData('FORM_MANAGER')`, and Go has no POM —
// engine.go's divergence 3 (header) makes it Config.FormManager instead. But that interface carries
// only RunForm/LoadFailure (engine.go:343-349), which is what FormTag needs; AnnotateHandler needs
// getResults / getCachedForm / setResults / reset, and #246's deliverable is THIS FILE ALONE, so
// engine.go's interface cannot be widened here.
//
// So the extra surface is declared here, as AnnotateFormManager/AnnotateForm, and reached by TYPE
// ASSERTION on Config.FormManager. That is additive: a FormManager that implements only engine.go's
// interface keeps working, and engine.go is untouched.
//
// The three states and their PHP counterparts:
//
//	Config.FormManager == nil                 -> `!isset($fm)`     -> $res = NULL   -> branch 1
//	set, does NOT implement AnnotateFormManager -> $fm set, formsArray has no
//	                                             'AnnotateForm'    -> $res = NULL   -> branch 1
//	set, DOES implement it                    -> $fm->getResults('AnnotateForm')
//
// The middle row is the one to be sure of: it is NOT a Go fudge for "can't ask". A live FormManager
// that has never loaded AnnotateForm returns NULL from getResults (FormManager.php:63-69) — the
// identical value, down the identical branch. A manager that cannot answer and a manager that
// answers NULL are the same tag render, so the assertion cannot manufacture a divergence.
//
// ── THE WRITE PATH: the one place this file opens a database engine.go's openDB cannot ──────────
//
// AnnotateHandler.php:42-43 opens `new PDO('sqlite:'.CONGRUENCY_SQLITE)` READ-WRITE, then CREATEs
// the table if absent and INSERTs. engine.go's openDB is read-only by construction (engine.go:1173-
// 1195) — correct for the ten read-only tags it was written for, and unusable for this one: a
// read-only handle turns branch 4 from an INSERT into an error div, which is not what the PHP does.
// So openAnnotationsDB below is a SECOND, WRITABLE open, local to this file.
//
// It deliberately mirrors PDO rather than improving on it, including the part that looks like a bug:
// PDO's sqlite DSN CREATES the database when the path is missing, and this does too. engine.go's
// divergence 2 chose NOT to create, and that choice was right for a read: a reader that conjures an
// empty db reports "no rows" where PHP reports real data. A WRITE inverts it — PHP would create the
// file, make the table and insert; refusing to create would diverge from the PHP on the very
// operation this tag exists to perform. Mirroring is the faithful call; per-tag, not package-wide.
//
// READ THIS BEFORE YOU FILE engine.go:70 AS A CONTRADICTION. That line says "Nothing in this package
// writes to the DB or to disk", and this file is why that sentence is now too broad — it was written
// when the package held ten read-only tags, and it is a true statement about engine.go, which still
// writes nothing. It cannot be corrected from here: #246's deliverable is this file alone, and
// engine.go is not mine to edit. The scope of the change is exactly this: AnnotateHandler's branch 4,
// the branch the PHP itself writes on, reachable only through a Config.FormManager that implements
// AnnotateFormManager. No other tag, no other branch of this tag, and nothing on either gate surface
// opens a writable handle — measured, not asserted; see THE SIDE-EFFECT PROBE below. A ticket whose
// deliverable covers engine.go should narrow that sentence from "this package" to "engine.go".
//
// WHAT THAT COSTS, EXACTLY, AND WHY THE GATE NEVER PAYS IT. Nothing here opens anything until
// branch 4, which is where the PHP opens too (:42, AFTER the three early returns at :33-41). Both
// gate surfaces take branch 1 and return at :34, so a gate request opens no handle, creates no file,
// runs no SQL and writes no row. Probed in isolation this session: the state directory listed before
// and after a ?page=tags&tag=AnnotateHandler render holds the same entries with the same sizes and
// mtimes, annotations still holds the same row count, and MAX(id) is unmoved. See THE GATE.
//
// ── PDO BINDS EVERYTHING AS A STRING, AND THAT REACHES THE STORED ROW ───────────────────────────
//
// PDOStatement::execute($array) binds every element PDO::PARAM_STR — there is no bindValue with a
// type here (AnnotateHandler.php:48). Four of the five values are already strings; the fifth is
// `microtime(true)`, a float, so PDO casts it with PHP's float->string rule, which is %.*G at the
// `precision` ini (default 14). microtime(true) carries ~16 significant digits, so the value that
// reaches sqlite is TRUNCATED TO 14 — "1752598800.1235", not "1752598800.123456". The declared REAL
// affinity of `ts` then converts that numeric string back to a float, so the row stores the
// truncated instant, not the full one.
//
// This file reproduces that: phpFloatString(engine.go:530) is the same %.*G-precision-14 cast, and
// every parameter is bound as a string, as PDO binds it. `ts` appears in no rendered byte, so this
// changes no output — it changes the ROW, and the row is part of the contract too.
//
// ── WHAT IS NOT BYTE-REPRODUCIBLE, STATED PLAINLY (branch 5 only) ───────────────────────────────
//
// PHP's catch arm renders `get_class($e) . ': ' . $e->getMessage()` (AnnotateHandler.php:59) — e.g.
// "PDOException: SQLSTATE[HY000]: General error: 5 database is locked". A Go error has neither a
// class nor PDO's SQLSTATE text, so throwableHTML/catchThrowable (engine.go:1703-1719) emit the Go
// message alone inside the identical `<div class='cy-form-error'>AnnotateHandler error: …</div>`
// frame. The FRAME is byte-identical; the message inside it is not, and is not claimed to be. This
// is the package's standing, documented limitation, not a new one — and it is unreachable from
// either gate surface, which never opens a database (see above).
//
// ── THE GATE — WHAT WAS RUN, AND WHAT IT MEASURED ───────────────────────────────────────────────
//
// The ticket's diff is `?page=tags&tag=AnnotateHandler` and `?page=annotateDone`, PHP:8899 vs
// Go:8900, byte-identical. Both were RUN this session, and BOTH DIFFS ARE NON-EMPTY — for a reason
// that is not this tag's, and that this file cannot fix from inside its own deliverable:
//
//	?page=tags&tag=AnnotateHandler   php 6616B   go  417B   NON-EMPTY (105 diff lines)
//	                                 this unit's 70 bytes: PRESENT on BOTH sides
//	?page=annotateDone               php 2937B   go 1037B   NON-EMPTY ( 90 diff lines)
//	                                 this unit's 70 bytes: present on PHP, ABSENT on Go
//
// Line 1 is the CMS page FRAME, which the Go server does not reproduce and says so itself:
// server.go:39-43 ("the page/path surface (Controller::control()) is a full PHP CMS and is NOT
// reproducible in Go") and server.go:64-66 ("NOT claimed: that the page's BYTES match PHP … larger
// by a constant ~6.2 KB of CMS chrome (nav/head/style)"). The tag's own bytes agree on both sides;
// the chrome around them does not.
//
// Line 2 is worse and worth stating exactly: server.go's handlePage routes every page key EXCEPT
// "tags" to handleCatalogPage, the table-list seam (server.go:730-736, 833-857), which never invokes
// the tag engine. So ?page=annotateDone on the Go server cannot reach AnnotateHandler at all — its
// 1037B are a list of table names. There is no committed Go entry point that serves that page, and
// wiring one is an edit to server.go, which #246 forbids ("touch nothing else").
//
// Neither diff, therefore, is this unit's gate: both would be exactly as non-empty with this file
// deleted. That is precisely the case the ticket tells me to report rather than settle for — "if you
// cannot make a diff here run against THIS unit, say so on the ticket rather than settling on a diff
// that would be empty even with the unit unimplemented". Reported; the real measurement follows.
//
// (Reproducing the two runs above needs a Go server on 8900, which db.go's main() has no flag for —
// its flags are -db/-route/-method/-input/-routes/-selftest/-immutable/-authorized, db.go:1310-1319.
// The runs used a throwaway harness in the scratch directory that calls NewServer(...).Listen; it is
// not part of this deliverable and was removed.)
//
// The gate that DOES exercise this unit is the repo's own, and it is not invented here: #282 built
// congruency-go/tags/equivalence_test.go precisely for this ("#226 landed 10 tags
// ported-not-measured … Every tag unit from #246 on otherwise re-hits that same wall. This file is
// the way through it", equivalence_test.go:9-13). It cuts the tag's OWN bytes out of the live PHP
// page with TagList.php's own anchors, brackets the Go render with two PHP fetches so a concurrent
// write reports VOLATILE instead of a false failure, and compares byte for byte over the SAME db.
// Registering AnnotateHandler moves it from that harness's skip list into its measured set with no
// edit to it — which is the intended #246 workflow, and what happened:
//
//	cd congruency-go && go test ./tags/ -run 'TestTagEquivalence/AnnotateHandler' -v -count=1
//	    --- PASS: TestTagEquivalence/AnnotateHandler   IDENTICAL: 70B byte-for-byte
//	    SUMMARY: 1/11 registered tags byte-identical to the live PHP; 0 differ; 0 volatile
//
// The 70 bytes are branch 1, and they are the whole of this tag's live render:
//
//	<p>No pending annotation. <a href='?page=forms'>Add one &rarr;</a></p>
//
// That run also reports "45 tags scanned, 11 registered in the Go engine" — 11, not #226's 10,
// which is this file's init() landing in the registry with no edit to engine.go.
//
// THE IN-PAGE SUBSTITUTION SITE was measured one level DOWN from the HTTP surface that cannot carry
// it — at the engine, which is where the substitution actually happens. tags.Render(cfg,
// page=annotateDone) does the real DAO lookup of the real stored template and expands it through the
// real engine; the bytes it substitutes at the <<<AnnotateHandler>>> slot are the same 70 the live
// PHP's ?page=annotateDone carries at that slot, and no raw <<<AnnotateHandler>>> survives. The rest
// of that 510B expansion is <<<TitleTag>>>, <<<Style>>> and <<<SiteMap>>> — three tags no unit has
// ported yet, so they come back as engine.go's marked notPorted notices and the WHOLE page cannot
// match. The SLOT is what this unit owns, and the slot matches.
//
// THE SIDE-EFFECT PROBE (docs/PLAYBOOK.md Theme 3: prove it, before/after, in isolation — do not
// assume the happy path). This tag CAN write, so "the gate writes nothing" is a claim that has to be
// measured, not reasoned. The state directory and the annotations table, either side of five
// RenderTag(AnnotateHandler) renders against the live db:
//
//	before  entries: README.md STATE.json component.json congruency.sqlite manifest.json state.lock
//	        annotations: count=18 max(id)=28
//	after   entries: IDENTICAL — no file created, no size or mtime moved (incl. no -wal/-shm)
//	        annotations: count=18 max(id)=28 — unmoved
//
// That is branch 1 returning at :34, before line :42 ever opens a handle.
//
// ALSO RUN THIS SESSION (go1.26.x, `go build ./...` and `go vet ./...` exit 0, `gofmt -l` clean on
// this file):
//
//   - SelfCheck() — GREEN with the eleventh tag registered. #281 made its registry invariants
//     subset-and-floor rather than equality for exactly this reason (engine.go:132-136), so a new
//     <Tag>.go keeps them green with no edit to engine.go. Confirmed by running it, not assumed.
//     PortedTags() now returns AnnotateHandler first, in sorted order, alongside #226's ten.
//   - THE WHOLE #282 SWEEP, not just this tag: 11/11 registered tags byte-identical to the live PHP,
//     0 differ, 0 volatile, 34 not-yet-ported skipped. Run because a new init() executes inside every
//     other tag's process too — the sweep is what proves this file cost none of them their render.
//
// ── BRANCHES 2-4 WERE MEASURED TOO, AND THAT NEEDED NO POM ──────────────────────────────────────
//
// The live surfaces only ever reach branch 1, so the other branches — the whole validation ladder,
// the SQL and the green panel — would otherwise ship as "derived from the source", unmeasured. They
// did not have to. AnnotateHandler calls exactly two methods on $fm (getResults, getCachedForm) and
// PHP is DUCK-TYPED, so a stub object with those two methods is a faithful FORM_MANAGER: it is the
// same seam this file's AnnotateFormManager assertion is, on the other side of the port. Injecting
// one with PersistentObjectManager::setData makes every branch reachable in BOTH engines.
//
// So both sides were driven over the SAME inputs and byte-identical private copies of the live db
// (snapshotted with sqlite's backup API from an immutable=1 handle; the live db was never opened for
// write and, verified after, is unmoved — same directory entries, annotations still count=18
// max(id)=28). 13 cases, one row each, PHP bytes vs Go bytes:
//
//	branch 1  no pending form              70B  SAME     branch 3  missing id             142B  SAME
//	branch 1  three empty fields           70B  SAME     branch 3  missing tag            142B  SAME
//	branch 2  bad kind                    148B  SAME     branch 4  write, no note         359B  SAME
//	branch 2  kind needs escaping         180B  SAME     branch 4  write, with note       466B  SAME
//	branch 2  kind present-but-NULL       143B  SAME     branch 4  write, trims+escapes   417B  SAME
//	branch 2  kind case-sensitive         147B  SAME     branch 4  write, tag holds a tag 387B  SAME
//	branch 4  kind untrimmed              354B  SAME
//	                                      *** EVERY BRANCH BYTE-IDENTICAL ***
//
// Four of those are aimed squarely at the traps this file's comments claim to have avoided, and each
// would have caught the mistake rather than let it ship:
//
//   - "kind present-but-NULL" (143B, branch 2) separates isset() from the (string) cast. A port that
//     dropped annotateResult's nil test would treat targetKind => NULL as a value, cast it to the
//     empty string, and render branch 1's 70B — a different branch, off by 73 bytes.
//   - "kind untrimmed" (354B) proves trim() runs BEFORE in_array, and it proves it by WRITING: " page "
//     trims to "page", passes the strict in_array, and stores target "page:x". A port that compared
//     before trimming would reject it into branch 2 instead of inserting a row.
//   - "kind case-sensitive" (147B, branch 2) is the other half of that: in_array's third argument is
//     TRUE, so "Page" is rejected. Trimming is not lowercasing, and the two cases pin both edges.
//   - "tag holds a tag" (387B, branch 4) pushes a stored <<<TicketList>>> through the green panel;
//     both engines escape it inert. That is the htmlspecialchars recursion guard engine.go's header
//     describes, exercised here rather than asserted.
//
// THE WRITE ITSELF was compared as a ROW, not just as a render — a byte-identical panel over a wrong
// INSERT would be a passing gate and a broken port. From identical snapshots both engines wrote id 29
// and agreed on every column: tag, target ("page:home", "ticket:246", "source:a&b", "page:x" —
// kind:id, built from the TRIMMED values), note, and meta ({"source":"annotate-form"}). Both also
// stored the RAW text and escaped only on the way out: the row holds tag "<t>" and "<<<TicketList>>>"
// literally, while the panel renders them escaped.
//
// `ts` is the one column that cannot be compared by value: it is microtime(true) AT THE INSTANT OF
// THE INSERT, and the two engines insert at different instants. It was compared by RULE instead, and
// the rule is the precision-14 truncation described above — PHP stored 1784124793.4135 and Go
// 1752598800.1235, each exactly 14 significant digits, neither carrying microtime's full ~16. That is
// the PDO PARAM_STR cast reproduced, measured on both sides.
//
// NOT measured, and so NOT claimed: branch 5, the \Throwable arm — for the reason given above, its
// message is PDO's and Go has no PDO. Its FRAME is byte-identical by construction (it is
// engine.go's throwableHTML, shared with every other tag); the text inside it is not.

import (
	"database/sql"
	"fmt"
)

// init self-registers this tag. This is the whole of #281's "add a file; change nothing central"
// contract (engine.go:1293-1321) — no edit to engine.go's registry, its init(), or its COVERAGE
// list. Register panics on a duplicate name, so two files claiming "AnnotateHandler" fails loudly at
// package init rather than silently shadowing.
func init() {
	Register("AnnotateHandler", func(e *Engine, a *TagArguments) Tag {
		return &AnnotateHandlerTag{e: e, args: a}
	})
}

// AnnotateFormManager is the part of the PHP FormManager surface this tag uses and engine.go's
// FormManager interface (engine.go:343-349) does not carry. Config.FormManager is type-asserted to
// it; see "THE FORM_MANAGER SEAM" in the file header for why that assertion cannot manufacture a
// divergence.
type AnnotateFormManager interface {
	// GetResults is FormManager::getResults($formId) (FormManager.php:63-69): the completed form's
	// results, or NULL when that form is not in formsArray. A nil map IS that NULL — indexing a nil
	// map is legal in Go and yields the zero value, exactly as isset($res['k']) is false on NULL.
	GetResults(formID string) map[string]any

	// GetCachedForm is FormManager::getCachedForm($formId) (FormManager.php:56-61), which returns the
	// cached form or falls off the end returning NULL. ok=false is that NULL — a bool rather than a
	// nil interface because a typed-nil pointer in an interface is non-nil in Go, and this reads
	// `isset($f)` on the PHP side.
	GetCachedForm(formID string) (AnnotateForm, bool)
}

// AnnotateForm is the part of StandardForm this tag touches — the two calls at
// AnnotateHandler.php:51, which clear the completed form so a reload cannot re-insert it.
type AnnotateForm interface {
	// SetResults is StandardForm::setResults($formResults); the tag passes array().
	SetResults(results map[string]any)
	// Reset is StandardForm::reset().
	Reset()
}

// annotateKinds is `$kinds = array('source','page','doc','ticket')` (AnnotateHandler.php:25).
// Compared with in_array(..., true) — STRICT — so only these four exact strings pass.
var annotateKinds = []string{"source", "page", "doc", "ticket"}

// annotateFormID is the form key the tag reads and resets. It is a literal in the PHP, repeated at
// :27 and :51; named once here so the two cannot drift.
const annotateFormID = "AnnotateForm"

// AnnotateHandlerTag is AnnotateHandler (AnnotateHandler.php:16).
type AnnotateHandlerTag struct {
	e *Engine

	// args is `private $arguments` (:18) — stored by the constructor (:19) and never read, here or
	// in the PHP. See "ARGUMENTS" in the file header.
	args *TagArguments
}

// annotateBack is `private static function back()` (AnnotateHandler.php:21), verbatim.
func annotateBack() string {
	return "<p><a href='?page=forms'>&larr; back to the admin forms</a></p>"
}

// annotateResult is the ternary AnnotateHandler.php:28-31 repeats for each of its four fields:
// isset($res[k]) ? trim((string) $res[k]) : <the empty string>.
//
// The isset() is load-bearing and easy to lose: PHP's isset() is FALSE for a key that is PRESENT
// with a NULL value, so a form that stored targetKind => NULL takes the empty-string path — it does
// NOT reach the (string) cast. Hence the explicit nil test; `v, ok := res[k]` alone would treat a
// present-but-NULL key as a value and cast it, which is a different branch of the PHP.
//
// phpTrim is trim()'s real charlist " \t\n\r\0\x0B" (engine.go:630); strings.TrimSpace is not.
func annotateResult(res map[string]any, key string) string {
	v, ok := res[key]
	if !ok || v == nil {
		return ""
	}
	return phpTrim(phpString(v))
}

// GetDocument is AnnotateHandler::get_document() (AnnotateHandler.php:23-61).
//
// The deferred catchThrowable is the `catch (\Throwable $e)` arm at :58-60. Every tag in this
// package has one because the engine has no error boundary of its own (engine.go:1703-1706) — a
// panic here would otherwise take the page down, which the PHP explicitly does not do.
func (t *AnnotateHandlerTag) GetDocument() (out string) {
	defer catchThrowable(&out, "AnnotateHandler")

	// :26-27 — $fm = PersistentObjectManager::getData('FORM_MANAGER');
	//          $res = isset($fm) ? $fm->getResults('AnnotateForm') : null;
	fm, hasFM := t.annotateFormManager()
	var res map[string]any
	if hasFM {
		res = fm.GetResults(annotateFormID)
	}

	// :28-31 — the four fields, each isset-guarded and trimmed.
	kind := annotateResult(res, "targetKind")
	id := annotateResult(res, "targetId")
	tag := annotateResult(res, "tag")
	note := annotateResult(res, "note")

	// :33-35 — BRANCH 1. Note it tests kind/id/tag only: a form carrying nothing but a $note is
	// still "no pending annotation", because $note is not in this condition. Ported as written.
	if kind == "" && id == "" && tag == "" {
		return "<p>No pending annotation. <a href='?page=forms'>Add one &rarr;</a></p>"
	}
	// :36-38 — BRANCH 2. in_array($kind, $kinds, true).
	if !inStrings(kind, annotateKinds) {
		return "<p style='color:#b00020'>Rejected: <code>" + esc(kind) +
			"</code> is not a valid target kind.</p>" + annotateBack()
	}
	// :39-41 — BRANCH 3.
	if id == "" || tag == "" {
		return "<p style='color:#b00020'>Rejected: a target id and a tag are both required.</p>" +
			annotateBack()
	}

	// ── BRANCH 4: the write. Nothing above this line opened anything. ──

	// :42-43 — new PDO('sqlite:'.CONGRUENCY_SQLITE); setAttribute(ERRMODE_EXCEPTION).
	// A Go error from here on lands in the same cy-form-error div PHP's catch arm renders; see
	// "WHAT IS NOT BYTE-REPRODUCIBLE" in the file header for the one part of it that differs.
	db, err := openAnnotationsDB(t.e.cfg.SQLite)
	if err != nil {
		return throwableHTML("AnnotateHandler", err)
	}
	defer db.Close()

	// :44 — $db->exec("CREATE TABLE IF NOT EXISTS annotations (...)"), verbatim. The tag makes its
	// own table rather than depending on a migration, which is why it works against a db that never
	// had one. The column list matches the live db's `annotations` schema exactly (read this session
	// from sqlite_master).
	if _, err := db.Exec("CREATE TABLE IF NOT EXISTS annotations (id INTEGER PRIMARY KEY AUTOINCREMENT, tag TEXT, target TEXT, note TEXT, ts REAL, meta TEXT)"); err != nil {
		return throwableHTML("AnnotateHandler", err)
	}

	// :46 — $target = $kind . ':' . $id;
	target := kind + ":" + id

	// :47-48 — the prepared INSERT. Every parameter is bound as a STRING because
	// PDOStatement::execute($array) binds PDO::PARAM_STR; the microtime float therefore goes in
	// through PHP's precision-14 float->string cast. See "PDO BINDS EVERYTHING AS A STRING".
	ins, err := db.Exec("INSERT INTO annotations (tag,target,note,ts,meta) VALUES (?,?,?,?,?)",
		tag, target, note, phpFloatString(annotateMicrotime(t.e.cfg)), annotateMeta)
	if err != nil {
		return throwableHTML("AnnotateHandler", err)
	}

	// :49 — $aid = (int) $db->lastInsertId();
	aid, err := ins.LastInsertId()
	if err != nil {
		return throwableHTML("AnnotateHandler", err)
	}

	// :51 — if (isset($fm)) { $f = $fm->getCachedForm('AnnotateForm');
	//                         if (isset($f)) { $f->setResults(array()); $f->reset(); } }
	// Clearing the completed form is what stops a reload re-inserting the same annotation. It runs
	// AFTER the insert, so a failed insert leaves the form intact — ported in place, not hoisted.
	if hasFM {
		if f, ok := fm.GetCachedForm(annotateFormID); ok {
			f.SetResults(map[string]any{}) // setResults(array()) — the empty PHP array
			f.Reset()
		}
	}

	// :53-57 — the green panel. Byte-for-byte the PHP's concatenation, in its order, including the
	// "\n" between the closing </div> and the Annotations link, and the $note ternary that emits
	// NOTHING (not an empty <p>) for an empty note.
	out = "<div style='border:1px solid #1a7a3a;border-left:5px solid #1a7a3a;border-radius:6px;padding:.7rem .9rem;background:#f3fbf5'>" +
		"<p style='margin:.2rem 0'><strong>Annotation #" + esc(aid) + " added.</strong></p>" +
		"<p style='margin:.2rem 0;font-size:.9rem'><code>" + esc(tag) + "</code> &rarr; <code>" +
		esc(target) + "</code></p>"
	if note != "" {
		out += "<p style='margin:.2rem 0;font-size:.9rem'>" + esc(note) + "</p>"
	}
	out += "</div>\n<p><a href='?page=annotations'>&rarr; see it in Annotations</a></p>"
	return out
}

// annotateMeta is json_encode(array('source' => 'annotate-form')) (AnnotateHandler.php:48).
//
// Precomputed as the literal it always encodes to: the input is a fixed single-pair map of ASCII
// with no character json_encode's default flags would escape, so PHP emits exactly these bytes on
// every call. Spelling the constant out makes the stored `meta` value readable here instead of
// requiring the reader to run PHP's encoder in their head.
const annotateMeta = `{"source":"annotate-form"}`

// annotateMicrotime is microtime(true) — the current unix time in SECONDS as a float, to
// microsecond resolution.
//
// It reads the engine's clock seam (Config.Now, engine.go:334-335) rather than time.Now directly,
// so a caller driving branch 4 can pin the instant; nil Now is time.Now, which is the live path.
func annotateMicrotime(cfg Config) float64 {
	return float64(cfg.now().UnixNano()) / 1e9
}

// openAnnotationsDB is `new PDO('sqlite:'.$path)` + setAttribute(ATTR_ERRMODE, ERRMODE_EXCEPTION)
// (AnnotateHandler.php:42-43): a WRITABLE handle, which is why this exists next to engine.go's
// read-only openDB rather than calling it. See "THE WRITE PATH" in the file header for why
// mirroring PDO's create-on-missing is the faithful choice for a writing tag, and why no gate
// request reaches this function.
//
// ERRMODE_EXCEPTION needs no counterpart: database/sql returns an error from every call already, and
// each caller above turns it into the same cy-form-error div PHP's catch arm produces.
//
// The sqlite driver is registered by engine.go's blank import of modernc.org/sqlite (engine.go:243),
// which is the same driver openDB uses — both handles speak to the same file through the same
// implementation.
func openAnnotationsDB(path string) (*sql.DB, error) {
	// PHP would build the DSN 'sqlite:' . CONGRUENCY_SQLITE and, with the constant undefined, throw
	// an Error that its catch arm renders. There is no such constant in Go: an empty Config.SQLite is
	// the same "no path was configured" state, reported the same way — through the error return, into
	// the same div. (Unreachable live: boot/configure.php:42 always defines it, and server.go pins
	// the field from DBPath at server.go:762.)
	if path == "" {
		return nil, fmt.Errorf("no database path configured (CONGRUENCY_SQLITE)")
	}
	// NB: NO os.Stat guard, deliberately — openDB has one because a READ of a missing db must not
	// invent an empty one, whereas PDO CREATES the file here and this tag's whole purpose is the
	// write that follows. Mirroring means letting the driver create it, exactly as PDO does.
	db, err := sql.Open("sqlite", "file:"+path)
	if err != nil {
		return nil, err
	}
	// One connection, as PDO has one. It also serializes this handle's CREATE TABLE and INSERT onto
	// the same sqlite connection, which is what makes LastInsertId belong to THIS insert — the same
	// property server.go:25-30 documents for its per-request PDO handle.
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, err
	}
	return db, nil
}

// annotateFormManager is `$fm = PersistentObjectManager::getData('FORM_MANAGER')` narrowed to the
// surface this tag calls. ok=false is `!isset($fm)` for this tag's purposes — either there is no
// FormManager at all, or the one configured answers only engine.go's narrower interface, which is
// indistinguishable in output from a FormManager holding no AnnotateForm. The header's three-state
// table spells that equivalence out.
func (t *AnnotateHandlerTag) annotateFormManager() (AnnotateFormManager, bool) {
	if t.e.cfg.FormManager == nil {
		return nil, false
	}
	fm, ok := t.e.cfg.FormManager.(AnnotateFormManager)
	return fm, ok
}
