package tags

// contenttag.go — ticket #310, unit go-port:tags:tag:ContentTag.
//
// The Go port of ONE tag: invocators/tags/document/ContentTag.php. Per #281 a tag port is
// ADD-A-FILE-ONLY: this file holds the tag's type, its constructor, its GetDocument, its helpers and
// its self-registration (the init() below), and it changes NOTHING in engine.go — the registry picks
// the tag up because Go runs every init() in a package before any other code in it
// (engine.go:1355 Register, engine.go:1393 newTag). Every identifier it defines is contentTag*-
// prefixed or ContentTag*-named, so it cannot collide with the sibling tag ports.
//
// THE CONTRACT: byte-identical HTML. The PHP is the SPEC. Where the two disagree THIS file is wrong.
//
// ── THE WHOLE TAG (ContentTag.php:7-30) ─────────────────────────────────────────────────────────
//
//	class ContentTag implements Tag_Interface{
//	    private $arguments; private $contentID; private $content;
//	    public function __construct($arguments){
//	        $this->arguments = $arguments;                   // :14  (stored, never read again)
//	        $this->contentID = $arguments->top();            // :15
//	        $this->lookup_content();                         // :16
//	    }
//	    public function get_document(){
//	        return $this->content->__toString();             // :20
//	    }
//	    private function lookup_content(){
//	        $contentDAO = new ContentDAO();                              // :24
//	        $contentData = $contentDAO->lookupContent($this->contentID); // :25
//	        $this->content = Content::sql_assoc_array($contentData);     // :26
//	    }
//	}
//
// Note WHERE the work happens: ALL of it is in the CONSTRUCTOR (:15-16), and get_document() only
// stringifies the already-built Content object. That placement is the single most load-bearing fact
// about this tag, because the constructor is what throws. See THE GALLERY RENDER below.
//
// It emits NO markup of its own — its output is one Content_Blocks.Content cell, or the empty
// string. There is no wrapper, no header, no empty-state text to get right; the empty state IS the
// empty string.
//
// ── THE GALLERY RENDER IS AN ERROR PATH, AND THAT IS THIS UNIT'S GATE ───────────────────────────
//
// The gate URL is ?page=tags&tag=ContentTag. TagList renders the selected tag by constructing it
// with NULL — `$obj = new $sel(null);` (TagList.php:67). ContentTag.php:15 then calls
// `$arguments->top()` on that NULL. On PHP 8 that is a fatal Error:
//
//	Error: Call to a member function top() on null
//
// ContentTag has NO try/catch of its own, so the Error propagates out of the constructor into
// TagList's, which wraps `new $sel(null)` AND `$obj->get_document()` in ONE try (TagList.php:66-72):
//
//	try {
//	    $obj = new $sel(null);                        // :67  <- ContentTag throws HERE
//	    $out .= (string)$obj->get_document();         // :68  <- never runs
//	} catch (\Throwable $e) {                         // :69
//	    $out .= "<p style='color:#b00020'>This tag needs context to render standalone: "
//	          . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</p>";   // :70-71
//	}
//
// So the tag's bytes inside the .tagout div are EXACTLY that one <p> — no more, no less, and no
// trailing newline (:71 emits none). This is not inferred: it was MEASURED off the live PHP server
// this session (see contentTagStandaloneHTML) at 120 bytes.
//
// CONSEQUENCE THAT IS EASY TO GET WRONG: `new ContentDAO()` (ContentTag.php:24, reached from :16) is
// NEVER REACHED on the gate path. The gallery render touches no database, no Content_Blocks table,
// and no content constants at all — line 15 throws first. A port that "helpfully" returned "" or a
// no-DB notice here would diverge on every byte of the diff.
//
// ── WHY THE THROW IS RE-SEATED IN GetDocument, AND WHY THAT IS BYTE-EXACT ───────────────────────
//
// A Go factory (`func(e *Engine, args *TagArguments) Tag`, engine.go:1355) CANNOT throw and CANNOT
// return an error — so a constructor-thrown PHP Error has no direct Go counterpart at the
// constructor. It is therefore represented as a value at construction (ctorThrew) and surfaced at
// the only point this file controls: GetDocument.
//
// Moving the throw from the `new` to the `get_document()` call changes NO observable byte, because
// TagList's ONE try covers BOTH statements (:67 and :68) and both land in the SAME catch producing
// the SAME <p>. That is the entire justification, and it holds for every caller that passes nil:
//
//   - TagList's gallery — renderSelected does `lookupTag(sel, nil)` then `obj.GetDocument()`
//     (engine.go:1571-1575), and has no PHP-shaped catch of its own. GetDocument returning the catch
//     <p> is what puts the PHP's bytes in the PHP's place.
//   - RenderTag — `lookupTag(name, nil)` (engine.go:4155), documented to return "the TAG's own
//     bytes", i.e. the slice equivalence_test.go cuts out of the live PHP page between TagList.php:62
//     and :76. For ContentTag that slice IS the catch <p>, so the same return is correct there too.
//   - SelfCheck — `newTag(NewEngine(Config{}), n, nil)` (engine.go:4377) requires the factory to
//     CONSTRUCT rather than blow up on nil args, which is exactly what deferring the throw achieves.
//
// nil args is EXCLUSIVELY the standalone path. The template path cannot reach it: getTagWrapper
// passes `w.parser.GetTagArguments()` (engine.go:950), and TagParser.initialize always assigns
// `ArgumentFactory(p.tag)` (engine.go:784), which always returns a non-nil *TagArguments
// (engine.go:699-703). So `args == nil` <=> "PHP was handed NULL" <=> "the constructor throws".
//
// ── WHY THERE IS NO catchThrowable HERE (a deliberate difference from the sibling ports) ────────
//
// Some ported tags open GetDocument with `defer catchThrowable(&out, "<Tag>")` because THEIR PHP
// class has its own `catch (\Throwable $e)` arm emitting a cy-form-error div. ContentTag.php has NO
// try and NO catch — its whole body is three assignments, a return, and a three-line private helper.
// Adding catchThrowable would invent a "<div class='cy-form-error'>ContentTag error: …</div>" branch
// the PHP can never emit, which is a divergence dressed as robustness. It is omitted on purpose. A
// Go panic here would surface through renderSelected's recover as a marked panic notice
// (engine.go:1564-1570), which is the header's documented divergence 1 (PHP would fatal the page
// instead of emitting anything).
//
// ── THE NON-GALLERY PATH: <<<ContentTag(<id>)>>> ────────────────────────────────────────────────
//
// Reachable only from document content, and per this ticket NO Document_Templates row mentions this
// tag today — so this path renders nowhere in production. It is ported anyway, faithfully.
//
// The argument is `$arguments->top()` = TagArguments::top() = end($this->arguments) — the FIRST
// argument the author wrote, because setArguments stores them reversed (engine.go:686-688). So
// <<<ContentTag(5)>>> yields "5". PHP's end([]) on an empty argument list returns FALSE where Go's
// Top() returns "" (engine.go:735-742); the two agree in outcome here, because DataConnection::quote
// turns BOTH into the same SQL literal — measured with the repo's PHP 8.3 binary this session:
// quote(false) === "''" and quote("") === "''". See contentTagQuote.
//
// Then `new ContentDAO()` (ContentDAO.php:17-20) does CreateConnection(MYSQL_SERVER,
// MYSQL_CONT_DATABASE, CONTENT_LOGIN, CONTENT_PASSWORD) — which performs NO I/O, it only stores the
// credentials (DataConnection.php:18-24) — and calls open(). open() IGNORES those credentials
// entirely when CONGRUENCY_SQLITE is defined:
//
//	if (defined('CONGRUENCY_SQLITE')) { $this->pdo = new PDO('sqlite:' . CONGRUENCY_SQLITE); }  // :32
//	else { $this->pdo = new PDO('mysql:host=' . MYSQL_SERVER . ';dbname=' . $this->database, …); } // :33
//	$this->pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_SILENT);                              // :34
//
// So the content DAO reads the SAME sqlite file as every other ported tag — cfg.SQLite — and the
// "content database" (MYSQL_CONT_DATABASE = 'CONGRUENCY_DOCUMENT') is a fiction the shim collapses.
// The live server always defines CONGRUENCY_SQLITE (boot/configure.php:42, which resolves it to
// <app>/../state/congruency.sqlite — the exact file Config.SQLite names, engine.go:304-305), so the
// mysql branch is unreachable under the gate; contentTagNoSQLiteDivergence documents what this port
// does with it.
//
// ERRMODE_SILENT (:34) is why this tag degrades SILENTLY rather than throwing: PDO::query() returns
// FALSE instead of raising, DataConnection::query() turns that into `return false`
// (DataConnection.php:47), lookupContent's `if($resultSet)` (ContentDAO.php:27) is skipped, $content
// stays NULL, and Content::sql_assoc_array(NULL) still hands back a Content OBJECT whose own
// $content is NULL (Content.php:38-41, the bug #108 guard) — so get_document()'s
// `$this->content->__toString()` does NOT null-deref, it returns Content.php:25's `$this->content ??
// ''`, i.e. "".
//
// THAT IS THIS TAG'S WHOLE DEGRADATION STORY, AND IT IS LIVE TODAY: the shared state db has NO
// Content_Blocks table at all (measured this session: 47 tables, Store_Content_Blocks among them,
// Content_Blocks NOT). So the SELECT fails, and the argument path renders "" for EVERY input right
// now. That is what the ticket means by "degrade IDENTICALLY" — the Go side must return "" here, not
// an error notice and not a diagnostic.

import "strings"

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there.
func init() {
	Register("ContentTag", func(e *Engine, a *TagArguments) Tag { return newContentTagTag(e, a) })
}

// ContentTagTag is ContentTag (ContentTag.php:8-29). The doubled "Tag" is the package convention
// (<TagName>Tag) applied to a tag whose own name already ends in "Tag"; it keeps the type in the
// same shape as CategoryViewTag, BugReportTag and the rest.
//
// The PHP's three properties are $arguments, $contentID and $content. $arguments is assigned at
// :14 and NEVER read again — porting it would be a field no code reads, so it is deliberately not
// carried. $content is NOT stored either: building it is the constructor's job in PHP, but a Go
// factory cannot report the failure of that work, so the computation is deferred to GetDocument
// (see the file header) and the input is stored instead.
type ContentTagTag struct {
	e *Engine

	// ctorThrew records that the PHP constructor throws before it assigns anything usable —
	// `$arguments->top()` on NULL (ContentTag.php:15). True exactly when args == nil, which is
	// exactly the standalone/gallery path.
	ctorThrew bool

	// contentID is $this->contentID (ContentTag.php:15) — the raw, unvalidated argument.
	contentID string
}

// newContentTagTag is ContentTag::__construct (ContentTag.php:13-17), minus the DB work that
// GetDocument now does. It must never panic: SelfCheck constructs every registered tag with nil args
// and asserts it yields a usable Tag (engine.go:4377-4378).
func newContentTagTag(e *Engine, args *TagArguments) *ContentTagTag {
	t := &ContentTagTag{e: e}
	if args == nil {
		// `$arguments->top()` on NULL -> Error. Nothing after :15 runs — in particular
		// lookup_content() (:16) and its `new ContentDAO()` (:24) never happen, so no DB is
		// opened on this path.
		t.ctorThrew = true
		return t
	}
	t.contentID = args.Top()
	return t
}

// contentTagNullArgError is get_class($e).': '.$e->getMessage() for the Error ContentTag.php:15
// throws when $arguments is NULL.
//
// This is not a guess about PHP's wording. It was produced by the repo's own PHP 8.3 binary this
// session (tooling/congruencey-harness/php/php, evaluating `$null->top()` inside the same
// get_class($e) . ": " . $e->getMessage() expression TagList.php:71 uses), and it is what the live
// server actually returns for this tag — see contentTagStandaloneHTML.
const contentTagNullArgError = "Error: Call to a member function top() on null"

// contentTagStandaloneHTML is TagList.php:70-71's catch body, verbatim:
//
//	"<p style='color:#b00020'>This tag needs context to render standalone: "
//	  . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</p>"
//
// MEASURED, not derived: fetching http://127.0.0.1:8899/?page=tags&tag=ContentTag from the live PHP
// server this session and cutting the slice between TagList.php:62's heading anchor and its :76
// close yields EXACTLY these 120 bytes:
//
//	<p style='color:#b00020'>This tag needs context to render standalone: Error: Call to a member function top() on null</p>
//
// The message is run through esc() — this package's htmlspecialchars($s, ENT_QUOTES) port
// (engine.go:599) — rather than hand-escaped, because that is the IDENTICAL call TagList::esc
// (TagList.php:20) makes on the IDENTICAL value, so the two cannot drift apart. (This particular
// message happens to contain no escapable byte, so esc is identity on it today; calling esc anyway
// is what keeps that a fact rather than an assumption.)
//
// There is NO trailing newline: TagList.php:71 ends at "</p>".
func contentTagStandaloneHTML() string {
	return "<p style='color:#b00020'>This tag needs context to render standalone: " +
		esc(contentTagNullArgError) + "</p>"
}

// contentTagNoSQLiteDivergence is emitted only when a tag argument IS present but no sqlite path is
// configured — i.e. PHP's `!defined('CONGRUENCY_SQLITE')`, which sends DataConnection::open() down
// its mysql branch (DataConnection.php:33) to `new PDO('mysql:host=localhost;dbname=CONGRUENCY_DOCUMENT',
// 'content','cont995')`. With no MySQL server that constructor throws a PDOException whose text is
// driver- and host-specific ("SQLSTATE[HY000] [2002] …"), and ContentTag has no catch, so the PHP
// page FATALS — the header's divergence 1 exactly (engine.go:206-212).
//
// This port refuses to forge that message: it returns a MARKED divergence notice, the same choice
// notPortedHTML makes (engine.go:1497-1506), rather than impersonating a PDOException or silently
// returning "" as if the DB had merely been empty. The branch is unreachable under both gates — the
// live server always defines CONGRUENCY_SQLITE (boot/configure.php:42), and the gallery path throws
// at ContentTag.php:15 long before any of this.
func contentTagNoSQLiteDivergence() string {
	return "<p style='color:#b00020'>congruency-go: ContentTag has no sqlite path configured; " +
		"the PHP would open MySQL here and fatal. This notice is a DIVERGENCE from the PHP render, " +
		"not a reproduction of it.</p>"
}

// GetDocument is ContentTag::get_document() (ContentTag.php:19-21) PLUS the constructor work
// (:15-16) that a Go factory cannot perform. It returns $this->content->__toString().
//
// It deliberately has NO `defer catchThrowable(...)` — ContentTag.php has no catch arm to model.
// See the file header.
func (t *ContentTagTag) GetDocument() string {
	// ContentTag.php:15 — the constructor threw; TagList's catch supplies the bytes.
	if t.ctorThrew {
		return contentTagStandaloneHTML()
	}

	// ContentTag.php:24 — new ContentDAO() -> DataConnection::CreateConnection(...)->open().
	if t.e.cfg.SQLite == "" {
		return contentTagNoSQLiteDivergence() // !defined('CONGRUENCY_SQLITE') -> the mysql branch
	}

	// ContentTag.php:25-26 + :20 — lookupContent, wrap in a Content, stringify it.
	return t.contentTagLookupContent()
}

// contentTagLookupContent is ContentTag::lookup_content() (ContentTag.php:23-27) followed by
// get_document()'s `$this->content->__toString()` (:20) — the three PHP steps collapsed into the one
// string they jointly produce, because the intermediate Content object is not observable from
// outside the tag.
//
// ContentDAO::lookupContent($key) (ContentDAO.php:22-35):
//
//	$content = NULL;
//	$key = DataConnection::quote($key);
//	$statement =  "SELECT * FROM Content_Blocks WHERE ContentID = $key ";;
//	$resultSet = $this->dataConnection->query($statement);
//	if($resultSet){
//	    $rows=count($resultSet->rows);
//	    if($rows == 1){        //Only want 1 result set anything else is an error.
//	        $content = $resultSet->rows[0];
//	    }
//	}
//	return $content;
//
// then Content::sql_assoc_array($contentData) (Content.php:36-43) and Content::__toString()
// (Content.php:24-26). Every failure below returns "" for the SAME reason: the Content object's own
// $content stays NULL and __toString returns `$this->content ?? ''`. PHP reaches that on every one
// of them WITHOUT throwing (ERRMODE_SILENT, DataConnection.php:34):
//
//   - db file absent            -> PHP's `new PDO('sqlite:…')` CREATES an empty db (header
//     divergence 2), so the SELECT then fails on the missing table          -> NULL -> ""
//   - Content_Blocks absent     -> PDO::query() returns FALSE, DataConnection::query() returns
//     false (:47), `if($resultSet)` skipped                                 -> NULL -> ""
//     THIS IS THE LIVE CASE: the shared state db has no Content_Blocks table.
//   - zero matching rows        -> MysqlShimResult is truthy, count 0 != 1                -> ""
//   - MORE THAN ONE row         -> count != 1; the DAO's own comment calls that "an error" -> ""
//   - exactly one row, Content NULL or absent -> isset() false -> set_content(null)        -> ""
//
// The `$rows == 1` test is EXACT: two matching rows render "" just as loudly as zero do.
func (t *ContentTagTag) contentTagLookupContent() string {
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return "" // the PDO would have made an empty db; the SELECT then fails just the same
	}
	defer db.Close()

	// ContentDAO.php:24-25 — the key is quoted by DataConnection::quote and INTERPOLATED, not bound,
	// and this port interpolates it too. That is not laziness on either side, and swapping in a
	// placeholder would be a real divergence: SQLite gives a bound "05" TEXT affinity while the bare
	// literal 05 is an INTEGER, so the two can match different rows of ContentID.
	//
	// SAFE BY CONSTRUCTION on the template path: FUNCTION_ARGUMENT is /\([A-Za-z0-9]*\)/
	// (Constants_patched.php:171, ported at engine.go:287), so a tag argument is ALPHANUMERIC ONLY —
	// it cannot contain a quote, a space or a semicolon. contentTagQuote's escaping arm is therefore
	// belt-and-braces on that path; it is ported because quote() is the spec, not because a template
	// can reach it.
	//
	// The trailing space before the closing quote is ContentDAO.php:25's own — reproduced verbatim.
	stmt := "SELECT * FROM Content_Blocks WHERE ContentID = " + contentTagQuote(t.contentID) + " "
	rows, err := queryRows(db, stmt)
	if err != nil {
		return "" // PDO::query() === false under ERRMODE_SILENT — DataConnection.php:47
	}

	// ContentDAO.php:28-32 — `if($rows == 1)`, and NOTHING else yields content.
	if len(rows) != 1 {
		return ""
	}

	// Content.php:39 — set_content(isset($row['Content']) ? $row['Content'] : null), then :25's
	// `$this->content ?? ''`. A missing column and a NULL cell both arrive here as nil, and both
	// PHP branches end at NULL, so phpString's (string)NULL === "" (engine.go:497-500) models both.
	//
	// phpString rather than a plain string assertion because Content_Blocks.Content need not be TEXT:
	// PDO's sqlite driver hands back an int for an INTEGER cell, and __toString() has no declared
	// return type, so PHP COERCES it to string (verified with the repo's PHP 8.3 binary this session:
	// a __toString returning int 42 yields the string "42", it does NOT throw). phpString is that
	// coercion, floats included (engine.go:530-550).
	return phpString(rows[0]["Content"])
}

// contentTagQuote is DataConnection::quote($value) (DataConnection.php:53-63):
//
//	if (get_magic_quotes_gpc()) { $value = stripslashes($value); }
//	if (!is_numeric($value)) { $value = "'" . str_replace("'", "''", $value) . "'"; }
//	return $value;
//
// THE stripslashes ARM IS DEAD. get_magic_quotes_gpc() was REMOVED in PHP 8; the harness restores it
// as a stub that returns FALSE (tooling/congruencey-harness/shim.php:8-9), so the branch never runs.
// The repo says so itself at dev/coverage/branch_test2.php:21 — "The line-64 branch
// (get_magic_quotes_gpc) is UNREACHABLE". It is therefore not ported: porting it would mean porting
// stripslashes for a call that cannot happen.
//
// So the whole function is: numeric -> raw and UNQUOTED; otherwise single-quoted with '' doubling.
// Measured against the repo's PHP 8.3 binary this session — every row is real output, not a guess:
//
//	quote("5")     -> 5        quote("")      -> ''       quote(" 5")   ->  5
//	quote("05")    -> 05       quote("abc")   -> 'abc'    quote("5 ")   -> 5
//	quote("0")     -> 0        quote("5abc")  -> '5abc'   quote("+5")   -> +5
//	quote("1e2")   -> 1e2      quote("0x1A")  -> '0x1A'   quote("-5")   -> -5
//	quote("5.0")   -> 5.0      quote(".5")    -> .5       quote("5.")   -> 5.
//	quote(false)   -> ''       <- end([]) on an empty argument list; identical to quote("")
//
// That last row is why Go's Top() returning "" where PHP's end() returns FALSE is not a divergence:
// is_numeric(false) and is_numeric("") are both false, and str_replace on both yields "", so both
// sides emit the same two bytes ''.
func contentTagQuote(value string) string {
	if contentTagIsNumeric(value) {
		return value
	}
	return "'" + strings.ReplaceAll(value, "'", "''") + "'"
}

// contentTagIsNumeric is PHP 8's is_numeric($value) for a STRING argument.
//
// PHP 8's numeric-string grammar (the trailing-whitespace clause is new in PHP 8.0):
//
//	WS* [+-]? ( DIGITS ("." DIGITS?)? | "." DIGITS ) ( [eE] [+-]? DIGITS )? WS*
//
// where WS is " \t\n\r\v\f" — PCRE's \s set, which isPHPSpace already models (engine.go:624-628).
// An exponent marker with no digits after it does NOT match, and since the pattern must consume the
// WHOLE string, "1e" is correctly reported non-numeric rather than parsed as 1. Hex ("0x1A") is not
// numeric in PHP 7+. Each of these is confirmed by the measured table in contentTagQuote.
//
// Only the boolean is needed: quote() branches on it and returns the ORIGINAL $value untouched when
// it is true, so the parsed value is never used.
func contentTagIsNumeric(s string) bool {
	i, n := 0, len(s)
	for i < n && isPHPSpace(s[i]) { // leading WS*
		i++
	}
	if i < n && (s[i] == '+' || s[i] == '-') { // [+-]?
		i++
	}
	intDigits := 0
	for i < n && s[i] >= '0' && s[i] <= '9' {
		i++
		intDigits++
	}
	fracDigits := 0
	if i < n && s[i] == '.' {
		i++
		for i < n && s[i] >= '0' && s[i] <= '9' {
			i++
			fracDigits++
		}
	}
	if intDigits == 0 && fracDigits == 0 { // neither "5"/"5." nor ".5" — not a number at all
		return false
	}
	if i < n && (s[i] == 'e' || s[i] == 'E') { // ([eE][+-]?DIGITS)?
		j := i + 1
		if j < n && (s[j] == '+' || s[j] == '-') {
			j++
		}
		expDigits := 0
		for j < n && s[j] >= '0' && s[j] <= '9' {
			j++
			expDigits++
		}
		if expDigits > 0 { // an exponent with no digits is not part of the match
			i = j
		}
	}
	for i < n && isPHPSpace(s[i]) { // trailing WS*
		i++
	}
	return i == n // anything left over means the string is not numeric ("5abc", "1e", "5 x")
}
