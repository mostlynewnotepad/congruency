package tags

// ticketlogger.go — ticket #342, unit go-port:tags:tag:TicketLogger.
//
// The Go port of ONE tag: invocators/tags/dev/TicketLogger.php. Nothing else. Per #281 a tag port is
// ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its helpers and its
// self-registration (the init() below), and it changes NOTHING in engine.go — the registry picks the
// tag up because Go runs every init() in a package before any other code in it (Register,
// engine.go:1355; newTag, engine.go:1393). Every identifier it defines is ticketLogger*-prefixed or
// TicketLogger*-named, so it cannot collide with the sibling tag ports.
//
// THE CONTRACT, as everywhere in this package: byte-identical HTML. THE PHP IS THE SPEC — where the
// two disagree THIS file is wrong, and a quirk below is a quirk because the PHP has it.
//
// ── WHAT THE PHP TAG IS ─────────────────────────────────────────────────────────────────────────
//
// TicketLogger is "the handler half of #38" (TicketLogger.php:8): the tag that FINALIZES a ticket
// submission. It reads the completed TicketForm out of the session's FORM_MANAGER, validates `type`
// against an allowlist it reads FROM THE forms TABLE, INSERTs one row into the unified `tickets`
// table with a mechanical AUTOINCREMENT id, clears the form so a refresh cannot file twice, and
// renders the confirmation. It renders at ?page=tags&tag=TicketLogger (the gallery) and is
// substituted into the one page whose template embeds it: `ticketDone`.
//
// It is a WRITING tag, like AnnotateHandler (#246) and NewCategoryHandler before it. Everything
// unusual about this file follows from that one fact; see "THE WRITE PATH" below.
//
// ── THE FIVE BRANCHES, in the order get_document() takes them (TicketLogger.php:51-93) ──────────
//
//	1. no pending form   type=='' && description==''   -> "No pending ticket submission. File one ->"
//	2. bad type          type not in allowed_types()   -> "Rejected: <type> is not an allowed ticket
//	                                                       type." + back()
//	3. no description    description==''               -> "Rejected: a description is required."
//	                                                       + back()
//	4. the write         everything else               -> INSERT, clear the form, the green
//	                                                       "Ticket #N logged." panel
//	5. any \Throwable                                  -> the cy-form-error div
//
// NOTE THE BRANCH ORDER, because it is not the obvious one: the TYPE is validated BEFORE the
// description is. A submission carrying a bad type AND an empty description renders branch 2, not
// branch 3. Ported in the PHP's order, not a tidier one.
//
// Branch 1 is the branch this unit's gate takes, and that is not an accident of the harness — it is
// the PHP's own steady state. bin/Initialize_POM.php puts a FRESH FormManager in the POM on every
// request that lacks one, and FormManager::getResults returns NULL for a form that is not in its
// formsArray (FormManager.php:63-69). So a request with no prior TicketForm submission — every gate
// request — reaches get_document() with $res === NULL, hence type/description both '', hence branch
// 1. MEASURED against the live PHP on 127.0.0.1:8899 this session; see THE GATE below.
//
// ── ARGUMENTS: this tag takes none, and that is a property of the PHP, not an omission here ─────
//
// TicketLogger.php:21-22 is the whole of its argument handling:
//
//	private $arguments;
//	public function __construct($arguments) { $this->arguments = $arguments; }
//
// $arguments is STORED AND NEVER READ — no method of the class touches it. So the two invocation
// shapes this unit can see are identical in output by construction:
//
//	the gallery     `new TicketLogger(null)`   (TagList.php:67-68) -> args nil
//	the ticketDone  `<<<TicketLogger>>>`       template            -> args empty
//
// The template's site was read out of the live db with the engine's own DAO join this session and is
// the BARE invocation, no parentheses:
//
//	Documents.DocumentID='ticketDone' -> Document_Templates.Content =
//	  "<!DOCTYPE html>\n<html>\n<head>\n<<<TitleTag>>>\n<<<Style>>>\n</head>\n<body>\n
//	   <nav><<<SiteMap>>></nav>\n<h1>Ticket submitted</h1>\n<<<TicketLogger>>>\n</body>\n</html>\n"
//
// That is the ONLY argument form the live site uses, and it passes none. The `args` field is kept
// below anyway, unread, because the PHP keeps it: a port that dropped it would be a tidier class
// than the one it claims to reproduce.
//
// ── THE FORM_MANAGER SEAM: why this file declares two interfaces ────────────────────────────────
//
// The tag's input is `PersistentObjectManager::getData('FORM_MANAGER')` (TicketLogger.php:55), and
// Go has no POM — engine.go's divergence 3 makes it Config.FormManager instead. But that interface
// carries only RunForm/LoadFailure (engine.go:343-349), which is what FormTag needs; TicketLogger
// needs getResults / getCachedForm / setResults / reset, and #342's deliverable is THIS FILE ALONE,
// so engine.go's interface cannot be widened here.
//
// So the extra surface is declared here, as TicketLoggerFormManager/TicketLoggerForm, and reached by
// TYPE ASSERTION on Config.FormManager. That is annotatehandler.go's precedent (#246), which
// login.go:111 names as the pattern for exactly this situation, and which newcategoryhandler.go
// (:377-391) followed. It is additive: a FormManager that implements only engine.go's interface keeps
// working, and engine.go is untouched.
//
// The three states and their PHP counterparts:
//
//	Config.FormManager == nil                     -> `!isset($fm)`  -> $res = NULL -> branch 1
//	set, does NOT implement TicketLoggerFormManager -> $fm set, formsArray has no
//	                                                 'TicketForm'   -> $res = NULL -> branch 1
//	set, DOES implement it                        -> $fm->getResults('TicketForm')
//
// The middle row is the one to be sure of: it is NOT a Go fudge for "can't ask". A live FormManager
// that has never loaded TicketForm returns NULL from getResults (FormManager.php:63-69) — the
// identical value, down the identical branch. A manager that cannot answer and a manager that answers
// NULL are the same tag render, so the assertion cannot manufacture a divergence.
//
// WHAT DECLARING THEM FILE-LOCALLY COSTS, stated plainly (newcategoryhandler.go:130-133 states the
// same): Go interface satisfaction is structural but NAMED-TYPE-EXACT on signatures, so this file's
// `GetCachedForm(string) (TicketLoggerForm, bool)`, annotatehandler.go's `(AnnotateForm, bool)` and
// newcategoryhandler.go's `(NewCategoryForm, bool)` are THREE DIFFERENT methods. One concrete
// FormManager therefore cannot serve all three handler tags at once. That costs nothing today —
// Config.FormManager is nil on every live path, and each tag's own tests inject their own stub — and
// the alternative is editing engine.go, which this ticket forbids. A ticket whose deliverable covers
// engine.go should hoist one shared form surface there and collapse all three.
//
// ── THE ALLOWLIST IS DATA, NOT A CONSTANT ───────────────────────────────────────────────────────
//
// This is the fact that most distinguishes TicketLogger from its sibling handlers, and the one most
// tempting to get wrong. AnnotateHandler's kinds are a literal array in its source; TicketLogger's
// are NOT. allowed_types() (TicketLogger.php:28-36) READS THEM OUT OF THE forms TABLE at render time
// and scrapes them with a regex:
//
//	SELECT elementString FROM forms WHERE formName='TicketForm' AND name='type'
//	preg_match_all('/<<([^>]+)>>/', (string)$row['elementString'], $m);  $types = $m[1];
//
// The PHP's own comment says why it does not just reference TicketForm::spec: "no cross-tag class
// ref — the tag loader and the app autoloader are different ClassLoaders; a tag cannot autoload
// another tag" (:26-27). So a port that hardcoded the list would be hardcoding a DB cell, and would
// silently stop matching the PHP the day an admin edits the form. This file does the query.
//
// The live cell, read this session:
//
//	<<build>><<bug>><<design>><<spec>><<test>><<documentation>><<tooling>><<cms>><<deploy>>
//
// i.e. today's allowlist is {build, bug, design, spec, test, documentation, tooling, cms, deploy}.
// That is a MEASUREMENT of the data, not a specification of it — nothing below depends on it.
//
// THE THREE WAYS allowed_types() RETURNS AN EMPTY LIST, all of which reject every type at :65:
//
//	!defined('CONGRUENCY_SQLITE')  -> :30 returns array() before opening anything
//	no matching forms row          -> fetch() === false -> `if ($row)` false -> $types stays array()
//	row present, no <<...>> pairs  -> preg_match_all finds nothing -> $m[1] is array()
//
// The middle one has a trap worth naming: `if ($row)` tests the ROW, not the CELL. A row whose
// elementString is NULL or '' is still a non-empty PHP array, hence TRUTHY, so it DOES reach
// preg_match_all — which then finds nothing and yields the same empty list by the third route. Both
// spellings agree on the outcome here; the code below transcribes the PHP's, not a shortcut.
//
// ── THE WRITE PATH: the one place this file opens a database engine.go's openDB cannot ──────────
//
// TicketLogger.php opens `new PDO('sqlite:' . CONGRUENCY_SQLITE)` TWICE — once in allowed_types()
// (:31) and once in insert_ticket() (:40) — each with ERRMODE_EXCEPTION, and each a DEFAULT PDO
// handle: read-write, and create-the-file-if-missing. engine.go's openDB is read-only by construction
// (engine.go:1173-1195) — correct for the read-only tags it was written for, and unusable for this
// one: a read-only handle turns branch 4 from an INSERT into an error div, which is not what the PHP
// does. So openTicketLoggerDB below is a SECOND, WRITABLE open, local to this file.
//
// IT IS USED FOR BOTH OPENS, INCLUDING allowed_types's READ-ONLY SELECT. That looks like an
// over-reach and is deliberate: :31 is a plain `new PDO(...)`, so on a MISSING db file the PHP
// CREATES an empty one and only then throws on the absent `forms` table. Opening that SELECT
// read-only in Go would refuse instead of creating — a different side-effect profile from the PHP on
// the identical line. Mirroring PDO is the faithful call, and it is per-tag, not package-wide;
// annotatehandler.go:96-101 reasons the same way about the same PDO quirk. (ContentTag reaches the
// opposite conclusion for ITS read and is also right: its DAO runs ERRMODE_SILENT, where a
// conjured-empty db and a refused open both render "". Here ERRMODE_EXCEPTION makes both an error
// div, so only the file-creation differs, and mirroring it is what keeps the two engines identical.)
//
// TWO HANDLES, NOT ONE, because the PHP opens two. This matters beyond pedantry: lastInsertId() is a
// property of the CONNECTION, and insert_ticket's handle is the one that did the INSERT. Collapsing
// them into a shared handle would be a refactor of the PHP, not a port of it.
//
// READ THIS BEFORE YOU FILE engine.go:70 AS A CONTRADICTION. That line says "Nothing in this package
// writes to the DB or to disk". It was written when the package held ten read-only tags; #246's
// annotatehandler.go already made it too broad, and this file is the third to do so. It remains a
// true statement about engine.go, which still writes nothing, and it cannot be corrected from here:
// #342's deliverable is this file alone. The scope of this file's write is exactly: TicketLogger's
// branch 4, the branch the PHP itself writes on, reachable only through a Config.FormManager that
// implements TicketLoggerFormManager AND a type on the DB-sourced allowlist AND a non-empty
// description. No other tag, and no other branch of this tag, opens a writable handle.
//
// WHAT THAT COSTS, EXACTLY, AND WHY THE GATE NEVER PAYS IT. Nothing here opens anything until branch
// 2's allowed_types() call at :64 — which is AFTER branch 1's early return at :60-62. The gate takes
// branch 1 and returns at :61, so a gate request opens no handle, creates no file, runs no SQL and
// writes no row. PROBED in isolation this session; see THE SIDE-EFFECT PROBE below.
//
// ── PDO BINDS EVERYTHING AS A STRING, AND THAT REACHES THE STORED ROW ───────────────────────────
//
// PDOStatement::execute($array) binds every element PDO::PARAM_STR — there is no bindValue with a
// type at TicketLogger.php:46-47. Most of the values are already strings; `ts` and `updated` are
// both `microtime(true)`, a float, so PDO casts them with PHP's float->string rule, which is %.*G at
// the `precision` ini (default 14). microtime(true) carries ~16 significant digits, so the value that
// reaches sqlite is TRUNCATED TO 14 — "1752598800.1235", not "1752598800.123456". The declared REAL
// affinity of `ts`/`updated` then converts that numeric string back to a float, so the row stores the
// truncated instant, not the full one.
//
// This file reproduces that: phpFloatString (engine.go:530) is the same %.*G-precision-14 cast, and
// every parameter is bound as a string, as PDO binds it. Neither column appears in a rendered byte,
// so this changes no output — it changes the ROW, and the row is part of the contract too.
//
// ONE microtime() CALL, TWO COLUMNS. :42 assigns `$now` once and :46 binds it to BOTH :ts and :up, so
// a stored row always has ts === updated EXACTLY. Calling the clock twice would drift them apart by
// the width of a json_encode; the code below calls it once, as the PHP does.
//
// ── WHAT IS NOT BYTE-REPRODUCIBLE, STATED PLAINLY (branch 5 only) ───────────────────────────────
//
// PHP's catch arm renders `get_class($e) . ': ' . $e->getMessage()` (TicketLogger.php:91) — e.g.
// "PDOException: SQLSTATE[HY000]: General error: 1 no such table: forms". A Go error has neither a
// class nor PDO's SQLSTATE text, so throwableHTML/catchThrowable (engine.go:1711-1719) emit the Go
// message alone inside the identical `<div class='cy-form-error'>TicketLogger error: …</div>` frame.
// The FRAME is byte-identical; the message inside it is not, and is not claimed to be. This is the
// package's standing, documented limitation, not a new one — and it is unreachable from the gate,
// which never opens a database (see above).
//
// ── THE GATE — WHAT WAS RUN, AND WHAT IT MEASURED ───────────────────────────────────────────────
//
// The gate is the #282 harness, and it is NOT a whole-page diff of ?page=tags (which is
// structurally non-empty for every tag, ported or not — the Go server frames the tag itself,
// server.go:820-823):
//
//	cd congruency-go && go test ./tags/ -run TestTagEquivalence -count=1 -v
//
// HONEST STATUS, AND THE ONE THING THIS FILE CANNOT CLAIM: that command was NOT executed in the
// session that wrote this file. Every `go` invocation — `go test`, `go build`, `go vet`, `gofmt` —
// was refused by this session's command permissions ("This command requires approval", auto-denied
// in a non-interactive pair-loop spawn). No PHP binary exists in this worktree either
// (tooling/congruencey-harness/php/ holds only .php sources; there is no system php), so the usual
// "measured with the repo's PHP 8.3 binary" claim is not available to this file and is NOT made
// anywhere in it. Statements below are labelled as measured only where python3 (which IS permitted)
// could measure them against the live PHP server and the live db. THE PORT IS THEREFORE UNVERIFIED
// ON THE GO SIDE; the next runner of this gate should treat that as the first thing to check.
//
// WHAT WAS MEASURED, with python3, against the live PHP on 127.0.0.1:8899 and the live state db:
//
//  1. THE PHP SIDE OF THE GATE, cut with the harness's own algorithm reimplemented in python —
//     pageTail() via TagList.php:77-78's "Unknown tag" branch (TAIL = "\n</body>\n</html>\n", 17B,
//     matching equivalence_test.go's own measurement), the :62 heading anchor asserted to occur
//     exactly once, the page asserted to end with "</div>\n"+TAIL, and the slice cut between. Fetched
//     TWICE, the harness's stability sandwich: both fetches returned the SAME 80 bytes, so the slice
//     is not volatile.
//
//     PHP's ?page=tags&tag=TicketLogger tag slice = 80B:
//
//     <p>No pending ticket submission. <a href='?page=tickets'>File one &rarr;</a></p>
//
//     Those are branch 1's bytes, and they are the whole of this tag's live render. ticketLoggerNone
//     below is that literal, and it is what GetDocument returns on the gate path. What is measured is
//     the PHP side and the equality of the Go SOURCE literal to it — NOT a Go execution.
//
//  2. THE ALLOWLIST CELL and the `tickets` schema, read from the live db with an immutable=1 handle
//     (zero sidecars, Theme 3): the forms row is the 9-type string quoted above, and `tickets` is
//     `id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, updated REAL NOT NULL, component TEXT,
//     title TEXT NOT NULL, severity TEXT, status TEXT NOT NULL, body TEXT, meta TEXT` (+ later
//     approval_sig/patch/kind). Every column this file's INSERT names exists, with the affinity the
//     "PDO BINDS EVERYTHING AS A STRING" section assumes.
//
//  3. THE ticketDone TEMPLATE, via the engine's own Documents/Document_Templates join — the bare
//     <<<TicketLogger>>> quoted in the ARGUMENTS section.
//
// ── THE SIDE-EFFECT PROBE (docs/PLAYBOOK.md Theme 3) ────────────────────────────────────────────
//
// This tag CAN write, so "the gate writes nothing" is a claim that must be measured, not reasoned.
// The live state directory and the `tickets` table, either side of the two gate fetches above:
//
//	before  tickets: count=334 max(id)=345
//	after   tickets: count=334 max(id)=345 — unmoved; no file created, no -wal/-shm
//
// That is branch 1 returning at :61, before :64 ever calls allowed_types(). Note what this probe does
// and does not cover: it exercises the PHP's branch 1 over the gate URL, which is the branch that
// decides the gate. It does NOT exercise the Go side, for the permissions reason stated above.
//
// ── WHAT IS PORTED BUT NOT MEASURED, LISTED SO NOBODY MISTAKES IT FOR VERIFIED ──────────────────
//
// Branches 2-4 and the json_encode below are transcribed from the PHP source and reasoned about, not
// executed on either side. #246 was able to drive its equivalents through both engines by injecting a
// duck-typed stub FORM_MANAGER with PersistentObjectManager::setData; that needs a php binary, and
// this session has none. The specific unverified claims, so they can be checked cheaply later:
//
//   - branch order (type before description), the four literal HTML strings, and the ?page=tickets
//     link targets — transcribed from TicketLogger.php:60-88 by eye.
//   - ticketLoggerMeta's json_encode, derived from PHP's DOCUMENTED default flags and ext/json's
//     escaping rules, NOT from a run. On today's allowlist every type is lowercase ASCII, where every
//     rule below is the identity, so the live value is plainly {"source":"web-form","type":"build"}
//     and friends. The escaping only becomes load-bearing if an admin puts a slash, a quote or a
//     non-ASCII byte in the form's <<...>> list.
//   - the PDO precision-14 float bind (engine.go's phpFloatString is #246's, already exercised there).

import (
	"database/sql"
	"fmt"
	"regexp"
	"strings"
	"unicode/utf8"
)

// init self-registers this tag. This is the whole of #281's "add a file; change nothing central"
// contract (engine.go:1344-1368) — no edit to engine.go's registry, its init(), or its COVERAGE list.
// Register PANICS on a duplicate name, so two files claiming "TicketLogger" fails loudly at package
// init rather than silently shadowing. Registering here is also what flips IsPorted("TicketLogger")
// to true, which is what makes the #282 harness MEASURE this tag instead of skipping it.
func init() {
	Register("TicketLogger", func(e *Engine, a *TagArguments) Tag {
		return &TicketLoggerTag{e: e, args: a}
	})
}

// TicketLoggerFormManager is the part of the PHP FormManager surface this tag uses and engine.go's
// FormManager interface (engine.go:343-349) does not carry. Config.FormManager is type-asserted to
// it; see "THE FORM_MANAGER SEAM" in the file header for why that assertion cannot manufacture a
// divergence, and for what declaring it file-locally costs.
type TicketLoggerFormManager interface {
	// GetResults is FormManager::getResults($formId) (FormManager.php:63-69): the completed form's
	// results, or NULL when that form is not in formsArray. A nil map IS that NULL — indexing a nil
	// map is legal in Go and yields the zero value, exactly as isset($res['k']) is false on NULL.
	GetResults(formID string) map[string]any

	// GetCachedForm is FormManager::getCachedForm($formId) (FormManager.php:56-61), which returns the
	// cached form or falls off the end returning NULL. ok=false is that NULL — a bool rather than a
	// nil interface because a typed-nil pointer in an interface is non-nil in Go, and this reads
	// `isset($form)` on the PHP side (TicketLogger.php:80).
	GetCachedForm(formID string) (TicketLoggerForm, bool)
}

// TicketLoggerForm is the part of StandardForm this tag touches — the two calls at
// TicketLogger.php:80, which clear the completed form so that, in the PHP's own words, "a
// refresh/return can't file it twice" (:77).
type TicketLoggerForm interface {
	// SetResults is StandardForm::setResults($formResults); the tag passes array().
	SetResults(results map[string]any)
	// Reset is StandardForm::reset().
	Reset()
}

// ticketLoggerFormID is the form key the tag reads and resets. It is a literal in the PHP, repeated
// at :56 and :79; named once here so the two cannot drift.
//
// It is a `forms`.formName value in the db, not a PHP class — the same table allowed_types() scrapes
// its allowlist out of. See "THE ALLOWLIST IS DATA" in the file header.
const ticketLoggerFormID = "TicketForm"

// ticketLoggerTypePattern is preg_match_all's '/<<([^>]+)>>/' (TicketLogger.php:34), which scrapes the
// allowlist out of the form's stored elementString.
//
// Go's regexp is leftmost-first (Perl/PCRE semantics, not POSIX-longest) for a pattern built with
// MustCompile, so it selects the same match PCRE's backtracking search would. That equivalence is not
// even stressed here: `[^>]+` cannot cross a '>', so on the live cell —
// "<<build>><<bug>><<design>>…" — there is exactly one way to match at each position, and both
// engines yield the same nine captures.
var ticketLoggerTypePattern = regexp.MustCompile(`<<([^>]+)>>`)

// TicketLoggerTag is TicketLogger (TicketLogger.php:19).
type TicketLoggerTag struct {
	e *Engine

	// args is `private $arguments` (:21) — stored by the constructor (:22) and never read, here or in
	// the PHP. See "ARGUMENTS" in the file header.
	args *TagArguments
}

// ticketLoggerBack is the "back to the form" paragraph TicketLogger.php:68 and :72 both emit. Unlike
// its sibling handlers, this tag has no `private static function back()` — the string is written out
// twice in the PHP. It is named once here so the two copies cannot drift; the BYTES are the PHP's,
// verbatim, including the ?page=tickets target (NOT ?page=forms, which is where AnnotateHandler and
// NewCategoryHandler send the reader — an easy and silent thing to copy wrong from those files).
func ticketLoggerBack() string {
	return "<p><a href='?page=tickets'>&larr; back to the form</a></p>"
}

// ticketLoggerNone is TicketLogger.php:61's branch-1 return, verbatim.
//
// MEASURED: these are exactly the 80 bytes the live PHP's ?page=tags&tag=TicketLogger carries between
// TagList.php's :62 and :76 anchors, cut with the #282 harness's own algorithm and stable across two
// fetches. See "THE GATE" in the file header — and note the caveat there, that the measurement is of
// the PHP side and of this literal's equality to it, not of a Go run.
const ticketLoggerNone = "<p>No pending ticket submission. <a href='?page=tickets'>File one &rarr;</a></p>"

// ticketLoggerResult is the ternary TicketLogger.php:57-58 repeats for each of its two fields:
// isset($res[k]) ? trim((string) $res[k]) : ''.
//
// The isset() is transcribed as the explicit nil test: PHP's isset() is FALSE for a key that is
// PRESENT with a NULL value, so a form that stored type => NULL takes the empty-string path and never
// reaches the (string) cast. As in newcategoryhandler.go:426-433, that nil test cannot change a byte
// for THIS tag — phpString(nil) is "" and phpTrim leaves it "", which is the same empty string the
// isset()-false arm returns — but it is what :57 SAYS, and a transcription that happens to be
// equivalent is still the right transcription.
//
// phpTrim is trim()'s real charlist " \t\n\r\0\x0B" (engine.go:630); strings.TrimSpace is not, and
// THAT one IS load-bearing here: it decides branch 1 vs branch 2 for a whitespace-only type, and
// branch 3 vs branch 4 for a whitespace-only description.
func ticketLoggerResult(res map[string]any, key string) string {
	v, ok := res[key]
	if !ok || v == nil {
		return ""
	}
	return phpTrim(phpString(v))
}

// ticketLoggerUrgent is TicketLogger.php:75, transcribed:
//
//	$urgent = isset($res['urgent']) && $res['urgent'] !== '' && $res['urgent'] !== null;
//
// Two things about that line are easy to "clean up" into a bug, and neither is cleaned up here:
//
//   - The `!== null` is REDUNDANT — isset() is already false for a NULL value — but it is harmless
//     and it is what the source says, so both tests are transcribed.
//   - `!== ''` is a STRICT comparison against the empty STRING, and that is NOT the same as PHP's
//     falsiness. A checkbox arriving as "0" is urgent. An int 0 is urgent. Even `false` is urgent,
//     because false !== ''. ONLY the exact empty string (or absent, or NULL) is not urgent. Hence
//     the string-typed test below rather than any emptiness or truthiness check.
//
// Non-string values are therefore urgent whenever they are present and non-nil, which is exactly what
// `!== ''` does to them: no non-string PHP value is identical to ''. (Form results are strings on
// every live path — they come from the session's StandardForm, not from a DB row — so the non-string
// arm is faithfulness insurance, not a live branch.)
func ticketLoggerUrgent(res map[string]any) bool {
	v, ok := res["urgent"]
	if !ok || v == nil { // isset(...) && ... !== null
		return false
	}
	if s, isString := v.(string); isString && s == "" { // ... !== ''
		return false
	}
	return true
}

// GetDocument is TicketLogger::get_document() (TicketLogger.php:51-93).
//
// The deferred catchThrowable is the `catch (\Throwable $e)` arm at :89-92. Every tag in this package
// has one whose PHP class has one, because the engine has no error boundary of its own
// (engine.go:1711-1719) — a panic here would otherwise take the page down, which the PHP explicitly
// does not do. The PHP's own comment says so: "Wrapped in try/catch: the tag engine has no error
// boundary (BUG-06)" (:16).
func (t *TicketLoggerTag) GetDocument() (out string) {
	defer catchThrowable(&out, "TicketLogger")

	// :55-56 — $fm = PersistentObjectManager::getData('FORM_MANAGER');
	//          $res = isset($fm) ? $fm->getResults('TicketForm') : null;
	fm, hasFM := t.ticketLoggerFormManager()
	var res map[string]any
	if hasFM {
		res = fm.GetResults(ticketLoggerFormID)
	}

	// :57-58 — the two fields, each isset-guarded and trimmed.
	typ := ticketLoggerResult(res, "type")
	description := ticketLoggerResult(res, "description")

	// :60-62 — BRANCH 1. This is the gate's branch, and nothing above this line opened anything.
	if typ == "" && description == "" {
		return ticketLoggerNone
	}

	// :64-69 — BRANCH 2. The allowlist comes from the forms table (see "THE ALLOWLIST IS DATA"), and
	// this is the FIRST line of the tag that touches a database.
	//
	// allowed_types() runs under ERRMODE_EXCEPTION, so a DB failure THROWS in the PHP and lands in its
	// catch arm at :89. The Go equivalent is an error return, turned into the same cy-form-error div
	// here rather than swallowed into an empty allowlist — swallowing it would render branch 2's
	// "Rejected" for what the PHP renders as an error.
	allow, err := t.ticketLoggerAllowedTypes()
	if err != nil {
		return throwableHTML("TicketLogger", err)
	}
	// in_array($type, $allow, true) — STRICT, so the comparison is case-sensitive and does no juggling.
	if !inStrings(typ, allow) {
		return "<p style='color:#b00020'>Rejected: <code>" + esc(typ) +
			"</code> is not an allowed ticket type.</p>" + ticketLoggerBack()
	}
	// :70-73 — BRANCH 3. NOTE: this runs AFTER the type check, not before it. See the header.
	if description == "" {
		return "<p style='color:#b00020'>Rejected: a description is required.</p>" + ticketLoggerBack()
	}

	// ── BRANCH 4: the write. ──

	// :75-76 — $urgent = ...; $id = self::insert_ticket($type, $description, $urgent ? 'high' : 'medium');
	severity := "medium"
	if ticketLoggerUrgent(res) {
		severity = "high"
	}
	id, err := t.ticketLoggerInsertTicket(typ, description, severity)
	if err != nil {
		return throwableHTML("TicketLogger", err)
	}

	// :77-81 — consume the submission so a refresh/return can't file it twice:
	//   if (isset($fm)) { $form = $fm->getCachedForm('TicketForm');
	//                     if (isset($form)) { $form->setResults(array()); $form->reset(); } }
	// It runs AFTER the insert, so a failed insert leaves the form intact — ported in place, not
	// hoisted above the write.
	if hasFM {
		if form, ok := fm.GetCachedForm(ticketLoggerFormID); ok {
			form.SetResults(map[string]any{}) // setResults(array()) — the empty PHP array
			form.Reset()
		}
	}

	// :82-88 — the green panel, byte-for-byte the PHP's concatenation in its order, including the
	// "\n" between the closing </div> and the ticket-list link.
	//
	// Unlike AnnotateHandler's $note and NewCategoryHandler's $desc, the description paragraph here is
	// UNCONDITIONAL — there is no ternary at :87. It cannot be empty anyway: branch 3 returned above
	// for an empty description. Both facts point the same way; the PHP is transcribed either way.
	return "<div style='border:1px solid #1a7a3a;border-left:5px solid #1a7a3a;border-radius:6px;" +
		"padding:.7rem .9rem;background:#f3fbf5'>" +
		"<p style='margin:.2rem 0'><strong>Ticket #" + esc(id) + " logged.</strong></p>" +
		"<p style='margin:.2rem 0;font-size:.9rem'>type <code>" + esc(typ) +
		"</code> &middot; status <code>OPEN</code></p>" +
		"<p style='margin:.4rem 0 .1rem;font-size:.9rem'>" + esc(description) + "</p>" +
		"</div>\n<p><a href='?page=tickets'>&larr; see it in the ticket list</a></p>"
}

// ticketLoggerAllowedTypes is TicketLogger::allowed_types() (TicketLogger.php:28-36):
//
//	$types = array();
//	if (!defined('CONGRUENCY_SQLITE')) { return $types; }
//	$db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
//	$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
//	$row = $db->query("SELECT elementString FROM forms WHERE formName='TicketForm' AND name='type'")
//	          ->fetch(PDO::FETCH_ASSOC);
//	if ($row) { preg_match_all('/<<([^>]+)>>/', (string)$row['elementString'], $m); $types = $m[1]; }
//	return $types;
//
// The error return is the ERRMODE_EXCEPTION throw; the caller turns it into the PHP's catch-arm div.
// A nil slice with a nil error is the PHP's `array()` — in_array on it is false for every type, which
// is branch 2 for everyone. See "THE THREE WAYS allowed_types() RETURNS AN EMPTY LIST" in the header.
func (t *TicketLoggerTag) ticketLoggerAllowedTypes() ([]string, error) {
	// :30 — if (!defined('CONGRUENCY_SQLITE')) { return $types; }
	//
	// There is no such constant in Go: an empty Config.SQLite is the same "no path was configured"
	// state. It returns the empty allowlist WITHOUT an error, because that is what :30 does — it
	// returns array(), it does not throw. (Unreachable live: boot/configure.php:42 always defines the
	// constant, and server.go pins the field from DBPath.)
	if t.e.cfg.SQLite == "" {
		return nil, nil
	}

	// :31-32 — new PDO('sqlite:'.CONGRUENCY_SQLITE); setAttribute(ERRMODE_EXCEPTION).
	// Writable ON PURPOSE even though this function only reads; see "THE WRITE PATH" in the header.
	db, err := openTicketLoggerDB(t.e.cfg.SQLite)
	if err != nil {
		return nil, err
	}
	defer db.Close()

	// :33 — the query, verbatim (the literals are in the SQL in the PHP too, not bound).
	rows, err := queryRows(db, "SELECT elementString FROM forms WHERE formName='TicketForm' AND name='type'")
	if err != nil {
		return nil, err
	}

	// :34 — `if ($row)`. fetch() returns the FIRST row or false, so this is "was there a row at all".
	// It tests the ROW, not the cell: a row whose elementString is NULL or '' is a non-empty PHP
	// array and therefore TRUTHY, so it still reaches preg_match_all — which finds nothing in
	// (string)NULL === "" and yields the same empty list. Transcribed as the PHP has it.
	if len(rows) == 0 {
		return nil, nil
	}

	// :34 — preg_match_all('/<<([^>]+)>>/', (string)$row['elementString'], $m); $types = $m[1];
	//
	// $m[1] is PREG_PATTERN_ORDER's group-1 column: every capture, in order, duplicates included (a
	// cell listing "<<bug>><<bug>>" yields two "bug" entries, exactly as PHP would — in_array does not
	// care, and neither does this).
	cell := phpString(rows[0]["elementString"])
	matches := ticketLoggerTypePattern.FindAllStringSubmatch(cell, -1)
	types := make([]string, 0, len(matches))
	for _, m := range matches {
		types = append(types, m[1])
	}
	return types, nil
}

// ticketLoggerInsertTicket is TicketLogger::insert_ticket() (TicketLogger.php:39-49) — "the only
// writer of web-submitted tickets" (:38).
//
// The PHP's `$severity = 'medium'` DEFAULT parameter is not carried: the tag's one call site (:76)
// always passes the argument explicitly, so the default is dead code in the PHP and a Go default
// would be a parameter this package cannot reach. Callers pass "high" or "medium", as :76 does.
//
// Returns `(int)$db->lastInsertId()` (:48) — the MECHANICAL id the PHP's header comment insists on:
// "callers never supply the id, same discipline as jazz open_ticket()" (:12-14).
func (t *TicketLoggerTag) ticketLoggerInsertTicket(typ, description, severity string) (int64, error) {
	// :40-41 — new PDO('sqlite:'.CONGRUENCY_SQLITE); setAttribute(ERRMODE_EXCEPTION).
	// A SECOND handle: the PHP opens one here too, and lastInsertId belongs to THIS connection.
	db, err := openTicketLoggerDB(t.e.cfg.SQLite)
	if err != nil {
		return 0, err
	}
	defer db.Close()

	// :42 — $now = microtime(true). ONE call, bound to BOTH :ts and :up at :46, so ts === updated
	// exactly. cfg.now() is the engine's clock seam (engine.go:334-335, 375-379); nil Now is
	// time.Now, which is the live path.
	now := phpFloatString(float64(t.e.cfg.now().UnixNano()) / 1e9)

	// :43 — $meta = json_encode(array('source' => 'web-form', 'type' => $type));
	meta := ticketLoggerMeta(typ)

	// :44-47 — the prepared INSERT, with 'OPEN' a SQL literal rather than a bound parameter, exactly
	// as the PHP writes it. Named placeholders become positional ones in the SAME column order:
	// ts, updated, component, title, severity, [status='OPEN'], body, meta.
	//
	// Every parameter is bound as a STRING because PDOStatement::execute($array) binds PDO::PARAM_STR;
	// the microtime float therefore goes in through PHP's precision-14 float->string cast. See "PDO
	// BINDS EVERYTHING AS A STRING" in the file header.
	//
	// Note which value goes where, because the PHP's execute() array is NOT in the column order and
	// reads as if it were: :ti (title) and :bo (body) BOTH get $description, and :cm (component) gets
	// $type. There is no title distinct from the body — the tag stores the description twice.
	res, err := db.Exec(
		"INSERT INTO tickets (ts,updated,component,title,severity,status,body,meta)\n"+
			"                                VALUES (?,?,?,?,?,'OPEN',?,?)",
		now, now, typ, description, severity, description, meta)
	if err != nil {
		return 0, err
	}

	// :48 — return (int)$db->lastInsertId();
	return res.LastInsertId()
}

// ticketLoggerMeta is json_encode(array('source' => 'web-form', 'type' => $type))
// (TicketLogger.php:43).
//
// It cannot be a precomputed constant the way annotatehandler.go:470's annotateMeta is: $type is a
// value scraped out of the forms table at render time (see "THE ALLOWLIST IS DATA" in the header), so
// the encoder has to be real.
//
// json_encode returns FALSE when its input is not valid UTF-8 (JSON_ERROR_UTF8). $meta is then the
// boolean false, which PDOStatement::execute binds PARAM_STR — i.e. (string)false === "" — so the row
// stores an empty meta rather than failing. That is what the empty return below models; it does NOT
// throw, because json_encode does not throw without JSON_THROW_ON_ERROR.
//
// NOT MEASURED — see "WHAT IS PORTED BUT NOT MEASURED" in the file header. This session had no PHP
// binary, so the rules encoded here come from PHP's documented default flags and ext/json's
// php_json_escape_string, not from a run. On today's live allowlist every type is lowercase ASCII,
// where every rule is the identity, so the value this produces is {"source":"web-form","type":"build"}
// and its eight siblings.
func ticketLoggerMeta(typ string) string {
	encoded, ok := ticketLoggerJSONString(typ)
	if !ok {
		return "" // json_encode(...) === false, bound PARAM_STR as ""
	}
	// "source", "type" and "web-form" contain no byte any default flag escapes, so they are spelled
	// out rather than routed through the encoder. PHP preserves insertion order for a string-keyed
	// array, so 'source' precedes 'type'.
	return `{"source":"web-form","type":` + encoded + `}`
}

// ticketLoggerJSONString is json_encode() with DEFAULT flags applied to one PHP string, including the
// surrounding quotes. ok=false is JSON_ERROR_UTF8 — the whole json_encode call returns false.
//
// The default flags mean, precisely:
//
//   - " \ / and the five short control escapes (\b \f \n \r \t) are escaped. The SLASH is the one
//     people forget: PHP escapes "/" as "\/" unless JSON_UNESCAPED_SLASHES is passed, and it is not.
//   - any other byte below 0x20 becomes \u00xx, LOWERCASE hex. 0x7F (DEL) is NOT escaped — ext/json
//     emits every byte >= 0x20 raw.
//   - every non-ASCII rune becomes \uXXXX (lowercase hex, UTF-16), because JSON_UNESCAPED_UNICODE is
//     not passed; runes above the BMP become a surrogate PAIR.
//   - a byte sequence that is not valid UTF-8 aborts the whole encode.
func ticketLoggerJSONString(s string) (string, bool) {
	var b strings.Builder
	b.Grow(len(s) + 2)
	b.WriteByte('"')
	for i := 0; i < len(s); {
		if c := s[i]; c < utf8.RuneSelf {
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
					fmt.Fprintf(&b, `\u%04x`, c)
				} else {
					b.WriteByte(c)
				}
			}
			i++
			continue
		}
		r, size := utf8.DecodeRuneInString(s[i:])
		if r == utf8.RuneError && size == 1 {
			return "", false // malformed UTF-8 -> JSON_ERROR_UTF8 -> json_encode returns false
		}
		if r > 0xFFFF { // outside the BMP: PHP emits the UTF-16 surrogate pair
			r -= 0x10000
			fmt.Fprintf(&b, `\u%04x\u%04x`, 0xD800+(r>>10), 0xDC00+(r&0x3FF))
		} else {
			fmt.Fprintf(&b, `\u%04x`, r)
		}
		i += size
	}
	b.WriteByte('"')
	return b.String(), true
}

// openTicketLoggerDB is `new PDO('sqlite:'.$path)` + setAttribute(ATTR_ERRMODE, ERRMODE_EXCEPTION)
// (TicketLogger.php:31-32 and :40-41, which are the same two lines twice): a WRITABLE handle, which
// is why this exists next to engine.go's read-only openDB rather than calling it. See "THE WRITE
// PATH" in the file header for why mirroring PDO's create-on-missing is the faithful choice — for
// BOTH of this tag's opens, the read included — and why no gate request reaches this function.
//
// ERRMODE_EXCEPTION needs no counterpart: database/sql returns an error from every call already, and
// every caller turns it into the same cy-form-error div PHP's catch arm produces.
//
// The sqlite driver is registered by engine.go's blank import of modernc.org/sqlite, which is the
// same driver openDB uses — both handles speak to the same file through the same implementation.
func openTicketLoggerDB(path string) (*sql.DB, error) {
	// PHP would build the DSN 'sqlite:' . CONGRUENCY_SQLITE and, with the constant undefined, throw an
	// Error its catch arm renders. There is no such constant in Go: an empty Config.SQLite is the same
	// "no path was configured" state, reported the same way — through the error return, into the same
	// div. Note this is NOT the path allowed_types takes for the same condition: :30 checks defined()
	// FIRST and returns an empty list without opening anything, which is why ticketLoggerAllowedTypes
	// has its own SQLite=="" guard above and never reaches here with an empty path.
	if path == "" {
		return nil, fmt.Errorf("no database path configured (CONGRUENCY_SQLITE)")
	}
	// NB: NO os.Stat guard, deliberately — openDB has one because a READ of a missing db must not
	// invent an empty one, whereas PDO CREATES the file here. Mirroring means letting the driver
	// create it, exactly as PDO does.
	db, err := sql.Open("sqlite", "file:"+path)
	if err != nil {
		return nil, err
	}
	// One connection, as PDO has one. It also serializes this handle's statements onto the same sqlite
	// connection, which is what makes LastInsertId belong to THIS insert — the same property
	// server.go:25-30 documents for its per-request PDO handle.
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, err
	}
	return db, nil
}

// ticketLoggerFormManager is `$fm = PersistentObjectManager::getData('FORM_MANAGER')`
// (TicketLogger.php:55) narrowed to the surface this tag calls. ok=false is `!isset($fm)` for this
// tag's purposes — either there is no FormManager at all, or the one configured answers only
// engine.go's narrower interface, which is indistinguishable in output from a FormManager holding no
// TicketForm. The header's three-state table spells that equivalence out.
func (t *TicketLoggerTag) ticketLoggerFormManager() (TicketLoggerFormManager, bool) {
	if t.e.cfg.FormManager == nil {
		return nil, false
	}
	fm, ok := t.e.cfg.FormManager.(TicketLoggerFormManager)
	return fm, ok
}
