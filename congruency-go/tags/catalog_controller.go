// catalog_controller.go — ticket #253, unit go-port:tags:tag:Catalog_Controller.
//
// The Go port of ONE tag: invocators/tags/store/Catalog_Controller.php. It is a self-contained
// leaf in the sense #281 established — this file holds the tag's type, its GetDocument, its
// helpers and its self-registration, and it changes NOTHING in engine.go. Adding it moves
// PortedTags() from 12 names to 13 (VERIFIED this session: engine.go:1374-1385 registers 10,
// annotations.go:157 and apireference.go:55 one each); that is the whole footprint.
//
// THE CONTRACT: byte-identical HTML. The PHP is the spec. Everything below that looks quirky is
// quirky because Catalog_Controller.php (and the classes it reaches through) is, and where the two
// disagree the Go is wrong.
//
// ── WHAT THE TAG IS ─────────────────────────────────────────────────────────────────────────────
//
// The STORE front controller: one tag that picks which of three store views the page shows, from
// $_GET alone. It is the first tag ported out of invocators/tags/store/ (the twelve before it are
// all under invocators/tags/dev/ — verified by listing both directories this session), and it is
// unlike them in three ways that drive everything below:
//
//	?product=<n>   -> a product pane   : "<div ...><<<ContentTag(storkmessage)>>>
//	                                     <<<Config_Form_Invocator(n)>>><<<ProductView(n)>>></div>"
//	?category=<n>  -> a product LIST   : "<<<ContentTag(ProductViewListing)>>>" + the list +
//	                                     "<<<CategoryView(n)>>>"
//	(neither)      -> the category LIST: "<<<ContentTag(CategoryViewListing)>>>" + the list
//
//  1. IT EMITS TAG INVOCATIONS, it does not render them. Every branch returns a string containing
//     <<<...>>> markup for OTHER tags. Substituting those is the ENGINE's job (ExecuteAllTags,
//     engine.go:1022 — the port of Tag_Wrapper::execute_all_tags), not this tag's, and each of
//     those tags is its own #230 unit. This file emits the invocations verbatim and expands
//     nothing. See "THE NESTED TAGS" below — it is the whole reason this unit's gate reads the way
//     it does.
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
// (boot/constants.default.json:33 — read this session, exact) — no underscore, no digits. So
// "<<<Catalog_Controller>>>" never matches identify_tag: the scan takes "<<<Catalog" and then needs
// ">>>" where "_" stands. The gallery reaches this class a different way — TagList instantiates the
// selected name DIRECTLY (`new $sel(null)`, TagList.php:67), bypassing the regex — which is why
// ?page=tags&tag=Catalog_Controller renders and a template never can.
//
// MEASURED this session over the live DB's public read API (boot/rest.php's ?api= surface): all 26
// Documents rows and all 27 Document_Templates rows carry ZERO occurrences of "Catalog_Controller",
// and the only template embedding <<<TagList>>> is TemplateID 14, whose sole Documents row is
// DocumentID='tags'.
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
// live PHP returns, as the tag's whole body (68 bytes, measured),
//
//	<div width='70%' align='center'><<<Config_Form_Invocator(1)>>></div>
//
// — the literal reaches the browser. This port emits the identical bytes and lets the identical
// regex decline them. (The five tags that DO match all render "" against this database; the bare
// gate's 238-byte body begins "\n<table ..." with no ContentTag residue, which is that fact
// measured rather than assumed.)
//
// ── WORKING_PAGE: THE ONE THING THIS TAG READS THAT THE GO ENGINE HAS NO POM FOR ─────────────────
//
// Category::catalog_string (Category.php:58-63) builds its href from
// `PersistentObjectManager::getData("WORKING_PAGE")->getKey()` — the Document the CONTROLLER is
// rendering. engine.go's header records that there is no POM in this port (divergence 3), so the
// value has to be re-derived. workingPageKey below does it by REPRODUCING THE TWO STEPS THAT
// PRODUCE IT, rather than by hardcoding "tags":
//
//	Controller::control()            (Controller.php:14-22) : validatePageKey($_GET['page']) at :16,
//	                                                          or "catalog" when ?page= is absent (:18)
//	DocumentManager::produceDocument (DocumentManager.php:42-54) : that key's Documents row, and
//	                                                          FAILING THAT the 'invalid' row (:47-51)
//	Document::getKey()               (Document.php:35-37)   : the row's DocumentID
//
// The 'invalid' fallback is the load-bearing half. MEASURED this session: the DocumentID lookup is
// case-SENSITIVE, so ?page=TAGS finds no row, falls back to the 'invalid' document (which exists in
// the live Documents table), and renders the 404 page — 3,133 bytes, byte-for-byte the same length
// as ?page=nosuchpage — whose template holds no <<<TagList>>>, so this tag never runs there.
// Hardcoding "tags" would be right for every URL that can reach this tag today and wrong about why,
// and it would rot silently the moment a second document embedded the gallery.
//
// On the live PHP at ?page=tags the derivation lands on "tags", and the rendered href is
// "?page=tags&category=1" — measured, not assumed.
//
// ── Categories HAS NO `picture` COLUMN, AND THE PHP READS IT ANYWAY ──────────────────────────────
//
// Category::sql_assoc_array (Category.php:14-21) does
// `$result->setPicture($array[CatalogDAO::FIELD_NAME_PICTURE])` at :17 — i.e. $array['picture'].
// MEASURED through the ?api=Categories surface this session: the live Categories table has exactly
// three columns — key, name, description — over exactly one row (key=1, "specifications",
// "Specification pages"). There IS no picture. So PHP 8 raises "Warning: Undefined array key
// \"picture\"" and evaluates it to NULL, "images/category/" . NULL is "images/category/", and the
// img renders with an EMPTY src path. The live bytes, cut from the page this session:
//
//	<td><img src='images/category/' alt=''  ></td>
//
// Go's map read of an absent key yields nil and phpString(nil) is "" (engine.go:497-500), so the
// same bytes fall out with no special case. This is a PHP defect worth a bug ticket of its own; per
// the ticket's instruction the defect is ported faithfully and NOT "improved" here.
//
// ── AND THE WARNING IS ON THE PAGE. display_errors IS ON. ────────────────────────────────────────
//
// Round 1 of this ticket asserted the opposite as a measurement — "the warning itself never reaches
// the page (display_errors is off — the rendered page contains zero occurrences of
// Warning/Notice/Deprecated/Fatal, checked this session)". THAT IS FALSE, and it is corrected here
// rather than carried forward. Fetching the gate URL this session, the page opens with a 234-byte
// PREAMBLE before its <!DOCTYPE — reproduced verbatim, only the path elided:
//
//	\n\n<br />\n<b>Warning</b>:  Undefined array key "picture" in
//	<b>/Users/.../lib/Modules/StoreModule/Catalog/Category/Category.php</b> on line <b>17</b><br />\n
//
// Line 17 is exactly the setPicture call above. A warning-free page's preamble is 2 bytes ("\n\n"),
// which is what ?tag=TagList, ?tag=Annotations and ?tag=BugCatalog each return — so this preamble
// is THIS TAG's, not the CMS's. It sits before the doctype because Controller::control() builds the
// whole page into $display_string and only print()s it at Controller.php:21, while PHP's error
// handler writes straight to the output stream as each warning happens.
//
// The category branch is louder. ?category=abc emits FIVE warnings and a 1,072-byte preamble, all
// "Undefined array key 0" from ValidateFields.php — three from line 32 and TWO FROM LINE 33. Those
// two are worth reading closely, because they are runtime proof of the both-arms claim under
// "validateNumericKey" below: :32 is `if($itemKey == $result[0])` and :33 is `return $result[0]`,
// so a line-33 warning means PHP took the TRUE arm and RETURNED the undefined value. The five are
// three calls, traced to source: GetDocument's own (:32 only — "abc" == NULL is false, so the ELSE
// arm returns the NULL literal); CatalogDAO::select_products_by_category re-validating that NULL
// (CatalogDAO.php:44 — :32 and :33, because NULL == NULL is TRUE); and the CategoryView tag the
// engine expands out of "<<<CategoryView()>>>", whose constructor calls
// CatalogDAO::get_category_details (CategoryView.php:14-18), which validates again at
// CatalogDAO.php:98 (:32 and :33 on ""). Three line-32s and two line-33s — exactly the five
// measured. The two branches that never read an undefined index emit ZERO warnings, which is the
// same trace run backwards: ?product=1 and ?category=5 both return a 2-byte preamble.
//
// THIS PORT EMITS NO WARNINGS, DELIBERATELY, and that is a real page-level divergence rather than a
// thing this file can fix:
//
//   - They are NOT get_document()'s bytes. They are the PHP runtime writing to the output stream
//     around it. The tag's return value — the 238 bytes this unit is responsible for — does not
//     contain them, which is why the slice this port is measured against is unaffected and still
//     matches byte for byte.
//   - They are not reproducible even in principle. The text embeds the ABSOLUTE PATH of the PHP
//     checkout on the machine that served it and a PHP SOURCE LINE NUMBER. There is no Category.php
//     in this port to have a line 17. Emitting a hand-forged copy would be inventing a PHP error
//     handler in Go and hardcoding another machine's filesystem layout into a tag.
//   - The Tag interface has no channel for them: a Tag returns one string (engine.go:852-854).
//     Nothing in #226's engine models PHP's output stream, and a port-ONE-tag ticket is not where
//     that gets built.
//
// So: the page-level gate carries this on top of the ~6.2 KB of chrome, and both are named in
// "THIS UNIT'S GATE" below. If the pages are ever to converge, an error-emission surface is a
// prerequisite and it is somebody's ticket — not this one's.
//
// Note the DOUBLE space before that '>': HTMLFunctions::image (HTMLFunctions.php:13-15) concatenates
// "' " . array_contents($attributes) . " >", and array_contents("") takes its `if(!empty($array))`
// false arm, which falls off the end of the function and returns NULL (HTMLFunctions.php:16-24) — an
// empty slot between two spaces. See htmlImage.
//
// ── validateNumericKey IS PHP 8's `==`, AND THAT IS THE HARDEST PART OF THIS FILE ────────────────
//
// ValidateFields::validateNumericKey (ValidateFields.php:29-37) is four lines:
//
//	preg_match("/[0-9]+/", $itemKey, $result);          // :31
//	if ($itemKey == $result[0]) { return $result[0]; } else { return NULL; }
//
// Two STRINGS compared with `==`. This is NOT "compare as floats", and it is NOT "compare as
// strings" — PHP 8 dispatches through zendi_smart_strcmp, which has FOUR outcomes, three of which
// this file has been bitten by. phpLooseEqualStrings below mirrors that function's structure
// deliberately, so it can be read against the PHP source rather than trusted:
//
//	a) either side is NOT a numeric string        -> compare BYTES
//	b) both sides overflow the int range, same
//	   sign, and are EQUAL as doubles             -> compare BYTES (accuracy was lost; zend says so)
//	c) either side is a double                    -> compare as doubles (the long side is cast)
//	d) both sides are ints                        -> compare as ints
//
// The needle $result[0] is always a digit run, so it is always numeric; the haystack decides. Every
// row below was DRIVEN AGAINST THE LIVE PHP this session (?page=tags&tag=Catalog_Controller&
// product=<v> renders "<<<Config_Form_Invocator(RET)>>>" when the key validates and "" when it does
// not — so the rendered bytes ARE validateNumericKey's return value, read directly):
//
//	"5"    -> "5"    5 == 5                     "5x"  -> NULL  not numeric -> "5x" !== "5"   (a)
//	" 5"   -> "5"    leading ws is numeric      "-5"  -> NULL  -5 != 5 (the '-' is not matched)
//	"5 "   -> "5"    trailing ws is numeric     "1e1" -> NULL  10 != 1                       (c)
//	"+5"   -> "5"    signed is numeric          "abc" -> NULL  no match at all
//	"5.0"  -> "5"    5.0 == 5   (!)             ""    -> NULL  no match at all
//	"05"   -> "05"   5 == 5                     "0"   -> "0"   0 == 0, and isset("0") is TRUE
//	"007"  -> "007"  7 == 7                     "-0"  -> "0"   -0 == 0 as ints              (d)
//	"5."   -> "5"    "5." is numeric, 5.0 == 5  ".5"  -> NULL  0.5 != 5
//
// Two of those are the ones a reasonable port gets wrong. The RETURN VALUE IS THE MATCH, NOT THE
// INPUT — "05" yields "05" and "007" yields "007", so ?product=007 renders
// <<<Config_Form_Invocator(007)>>> with the zeros intact (measured, 70 bytes). And "5.0" and "+5"
// and " 5" all reach the DB as category 5 — a strict is-this-all-digits check would render an empty
// page for each, and the live PHP renders category 5's two products (172 bytes) for all three.
//
// A non-match returns NULL down BOTH arms: $result[0] is undefined, so `$itemKey == NULL` is a
// comparison against NULL, and the `if` arm then returns that same undefined $result[0]. So
// "no digits anywhere" is NULL whichever way the branch falls, which is why validateNumericKey
// below needs no third case. This is not read off the source alone — ?category=abc makes the live
// PHP emit "Undefined array key 0" warnings from ValidateFields.php line 33, and line 33 IS
// `return $result[0]`, so the TRUE arm demonstrably runs and returns the undefined value. See
// "display_errors IS ON" above.
//
// ── THE INT/DOUBLE BOUNDARY: WHERE ROUND 1 OF THIS TICKET WAS WRONG, TWICE ───────────────────────
//
// Round 1 shipped `phpLooseEqualStrings` as "if both numeric, compare phpParseFloat(a) ==
// phpParseFloat(b)". That is outcome (c) applied to all four cases, and it is wrong twice. Both
// defects are FIXED below and both are pinned by a measured input:
//
//  1. OVERFLOW TO ±Inf WAS THROWN AWAY (the round-1 adversary's finding, reproduced and confirmed).
//     Go's strconv.ParseFloat returns +Inf TOGETHER WITH ErrRange for a grammatically-valid but
//     overflowing value; round 1's `if err != nil { return 0 }` turned that Inf into 0. For
//     ?product=0.1e400 the /[0-9]+/ match is "0", so the Go compared 0 == 0 -> TRUE and rendered
//     68 bytes where the live PHP compares INF == 0 -> false and renders 0. The round-1 doc comment
//     asserted the grammar made the error unreachable; the grammar makes ErrSyntax unreachable, NOT
//     ErrRange. phpParseFloat now returns f unconditionally — see its comment for why that is
//     correct and not merely lax.
//
//  2. OUTCOME (b) DID NOT EXIST — a SECOND divergence, of a class round 1 never modelled, found by
//     sweeping this file's own logic against the live PHP (see "WHAT WAS MEASURED"). When BOTH
//     operands overflow the int range in the same direction AND are equal as doubles, zend
//     ABANDONS the numeric comparison and compares BYTES, because the float compare has lost the
//     accuracy needed to separate them. So:
//
//	"99999999999999999999"    -> "99999999999999999999"   bytes are equal        -> TRUE
//	" 99999999999999999999"   -> NULL                     bytes differ (the ws)  -> FALSE
//	"+99999999999999999999"   -> NULL                     bytes differ (the '+') -> FALSE
//	" 9223372036854775808"    -> NULL                     2^63 overflows -> (b)
//	" 9223372036854775807"    -> "9223372036854775807"    2^63-1 FITS    -> (d), ints, equal
//
//     A pure float compare says all five are equal and renders a product pane for each; the PHP
//     renders 0 bytes for three of them. Note the boundary is the VALUE 2^63-1, not a digit count:
//     the two 19-digit neighbours above fall on opposite sides of it.
//
// The classification that produces (b) has two more edges, both measured, both encoded in
// phpClassify:
//
//   - LEADING ZEROS ARE SKIPPED BEFORE THE DIGITS ARE COUNTED. " 0000000000000000000009" is 22
//     digits but classifies as the int 9, so it is (d) and validates to "0000000000000000000009".
//     Counting the zeros would make it (b) and return NULL. (And that key then reaches the SQL as
//     `where category=0000000000000000000009`, which sqlite reads as 9 — the live PHP renders
//     category 9's one product, 96 bytes, for it.)
//   - THE 20-DIGIT OVERFLOW FIRES DURING THE INT SCAN, so it fires even when a '.' or exponent
//     follows. "10000000000000000000.0" (20 int digits) overflows -> (b) -> bytes differ -> NULL,
//     while "9223372036854775808.0" (19 int digits) does NOT set the overflow flag -> (c) ->
//     doubles are equal -> "9223372036854775808". Those two inputs differ ONLY in digit count and
//     land in different outcomes; they are why phpClassify tests the digit count before the '.'.
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
// The PHP's degradation is NOT an error page — it is silence, and it comes from two lines:
// DataConnection::open sets PDO::ERRMODE_SILENT (DataConnection.php:34) and DataConnection::query
// returns FALSE on a failed statement (DataConnection.php:47, inside :43-49); both DAO methods then
// guard with `if($resultSet)` (CatalogDAO.php:32, :48). So a missing/unreadable table yields an
// EMPTY array, an empty list, and a tag body of just its ContentTag invocation. safeRows
// (engine.go:1282-1288) returns nil on exactly that error, so the Go takes the same silent path and
// emits the same bytes with no special case.
//
// Two divergences, both inherited from engine.go's openDB policy (divergence 2), both stated
// rather than quietly widened:
//
//   - DB FILE MISSING. PHP's `new PDO('sqlite:'.$path)` (DataConnection.php:32) is READ-WRITE and
//     CREATES an empty file; the Categories query then fails and the tag renders its silent empty
//     state. openDB refuses to create anything and errors (engine.go:1177-1179), and this file's
//     readers turn that error into the same empty state. So THE BYTES AGREE — only the side effect
//     differs, and the side effect Go declines is the one #153/Theme 3 forbids. This is the rare
//     case where the port's stricter open costs nothing.
//   - CONGRUENCY_SQLITE UNDEFINED (Config.SQLite == ""). PHP falls through to
//     `new PDO('mysql:host=...')` (DataConnection.php:33), which throws PDOException — uncaught
//     in this tag (it has no try/catch of its own), so TagList's catch (TagList.php:69-72) renders
//     "This tag needs context to render standalone: PDOException: ...". Go renders the empty state
//     instead. That is a real byte difference on one input, unreachable from the gate (DefaultConfig
//     always derives a path, engine.go:367) and out of scope for a port-ONE-tag ticket.
//
// NO catchThrowable HERE, DELIBERATELY. Annotations/CategoryBrowse wrap themselves in one because
// their PHP classes have their own `catch (\Throwable $e)` arm. Catalog_Controller.php has NO
// try/catch: a throw propagates out of the tag and is caught by TagList (TagList.php:69-72).
// TagListTag.renderSelected's recover() (engine.go:1564-1576) is that same outer net. Adding a
// cy-form-error div here would invent an error surface the PHP does not have.
//
// ── WHAT WAS AND WAS NOT RUN (read this before trusting a claim above) ──────────────────────────
//
// THIS FILE WAS NEVER COMPILED, and that is stated first because it bounds everything after it. The
// Go toolchain is not invocable in the session that wrote it: `go version` and `go build ./...` were
// both refused by the harness with "This command requires approval", and there was no one to
// approve. So there is NO build, NO vet, NO gofmt, NO SelfCheck() run and NO `go test` run behind
// this port, and none is claimed. Shelling out to go from the python that IS permitted would route
// around a permission gate, which is not a measurement; it was not done. THE FIRST THING TO DO WITH
// THIS FILE IS RUN:
//
//	cd congruency-go && go build ./... && go vet ./... && gofmt -l .
//
// WHAT WAS DONE INSTEAD, AND WHY IT IS NOT THE ROUND-1 EVIDENCE. Round 1 offered a Python
// transliteration of its ALGORITHM, diffed 26/26 against the live PHP. Its adversary showed that
// method was structurally blind to the bug it shipped: Python's float("0.1e400") silently returns
// inf where Go's ParseFloat returns (+Inf, ErrRange), so a transliteration that calls float()
// cannot see a defect in the Go's ERROR HANDLING. That criticism is correct and it is answered
// here by changing the method, not by repeating it:
//
//   - The transliteration now models GO's strconv.ParseFloat CONTRACT — the (value, err) PAIR, with
//     ErrRange returned alongside ±Inf on overflow and ±0 on underflow — and then runs THIS FILE's
//     own control flow and error handling over it. The Go primitive is what is under test, not an
//     idealised one.
//   - PROOF THAT THE METHOD NOW HAS THE RESOLVING POWER IT LACKED: run with round 1's phpParseFloat
//     and phpLooseEqualStrings, the same harness FAILS 53 of 988 inputs — including
//     product=0.1e400, the adversary's exact finding, reproduced byte-for-byte ("" from PHP vs this
//     port's 68-byte div). A method that reproduces the bug it is asked to certify against is a
//     method that can see it. Round 1's could not.
//   - THE ORACLE IS THE LIVE PHP, not a reading of it. The PHP this repo serves is up on
//     127.0.0.1:8899, and the tag's own bytes are cut out of its rendered page with #282's anchors
//     (equivalence_test.go:35-75): the page is [WARNINGS +] CHROME + gallery + <the tag> + TAIL,
//     the head cut is TagList.php:62's
//     "<div class='tagout'><h3>&lt;&lt;&lt;Catalog_Controller&gt;&gt;&gt;</h3>\n" literal and the
//     tail cut is len(page) - len("</div>\n" + TAIL). Both cuts are SEARCHED for, not offsets, so
//     the warning preamble that only this tag produces cannot shift them. TAIL was DERIVED, not
//     hardcoded, from TagList.php:77-78's "Unknown tag" branch (fetch a name no tag file has;
//     everything after that marker is TAIL): "\n</body>\n</html>\n", 17 bytes — the same 17 bytes
//     equivalence_test.go:72 records, measured independently this session. Every fetched page is
//     REQUIRED to end with "</div>\n"+TAIL before a slice is cut, so a page that does not is
//     reported rather than silently mis-sliced.
//   - THE ENGINE'S SUBSTITUTION WAS MEASURED, NOT ASSUMED. The PHP slice comes off a page
//     ExecuteAllTags has already run over, so the comparison applies the same rule to this file's
//     raw output: ContentTag/ProductView/CategoryView -> "", Config_Form_Invocator -> verbatim.
//     Each half was confirmed against real bytes (the bare body starts "\n<table" with no ContentTag
//     residue; the product body keeps its Config_Form_Invocator literal).
//
// THE RESULT: 988 inputs, 0 mismatches. 175 of the 988 carry NON-EMPTY bytes (a pass on "" vs ""
// is weak evidence, so they are counted separately). The inputs are both branches driven over the
// hand-picked table above, the whole int/double boundary family, 400-digit runs, and ~440 random
// strings over "0123456789+-.eE \t\v\fxz". Two narrower sweeps back it up, both also 0 mismatches:
// validateNumericKey alone over 549 inputs (207 non-empty) against the live PHP's readout, and a
// 52-input grammar check aimed at phpNumericStringPattern itself — the forms where Go's float
// parser and PHP's numeric-string grammar are most likely to disagree ("5.e3", "9223372036854775808.",
// "10000000000000000000.", "1.7976931348623157e308" and its next value up, "4.9e-324", "0x1A",
// "1_0", "INF", "NAN"). Representative non-empty rows:
//
//	(bare)                                    238B  the category table — the ticket's gate
//	&category=5 | &category=9                 172B / 96B  the two populated categories
//	&category=%205 | 5%20 | %2B5 | 5.0 | 05   172B  the five PHP-8 `==` quirks, all -> category 5
//	&category=0000000000000000000009           96B  22 digits -> int 9 -> sqlite reads the literal as 9
//	&product=1 | 2 | 3 | 0 | 007 | -0 | %201  68-70B  the Config_Form_Invocator literal survives
//	&product=1&category=5                       68B  product wins; category is not consulted
//	&product=abc | "" | 0.1e400 | %2099..9      0B  the empty states, incl. both round-1 defects
//
// WHAT THAT DOES AND DOES NOT ESTABLISH. It establishes that the LOGIC encoded here — including its
// handling of Go's ParseFloat error contract — reproduces the live PHP byte for byte on every
// branch this tag has, and that the harness can detect the class of defect that broke round 1. It
// does NOT establish that this file COMPILES, that gofmt/vet are clean, or that Go's ParseFloat
// matches the emulated contract in a corner the emulation got wrong. Those need the toolchain, and
// the toolchain needs an approval this session did not have. To reduce the compile risk that the
// toolchain would otherwise have caught, every external symbol this file uses was read out of
// engine.go this session and checked against its real signature (Tag/Engine.cfg/Config.SQLite/
// Document.Key/getIsset/validatePageKey/GetDocumentByKey/openDB/safeRows/phpString/Register), and
// every name this file DECLARES was checked against every other file in package tags for a
// redeclaration — Register panics on a duplicate name (engine.go:4398-4399), and nothing else
// registers "Catalog_Controller".
//
// ── THIS UNIT'S GATE IS NOT EMPTY, AND THE REASON IS NOT THIS UNIT ──────────────────────────────
//
// Stated plainly because the ticket asks for exactly this ("if you cannot make a diff here run
// against THIS unit, say so on the ticket rather than settling on a diff that would be empty even
// with the unit unimplemented"). The ticket's literal gate is
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=Catalog_Controller') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=Catalog_Controller')
//
// RUN THIS SESSION: 7,019 bytes from 8899 against 4,122 bytes from 8900 — DIFFERS. It is non-empty
// for FOUR independent reasons, in increasing order of interest. None is fixable from inside this
// file; reasons 2 and 3 are non-empty for EVERY tag, ported or not:
//
//  1. THE DEPLOYED GO BINARY ON 8900 DOES NOT CONTAIN THIS FILE, and cannot: building it needs the
//     toolchain this session was refused. 8900 currently answers Catalog_Controller with the
//     gallery's notPortedHTML notice ("no Go port of Catalog_Controller yet"). It is stale
//     generally, not just for this ticket — it says the same for Annotations (#247) and
//     ApiReference (#248), whose tickets are already merged to main. Rebuilding 8900 is a
//     precondition for ANY tag's gate here, and it is not this ticket's deliverable.
//  2. PAGE CHROME, PLUS THIS TAG'S WARNING PREAMBLE. congruency-go's server does not reproduce the
//     PHP CMS chrome and declines to forge it (server.go:39-43, :62-66 — "larger by a constant
//     ~6.2 KB of CMS chrome ... which the frame here deliberately does not forge"). The two pages
//     differ by that ~6.2 KB whether or not this file exists. On top of it, and unlike every other
//     tag, THIS tag's page opens with PHP's own "Undefined array key" warning text — 234 bytes on
//     the gate URL, 1,072 on ?category=abc — which is not get_document()'s output and is not
//     reproducible in Go (it embeds the serving machine's absolute paths and PHP line numbers). See
//     "display_errors IS ON" above.
//  3. THE GALLERY FRAME. handleTagsPage (server.go:792-829) answers a REGISTERED tag by rendering
//     THAT TAG ALONE via tags.RenderTag (server.go:796-801) — no tag list, no <div class='tagout'>
//     wrapper. The PHP page carries the whole gallery around the tag. So registering this tag
//     CHANGES the Go page's shape; it does not converge it. (This is visible today: 8900's 4,122
//     bytes are the GALLERY, because the tag is unregistered there and sel falls back to "TagList".)
//  4. THE ONE THAT IS ABOUT THIS TAG. RenderTag returns get_document()'s bytes UNEXPANDED
//     (engine.go:4147-4159), while the PHP slice is cut from a page ExecuteAllTags has already run
//     over. This tag ALWAYS emits nested invocations, so the two are not the same measurement for
//     it — and even comparing expansion-to-expansion would differ, because ContentTag, ProductView
//     and CategoryView have no Go port yet (they are separate #230 units — ContentTag.php lives in
//     invocators/tags/document/, the other two in invocators/tags/store/ — and they are NOT in this
//     ticket's DEPENDS ON list, which names only the four engine units). The Go engine would render
//     each as unknownTagHTML's marked comment where the PHP renders "".
//
// So the honest measurement — the one that isolates THIS unit's bytes and changes exactly when this
// file changes — is the 988-input diff recorded above. With this unit unimplemented that diff is
// not empty, it is 238 bytes of category table against notPortedHTML's divergence notice, so it is
// not a diff that passes vacuously.
//
// WHAT WOULD MAKE THE LITERAL GATE EMPTY, for whoever picks this up: a rebuilt 8900, plus ports of
// ContentTag, ProductView and CategoryView (then the slices agree), plus a server that renders the
// gallery frame and the CMS chrome (then the pages agree). Three tag units, a server ticket, and a
// deploy — none of them this one.
package tags

import (
	"math"
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
//     products. getIsset is that isset (engine.go:923-932 — a present-but-empty ?product= is SET,
//     and validates NULL).
//  2. THE INNER isset IS ON THE PRODUCT BRANCH ONLY. The category branch takes validateNumericKey's
//     result unchecked and interpolates it straight into "<<<CategoryView($category)>>>", so an
//     invalid ?category= yields "<<<CategoryView()>>>" — which the engine's regex DOES match (its
//     arguments group is "(\([A-Za-z0-9]*\))*", boot/constants.default.json:34, and "()" satisfies
//     the * on the inner class). That empty invocation is a real byte this port must emit, not a
//     case to guard away.
//  3. NULL RENDERS AS "". PHP's $result starts NULL and the product branch may leave it NULL;
//     TagList does `(string)$obj->get_document()` (TagList.php:68), so NULL becomes "". Go's ""
//     is that value directly. Likewise NULL interpolated into the CategoryView invocation is "".
//  4. isset("0") IS TRUE. ?product=0 validates to "0" (0 == 0) and renders the product pane;
//     isset() tests for NULL, not for truthiness. Measured, 68 bytes.
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
// (Category.php:14-21, 58-63), fused: the bean is a pure carrier between the two, so the row map is
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
// affinity, so the two are the same query only by accident of the schema. It also matters for the
// leading-zero keys the header describes: `category=0000000000000000000009` is the integer 9 to
// sqlite's parser, which is exactly what the live PHP renders for it. The interpolation is the
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
	key := "catalog" // Controller.php:17-19: no ?page= at all
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
//
// This block is PHP 8's `==` between two strings. It is long for a reason: round 1 of this ticket
// wrote it as a float comparison and was wrong on two whole classes of input. See "THE INT/DOUBLE
// BOUNDARY" in the file header for the measured evidence behind every branch below.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// numericKeyPattern is validateNumericKey's /[0-9]+/ (ValidateFields.php:31).
var numericKeyPattern = regexp.MustCompile(`[0-9]+`)

// phpNumericWhitespace is the whitespace set PHP's numeric-string grammar allows around a number:
// " \t\n\r\v\f". It is the same set isPHPSpace names (engine.go:624-626), and it is NOT the set
// PHP's trim() uses (that one has \0 and lacks \f — see phpTrim, engine.go:630-632), which is why
// this is spelled out rather than borrowed.
const phpNumericWhitespace = " \t\n\r\v\f"

// phpLongMinDigits is the magnitude of PHP_INT_MIN as zend spells it — the 19-digit string a
// 19-digit candidate is strcmp'd against to decide whether it still fits a PHP int. A 19-digit run
// STRICTLY BELOW this is an int; equal-and-negative is PHP_INT_MIN and still an int; anything else
// overflows to double. (Measured: " 9223372036854775807" validates, " 9223372036854775808" does
// not — those two are this constant's boundary, one on each side.)
const phpLongMinDigits = "9223372036854775808"

// phpNumericStringPattern is PHP 8's is-numeric-string grammar, the test `==` applies before it
// decides whether to compare two strings as numbers:
//
//	WHITESPACE* [+-]? (DIGITS ("." DIGITS?)? | "." DIGITS) ([eE] [+-]? DIGITS)? WHITESPACE*
//
// PHP 8.0 made TRAILING whitespace legal here (7.x accepted leading only). Go's \s inside a
// character class is [\t\n\f\r ], missing \v, so the set is written out. This grammar is also what
// makes phpParseFloat's ErrSyntax unreachable: every string it admits is one Go's ParseFloat
// accepts once the whitespace and leading '+' are stripped. It admits none of Go's EXTRA forms
// ("Inf", "NaN", "0x1A", "1_0") — each was driven against the live PHP and each is NOT numeric
// there, so each takes the byte-compare arm.
var phpNumericStringPattern = regexp.MustCompile(
	`^[ \t\n\r\v\f]*[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?[ \t\n\r\v\f]*$`)

// phpIsNumericString is PHP 8's is_numeric() for a string operand of `==`.
func phpIsNumericString(s string) bool { return phpNumericStringPattern.MatchString(s) }

// phpParseFloat is zend_strtod — the (float) value `==` computes for a numeric string. The string
// has already passed phpNumericStringPattern, so it is one of PHP's numeric literals; ParseFloat
// accepts every one of them once the PHP-legal surrounding whitespace and the leading '+' are
// removed (Go's parser takes '+' itself, but stripping it keeps this function's input in one shape).
//
// THE ERROR IS DELIBERATELY DISCARDED, and the discard IS the fix for this ticket's round-1
// finding. Round 1 wrote `if err != nil { return 0 }`, which is wrong because ParseFloat returns a
// USEFUL f alongside its error:
//
//	err == nil       -> f is the value.
//	err == ErrRange  -> f is ALREADY what zend_strtod produces: ±Inf on overflow and ±0 on
//	                    underflow. Returning 0 instead of f is what made ?product=0.1e400 render
//	                    68 bytes against the live PHP's 0 (the /[0-9]+/ match is "0", so 0 == 0 was
//	                    TRUE where INF == 0 is false). ErrRange is REACHABLE for any grammatically
//	                    valid overflowing value; it is ErrSyntax the grammar rules out, not this.
//	err == ErrSyntax -> unreachable (see phpNumericStringPattern). f would be 0.
func phpParseFloat(s string) float64 {
	t := strings.Trim(s, phpNumericWhitespace)
	t = strings.TrimPrefix(t, "+")
	f, _ := strconv.ParseFloat(t, 64)
	return f
}

// The three outcomes of is_numeric_string_ex, which is what `==` classifies each operand with.
const (
	phpNotNumeric = iota // not a numeric string at all: `==` compares bytes
	phpIsLong            // an integer that fits a PHP int (int64)
	phpIsDouble          // a float, OR an integer too big for a PHP int (then oflow is set)
)

// phpNum is one operand of `==` as is_numeric_string_ex classifies it.
//
// digits carries the SIGNIFICANT integer digits (leading zeros stripped, sign removed) so that two
// phpIsLong operands can be compared EXACTLY without parsing them into an int64 — which would have
// to handle PHP_INT_MIN's asymmetry and could overflow. dval is set for every numeric kind, so the
// "cast the int side to double" arms of zendi_smart_strcmp need no extra work: for an integer-form
// numeric string, zend_strtod and (double)lval are both correctly-rounded conversions of the same
// integer and therefore identical.
type phpNum struct {
	kind   int
	neg    bool
	digits string
	dval   float64
	oflow  int // 0, or ±1 when the operand is an INTEGER that overflowed the int range
}

// phpClassify is is_numeric_string_ex: the kind, the value, and the overflow flag.
//
// THE ORDER OF THE CASES IS THE POINT. The digit-count overflow test comes BEFORE the "is there a
// '.' or exponent" test because zend sets oflow during the integer-part SCAN, so it fires even when
// a '.' follows. That ordering is not a guess — it is forced by two measured inputs that differ
// only in digit count: "10000000000000000000.0" (20 int digits) overflows and validates to NULL,
// while "9223372036854775808.0" (19) does not and validates to its digit run.
func phpClassify(s string) phpNum {
	if !phpIsNumericString(s) {
		return phpNum{kind: phpNotNumeric}
	}
	t := strings.Trim(s, phpNumericWhitespace)
	neg := strings.HasPrefix(t, "-")
	if len(t) > 0 && (t[0] == '+' || t[0] == '-') {
		t = t[1:]
	}
	i := 0
	for i < len(t) && t[i] >= '0' && t[i] <= '9' {
		i++
	}
	intPart, rest := t[:i], t[i:]
	digits := strings.TrimLeft(intPart, "0") // zend skips leading 0s before it counts
	oflow := 1
	if neg {
		oflow = -1
	}
	n := phpNum{neg: neg, digits: digits, dval: phpParseFloat(s)}
	switch {
	case len(digits) >= 20:
		// More digits than any int64 has: overflow, decided during the scan.
		n.kind, n.oflow = phpIsDouble, oflow
	case rest != "":
		// A '.' or an exponent follows: a plain float, and oflow stays 0.
		n.kind = phpIsDouble
	case len(digits) == 19 && !(digits < phpLongMinDigits || (digits == phpLongMinDigits && neg)):
		// 19 digits straddles the boundary; strcmp against PHP_INT_MIN's magnitude decides.
		n.kind, n.oflow = phpIsDouble, oflow
	default:
		n.kind = phpIsLong
	}
	return n
}

// phpLongEqual compares two phpIsLong operands exactly, on their normalized digits and sign. The
// digits are already leading-zero-stripped, so "05" and "5" carry the same digits. An all-zero
// operand has EMPTY digits and no sign, which is how "-0" == "0" comes out TRUE (measured:
// ?product=-0 renders the pane with "0").
func phpLongEqual(x, y phpNum) bool {
	if x.digits != y.digits {
		return false
	}
	if x.digits == "" {
		return true // both are zero; -0 and +0 are the same int
	}
	return x.neg == y.neg
}

// phpLooseEqualStrings is PHP 8's `==` between two STRINGS (the only shape validateNumericKey
// needs), mirroring zendi_smart_strcmp arm for arm. This is the PHP 8 rule, not PHP 7's — 7.x cast
// the non-numeric side to a number, which is why "abc" == 0 was once true. The port targets the PHP
// that serves this repo; see the file header's measured tables.
func phpLooseEqualStrings(a, b string) bool {
	n1, n2 := phpClassify(a), phpClassify(b)

	// (a) Not both numeric -> a plain byte comparison.
	if n1.kind == phpNotNumeric || n2.kind == phpNotNumeric {
		return a == b
	}

	// (b) Both are INTEGERS that overflowed the same way and are equal as doubles. The float
	// compare has lost the accuracy needed to separate them, so zend falls back to bytes. This is
	// why " 99999999999999999999" is NOT equal to "99999999999999999999" while
	// "99999999999999999999" is equal to itself. (Inf - Inf is NaN, so this test is false for two
	// infinities; the !finite arm below catches those and reaches the same byte comparison.)
	if n1.oflow != 0 && n1.oflow == n2.oflow && n1.dval-n2.dval == 0 {
		return a == b
	}

	// (c) At least one side is a double -> compare as doubles, casting the int side.
	if n1.kind == phpIsDouble || n2.kind == phpIsDouble {
		if n1.kind != phpIsDouble {
			if n2.oflow != 0 {
				// b is an integer outside the int range; a (an int) cannot equal it.
				return false
			}
		} else if n2.kind != phpIsDouble {
			if n1.oflow != 0 {
				return false
			}
		} else if n1.dval == n2.dval && math.IsInf(n1.dval, 0) {
			// Both overflowed to the same infinity: no numeric compare can separate them.
			return a == b
		}
		return n1.dval-n2.dval == 0
	}

	// (d) Both are ints.
	return phpLongEqual(n1, n2)
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
		// No match. ("" is unambiguous here: /[0-9]+/ cannot match the empty string.) $result[0] is
		// undefined ("Warning: Undefined array key 0"), so the comparison is against NULL and BOTH
		// arms of the if return that same undefined value: NULL either way.
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
// surrounding spaces, so the output carries a DOUBLE space before '>' (measured on the live page):
//
//	<img src='images/category/' alt=''  >
//
// The empty string below is that NULL slot, kept explicit so the double space reads as deliberate.
func htmlImage(imageLocation, altText string) string {
	return "<img src='" + imageLocation + "' alt='" + altText + "' " + "" + " >"
}
