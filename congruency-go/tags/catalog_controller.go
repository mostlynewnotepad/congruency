// catalog_controller.go — ticket #253, unit go-port:tags:tag:Catalog_Controller.
//
// The Go port of ONE tag: invocators/tags/store/Catalog_Controller.php. It is a self-contained
// leaf in the sense #281 established — this file holds the tag's type, its GetDocument, its
// helpers and its self-registration, and it changes NOTHING in engine.go. Adding it moves
// PortedTags() from 12 names to 13; that is the whole footprint.
//
// THE CONTRACT: byte-identical HTML. The PHP is the spec. Everything below that looks quirky is
// quirky because Catalog_Controller.php (and the four classes it reaches through) is, and where
// the two disagree the Go is wrong.
//
// ── WHAT THE TAG IS ─────────────────────────────────────────────────────────────────────────────
//
// The STORE front controller: one tag that picks which of three store views the page shows, from
// $_GET alone. It is the first tag ported out of invocators/tags/store/ (the twelve before it are
// dev tags), and it is unlike them in three ways that drive everything below:
//
//	?product=<n>   -> a product pane   : "<div ...><<<ContentTag(storkmessage)>>>
//	                                     <<<Config_Form_Invocator(n)>>><<<ProductView(n)>>></div>"
//	?category=<n>  -> a product LIST   : "<<<ContentTag(ProductViewListing)>>>" + the list +
//	                                     "<<<CategoryView(n)>>>"
//	(neither)      -> the category LIST: "<<<ContentTag(CategoryViewListing)>>>" + the list
//
//  1. IT EMITS TAG INVOCATIONS, it does not render them. Every branch returns a string containing
//     <<<...>>> markup for OTHER tags. Substituting those is the ENGINE's job
//     (Tag_Wrapper::execute_all_tags, engine.go:1022), not this tag's, and each of those tags is
//     its own #230 unit. This file emits the invocations verbatim and expands nothing. See "THE
//     NESTED TAGS" below — it is the whole reason this unit's gate reads the way it does.
//  2. IT ESCAPES NOTHING. See "NO ESCAPING" below. This is the opposite of every other tag here.
//  3. ITS DATA COMES THROUGH FOUR NON-TAG CLASSES that have no unit ticket of their own —
//     CategoryList, Category, ProductList, Product — plus CatalogDAO. They are not tags, so the
//     decomposer never enumerated them; they are reachable ONLY from this tag's two list branches,
//     so their bytes are this unit's bytes and they are ported here, inline, and nowhere else.
//
// ── IT TAKES NO TAG ARGUMENTS, AND STORES NONE ──────────────────────────────────────────────────
//
// Catalog_Controller.php:10-11 is `public function __construct($arguments){}` — an EMPTY body. It
// does not even keep $arguments, which is why this struct has no args field (AnnotationsTag has
// one because Annotations.php stores its own and never reads it; this PHP does not store it at
// all). Every input arrives through $_GET. So `new Catalog_Controller(null)` — the standalone /
// gallery shape, TagList.php:67 — is a no-op here exactly as it is there.
//
// ── IT CANNOT BE INVOKED FROM A TEMPLATE, AND THAT IS THE REGEX, NOT AN ACCIDENT ─────────────────
//
// The ticket says "no Document_Templates row mentions it". The stronger fact is that no row COULD
// usefully mention it: the engine's tag pattern is TAG_KEY_PREFIX + FUNCTION_NAME +
// FUNCTION_ARGUMENTS + TAG_KEY_SUFFIX, and FUNCTION_NAME is "[a-zA-Z]+"
// (boot/constants.default.json:33) — no underscore, no digits. So "<<<Catalog_Controller>>>" never
// matches identify_tag: the scan takes "<<<Catalog" and then needs ">>>" where "_" stands. The
// gallery reaches this class a different way — TagList instantiates the selected name DIRECTLY
// (`new $sel(null)`, TagList.php:67), bypassing the regex — which is why ?page=tags&tag=
// Catalog_Controller renders and a template never can. MEASURED, not inferred: scanning all 26
// Documents rows joined to their templates this session, ZERO mention Catalog_Controller, and the
// only row embedding <<<TagList>>> is DocumentID='tags'.
//
// ── THE NESTED TAGS: WHICH THE ENGINE SUBSTITUTES, AND WHICH SURVIVE VERBATIM ────────────────────
//
// The same [a-zA-Z]+ rule splits this tag's OWN emissions in two, and both halves were measured on
// the live PHP:
//
//	<<<ContentTag(CategoryViewListing)>>>   name is letters-only  -> MATCHES   -> engine substitutes
//	<<<ContentTag(ProductViewListing)>>>    ""                    -> MATCHES   -> engine substitutes
//	<<<ContentTag(storkmessage)>>>          ""                    -> MATCHES   -> engine substitutes
//	<<<ProductView(n)>>>                    ""                    -> MATCHES   -> engine substitutes
//	<<<CategoryView(n)>>>                   ""                    -> MATCHES   -> engine substitutes
//	<<<Config_Form_Invocator(n)>>>          has '_'               -> NO MATCH  -> SURVIVES VERBATIM
//
// That last line is not a defect to be tidied: ?page=tags&tag=Catalog_Controller&product=1 on the
// live PHP returns, as the tag's whole body,
//
//	<div width='70%' align='center'><<<Config_Form_Invocator(1)>>></div>
//
// — the literal reaches the browser. This port emits the identical bytes and lets the identical
// regex decline them. (The three tags that DO match all render "" against this database; see
// "DEGRADATION".)
//
// ── WORKING_PAGE: THE ONE THING THIS TAG READS THAT THE GO ENGINE HAS NO POM FOR ─────────────────
//
// Category::catalog_string (Category.php:58-62) builds its href from
// `PersistentObjectManager::getData("WORKING_PAGE")->getKey()` — the Document the CONTROLLER is
// rendering. engine.go's header records that there is no POM in this port (divergence 3), so the
// value has to be re-derived. workingPageKey below does it by REPRODUCING THE TWO STEPS THAT
// PRODUCE IT, rather than by hardcoding "tags":
//
//	Controller::control()            (Controller.php:15-19) : validatePageKey($_GET['page']),
//	                                                          or "catalog" when ?page= is absent
//	DocumentManager::produceDocument (DocumentManager.php:42-53) : that key's Documents row, and
//	                                                          FAILING THAT the 'invalid' row
//	Document::getKey()               (Document.php:35-37)   : the row's DocumentID
//
// The 'invalid' fallback is the load-bearing half. MEASURED this session: the DocumentID lookup is
// case-SENSITIVE, so ?page=TAGS finds no row, falls back to the 'invalid' document, and renders
// the 404 page (3,133 bytes) — whose template holds no <<<TagList>>>, so this tag never runs
// there. Hardcoding "tags" would be right for every URL that can reach this tag today and wrong
// about why, and it would rot silently the moment a second document embedded the gallery.
//
// On the live PHP at ?page=tags the derivation lands on "tags", and the rendered href is
// "?page=tags&category=1" — measured, not assumed.
//
// ── Categories HAS NO `picture` COLUMN, AND THE PHP READS IT ANYWAY ──────────────────────────────
//
// Category::sql_assoc_array (Category.php:14-21) does
// `$result->setPicture($array[CatalogDAO::FIELD_NAME_PICTURE])` — i.e. $array['picture']. MEASURED:
// the live Categories table has exactly three columns — key, name, description. There IS no
// picture. So PHP 8 raises "Warning: Undefined array key \"picture\"" and evaluates it to NULL,
// "images/category/" . NULL is "images/category/", and the img renders with an EMPTY src path:
//
//	<td><img src='images/category/' alt=''  ></td>
//
// Go's map read of an absent key yields nil and phpString(nil) is "", so the same bytes fall out
// with no special case. The warning itself never reaches the page (display_errors is off — the
// rendered page contains zero occurrences of Warning/Notice/Deprecated/Fatal, checked this
// session), so it costs no bytes and this port raises no counterpart. This is a PHP defect worth a
// bug ticket of its own; per the ticket's instruction the defect is ported faithfully and NOT
// "improved" here.
//
// Note the DOUBLE space before that '>': HTMLFunctions::image concatenates
// "' " . array_contents($attributes) . " >", and array_contents("") takes its `if(!empty($array))`
// false arm, which falls off the end of the function and returns NULL — an empty slot between two
// spaces. See htmlImage.
//
// ── validateNumericKey IS PHP 8's `==`, AND THAT IS NOT A DETAIL ─────────────────────────────────
//
// ValidateFields::validateNumericKey (ValidateFields.php:29-37) is four lines:
//
//	preg_match("/[0-9]+/", $itemKey, $result);
//	if ($itemKey == $result[0]) { return $result[0]; } else { return NULL; }
//
// `==` between two strings in PHP 8 compares them NUMERICALLY when BOTH are numeric strings, and
// byte-wise otherwise — and a numeric string may carry leading AND trailing whitespace and a sign.
// The needle $result[0] is always a digit run, so it is always numeric; the haystack decides.
// Every one of these was driven against the live PHP this session and every one is reproduced:
//
//	"5"    -> "5"    5 == 5                     "5x"  -> NULL  not numeric -> "5x" !== "5"
//	" 5"   -> "5"    leading ws is numeric      "-5"  -> NULL  -5 != 5 (the '-' is not matched)
//	"5 "   -> "5"    trailing ws is numeric     "1e1" -> NULL  10 != 1
//	"+5"   -> "5"    signed is numeric          "abc" -> NULL  no match at all
//	"5.0"  -> "5"    5.0 == 5   (!)             ""    -> NULL  no match at all
//	"05"   -> "05"   5 == 5                     "0"   -> "0"   0 == 0, and isset("0") is TRUE
//	"007"  -> "007"  7 == 7
//
// Two of those are the ones a reasonable port gets wrong. The RETURN VALUE IS THE MATCH, NOT THE
// INPUT — "05" yields "05" and "007" yields "007", so ?product=007 renders
// <<<Config_Form_Invocator(007)>>> with the zeros intact (measured). And "5.0" and "+5" and " 5"
// all reach the DB as category 5 — a strict is-this-all-digits check would render an empty page
// for each, and the live PHP renders category 5's two products for all three.
//
// A non-match returns NULL down BOTH arms: $result[0] is undefined, so `$itemKey == NULL` is a
// comparison against NULL, and the `if` arm then returns that same undefined $result[0]. So
// "no digits anywhere" is NULL whichever way the branch falls, which is why validateNumericKey
// below needs no third case.
//
// ── NO ESCAPING. NOT ONE BYTE. ──────────────────────────────────────────────────────────────────
//
// Every other tag in this package runs DB-derived bytes through esc() — the htmlspecialchars(...,
// ENT_QUOTES) recursion guard engine.go's header describes. THIS TAG'S CHAIN DOES NOT, ANYWHERE:
// Category::catalog_string and Product::catalog_string hand the raw name/description/key straight
// to HTMLFunctions::link/image, and HTMLFunctions (HTMLFunctions.php:10-24) is bare concatenation.
// So a category named `<b>x</b>` renders as live markup, and one named `<<<TitleTag>>>` would be
// substituted by the engine on the parent frame's scan — a stored-XSS/tag-injection defect that is
// real and live in the PHP today.
//
// Reaching for esc() here would be tidier, safer, and WRONG: it is a byte difference on the first
// category whose name or description contains &, <, >, ' or ", and the PHP is the spec. The gate
// cannot see it (the one live category is "specifications" / "Specification pages", all plain
// ASCII), which is exactly why it is written down here instead of left to be rediscovered. It
// deserves a bug ticket; per the ticket's instruction the defect is ported faithfully, not fixed.
//
// ── DEGRADATION AGAINST A MISSING DEPENDENCY (the ticket asks for this explicitly) ───────────────
//
// The dependency is CONGRUENCY_SQLITE, through CatalogDAO's `Categories` and `Products` tables.
// The PHP's degradation is NOT an error page — it is silence, and it comes from one line:
// DataConnection::query (DataConnection.php:43-49) sets PDO::ERRMODE_SILENT and returns FALSE on a
// failed statement, and both DAO methods guard with `if($resultSet)`. So a missing/!unreadable
// table yields an EMPTY array, an empty list, and a tag body of just its ContentTag invocation.
// safeRows (engine.go:1282) returns nil on exactly that error, so the Go takes the same silent
// path and emits the same bytes with no special case.
//
// Two divergences, both inherited from engine.go's openDB policy (divergence 2), both stated
// rather than quietly widened:
//
//   - DB FILE MISSING. PHP's `new PDO('sqlite:'.$path)` is READ-WRITE and CREATES an empty file;
//     the Categories query then fails and the tag renders its silent empty state. openDB refuses
//     to create anything and errors, and this file's readers turn that error into the same empty
//     state. So THE BYTES AGREE — only the side effect differs, and the side effect Go declines is
//     the one #153/Theme 3 forbids. This is the rare case where the port's stricter open costs
//     nothing.
//   - CONGRUENCY_SQLITE UNDEFINED (Config.SQLite == ""). PHP falls through to
//     `new PDO('mysql:host=...')` (DataConnection.php:33), which throws PDOException — uncaught
//     in this tag (it has no try/catch of its own), so TagList's catch renders "This tag needs
//     context to render standalone: PDOException: ...". Go renders the empty state instead. That
//     is a real byte difference on one input, unreachable from the gate (DefaultConfig always
//     derives a path) and out of scope for a port-ONE-tag ticket.
//
// NO catchThrowable HERE, DELIBERATELY. Annotations/CategoryBrowse wrap themselves in one because
// their PHP classes have their own `catch (\Throwable $e)` arm. Catalog_Controller.php has NO
// try/catch: a throw propagates out of the tag and is caught by TagList (TagList.php:69-72).
// TagListTag.renderSelected's recover() (engine.go:1564-1582) is that same outer net. Adding a
// cy-form-error div here would invent an error surface the PHP does not have.
//
// ── WHAT WAS AND WAS NOT RUN (read this before trusting a claim above) ──────────────────────────
//
// THIS FILE WAS NEVER COMPILED — the same wall annotations.go (#247) hit and recorded. The Go
// toolchain is not invocable in the session that wrote it: `go version` was refused by the harness
// with "This command requires approval", and there was no one to approve it. So there is NO build,
// NO vet, NO gofmt, NO SelfCheck() run and NO `go test` run behind this port, and none is claimed.
// Shelling out to go from the python that IS permitted would route around a permission gate, which
// is not a measurement; it was not done.
//
// WHAT WAS ACTUALLY MEASURED — the PHP semantics, not the Go binary. The live PHP this repo serves
// IS up on 127.0.0.1:8899 and its state db IS readable through rest.php's public ?api read
// surface, so the risky half of a port — "have I read the PHP right?" — was checked directly. A
// line-by-line PYTHON TRANSLITERATION of this file (same branches, same helpers, same literals,
// same order, same live DB) was diffed against the live PHP's own bytes over 26 inputs, with the
// engine's substitution applied to the raw output as the page applies it. ALL 26 WERE
// BYTE-IDENTICAL, and 15 of the 26 carry non-empty bytes (a pass on "" vs "" would be weak
// evidence, so they are counted separately):
//
//	(bare)                                    238B  the category table — the ticket's gate
//	&category=5 | &category=9                 172B / 96B  the two populated categories
//	&category=%205 | 5%20 | %2B5 | 5.0 | 05   172B  the five PHP-8 `==` quirks, all -> category 5
//	&product=1 | 2 | 3 | 0 | 007 | %201        68-70B  the Config_Form_Invocator literal survives
//	&product=1&category=5                      68B  product wins; category is not consulted
//	&category=1 | 99 | abc | "" | 0 | 5x | -5 | 1e1    0B  the empty states
//	&product=abc | ""                           0B  isset($_GET) is TRUE, the value validates NULL
//
// The PHP slices were cut from the live pages on the pages' own literals — TagList.php:62 and :76
// plus the 17-byte page tail measured from TagList.php:77-78's "Unknown tag" branch (#282's
// method, equivalence_test.go:35-75).
//
// WHAT THAT DOES AND DOES NOT ESTABLISH. It establishes that the ALGORITHM encoded here reproduces
// the live PHP byte for byte on every branch this tag has. It does NOT establish that this Go file
// compiles, nor that Go's own primitives behave as the transliteration assumed. THE FIRST THING TO
// DO WITH THIS FILE IS RUN:
//
//	cd congruency-go && go build ./... && go vet ./... && gofmt -l .
//
// ── THIS UNIT'S GATE CANNOT BE EMPTY, AND THE REASON IS NOT THIS UNIT ───────────────────────────
//
// Stated plainly because the ticket asks for exactly this ("if you cannot make a diff here run
// against THIS unit, say so on the ticket rather than settling on a diff that would be empty even
// with the unit unimplemented"). The ticket's literal gate is
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=Catalog_Controller') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=Catalog_Controller')
//
// and it is non-empty for THREE independent reasons, in increasing order of interest. None is
// fixable from inside this file, and the first two are non-empty for every tag, ported or not:
//
//  1. PAGE CHROME. congruency-go's server does not reproduce the PHP CMS chrome and declines to
//     forge it (server.go:39-66). The two pages differ by ~6.2 KB of nav/head/style whether or not
//     this file exists.
//  2. THE GALLERY FRAME. handleTagsPage (server.go:792-830) answers a REGISTERED tag by rendering
//     THAT TAG ALONE via tags.RenderTag — no tag list, no <div class='tagout'> wrapper. The PHP
//     page carries the whole gallery around the tag. So registering this tag CHANGES the Go page's
//     shape; it does not converge it.
//  3. THE ONE THAT IS ABOUT THIS TAG. RenderTag returns get_document()'s bytes UNEXPANDED
//     (engine.go:4147-4160), while the PHP slice is cut from a page execute_all_tags has already
//     run over. This tag ALWAYS emits nested invocations, so the two are not the same measurement
//     for it — and even comparing expansion-to-expansion would differ, because ContentTag,
//     ProductView and CategoryView have no Go port yet (they are separate #230 units, and they are
//     NOT in this ticket's DEPENDS ON list, which names only the four engine units). The Go engine
//     would render each as unknownTagHTML's marked comment where the PHP renders "".
//
// So the honest measurement — the one that isolates THIS unit's bytes and changes exactly when
// this file changes — is the transliteration diff recorded above: 26/26 byte-identical, PHP slice
// vs this algorithm's raw output with the engine's own substitution applied. With this unit
// unimplemented that diff is not empty, it is 238 bytes of category table against
// notPortedHTML's divergence notice, so it is not a diff that passes vacuously.
//
// WHAT WOULD MAKE THE LITERAL GATE EMPTY, for whoever picks this up: ports of ContentTag,
// ProductView and CategoryView (then the slices agree), plus a server that renders the gallery
// frame and the CMS chrome (then the pages agree). Three tag units and a server ticket — none of
// them this one.
package tags

import (
	"regexp"
	"strconv"
	"strings"
)

// init self-registers the tag (#281's add-a-file model: engine.go is untouched). The factory drops
// its *TagArguments on the floor because the PHP constructor does — Catalog_Controller.php:10-11
// is an empty body that neither reads nor stores $arguments.
func init() {
	Register("Catalog_Controller", func(e *Engine, _ *TagArguments) Tag {
		return &CatalogControllerTag{e: e}
	})
}

// CatalogControllerTag is Catalog_Controller (Catalog_Controller.php:8). It has no fields beyond
// the engine: the class has no properties, and its constructor is empty.
type CatalogControllerTag struct {
	e *Engine
}

// GetDocument is Catalog_Controller::get_document() (Catalog_Controller.php:13-33).
//
//	$result = NULL;
//	if(isset($_GET['product'])){
//	    $product = ValidateFields::ValidateNumericKey($_GET['product']);
//	    if(isset($product)){ $result = "<div ...>...<<<ProductView($product)>>></div>"; }
//	}else{
//	    if( isset($_GET['category']) ){
//	        $category = ValidateFields::ValidateNumericKey($_GET['category']);
//	        $productList = new ProductList($category);
//	        $result = "<<<ContentTag(ProductViewListing)>>>".$productList->__toString()."<<<CategoryView($category)>>>";
//	    }else{
//	        $result = "<<<ContentTag(CategoryViewListing)>>>";
//	        $catList = new CategoryList();
//	        $result .= $catList->__toString();
//	    }
//	}
//	return $result;
//
// Four details that must survive the port, because each changes the bytes:
//
//  1. THE BRANCH IS ON isset($_GET['product']), NOT ON ITS VALIDITY. ?product=abc takes the product
//     branch, fails the inner isset, and returns NULL — it does NOT fall through to the category
//     branch. Measured: ?product=abc&category=5 renders "" on the live PHP, not category 5's
//     products. getIsset is that isset (a present-but-empty ?product= is SET, and validates NULL).
//  2. THE INNER isset IS ON THE PRODUCT BRANCH ONLY. The category branch takes validateNumericKey's
//     result unchecked and interpolates it straight into "<<<CategoryView($category)>>>", so an
//     invalid ?category= yields "<<<CategoryView()>>>" — which the engine's regex DOES match (its
//     arguments group is (\([A-Za-z0-9]*\))*, and "()" satisfies the * on the inner class). That
//     empty invocation is a real byte this port must emit, not a case to guard away.
//  3. NULL RENDERS AS "". PHP's $result starts NULL and the product branch may leave it NULL;
//     TagList does `(string)$obj->get_document()` (TagList.php:68), so NULL becomes "". Go's ""
//     is that value directly. Likewise NULL interpolated into the CategoryView invocation is "".
//  4. isset("0") IS TRUE. ?product=0 validates to "0" (0 == 0) and renders the product pane;
//     isset() tests for NULL, not for truthiness. Measured.
func (t *CatalogControllerTag) GetDocument() string {
	result := "" // $result = NULL;
	if productParam, productSet := t.e.getIsset("product"); productSet {
		if product, isset := validateNumericKey(productParam); isset {
			result = "<div width='70%' align='center'><<<ContentTag(storkmessage)>>>" +
				"<<<Config_Form_Invocator(" + product + ")>>><<<ProductView(" + product + ")>>></div>"
		}
	} else {
		if categoryParam, categorySet := t.e.getIsset("category"); categorySet {
			// NOT isset-checked by the PHP: an invalid key is NULL, which interpolates as "".
			category, _ := validateNumericKey(categoryParam)
			productList := t.productListString(category)
			result = "<<<ContentTag(ProductViewListing)>>>" + productList +
				"<<<CategoryView(" + category + ")>>>"
		} else {
			result = "<<<ContentTag(CategoryViewListing)>>>"
			result += t.categoryListString()
		}
	}
	return result
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// CategoryList / Category — lib/Modules/StoreModule/Catalog/List/CategoryList.php
//                           lib/Modules/StoreModule/Catalog/Category/Category.php
//
// Not tags, so the decomposer filed no unit for them; reachable only from this tag, so their bytes
// are this unit's bytes. Ported inline (see point 3 of the file header).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// categoryListString is `new CategoryList()` + its __toString (CategoryList.php:15-22):
//
//	$listing = '';
//	for($index=0, $fill=count($this->allCategories); $index < $fill; $index++){
//	    $category = $this->allCategories[$index];
//	    $listing .= $category->catalog_string() . "<br /><br />";
//	}
//
// It is an INDEXED for, not a foreach (ProductList's is the foreach). The distinction costs no
// bytes here — the array is a dense 0..n-1 push list built by instantiate_categories
// (CategoryList.php:48-53, an array_push loop) — so a Go range over the rows is the same walk in
// the same order.
//
// The WORKING_PAGE lookup is hoisted out of the per-row catalog_string() call. That is
// behaviour-preserving, not an optimization with a caveat: PersistentObjectManager::getData is a
// pure static read of a value the controller set before rendering began, so every row's call
// returns the identical Document. Hoisting it costs one Documents lookup instead of N, and emits
// the same bytes. It is skipped entirely when there are no categories, where the PHP would also
// never call it.
func (t *CatalogControllerTag) categoryListString() string {
	rows := t.selectAllCategories()
	if len(rows) == 0 {
		return "" // $listing = ''; the loop body never runs
	}
	pageKey := t.workingPageKey()
	listing := ""
	for _, row := range rows {
		listing += categoryCatalogString(row, pageKey) + "<br /><br />"
	}
	return listing
}

// categoryCatalogString is Category::sql_assoc_array + Category::catalog_string
// (Category.php:14-21, 58-62), fused: the bean is a pure carrier between the two, so the row map is
// read where the setters would have been. The field names are CatalogDAO's constants
// (CatalogDAO.php:11-14): 'name', 'description', 'key', 'picture'.
//
//	$result = "\n<table width='80%' align='center'>\n<tr>\n<td>"
//	        . HTMLFunctions::image("images/category/" . $this->picture,"","")
//	        . "</td>\n<td width='80%'>"
//	        . HTMLFunctions::link($this->name,"View Category Items",
//	                              "?page=". $document->getKey() . "&category=" . $this->numberKey)
//	        . "<br />" . $this->description;
//	$result .= "</td>\n</tr>\n</table>\n";
//
// 'picture' is ABSENT from the live Categories table, so row["picture"] is nil and phpString(nil)
// is "" — the same NULL the PHP's undefined-array-key warning evaluates to. See the file header.
// Nothing here is escaped, deliberately; see "NO ESCAPING" in the file header.
func categoryCatalogString(row map[string]any, pageKey string) string {
	result := "\n<table width='80%' align='center'>\n<tr>\n<td>" +
		htmlImage("images/category/"+phpString(row["picture"]), "") +
		"</td>\n<td width='80%'>" +
		htmlLink(phpString(row["name"]), "View Category Items",
			"?page="+pageKey+"&category="+phpString(row["key"])) +
		"<br />" + phpString(row["description"])
	return result + "</td>\n</tr>\n</table>\n"
}

// selectAllCategories is CatalogDAO::select_all_categories (CatalogDAO.php:28-39) — `SELECT * FROM
// Categories`, no WHERE, no ORDER BY, so the rows arrive in sqlite's scan order exactly as PDO
// hands them to the PHP.
//
// A failed open or a failed query yields nil, which is the PHP's `$result = array()` surviving
// `if($resultSet)` being false — its silent empty state. See "DEGRADATION" in the file header.
func (t *CatalogControllerTag) selectAllCategories() []map[string]any {
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return nil
	}
	defer db.Close()
	return safeRows(db, "SELECT * FROM Categories")
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// ProductList / Product — lib/Modules/StoreModule/Catalog/List/ProductList.php
//                         lib/Modules/StoreModule/Catalog/Product/Product.php
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// productListString is `new ProductList($category)` + its __toString (ProductList.php:17-23):
//
//	foreach ($products as $product) { $listing .= $product->catalog_string() . "<br /><br />"; }
//
// It does NOT consult WORKING_PAGE: Product::catalog_string reads the Document into a $document
// local and then never uses it, hardcoding "?page=catalog" in the href instead (Product.php:73-76).
// So a product link rendered inside the ?page=tags gallery points at ?page=catalog — measured on
// the live PHP, and reproduced here rather than "corrected" to the current page.
func (t *CatalogControllerTag) productListString(category string) string {
	listing := ""
	for _, row := range t.selectProductsByCategory(category) {
		listing += productCatalogString(row) + "<br /><br />"
	}
	return listing
}

// productCatalogString is Product::sql_assoc_array + Product::catalog_string (Product.php:15-23,
// 73-76), fused for the same reason categoryCatalogString is:
//
//	HTMLFunctions::link($this->name,"Product Details","?page=catalog&product=".$this->key)
//	    . "<br />\n" . $this->description
//
// Product::setPicture's blank.gif/images/catalog/ defaulting (Product.php:43-50) is real but
// UNREACHABLE from any byte: catalog_string never reads $this->picture. It is not ported, because
// porting it would add a branch no output depends on.
func productCatalogString(row map[string]any) string {
	return htmlLink(phpString(row["name"]), "Product Details",
		"?page=catalog&product="+phpString(row["key"])) +
		"<br />\n" + phpString(row["description"])
}

// selectProductsByCategory is CatalogDAO::select_products_by_category (CatalogDAO.php:42-56).
//
//	$itemKey = ValidateFields::validateNumericKey($key);
//	if(isset($itemKey)){ $selectString = "SELECT * FROM Products where category=$itemKey"; ... }
//
// THE KEY IS RE-VALIDATED HERE, not trusted from the caller — the PHP validates in both places, and
// it matters for the NULL case: GetDocument's category branch passes an unvalidated-through NULL
// (as "") straight in, and this second validateNumericKey is what turns it into "no rows" instead
// of a broken query. On a value that already passed, the check is idempotent (its output is always
// a digit run, which re-validates to itself).
//
// THE PHP INTERPOLATES $itemKey INTO THE SQL, and so does this — the one place in this package that
// does not bind. Binding would be WRONG here rather than merely different: $itemKey is a string,
// and a bound TEXT '5' vs the integer literal 5 is a comparison sqlite resolves through column
// affinity, so the two are the same query only by accident of the schema. The interpolation is the
// PHP's exact bytes and is provably injection-free — $itemKey is a preg_match("/[0-9]+/") RESULT,
// so it is a run of ASCII digits and nothing else. isDigitRun re-asserts that locally, so a reader
// need not trace validateNumericKey to see that this line is safe; it can only fail if this file
// is later changed to feed it something else.
func (t *CatalogControllerTag) selectProductsByCategory(key string) []map[string]any {
	itemKey, isset := validateNumericKey(key)
	if !isset {
		return nil // $result stays array()
	}
	if !isDigitRun(itemKey) {
		return nil // unreachable: validateNumericKey returns a /[0-9]+/ match or nothing
	}
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return nil
	}
	defer db.Close()
	return safeRows(db, "SELECT * FROM Products where category="+itemKey)
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// WORKING_PAGE — Controller.php + DocumentManager.php + Document.php
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// workingPageKey is PersistentObjectManager::getData("WORKING_PAGE")->getKey(), re-derived from the
// two steps that produce it. See "WORKING_PAGE" in the file header for why it is derived and not
// hardcoded to "tags".
//
//	Controller::control()            : isset($_GET['page']) ? validatePageKey($_GET['page']) : "catalog"
//	DocumentManager::produceDocument : that key's row, else the 'invalid' row
//	Document::getKey()               : the row's DocumentID
//
// validatePageKey's NULL (ok=false) becomes "", which matches no DocumentID and so takes the
// 'invalid' fallback — the same place the PHP lands, since it passes that same NULL to
// getDocumentData().
func (t *CatalogControllerTag) workingPageKey() string {
	key := "catalog" // Controller.php:15-19: no ?page= at all
	if v, ok := t.e.getIsset("page"); ok {
		key, _ = validatePageKey(v)
	}
	if doc, err := t.e.GetDocumentByKey(key); err == nil {
		return doc.Key
	}
	if doc, err := t.e.GetDocumentByKey("invalid"); err == nil {
		return doc.Key // DocumentManager.php:47-51
	}
	// produceDocument returns NULL, and Controller::display then fatals on NULL->__toString()
	// before any tag runs — so the PHP never reaches this tag in this state and has no bytes to
	// match. Unreachable from a render; "" keeps the href's shape.
	return ""
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The PHP primitives this tag needs and engine.go does not already have.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// numericKeyPattern is validateNumericKey's /[0-9]+/ (ValidateFields.php:31).
var numericKeyPattern = regexp.MustCompile(`[0-9]+`)

// phpNumericStringPattern is PHP 8's is-numeric-string grammar, the test `==` applies before it
// decides whether to compare two strings as numbers:
//
//	WHITESPACE* [+-]? (DIGITS ("." DIGITS?)? | "." DIGITS) ([eE] [+-]? DIGITS)? WHITESPACE*
//
// PHP 8.0 made TRAILING whitespace legal here (7.x accepted leading only), and the whitespace set
// is " \t\n\r\v\f" — the same set isPHPSpace names (engine.go:624). Go's \s inside a character
// class is [\t\n\f\r ], missing \v, so the set is written out.
var phpNumericStringPattern = regexp.MustCompile(
	`^[ \t\n\r\v\f]*[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?[ \t\n\r\v\f]*$`)

// phpIsNumericString is PHP 8's is_numeric() for a string operand of `==`.
func phpIsNumericString(s string) bool { return phpNumericStringPattern.MatchString(s) }

// phpLooseEqualStrings is PHP 8's `==` between two STRINGS (the only shape validateNumericKey
// needs): numeric comparison when both are numeric strings, byte comparison otherwise. This is the
// PHP 8 rule, not PHP 7's — 7.x cast the non-numeric side to a number, which is why "abc" == 0 was
// once true. The port targets the PHP that serves this repo; see the file header's table.
func phpLooseEqualStrings(a, b string) bool {
	if phpIsNumericString(a) && phpIsNumericString(b) {
		return phpParseFloat(a) == phpParseFloat(b)
	}
	return a == b
}

// phpParseFloat is the (float) cast `==` applies to a numeric string. The string has already
// passed phpIsNumericString, so it is one of PHP's numeric literals; ParseFloat accepts every one
// of them once the PHP-legal surrounding whitespace and leading '+' are removed, neither of which
// Go's ParseFloat takes. A value too large for float64 parses to ±Inf in both languages, and an
// error (which the grammar makes unreachable) yields 0.
func phpParseFloat(s string) float64 {
	t := ""
	for i := 0; i < len(s); i++ {
		if !isPHPSpace(s[i]) {
			t = s[i:]
			break
		}
	}
	for len(t) > 0 && isPHPSpace(t[len(t)-1]) {
		t = t[:len(t)-1]
	}
	t, _ = strings.CutPrefix(t, "+")
	f, err := strconv.ParseFloat(t, 64)
	if err != nil {
		return 0
	}
	return f
}

// validateNumericKey is ValidateFields::validateNumericKey (ValidateFields.php:29-37). ok=false is
// the PHP's NULL — i.e. `isset($itemKey)` being false. See the file header for the measured table
// of inputs and why the RETURN IS THE MATCH, not the input.
//
// Catalog_Controller.php calls it as ValidateFields::ValidateNumericKey with a capital V; PHP
// method names are case-insensitive, so that is this same method.
func validateNumericKey(itemKey string) (string, bool) {
	m := numericKeyPattern.FindString(itemKey)
	if m == "" {
		// $result[0] is undefined here ("Warning: Undefined array key 0"), so the comparison is
		// against NULL and BOTH arms of the if return that same undefined value: NULL either way.
		return "", false
	}
	if !phpLooseEqualStrings(itemKey, m) {
		return "", false
	}
	return m, true
}

// isDigitRun re-asserts selectProductsByCategory's interpolation precondition locally. See the
// comment there for why the query interpolates rather than binds.
func isDigitRun(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return true
}

// htmlLink is HTMLFunctions::link (HTMLFunctions.php:10-12) — bare concatenation, no escaping of
// any of the three parts. See "NO ESCAPING" in the file header.
//
//	return "<a href='" . $href . "' alt='" . $altText . "'>" . $linkText . "</a>";
func htmlLink(linkText, altText, href string) string {
	return "<a href='" + href + "' alt='" + altText + "'>" + linkText + "</a>"
}

// htmlImage is HTMLFunctions::image (HTMLFunctions.php:13-15):
//
//	return "<img src='" . $imageLocation . "' alt='" . $altText . "' "
//	     . HTMLFunctions::array_contents($attributes) . " >";
//
// The $attributes parameter is dropped: Category::catalog_string is the ONLY caller in this tag's
// reach and it passes "" (Category.php:60), and array_contents("") returns NULL — `if(!empty(""))`
// is false, so the function falls off its end (HTMLFunctions.php:16-24). Modelling an attribute
// list no caller supplies would be inventing surface; what it CANNOT drop is the empty slot's two
// surrounding spaces, so the output carries a DOUBLE space before '>':
//
//	<img src='images/category/' alt=''  >
func htmlImage(imageLocation, altText string) string {
	return "<img src='" + imageLocation + "' alt='" + altText + "' " + "" + " >"
}
