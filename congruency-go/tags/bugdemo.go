// bugdemo.go — ticket #251, unit go-port:tags:tag:BugDemo.
//
// The Go port of ONE tag: invocators/tags/dev/BugDemo.php. Nothing else. It is a per-tag file of
// the shape #281 established (engine.go:1293-1321): the tag's type, its GetDocument, and an init()
// that self-registers it. engine.go is not touched, and nothing here is central.
//
// THE CONTRACT (engine.go:9-11): byte-identical HTML. THE PHP IS THE SPEC. Where the two disagree
// the Go is wrong — the quirks below are reproduced, not corrected.
//
// ── WHAT BugDemo IS ─────────────────────────────────────────────────────────────────────────────
//
// A dev tag that RUNS a catalogued bug live inside the page rather than describing it (its sibling
// BugReport describes them). It takes one slug argument selecting which bug to demonstrate:
//
//	<<<BugDemo(sqli)>>>   BUG-01 — the SQL-injection path through CatalogDAO
//	<<<BugDemo(lifo)>>>   BUG-08 — the command "queue" that drains last-in-first-out
//	anything else         the "Unknown demo" box
//
// Only non-fatal bugs are demonstrated live; BugDemo.php:14-16 says the fatal ones are left to
// BugReport, "since firing them would take the page down with it".
//
// ── THE FILES THIS PORT MIRRORS, AND WHY EACH IS IN THIS FILE ───────────────────────────────────
//
//	invocators/tags/dev/BugDemo.php                       the tag itself — the spec
//	lib/Modules/StoreModule/Catalog/DAO/CatalogDAO.php    select_products_by_category — THIS TAG'S SQL
//	lib/IOControl/Validators/ValidateFields.php           validateNumericKey — the "patch" the demo demonstrates
//	lib/DatabaseDrivers/MySQL/DataConnection.php          open()/query() — how that SQL reaches sqlite
//	lib/CommandQueues/InterfaceObject/CommandInterfaceObject.php   enqueueCommand/execute — BUG-08 itself
//	lib/CommandQueues/Execution/CommandInterpreter.php    executeCommand — $command->execute()
//	lib/Commands/Command.php                              the Command interface the eval'd probe implements
//
// #251 is scoped to "port THIS tag only — its arguments, its SQL, its markup, and its empty/error
// state", and its deliverable is this file alone. The six collaborators above are not separate
// units: they ARE this tag's SQL and this tag's demonstrated bug, reachable from nowhere else in
// the Go port. So each is ported here, privately, at exactly the depth BugDemo reaches into it —
// not as a general port of the store or command layers, which are their own units.
//
// ── WHY EVERY NEW NAME HERE IS PREFIXED bugDemo ─────────────────────────────────────────────────
//
// package tags is ONE package that ~45 per-tag files (#246+) are being added to CONCURRENTLY, each
// by a different ticket that cannot see the others' files. A private helper named
// validateNumericKey or box in this file would collide at compile time with the identical obvious
// name in a sibling tag's file, and neither ticket could have known. Every identifier this file
// introduces is therefore bugDemo-prefixed, which no other tag's port can plausibly claim. The
// shared primitives it does NOT re-derive — esc, openDB, queryRows, digitRun — are engine.go's,
// reused rather than duplicated.
//
// ── WHAT WAS MEASURED (#251, this session) ──────────────────────────────────────────────────────
//
// Unlike #226/#281 — which recorded that neither php nor the state db existed in their worktree —
// BOTH were present and reachable for this ticket, so this port is MEASURED, not merely derived:
//
//   - php 8.4.23 (tooling/congruencey-harness/php/php) and the live state db
//     (checkouts/current/state/congruency.sqlite, WAL, 13.5MB) both exist, and the PHP app is
//     serving on 127.0.0.1:8899 (`php -S 0.0.0.0:8899 boot/router.php`).
//   - THE GATE, restricted to this unit: EMPTY — this tag's 263 bytes are byte-identical between
//     the live PHP and this port, over that same db. Read "THE GATE" below before trusting that
//     sentence: the ticket's diff as literally written is NOT empty, and cannot be, for reasons
//     that have nothing to do with this tag.
//   - ALL FOUR BRANCHES of get_document() were driven through the REAL PHP class, loaded by the
//     real ClassLoader over the real db (a driver mirroring boot/router.php's bootstrap), and each
//     branch's bytes diffed against this port's: sqli (599B), lifo (513B), the nil-arguments case
//     the gallery takes (263B), and an unknown slug (266B). All four diffs are EMPTY.
//   - THE PHP SEMANTICS BELOW WERE PROBED, NOT REMEMBERED — htmlspecialchars()'s default flags,
//     validateNumericKey's loose ==, switch(NULL), array_pop([]). Each probe's result is recorded
//     at the line that depends on it.
//   - `go build ./...`, `go vet ./...`, `gofmt -l`, `go test ./...` and `go run . -selftest`
//     (engine.go's SelfCheck) all clean with this file present.
//
// ── THE GATE (ticket #251): what is empty, what is not, and why ─────────────────────────────────
//
// The ticket's gate is the gallery render, and for BugDemo that is the WHOLE gate: no
// Document_Templates row mentions <<<BugDemo>>>, so no page embeds it. The gallery constructs
// every tag as `new $sel(null)` (TagList.php:67) — NULL arguments — so the gate exercises the
// "Unknown demo" branch with an EMPTY slug, and nothing else: demo_sqli and demo_lifo are
// unreachable from it. They are ported and diffed anyway (see above), because the ticket asks for
// this tag's arguments and SQL, not only for the bytes the gate happens to touch.
//
// THE TICKET'S DIFF AS WRITTEN COMPARES WHOLE PAGES, AND IS NOT EMPTY:
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=BugDemo') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=BugDemo')
//
// Ran this session (with 8900 replaced — see below): 6801B of PHP against 594B of Go, differing.
// This is STRUCTURAL AND NOT ABOUT THIS TAG. The PHP URL returns a full CMS page — Controller
// chrome, the telemetry <script>, the nav, and the whole 45-entry gallery — and the Go server
// answers it with its own deliberately minimal frame, which server.go:820-823 states outright:
// "the CMS Controller::control() page chrome is still not reproduced here". So that diff is
// non-empty for EVERY tag, ported or not, and would stay non-empty if this file did not exist. A
// gate that cannot distinguish those two states is not this unit's gate, so it is reported here
// rather than quietly replaced.
//
// THE DIFF THAT DOES ISOLATE THIS UNIT IS EMPTY. It is the same two HTTP responses, cut down to
// the tag's own bytes with the anchors #282 established (equivalence_test.go:35-58): the PHP side
// between TagList.php:62's heading and :76's close, minus the measured 17B page tail; the Go side
// with server.go's 4-line frame stripped:
//
//	$ diff php-8899-BugDemo go-18951-BugDemo
//	(empty)
//	rc=0  [263B vs 263B]
//
// The same result arrives independently through the repo's own harness, which is the maintained
// way to re-run this and needs no hand-cutting:
//
//	$ cd congruency-go && go test ./tags/ -run TestTagEquivalence/BugDemo -v
//	    equivalence_test.go:447: coverage : 45 tags scanned, 11 registered in the Go engine, ...
//	    equivalence_test.go:501: IDENTICAL: 263B byte-for-byte
//	--- PASS: TestTagEquivalence/BugDemo
//
// That harness SKIPS an unported tag and only measures a registered one, so its PASS is evidence
// about this file specifically — it could not have passed before this file existed.
//
// WHY 18951 AND NOT THE 8900 THE TICKET NAMES. Port 8900 was already held, this session, by ticket
// #246's coder running its own Go server out of congruency-pair-worktrees/ticket-246 — a worktree
// that has no bugdemo.go. Left alone, the ticket's diff therefore measured a SIBLING'S BINARY:
// its Go side rendered notPortedHTML ("congruency-go: no Go port of BugDemo yet"), which would
// have looked like this port failing when this port was never in the request. That server was not
// disturbed; this worktree's build was served on a free port instead. Anyone re-running the gate
// on a machine with parallel tag tickets in flight must check who owns 8900 first — `lsof -nP
// -iTCP:8900 -sTCP:LISTEN` — because the failure mode is a confident wrong answer, not an error.
//
// ── THE ONE DELIBERATE DIVERGENCE: a MISSING db file ────────────────────────────────────────────
//
// PHP's DataConnection::open() does `new PDO('sqlite:' . CONGRUENCY_SQLITE)` READ-WRITE
// (DataConnection.php:32). That splits into two behaviors this port cannot tell apart:
//
//	db file missing, directory writable -> PDO CREATES an empty db; "SELECT * FROM Products" then
//	                                       fails; ERRMODE_SILENT (DataConnection.php:34) makes that
//	                                       a `false` return, not a throw; `if($resultSet)`
//	                                       (CatalogDAO.php:48) is false, so the DAO returns
//	                                       array() -> 0 rows -> the "Blocked" box renders.
//	directory missing/unwritable        -> PDO THROWS PDOException; BugDemo's catch (BugDemo.php:38)
//	                                       renders box('BugDemo error', 'PDOException: ...').
//
// engine.go's openDB opens READ-ONLY and never creates (engine.go:213-215, 1173-1179), so it
// returns one error for both. This port takes the FIRST branch: a failed open degrades to zero
// rows and the "Blocked" box, exactly as the overwhelmingly likelier missing-file case does in
// PHP. The second branch therefore diverges — a Go "Blocked" box where PHP would show an error
// box — and it is named here rather than papered over. Fabricating PDOException's SQLSTATE text
// would be the worse choice: it would be a false claim about the PHP in the case that actually
// happens. The gate is unaffected either way: the db is present.
//
// Every claim above was read off the cited file, or measured, in THIS checkout this session.
package tags

import (
	"database/sql"
	"fmt"
	"strconv"
	"strings"
)

// init self-registers BugDemo. This is the whole of this file's contract with the rest of the
// package (engine.go:1299-1314): Register is order-independent and Go runs every init() in the
// package before any other code in it, so the registry holds BugDemo before the first render.
func init() {
	Register("BugDemo", func(e *Engine, a *TagArguments) Tag { return newBugDemoTag(e, a) })
}

// BugDemoTag is BugDemo (BugDemo.php:22-97).
type BugDemoTag struct {
	e *Engine

	// which is `private $which` — the slug naming the demo to run.
	which string
}

// newBugDemoTag is BugDemo::__construct (BugDemo.php:26-29):
//
//	$this->which = $arguments ? $arguments->pop() : '';
//
// Two PHP facts collapse into the single Go string "":
//
//  1. $arguments is an OBJECT when present, and every object is truthy, so the ternary tests only
//     "were there arguments at all". A nil *TagArguments is the PHP's NULL — the shape the gallery
//     always uses (`new $sel(null)`, TagList.php:67) and therefore the shape the ticket's gate
//     takes.
//  2. TagArguments::pop() on an EMPTY argument list is array_pop(array()), which is NULL, not "".
//     Probed on php 8.4.23 this session: array_pop([]) === NULL. That NULL then reaches
//     switch($this->which) and htmlspecialchars($this->which), and both treat it exactly as ""
//     (also probed: switch(NULL) takes `default`, and htmlspecialchars((string)NULL) === ""). So
//     the two cases are observationally identical and "" faithfully represents both. Pop's second
//     result — engine.go:747's "there was no value" flag — is discarded for precisely that reason.
func newBugDemoTag(e *Engine, args *TagArguments) *BugDemoTag {
	t := &BugDemoTag{e: e}
	if args != nil {
		t.which, _ = args.Pop()
	}
	return t
}

// GetDocument is BugDemo::get_document() (BugDemo.php:31-41).
//
//	try {
//	    switch ($this->which) {
//	        case 'sqli': return $this->demo_sqli();
//	        case 'lifo': return $this->demo_lifo();
//	        default:     return $this->box('BugDemo', "Unknown demo '" . htmlspecialchars($this->which) . "'. Try sqli or lifo.");
//	    }
//	} catch (\Throwable $e) { ... }
//
// PHP's switch uses LOOSE ==, which is not Go's ==. It cannot diverge here: FUNCTION_ARGUMENTS is
// [A-Za-z0-9]* (engine.go:274), so `which` is alphanumeric-or-empty, while 'sqli' and 'lifo' are
// non-numeric strings — and PHP 8 compares a non-numeric string to anything else AS A STRING. So
// every reachable comparison is the byte comparison Go performs.
func (t *BugDemoTag) GetDocument() (out string) {
	defer t.catchThrowable(&out)
	switch t.which {
	case "sqli":
		return t.demoSQLI()
	case "lifo":
		return t.demoLIFO()
	default:
		// htmlspecialchars($this->which) — DEFAULT flags, not the ENT_QUOTES the tag's siblings
		// pass explicitly. On php 8.1+ those are the same thing: the default became
		// ENT_QUOTES|ENT_SUBSTITUTE|ENT_HTML401. Probed on this checkout's php 8.4.23 this
		// session: htmlspecialchars($s) === htmlspecialchars($s, ENT_QUOTES) for a string holding
		// all five escapable characters. So esc — engine.go:599's port of the ENT_QUOTES call — is
		// the right primitive here, and phpHTMLSpecialChars's ENT_SUBSTITUTE handling
		// (engine.go:403-405) is likewise what the default flags ask for.
		return bugDemoBox("BugDemo", "Unknown demo '"+esc(t.which)+"'. Try sqli or lifo.")
	}
}

// catchThrowable is BugDemo.php:38-40's own catch arm:
//
//	catch (\Throwable $e) {
//	    return $this->box('BugDemo error', htmlspecialchars(get_class($e) . ': ' . $e->getMessage()));
//	}
//
// It is deliberately NOT engine.go:1715's shared catchThrowable, which emits CategoryBrowse's
// cy-form-error div — a different tag's markup. The FRAME here is BugDemo's own box, faithfully.
//
// The MESSAGE cannot be faithful, and says so instead of pretending. Neither PHP branch this
// catches can fire in the Go: the db errors demo_sqli can provoke are swallowed by CatalogDAO's
// `if($resultSet)` rather than thrown (see bugDemoCatalogDAO), and demo_lifo touches only memory.
// What remains is a Go panic — a nil deref, say — which has no PHP counterpart and therefore no
// get_class($e) to report. Inventing a plausible PHP exception name would be a false claim about
// the PHP dressed as equivalence (engine.go:1499-1501 refuses the same trade), so the text names
// the panic for what it is. Recovering at all follows engine.go's divergence 1: a crash is a
// finding, and an engine that dies on bad state is not a better port than one that says so.
func (t *BugDemoTag) catchThrowable(out *string) {
	if r := recover(); r != nil {
		*out = bugDemoBox("BugDemo error", esc("congruency-go panic (no PHP counterpart): "+fmt.Sprint(r)))
	}
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// BUG-01 live — "validated key discarded, raw input reaches SQL" (BugDemo.php:43-62)
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// demoSQLI is BugDemo::demo_sqli().
//
// The title says PATCHED, and the code proves it at run time rather than asserting it: it calls
// the DAO twice, once with a legitimate key and once with an injection payload, and BRANCHES ON
// THE ROW COUNTS. Against this checkout's db the payload yields 0 rows — validateNumericKey
// rejects it before any SQL is built — so the "Blocked" arm renders. The "Injected" arm is the
// live-bug render this tag showed before the patch; it is ported because the PHP still contains
// it and would still take it if the validation regressed.
//
// $leaked is built from the INJECT rows and read only by the "Injected" arm, exactly as the PHP
// builds it unconditionally at BugDemo.php:49-50 and uses it only at :56.
func (t *BugDemoTag) demoSQLI() string {
	dao := t.newBugDemoCatalogDAO() // new CatalogDAO() — one connection, opened in the constructor
	defer dao.close()

	legit := dao.selectProductsByCategory("5")         // category 5
	inject := dao.selectProductsByCategory("0 OR 1=1") // "validated" — but ignored

	leaked := make([]string, 0, len(inject))
	for _, row := range inject {
		// htmlspecialchars($row['name']) — default flags; see GetDocument's note on why that is esc.
		// A NULL name is (string)NULL === "" (engine.go:499-500), which is what PHP renders too.
		leaked = append(leaked, esc(row["name"]))
	}

	body := "<code>select_products_by_category('5')</code> &rarr; <b>" + strconv.Itoa(len(legit)) + "</b> row(s)<br>"
	body += "<code>select_products_by_category('0 OR 1=1')</code> &rarr; <b>" + strconv.Itoa(len(inject)) + "</b> row(s)"
	if len(inject) > len(legit) {
		body += "<br><br><b style='color:#b00020'>Injected.</b> The <code>WHERE</code> clause became " +
			"<code>category=0 OR 1=1</code>, leaking every product: " + strings.Join(leaked, ", ") + "."
	} else {
		body += "<br><br><b style='color:#1a7a3a'>Blocked &#10003;</b> The validated numeric key sanitised the input " +
			"(<code>0 OR 1=1</code> &rarr; <code>NULL</code>), so no injectable query was built."
	}
	return bugDemoBox("BUG-01 &mdash; PATCHED (was live SQL injection)", body)
}

// bugDemoCatalogDAO is CatalogDAO (CatalogDAO.php:8-121) reduced to the ONE method BugDemo calls.
// The other eight are other units' business, and porting them here would be exactly the
// layer-at-once mistake #230 corrected.
//
// db is nil when the connection could not be opened. That models PHP's silent-failure path rather
// than an error: see the file header's "THE ONE DELIBERATE DIVERGENCE".
type bugDemoCatalogDAO struct {
	db *sql.DB
}

// newBugDemoCatalogDAO is `new CatalogDAO()` (CatalogDAO.php:23-26), which builds the connection
// and opens it:
//
//	$this->dataConnection = DataConnection::CreateConnection(MYSQL_SERVER,MYSQL_STORE_DATABASE,STORE_LOGIN,STORE_PASSWORD);
//	$this->dataConnection->open();
//
// The four arguments are dead against this checkout: DataConnection::open() (DataConnection.php:31-35)
// tests `defined('CONGRUENCY_SQLITE')` FIRST and, when it is defined — it always is, boot/configure.php
// defines it — opens `new PDO('sqlite:' . CONGRUENCY_SQLITE)`, ignoring the server/database/login/
// password entirely. So the store catalog and the CMS live in ONE sqlite file, and it is the same
// Config.SQLite every other ported tag reads. Verified this session against the running server:
// its CONGRUENCY_SQLITE resolves to checkouts/current/state/congruency.sqlite, and that file holds
// the Products table (`CREATE TABLE Products (\`key\` INTEGER, category INTEGER, name TEXT,
// description TEXT, page TEXT, picture TEXT)`).
func (t *BugDemoTag) newBugDemoCatalogDAO() *bugDemoCatalogDAO {
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return &bugDemoCatalogDAO{} // db stays nil — PHP's silent-failure path; see the file header
	}
	return &bugDemoCatalogDAO{db: db}
}

// close is DataConnection::close() (DataConnection.php:38-40) — `$this->pdo = null`.
func (d *bugDemoCatalogDAO) close() {
	if d.db != nil {
		d.db.Close()
	}
}

// selectProductsByCategory is CatalogDAO::select_products_by_category (CatalogDAO.php:42-56):
//
//	$result = array();
//	$itemKey = ValidateFields::validateNumericKey($key);
//	if(isset($itemKey)){
//	    $selectString = "SELECT * FROM Products where category=$itemKey";
//	    $resultSet = $this->dataConnection->query($selectString);
//	    if($resultSet){ foreach($resultSet->rows as $__row){ array_push($result,$__row); } }
//	}
//	return $result;
//
// THIS IS THE PATCH BugDemo DEMONSTRATES, and the order of the two guards is the whole point:
// validateNumericKey runs BEFORE any SQL is built, so a rejected key never reaches the string
// interpolation at all. That is why '0 OR 1=1' returns 0 rows instead of every product.
//
// WHY THE KEY IS INTERPOLATED AND NOT BOUND. The PHP interpolates, and this reproduces it — but
// it is not an injection, and the proof is structural rather than a promise: validateNumericKey
// returns $result[0], which is preg_match("/[0-9]+/")'s matched text and therefore ALWAYS a pure
// run of digits, whatever the input was. No other value can reach this line. Interpolating keeps
// the SQL TEXT byte-identical to PHP's, which also sidesteps a real trap: binding would send the
// key as TEXT, and sqlite's comparison of a TEXT parameter against an INTEGER-affinity column is
// not the same operation as comparing an integer literal. engine.go:1098-1101 binds its own
// already-validated key for the same reason of safety; here identical SQL is the stronger
// guarantee, because equivalence is what is being measured.
//
// EVERY failure degrades to zero rows, never to an error — matching PHP exactly: a rejected key
// skips the query (`isset`), and a query that fails returns `false` under ERRMODE_SILENT
// (DataConnection.php:34,45-46) rather than throwing, which `if($resultSet)` turns into the empty
// array. A missing Products table, a missing db, a locked db: all are 0 rows on both sides.
func (d *bugDemoCatalogDAO) selectProductsByCategory(key string) []map[string]any {
	itemKey, ok := bugDemoValidateNumericKey(key)
	if !ok {
		return nil // !isset($itemKey) — no SQL is built at all
	}
	if d.db == nil {
		return nil // the connection failed; PHP's query() returns false -> if($resultSet) -> array()
	}
	rows, err := queryRows(d.db, "SELECT * FROM Products where category="+itemKey)
	if err != nil {
		return nil // ERRMODE_SILENT: query() === false -> if($resultSet) is false -> array()
	}
	return rows
}

// bugDemoValidateNumericKey is ValidateFields::validateNumericKey (ValidateFields.php:29-35):
//
//	$result = array();
//	preg_match("/[0-9]+/",$itemKey,$result);
//	if($itemKey == $result[0]){ return $result[0]; } else { return NULL; }
//
// ok=false is the PHP's NULL (every caller tests isset()). Three details decide the bytes:
//
//  1. THE RETURNED VALUE IS $result[0] — the MATCHED DIGIT RUN — never $itemKey. So a caller can
//     rely on the result being pure digits even where the loose == below let a scruffier input
//     through (PHP 8 reads ' 5' and '5.0' as numeric, so both == '5' and both return "5"). That
//     is what makes selectProductsByCategory's interpolation safe.
//  2. `==` IS LOOSE, and PHP 8 changed it: a numeric string compared to a numeric string compares
//     NUMERICALLY; anything involving a non-numeric string compares as strings. bugDemoLooseEq is
//     that rule. This is the line the whole demo turns on — probed against php 8.4.23 this
//     session: validateNumericKey('5') === '5', validateNumericKey('0 OR 1=1') === NULL, because
//     '0 OR 1=1' is not a numeric string, so '0 OR 1=1' == '0' is a byte comparison and fails.
//  3. NO MATCH IS STILL NULL. With no digits, $result is array() and $result[0] raises "Undefined
//     array key 0" and evaluates to NULL. For $itemKey === "" that makes the test "" == NULL, which
//     is TRUE, so PHP returns $result[0] — i.e. NULL itself — and the caller's isset() is false.
//     For any other non-digit input the == is false and PHP returns NULL explicitly. Both paths end
//     at "not set", which is the single ok=false below.
//
// digitRun is engine.go:290's /[0-9]+/ — the same pattern PHP compiles here, reused rather than
// recompiled.
func bugDemoValidateNumericKey(itemKey string) (string, bool) {
	m := digitRun.FindString(itemKey)
	if m == "" {
		return "", false // no match -> NULL either way; see detail 3
	}
	if bugDemoLooseEq(itemKey, m) {
		return m, true
	}
	return "", false
}

// bugDemoLooseEq is PHP 8's `==` between two STRINGS (the only shape validateNumericKey compares):
//
//	both operands are numeric strings -> compare them as NUMBERS
//	otherwise                         -> compare them as strings (a byte comparison)
//
// This is the PHP 8.0 "saner string to number comparisons" rule. Under PHP 7 the non-numeric
// operand would have been cast to a number instead, making '0 OR 1=1' == '0' TRUE — i.e. BUG-01
// would still be LIVE on a PHP 7 host, and this tag would render its "Injected" arm. The port
// follows the checkout's actual engine (php 8.4.23), which is the one the gate measures.
//
// Integers are compared as integers when both fit, and as floats otherwise, which is zend_compare's
// own order. Only the int path is reachable from this tag — both keys are literals in BugDemo.php
// — but the float fallback is what makes this the rule rather than a special case for them.
func bugDemoLooseEq(a, b string) bool {
	an, aok := bugDemoNumericString(a)
	bn, bok := bugDemoNumericString(b)
	if !aok || !bok {
		return a == b // at least one is not numeric -> PHP 8 compares as strings
	}
	if ai, err := strconv.ParseInt(an, 10, 64); err == nil {
		if bi, err := strconv.ParseInt(bn, 10, 64); err == nil {
			return ai == bi
		}
	}
	af, aerr := strconv.ParseFloat(an, 64)
	bf, berr := strconv.ParseFloat(bn, 64)
	if aerr != nil || berr != nil {
		return a == b
	}
	return af == bf
}

// bugDemoNumericString reports whether s is a PHP 8 NUMERIC STRING, returning it stripped of the
// surrounding whitespace PHP permits. The grammar (PHP 8 language spec, "Numeric strings"):
//
//	WHITESPACE* [+-]? ( DIGITS ('.' DIGITS?)? | '.' DIGITS ) ( [eE] [+-]? DIGITS )? WHITESPACE*
//
// TRAILING whitespace is deliberate: PHP 8.0 made "5 " numeric where PHP 7 did not. PHP's
// whitespace here is " \t\n\r\v\f" — isPHPSpace (engine.go:624-626) is exactly that set, reused.
// The value returned is safe for strconv, which accepts no whitespace of its own.
func bugDemoNumericString(s string) (string, bool) {
	i, j := 0, len(s)
	for i < j && isPHPSpace(s[i]) {
		i++
	}
	for j > i && isPHPSpace(s[j-1]) {
		j--
	}
	body := s[i:j]
	if body == "" {
		return "", false
	}
	k := 0
	if body[k] == '+' || body[k] == '-' {
		k++
	}
	intDigits := 0
	for k < len(body) && body[k] >= '0' && body[k] <= '9' {
		k++
		intDigits++
	}
	fracDigits := 0
	if k < len(body) && body[k] == '.' {
		k++
		for k < len(body) && body[k] >= '0' && body[k] <= '9' {
			k++
			fracDigits++
		}
	}
	if intDigits == 0 && fracDigits == 0 {
		return "", false // neither "5", "5." nor ".5" — not a number at all
	}
	if k < len(body) && (body[k] == 'e' || body[k] == 'E') {
		k++
		if k < len(body) && (body[k] == '+' || body[k] == '-') {
			k++
		}
		expDigits := 0
		for k < len(body) && body[k] >= '0' && body[k] <= '9' {
			k++
			expDigits++
		}
		if expDigits == 0 {
			return "", false // "1e" / "1e+" — the exponent must have digits
		}
	}
	if k != len(body) {
		return "", false // trailing garbage: "0 OR 1=1", "12abc"
	}
	return body, true
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// BUG-08 live — "the command queue runs last-in-first-out" (BugDemo.php:64-89)
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// demoLIFO is BugDemo::demo_lifo(). It enqueues FIRST then SECOND and prints the order they
// actually ran in — which is SECOND then FIRST, because the "queue" drains with array_pop().
// This arm demonstrates a bug that is still LIVE: unlike BUG-01, nothing has patched it, so the
// "Reversed." note always appends against the real CommandInterfaceObject.
//
// TWO PIECES OF PHP MACHINERY VANISH IN THE PORT, and both are no-ops rather than omissions:
//
//  1. `getClassLoader()->loadClassByName('Command')` (BugDemo.php:67) — the PHP must pull the
//     Command interface into scope before eval() can declare a class implementing it. Go resolves
//     types at compile time; there is nothing to load.
//  2. The eval'd BugDemoOrderProbe class (BugDemo.php:68-75), guarded by class_exists so it is
//     declared at most once per process, is bugDemoOrderProbe below — an ordinary Go type. Its
//     `public static $ran`, reset to array() at BugDemo.php:76 immediately before use and read at
//     :83 immediately after, is a plain local slice here: execute() is synchronous, nothing else
//     touches $ran between the reset and the read, so the static is observationally local to one
//     demo_lifo call and a local reproduces it exactly.
func (t *BugDemoTag) demoLIFO() string {
	var ran []string // BugDemoOrderProbe::$ran = array();

	queue := &bugDemoCommandInterfaceObject{}
	queue.enqueueCommand(bugDemoOrderProbeFactory("FIRST", &ran))
	queue.enqueueCommand(bugDemoOrderProbeFactory("SECOND", &ran))
	queue.execute()

	body := "enqueued: <code>FIRST</code> then <code>SECOND</code><br>"
	// implode('</code> then <code>', $ran). The names are literals from two lines up, never DB or
	// user text, so the PHP does not escape them and neither does this — escaping would ADD bytes
	// the PHP never emits. (The htmlspecialchars guard of engine.go:50-60 is about DB-derived text;
	// there is none in this arm.)
	body += "executed: <code>" + strings.Join(ran, "</code> then <code>") + "</code>"
	// PHP: if (BugDemoOrderProbe::$ran === array('SECOND', 'FIRST'))  — === on arrays is
	// same-length, same-order, same-type. The note appends only when the bug actually fired.
	if len(ran) == 2 && ran[0] == "SECOND" && ran[1] == "FIRST" {
		body += "<br><br><b style='color:#b5651d'>Reversed.</b> <code>execute()</code> drains with " +
			"<code>array_pop()</code>, so the queue is really a stack."
	}
	return bugDemoBox("BUG-08 &mdash; live command-queue ordering", body)
}

// bugDemoCommand is the Command interface (lib/Commands/Command.php) at the depth demo_lifo uses
// it. The PHP interface also declares a static commandFactory($parameters) — Go has no static
// interface methods, so that half is bugDemoOrderProbeFactory, the concrete constructor the tag
// actually calls (BugDemo.php:78-79 calls it on the class, never through the interface).
type bugDemoCommand interface {
	execute()
	String() string // __toString()
}

// bugDemoOrderProbe is the eval'd BugDemoOrderProbe (BugDemo.php:69-74). ran points at the caller's
// slice — the port of the class's `public static $ran` (see demoLIFO's note 2).
type bugDemoOrderProbe struct {
	name string
	ran  *[]string
}

// bugDemoOrderProbeFactory is BugDemoOrderProbe::commandFactory($p):
//
//	public static function commandFactory($p){ $c=new self(); $c->name=$p; return $c; }
func bugDemoOrderProbeFactory(p string, ran *[]string) *bugDemoOrderProbe {
	return &bugDemoOrderProbe{name: p, ran: ran}
}

// execute is `public function execute(){ self::$ran[] = $this->name; }` — the probe records that
// it ran, and the ORDER of those records is the whole measurement.
func (p *bugDemoOrderProbe) execute() { *p.ran = append(*p.ran, p.name) }

// String is `public function __toString(){ return "probe(".$this->name.")"; }`.
//
// Nothing in demo_lifo calls it: the only __toString consumer is CommandInterfaceObject's
// commented-out debug print (CommandInterfaceObject.php:19). It is ported because the Command
// interface REQUIRES it (Command.php:13) — the eval'd class would be a fatal without it, so it is
// part of the shape this tag depends on, not decoration.
func (p *bugDemoOrderProbe) String() string { return "probe(" + p.name + ")" }

// bugDemoCommandInterfaceObject is CommandInterfaceObject (CommandInterfaceObject.php:8-38),
// minus two fields demo_lifo never reaches: $commandClasses (dead — declared, never assigned) and
// $commandRegistry (`new CommandRegistry()` in the constructor, then never read by any code path
// this tag touches).
//
// THIS TYPE IS BUG-08. Porting it correctly means porting the defect: execute() drains with
// array_pop(), so a queue built FIRST-then-SECOND runs SECOND-then-FIRST. #251 is explicit that
// the PHP is the spec and a genuine defect is ported faithfully, not fixed here.
type bugDemoCommandInterfaceObject struct {
	// commandQueue is `private $commandQueue = array()` (set in the constructor).
	commandQueue []bugDemoCommand
}

// enqueueCommand is `array_push($this->commandQueue,$command)` (CommandInterfaceObject.php:18-21)
// — it appends, which is the correct half of the queue.
func (q *bugDemoCommandInterfaceObject) enqueueCommand(c bugDemoCommand) {
	q.commandQueue = append(q.commandQueue, c)
}

// execute is CommandInterfaceObject::execute() (CommandInterfaceObject.php:23-36) — THE BUG:
//
//	reset($this->commandQueue);
//	while(!empty($this->commandQueue)){
//	    CommandInterpreter::executeCommand(array_pop($this->commandQueue));
//	}
//
// array_pop takes the LAST element, so the queue drains newest-first: it is a stack wearing a
// queue's name. The reset() is a no-op for the ordering — its own comment (":29") says it is there
// only to normalise the internal array pointer, which array_pop resets anyway — so it has no Go
// counterpart. CommandInterpreter::executeCommand is a one-line forwarder,
// `$command->execute()` (CommandInterpreter.php:14-16), inlined here.
func (q *bugDemoCommandInterfaceObject) execute() {
	for len(q.commandQueue) > 0 {
		last := q.commandQueue[len(q.commandQueue)-1]
		q.commandQueue = q.commandQueue[:len(q.commandQueue)-1] // array_pop
		last.execute()                                          // CommandInterpreter::executeCommand
	}
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The markup
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// bugDemoBox is BugDemo::box($title, $body) (BugDemo.php:91-96) — the frame every branch returns.
//
// Neither argument is escaped, on either side. Each call site passes a literal title, and passes a
// body it has already escaped where escaping was due (the "Unknown demo" slug, the leaked product
// names) — so escaping here would double-escape the markup the bodies deliberately contain.
// Reproduced exactly: the string concatenation below is BugDemo.php:92-95 line for line, including
// the &#9654; play-triangle and the space after it.
func bugDemoBox(title, body string) string {
	return "<div style='border:1px solid #d8d2c4;border-radius:6px;background:#f3efe4;" +
		"padding:.7rem .9rem;margin:.6rem 0;font-size:.85rem'>" +
		"<div style='font:600 .72rem/1 monospace;color:#7a5a2a;margin-bottom:.4rem'>&#9654; " +
		title + "</div>" + body + "</div>"
}
