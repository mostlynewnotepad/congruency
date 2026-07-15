package tags

// productview.go — ticket #326, unit go-port:tags:tag:ProductView.
//
// The Go port of ONE tag: invocators/tags/store/ProductView.php. Per #281 a tag port is
// ADD-A-FILE-ONLY: this file holds the tag's type, its constructor, its GetDocument, its helpers and
// its self-registration (the init() below), and it changes NOTHING in engine.go — the registry picks
// the tag up because Go runs every init() in a package before any other code in it
// (engine.go:1355 Register, engine.go:1393 newTag). Every identifier it defines is productView*-
// prefixed or ProductView*-named, so it cannot collide with the sibling tag ports.
//
// (engine.go:189-198's PORTED/NOT PORTED lists still name ProductView under NOT PORTED. That is not
// an omission on this ticket's part: engine.go:190-191 declares itself "a copy" and names
// PortedTags() — which is registry-derived, engine.go:1406-1415 — as "the authority". The sibling
// CategoryView port is stale in that same list for the same reason. Correcting a comment in
// engine.go is a different file than this ticket's deliverable, so it is left alone.)
//
// THE CONTRACT: byte-identical HTML. The PHP is the SPEC. Where the two disagree THIS file is wrong.
//
// ── THE WHOLE TAG (ProductView.php:7-24) ────────────────────────────────────────────────────────
//
//	class ProductView implements Tag_Interface{
//	    private $product_id;
//	    private $product_string;
//	    public function __construct($arguments){
//	        $this->product_id = $arguments->top();                                     // :15
//	        $catalogDAO = new CatalogDAO();                                            // :16
//	        $this->product_string = $catalogDAO->get_product_details($this->product_id); // :17
//	    }
//	    public function get_document(){ return $this->product_string; }                // :20-22
//	}
//
// ProductView is the structural TWIN of CategoryView (invocators/tags/store/CategoryView.php,
// ported in categoryview.go under #256): same shape, same argument handling, same degradation. The
// tags differ in exactly two observable ways — the DAO method called at :17
// (get_product_details vs get_category_details) and, inside it, the SQL's filter column
// (productID vs categoryID; CatalogDAO.php:82 vs :100). Everything else below is the same
// reasoning re-verified against ProductView's own lines this session, not inherited.
//
// Note WHERE the work happens: ALL of it is in the CONSTRUCTOR, and get_document() only returns the
// already-computed string. That placement is the single most load-bearing fact about this tag,
// because the constructor is what throws. See THE GALLERY RENDER below.
//
// It emits NO markup of its own — its output is raw Store_Content_Blocks.Content concatenated, or
// nothing at all. There is no wrapper, no header, no empty-state text to get right; the empty state
// IS the empty string.
//
// ── THE GALLERY RENDER IS AN ERROR PATH, AND THAT IS THIS UNIT'S GATE ───────────────────────────
//
// The gate URL is ?page=tags&tag=ProductView. The ticket states that NO Document_Templates row
// mentions <<<ProductView>>>, so this gallery render is this unit's ENTIRE gate. TagList renders the
// selected tag by constructing it with NULL — `$obj = new $sel(null);` (TagList.php:67).
// ProductView.php:15 then calls `$arguments->top()` on that NULL. On PHP 8 that is a fatal Error:
//
//	Error: Call to a member function top() on null
//
// This is NOT speculation about PHP's wording. This repo records that exact message shape from real
// PHP 8 runs of its own code: tooling/congruencey-bugs/repro/bug02_productdao_no_connection.php:10
// expects "Error: Call to a member function query() on null", and bug15_configformfce_null_deref.php:25
// expects "Error: Call to a member function getElementString() on null". Both strings are produced by
// bootstrap.php:96's `get_class($e) . ": " . $e->getMessage()` — character-for-character the SAME
// expression TagList.php:71 uses. So the class is "Error", the message is
// "Call to a member function <method>() on null", and for this tag <method> is `top` — ProductView
// calls the SAME TagArguments method CategoryView does (:15 in both), so the message is identical.
//
// ProductView has NO try/catch of its own, so the Error propagates out of the constructor into
// TagList's, which wraps `new $sel(null)` AND `$obj->get_document()` in ONE try (TagList.php:66-72):
//
//	try {
//	    $obj = new $sel(null);                        // :67  <- ProductView throws HERE
//	    $out .= (string)$obj->get_document();         // :68  <- never runs
//	} catch (\Throwable $e) {                         // :69
//	    $out .= "<p style='color:#b00020'>This tag needs context to render standalone: "
//	          . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</p>";   // :70-71
//	}
//
// So the tag's bytes inside the .tagout div are EXACTLY that one <p> — no more, no less, and no
// trailing newline (:71 emits none).
//
// CONSEQUENCE THAT IS EASY TO GET WRONG: `new CatalogDAO()` (ProductView.php:16) is NEVER REACHED
// on the gate path. The gallery render touches no database, no Store_Content_Blocks table, and no
// store constants at all — line 15 throws first. A port that "helpfully" returned "" or a no-DB
// notice here would diverge on every byte of the diff.
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
//     and :76. For ProductView that slice IS the catch <p>, so the same return is correct there too.
//   - SelfCheck — `newTag(NewEngine(Config{}), n, nil)` (engine.go:4377) requires the factory to
//     CONSTRUCT rather than blow up on nil args, which is exactly what deferring the throw achieves.
//
// nil args is EXCLUSIVELY the standalone path. The template path cannot reach it: getTagWrapper
// passes `w.parser.GetTagArguments()` (engine.go:950), and TagParser.initialize always assigns
// `ArgumentFactory(p.tag)` (engine.go:784), which always returns a non-nil *TagArguments
// (engine.go:699-703). So `args == nil` <=> "PHP was handed NULL" <=> "the constructor throws".
//
// This is why the nil check below tests `args == nil` and NOT `args.Top() == ""`: TagArguments.Top()
// is nil-safe and returns "" for BOTH a nil wrapper and an empty argument list (engine.go:737-742),
// which would collapse the throwing path into the silent-empty path and lose the gate's only bytes.
//
// ── WHY THERE IS NO catchThrowable HERE (a deliberate difference from the sibling ports) ────────
//
// Several ported tags open GetDocument with `defer catchThrowable(&out, "<Tag>")` (engine.go:1715)
// because THEIR PHP class has its own `catch (\Throwable $e)` arm emitting a cy-form-error div.
// ProductView.php has NO try and NO catch — its whole body is three assignments and a return.
// Adding catchThrowable would invent a "<div class='cy-form-error'>ProductView error: …</div>"
// branch the PHP can never emit, which is a divergence dressed as robustness. It is omitted on
// purpose. A Go panic here would surface through renderSelected's recover as a marked panic notice
// (engine.go:1564-1570), which is the header's documented divergence 1 (PHP would fatal the page
// instead of emitting anything).
//
// ── THE NON-GALLERY PATH: <<<ProductView(<id>)>>> ───────────────────────────────────────────────
//
// Reachable only from document content, and per this ticket NO Document_Templates row mentions this
// tag today — so this path renders nowhere in production and NO diff can exercise it. It is ported
// anyway, faithfully, rather than stubbed.
//
// The argument is `$arguments->top()` = TagArguments::top() = end($this->arguments) — the FIRST
// argument the author wrote, because setArguments stores them reversed (engine.go:686-688,
// TagArguments.php:47). So <<<ProductView(5)>>> yields "5". PHP's end([]) on an empty argument list
// returns FALSE where Go's Top() returns "" (engine.go:737-742); the two agree in outcome here,
// because validateNumericKey turns both FALSE and "" into NULL (see below) and the tag renders ""
// either way.
//
// Then `new CatalogDAO()` (CatalogDAO.php:23-26) does CreateConnection(MYSQL_SERVER,
// MYSQL_STORE_DATABASE, STORE_LOGIN, STORE_PASSWORD) — which performs NO I/O, it only stores the
// credentials (DataConnection.php:18-24) — and calls open(). open() IGNORES those credentials
// entirely when CONGRUENCY_SQLITE is defined:
//
//	if (defined('CONGRUENCY_SQLITE')) { $this->pdo = new PDO('sqlite:' . CONGRUENCY_SQLITE); }  // :32
//	else { $this->pdo = new PDO('mysql:host=' . MYSQL_SERVER . ';dbname=' . $this->database, …); } // :33
//	$this->pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_SILENT);                              // :34
//
// So the store DAO reads the SAME sqlite file as every other ported tag — cfg.SQLite — and the
// "store database" is a fiction the shim collapses. The harness always defines CONGRUENCY_SQLITE
// (tooling/congruencey-harness/router.php:5), so the mysql branch is unreachable under the gate;
// productViewNoSQLiteDivergence documents what this port does with it.
//
// ERRMODE_SILENT (:34) is why this tag degrades SILENTLY rather than throwing: PDO::query() returns
// FALSE instead of raising, DataConnection::query() turns that into `return false`
// (DataConnection.php:47), get_product_details' `if($resultSet)` (CatalogDAO.php:84) is skipped,
// $result stays NULL, and get_document() returns NULL — which TagList casts with (string) to "".
// A MISSING Store_Content_Blocks TABLE THEREFORE RENDERS THE EMPTY STRING, not an error. That is
// this tag's entire degradation story, and it is what the ticket means by "degrade IDENTICALLY".

import (
	"strconv"
	"strings"
)

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there.
func init() {
	Register("ProductView", func(e *Engine, a *TagArguments) Tag { return newProductViewTag(e, a) })
}

// ProductViewTag is ProductView (ProductView.php:8-23).
//
// The PHP's two properties are $product_id and $product_string. $product_string is NOT stored here:
// computing it is the constructor's job in PHP, but a Go factory cannot report the failure of that
// work, so the computation is deferred to GetDocument (see the file header) and the inputs are
// stored instead.
type ProductViewTag struct {
	e *Engine

	// ctorThrew records that the PHP constructor throws before it assigns anything —
	// `$arguments->top()` on NULL (ProductView.php:15). True exactly when args == nil, which is
	// exactly the standalone/gallery path.
	ctorThrew bool

	// productID is $this->product_id (ProductView.php:15) — the raw, unvalidated argument.
	productID string
}

// newProductViewTag is ProductView::__construct (ProductView.php:14-18), minus the DB work that
// GetDocument now does. It must never panic: SelfCheck constructs every registered tag with nil args
// and asserts it yields a usable Tag (engine.go:4377-4378).
func newProductViewTag(e *Engine, args *TagArguments) *ProductViewTag {
	t := &ProductViewTag{e: e}
	if args == nil {
		// `$arguments->top()` on NULL -> Error. Nothing after :15 runs — in particular
		// `new CatalogDAO()` (:16) never happens, so no DB is opened on this path.
		t.ctorThrew = true
		return t
	}
	t.productID = args.Top()
	return t
}

// productViewNullArgError is get_class($e).': '.$e->getMessage() for the Error ProductView.php:15
// throws when $arguments is NULL. Corroborated against this repo's own recorded PHP 8 output — see
// the file header's citation of tooling/congruencey-bugs/repro/*.php and bootstrap.php:96.
const productViewNullArgError = "Error: Call to a member function top() on null"

// productViewStandaloneHTML is TagList.php:70-71's catch body, verbatim:
//
//	"<p style='color:#b00020'>This tag needs context to render standalone: "
//	  . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</p>"
//
// The message is run through esc() — this package's htmlspecialchars($s, ENT_QUOTES) port
// (engine.go:599) — rather than hand-escaped, because that is the IDENTICAL call TagList::esc
// (TagList.php:20) makes on the IDENTICAL value, so the two cannot drift apart. (This particular
// message happens to contain no escapable byte, so esc is identity on it today; calling esc anyway
// is what keeps that a fact rather than an assumption.)
//
// There is NO trailing newline: TagList.php:71 ends at "</p>".
func productViewStandaloneHTML() string {
	return "<p style='color:#b00020'>This tag needs context to render standalone: " +
		esc(productViewNullArgError) + "</p>"
}

// productViewNoSQLiteDivergence is emitted only when a tag argument IS present but no sqlite path is
// configured — i.e. PHP's `!defined('CONGRUENCY_SQLITE')`, which sends DataConnection::open() down
// its mysql branch (DataConnection.php:33) to `new PDO('mysql:host=localhost;dbname=CONGRUENCY_STORE',
// 'store','store995')`. With no MySQL server that constructor throws a PDOException whose text is
// driver- and host-specific ("SQLSTATE[HY000] [2002] …"), and ProductView has no catch, so the PHP
// page FATALS — the header's divergence 1 exactly (engine.go:206-212).
//
// This port refuses to forge that message: it returns a MARKED divergence notice, the same choice
// notPortedHTML makes (engine.go:1497-1506), rather than impersonating a PDOException or silently
// returning "" as if the DB had merely been empty. The branch is unreachable under both gates — the
// harness always defines CONGRUENCY_SQLITE (router.php:5), and the gallery path throws at
// ProductView.php:15 long before any of this.
func productViewNoSQLiteDivergence() string {
	return "<p style='color:#b00020'>congruency-go: ProductView has no sqlite path configured; " +
		"the PHP would open MySQL here and fatal. This notice is a DIVERGENCE from the PHP render, " +
		"not a reproduction of it.</p>"
}

// GetDocument is ProductView::get_document() (ProductView.php:20-22) PLUS the constructor work
// (:15-17) that a Go factory cannot perform. It returns (string)$this->product_string: PHP's NULL
// renders as "" through TagList's (string) cast at :68.
//
// It deliberately has NO `defer catchThrowable(...)` — ProductView.php has no catch arm to model.
// See the file header.
func (t *ProductViewTag) GetDocument() string {
	// ProductView.php:15 — the constructor threw; TagList's catch supplies the bytes.
	if t.ctorThrew {
		return productViewStandaloneHTML()
	}

	// ProductView.php:16 — new CatalogDAO() -> DataConnection::CreateConnection(...)->open().
	if t.e.cfg.SQLite == "" {
		return productViewNoSQLiteDivergence() // !defined('CONGRUENCY_SQLITE') -> the mysql branch
	}

	// ProductView.php:17 — $catalogDAO->get_product_details($this->product_id).
	return t.productViewGetProductDetails()
}

// productViewGetProductDetails is CatalogDAO::get_product_details($key) (CatalogDAO.php:78-93):
//
//	$result = NULL;
//	$itemKey = ValidateFields::validateNumericKey($key);
//	if(isset($itemKey)){
//	    $selectString = "SELECT Content FROM Store_Content_Blocks WHERE productID=$itemKey ORDER BY display_order";
//	    $resultSet = $this->dataConnection->query($selectString);
//	    if($resultSet){ foreach($resultSet->rows as $__row){ $result .= $__row['Content']; } }
//	}
//	return $result;
//
// This is get_category_details (CatalogDAO.php:96-111) with ONE byte-level difference that matters:
// the filter column is `productID` (:82), not `categoryID` (:100). Everything else — the selected
// column, the table, the ORDER BY, the interpolation, the NULL start — is identical.
//
// Every failure below returns "" because that is what PHP's NULL becomes at the (string) cast, and
// PHP reaches NULL on every one of them WITHOUT throwing (ERRMODE_SILENT, DataConnection.php:34):
//
//   - key not numeric        -> isset($itemKey) false, no query at all       -> NULL -> ""
//   - db file absent         -> PHP's `new PDO('sqlite:…')` CREATES an empty db (header divergence
//     2), so the SELECT then fails on the missing table       -> NULL -> ""
//   - Store_Content_Blocks absent -> PDO::query() returns FALSE, DataConnection::query() returns
//     false (:47), `if($resultSet)` skipped                   -> NULL -> ""
//   - zero matching rows     -> MysqlShimResult is truthy, the foreach body never runs -> NULL -> ""
func (t *ProductViewTag) productViewGetProductDetails() string {
	itemKey, ok := productViewValidateNumericKey(t.productID)
	if !ok {
		return "" // isset($itemKey) is false — CatalogDAO.php:81
	}

	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return ""
	}
	defer db.Close()

	// CatalogDAO.php:82 — the key is INTERPOLATED, not bound, and this port interpolates it too.
	// That is not laziness on either side, and swapping in a placeholder would be a real divergence:
	// SQLite gives a bound "05" TEXT affinity while the literal 05 is an INTEGER, so the two could
	// match different rows of productID.
	//
	// SAFE BY CONSTRUCTION: validateNumericKey returns $result[0] — the [0-9]+ MATCH, never the raw
	// input (ValidateFields.php:33) — so what lands in the SQL is always a bare run of digits, even
	// when the accepted input was " 5" or "+5". productViewValidateNumericKey preserves that
	// property; see its comment.
	rows, err := queryRows(db, "SELECT Content FROM Store_Content_Blocks WHERE productID="+itemKey+" ORDER BY display_order")
	if err != nil {
		return "" // PDO::query() === false under ERRMODE_SILENT — DataConnection.php:47
	}

	// CatalogDAO.php:85-88 — `$result .= $row['Content']` from a NULL start. NULL . "x" === "x",
	// so this is plain concatenation in source order; phpString models (string)NULL === "" for a
	// NULL Content cell (engine.go:497-500).
	var out strings.Builder
	for _, r := range rows {
		out.WriteString(phpString(r["Content"]))
	}
	return out.String()
}

// productViewValidateNumericKey is ValidateFields::validateNumericKey($itemKey)
// (ValidateFields.php:29-37):
//
//	$result = array();
//	preg_match("/[0-9]+/",$itemKey,$result);
//	if($itemKey == $result[0]){ return $result[0]; } else { return NULL; }
//
// ok=false is the PHP's NULL return, which CatalogDAO.php:81 tests with isset() — and isset(NULL) is
// FALSE, so a NULL key skips the query entirely.
//
// THE UNMATCHED CASE. When the subject holds no digit, $result stays an EMPTY ARRAY and `$result[0]`
// is an undefined index: PHP 8 emits a warning and evaluates it to NULL. The comparison is then
// `$itemKey == NULL`, and the two sub-cases both end at "no key":
//
//   - $itemKey === "" (or FALSE, from end([]) on an empty argument list): "" == NULL is TRUE, so the
//     function returns $result[0] — which IS NULL. isset(NULL) is false.
//   - $itemKey is a non-empty non-numeric string ("abc"): PHP 8 compares it against "", which is
//     FALSE, so the else-branch returns NULL.
//
// Both are ok=false, which is why the no-digit case needs no further distinction here.
//
// THE MATCHED CASE returns $result[0] — the DIGIT RUN — and never $itemKey. That is what keeps the
// interpolated SQL injection-proof, and it is why the accepted inputs " 5", "+5" and "5.0" all send
// the bare "5" to the database.
func productViewValidateNumericKey(itemKey string) (string, bool) {
	digits, found := productViewFirstDigitRun(itemKey)
	if !found {
		return "", false
	}
	if !productViewLooseEqNumeric(itemKey, digits) {
		return "", false
	}
	return digits, true
}

// productViewFirstDigitRun is preg_match("/[0-9]+/", $itemKey, $result) -> $result[0]: the FIRST
// maximal run of ASCII digits anywhere in the subject (the pattern is unanchored, so "abc5" matches
// "5"), or not-found when the subject holds no digit.
func productViewFirstDigitRun(s string) (string, bool) {
	for i := 0; i < len(s); i++ {
		if s[i] >= '0' && s[i] <= '9' {
			j := i
			for j < len(s) && s[j] >= '0' && s[j] <= '9' {
				j++
			}
			return s[i:j], true
		}
	}
	return "", false
}

// productViewLooseEqNumeric is PHP 8's `$itemKey == $digits`, where $digits is a NON-EMPTY [0-9]+
// run and both operands are strings.
//
// PHP 8's string-to-string `==` rule: if BOTH operands are numeric strings, compare them NUMERICALLY;
// otherwise compare them as strings. (This is the PHP 8 rule specifically — PHP 7 would have cast the
// non-numeric side to a number instead. The harness is PHP 8.3, per tooling/congruencey-harness/README.md.)
//
// $digits is always numeric, so the test reduces to "is $itemKey numeric?":
//
//	"5"    vs "5"  -> numeric, 5 == 5      -> true
//	"05"   vs "05" -> numeric, 5 == 5      -> true   (and "05" is what reaches the SQL)
//	" 5"   vs "5"  -> numeric, 5 == 5      -> true   (PHP 8 allows leading AND trailing whitespace)
//	"+5"   vs "5"  -> numeric, 5 == 5      -> true
//	"5.0"  vs "5"  -> numeric, 5.0 == 5    -> true
//	"-5"   vs "5"  -> numeric, -5 != 5     -> false
//	"5.5"  vs "5"  -> numeric, 5.5 != 5    -> false
//	"1e2"  vs "1"  -> numeric, 100 != 1    -> false
//	"5abc" vs "5"  -> NOT numeric, "5abc" != "5" as strings -> false
func productViewLooseEqNumeric(itemKey, digits string) bool {
	a, aNum := productViewPHPNumericValue(itemKey)
	if !aNum {
		return itemKey == digits // neither-both-numeric -> plain string comparison
	}
	b, bNum := productViewPHPNumericValue(digits)
	if !bNum {
		return itemKey == digits // unreachable: a [0-9]+ run is always numeric
	}
	return a == b
}

// productViewPHPNumericValue reports whether s is a PHP 8 NUMERIC STRING and, if so, its value.
//
// PHP 8's grammar (the trailing-whitespace clause is new in PHP 8.0):
//
//	WS* [+-]? ( DIGITS ("." DIGITS?)? | "." DIGITS ) ( [eE] [+-]? DIGITS )? WS*
//
// where WS is " \t\n\r\v\f" — PCRE's \s set, which isPHPSpace already models (engine.go:624-628).
// An exponent marker with no digits after it does NOT match, and since the pattern must consume the
// WHOLE string, "1e" is correctly reported non-numeric rather than parsed as 1.
func productViewPHPNumericValue(s string) (float64, bool) {
	i, n := 0, len(s)
	for i < n && isPHPSpace(s[i]) { // leading WS*
		i++
	}
	start := i
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
		return 0, false
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
	end := i
	for i < n && isPHPSpace(s[i]) { // trailing WS*
		i++
	}
	if i != n { // anything left over means the string is not numeric ("5abc", "1e", "5 x")
		return 0, false
	}
	f, err := strconv.ParseFloat(s[start:end], 64)
	if err != nil {
		return 0, false
	}
	return f, true
}
