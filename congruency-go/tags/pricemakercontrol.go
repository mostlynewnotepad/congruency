package tags

// pricemakercontrol.go — ticket #325, unit go-port:tags:tag:PriceMakerControl.
//
// The Go port of ONE tag: invocators/tags/Maker/PriceMakerControl.php. Per #281 a tag port is
// ADD-A-FILE-ONLY: this file holds the tag's type, its constructor, its GetDocument, the helpers
// those need, and the init() that self-registers it. Nothing in engine.go changes — Go runs every
// init() in a package before any other code in it, so the registry picks this tag up on its own
// (engine.go:1309-1314; Register at engine.go:1355, newTag at engine.go:1393). Adding this file
// moves PortedTags() by one name; that is the whole footprint.
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. THE PHP IS THE SPEC — where the two
// disagree, THIS file is wrong. Nearly everything below is quirky, because this tag is: it is a
// four-line class sitting on top of a defect in AbstractMaker and a PHP source file that does not
// parse. Each quirk is named at the code that needs it, so a later reader does not "correct" one
// back into a divergence.
//
// (engine.go:193-198's COVERAGE comment still lists PriceMakerControl under "NOT PORTED (35)". That
// list is a hand-maintained COPY whose own text names PortedTags() as "the authority"
// (engine.go:191-192), and PortedTags is registry-derived (engine.go:1406-1415), so it answers
// correctly the moment this file's init() runs. Correcting the copy means editing engine.go, which
// this ticket forbids — the same stale-copy state #312/#316/#319 left behind for DocList, Login and
// MemoryList. It is a comment, not behaviour.)
//
// ── THE PHP, IN FULL (PriceMakerControl.php:7-20 — there is no summary shorter than the source) ──
//
//	if (!class_exists("PriceMakerControl")) {
//	    class PriceMakerControl implements Tag_Interface {
//	        public function __construct($arguments) {         // :11-13 — an EMPTY constructor.
//	        }
//	        public function get_document() {                  // :15-18
//	            $priceMaker = new PriceMaker();
//	            return ($priceMaker->control());
//	        }
//	    }
//	}
//
// It has NO SQL, NO markup and NO arguments of its own: the constructor takes $arguments and drops
// it on the floor, so this tag renders identically however it is invoked. Every byte it can emit
// comes from PriceMaker::control(), three files away. So this port is a port of that chain, and the
// chain is short because it dead-ends:
//
//	PriceMaker.php:10-15        __construct: keyVariable="priceMaker", formName="PRICEMAKER",
//	                            selectionLink="<a href='?page=priceChange'>View all prices.</a>",
//	                            then init().
//	AbstractMaker.php:20-27     init(): $this->setKey($_GET['priceMaker']), and — only if the key
//	                            survived — fetch FORM_MANAGER out of the POM.
//	AbstractMaker.php:58-62     setKey(): $this->key = ValidateFields::validateNumericKey($prospect).
//	ValidateFields.php:29-37    THE VALIDATOR. Ported below; it is the only real logic in the unit.
//	AbstractMaker.php:29-36     control(): the two branches, one of which is a defect (see below).
//	AbstractMaker.php:38-49     initializeForm() -> PriceMaker::initFormArray() -> `new PriceDAO()`
//	                            -> ParseError, ALWAYS (see "THE SECOND DEFECT"). Nothing downstream
//	                            of that line has ever run in this app.
//
// So the tag has exactly TWO reachable outputs, and this file emits both:
//
//	no usable key  ->  "" (zero bytes)         — control()'s fall-through defect
//	a usable key   ->  TagList's 153-byte catch arm for the ParseError
//
// ── THE FIRST DEFECT: control() BUILDS ITS MESSAGE AND THROWS IT AWAY ───────────────────────────
//
// AbstractMaker::control() (AbstractMaker.php:29-36) is:
//
//	public function control(){
//	    $makerString = NULL;
//	    if(isset($this->key)){
//	        return $this->initializeForm() . $this->runForm();
//	    }else{
//	        $makerString = "<br />Invalid $this->keyVariable supplied. $this->selectionLink";
//	    }
//	}
//
// Look at the else arm: it ASSIGNS $makerString and the function then ENDS. There is no
// `return $makerString`. A PHP function that falls off its end returns NULL, get_document() passes
// that NULL straight up (PriceMakerControl.php:17), and TagList casts it with `(string)` at
// TagList.php:68 — and (string)NULL is "". So the tag whose entire purpose on this URL is to say
// "Invalid priceMaker supplied" says NOTHING: it contributes zero bytes.
//
// That is a REAL defect and it is ported faithfully, per #325 ("If the PHP is genuinely defective,
// file a separate bug ticket and port the defect faithfully"). It is MEASURED, not deduced — the
// live PHP contributes exactly 0 bytes on the gate URL (see "THE GATE"). pmcPriceMaker.control
// below builds the string and drops it exactly as the PHP builds it and drops it, so that a reader
// diffing the two functions finds a line for every line.
//
// ── THE SECOND DEFECT: PriceDAO.php DOES NOT PARSE, SO THE KEY PATH ALWAYS THROWS ───────────────
//
// This one is why the port is COMPLETE rather than half-marked: the entire form/DB half of
// AbstractMaker is unreachable in the live app, so there is nothing there to forge.
//
// With a usable key, control() takes its `return $this->initializeForm() . $this->runForm();` arm.
// PHP evaluates the LEFT operand first: initializeForm() (AbstractMaker.php:38-49) calls
// $this->initFormArray(), which for PriceMaker (PriceMaker.php:26-31) is
//
//	$priceDAO = new PriceDAO();          // PriceMaker.php:28
//
// ...and `new PriceDAO()` triggers the app's autoloader (boot/router.php:31,
// `spl_autoload_register(function ($class) use ($LOADER) { $LOADER->loadClassByName($class); })`),
// which include_once's the file (ClassLoader.php:23-32). That include NEVER COMPILES.
// lib/Modules/StoreModule/Catalog/price/PriceDAO.php has a NESTED-COMMENT bug: a `/*` opens above
// the commented-out get_only_prices(), and the first `*/` PHP meets is the one ending the
// `/* #25: no free */` line INSIDE it — PHP block comments do not nest, so the comment closes early
// and the rest of the block re-enters the parser as code. The stray `*/` on the `}*/` line then
// lands at top level, after every brace has been closed, and PHP reports:
//
//	ParseError: syntax error, unexpected token "*", expecting end of file
//
// A ParseError from an include is a \Throwable, so it unwinds out of get_document() and TagList
// catches it (TagList.php:69-72) and prints its catch arm. That is the tag's whole key-path output.
// The class never constructs, so PriceDAO::get_price never runs, no DataConnection is opened, no
// SQL is issued, and FormManager::runForm is never called. NONE of that needs porting, because none
// of it has ever executed on this URL. (Measured: 22 of the 50 inputs in "THE GATE" take this arm,
// and every one of them returns exactly the same 153 bytes — a DB-backed render could not be
// input-independent like that.)
//
// This is a bug in PriceDAO.php, not in this unit, and not a fatal for the page. FILING it is a
// separate ticket, not this one: #325 authorizes this file alone, and a bug ticket asserting
// "PriceDAO.php does not parse" is a claim about a file this unit may neither touch nor fix. The
// defect is ported, not repaired — pmcPriceDAOParseError* below carry the exact class and message
// the live interpreter produces.
//
// ── WHY GetDocument RETURNS TagList's CATCH ARM (the one design decision here — read it) ────────
//
// This looks like a layering violation — a tag emitting its caller's markup. It is the same call
// #257 made for Config_Form_Invocator (config_form_invocator.go:65-88), for the same reasons, and
// it is the only faithful option:
//
//   - GO HAS NO EXCEPTIONS, and the PHP's bytes here are produced by one. A Go Tag is
//     `GetDocument() string` (engine.go:852-854) — there is nowhere to put a throw — and engine.go
//     is not this ticket's deliverable ("touch nothing else"), so the throw cannot be signalled at
//     the point the PHP signals it.
//   - THE CATCH IS THE THROW'S ONLY OBSERVER IN THE WHOLE APP. Both Go entry points that can reach
//     this tag return GetDocument()'s bytes VERBATIM to the caller — TagList.renderSelected
//     (engine.go:1571-1575) and RenderTag (engine.go:4155-4159), which is #280's ?page=tags&tag=<T>
//     wiring (server.go:801). There is no third caller that would see these bytes in a context
//     where the PHP would not have printed them. The engine cannot invoke this tag from a document
//     either: no Document_Templates row mentions <<<PriceMakerControl>>> — #325 says so, and it was
//     re-checked against the live db this session (0 of 27 rows; see "THE GATE").
//   - THE ALTERNATIVE PROVABLY FAILS THE GATE. Panicking from GetDocument lands in renderSelected's
//     recover(), which emits "congruency-go: panic rendering <code>…" (engine.go:1565-1570) — a
//     marked Go notice with no PHP counterpart. That is the honest thing to emit for a Go bug and
//     the WRONG thing to emit for a faithfully reproduced PHP Throwable: the PHP prints the catch
//     arm, so the port must print the catch arm.
//
// So pmcStandaloneCatch is TagList.php:70-71 verbatim, built from the Throwable's CLASS and MESSAGE
// the way the PHP builds it — `self::esc(get_class($e) . ': ' . $e->getMessage())` — rather than
// pasted in as one opaque string, so a reader can check it against both sources side by side.
//
// ── THE PHP EMITS WARNINGS THIS PORT CANNOT AND MUST NOT REPRODUCE (a MEASURED divergence) ──────
//
// READ THIS BEFORE CONCLUDING THE PORT IS INCOMPLETE. On the gate URL the live PHP page is 7,205
// bytes and this tag's own bytes are 0 of them — but the page ALSO carries 657 bytes the tag caused:
//
//	<br />
//	<b>Warning</b>:  Undefined array key "priceMaker" in <b>…/Admin/AbstractMaker.php</b> on line <b>21</b><br />
//	<br />
//	<b>Warning</b>:  Undefined array key 0 in <b>…/Validators/ValidateFields.php</b> on line <b>32</b><br />
//	<br />
//	<b>Warning</b>:  Undefined array key 0 in <b>…/Validators/ValidateFields.php</b> on line <b>33</b><br />
//
// display_errors is ON in the deployed app — that block is really served, measured — and those three
// warnings are the three undefined reads this chain performs: $_GET['priceMaker'] when the URL has
// no priceMaker (AbstractMaker.php:21), and $result[0] on an empty $result at ValidateFields.php:32
// and :33 (the validator port below says why there are two).
//
// THEY ARE NOT THIS TAG'S RETURN VALUE, and the proof is their POSITION: PHP's error handler writes
// them straight to the output stream at the instant they occur, which is while the document is being
// rendered — BEFORE the controller echoes the page. So they land ABOVE `<!DOCTYPE html>`, while the
// tag's own return value lands ~7 KB later, inside `<div class='tagout'>`. A tag file that returns a
// string cannot put bytes above the doctype; and if GetDocument DID return them they would land
// inside the tagout div — the wrong place — and this tag's measured 0-byte body would become a
// 657-byte body, breaking the very gate they are absent from. Emitting them here would be a defect,
// not a fix.
//
// Reproducing them belongs to whoever owns the PHP-error-emission channel (engine.go's engine or
// server.go's frame); congruency-go models no PHP error handler at all, and this ticket may touch
// neither file. The warning block is therefore a KNOWN, MEASURED, LOCATED divergence of the PAGE,
// not of this unit — and it is a second, independent reason the ticket's literal whole-page diff
// cannot be empty today (the first is the page frame; see "THE GATE").
//
// Measured, per input. The count is INPUT-DEPENDENT, which is itself the evidence that the warnings
// track this chain and nothing else — a tag with no notices (BugCatalog, the control) emits a
// 2-byte "\n\n" prefix and no more, and that 2-byte prefix is subtracted from every figure here:
//
//	no priceMaker   -> 3 warnings (657B)   the $_GET read, then :32, then :33
//	priceMaker=     -> 2 warnings (428B)   the key IS set, so no $_GET warning; :32 and :33 still warn
//	priceMaker=abc  -> 1 warning  (214B)   :32 warns; the comparison is FALSE so :33 never runs
//	priceMaker=5    -> 0 warnings          nothing is undefined on this path
//	priceMaker=-5   -> 0 warnings          the regex MATCHED, so $result[0] exists; the compare fails
//
// No E_DEPRECATED notice for `preg_match(…, NULL, …)` appears on this build, measured — so nothing
// is claimed about one. This file records what was served, not what a PHP version ought to say.
//
// ── WHAT THIS FILE REUSES, AND WHAT IT DELIBERATELY DOES NOT ────────────────────────────────────
//
// It reuses engine.go's audited primitives rather than restating them: esc
// (htmlspecialchars($s, ENT_QUOTES), engine.go:599) and isPHPSpace (PCRE's \s, which is also PHP's
// numeric-string whitespace set — " \t\n\r\f\v" — engine.go:624-626).
//
// It does NOT call categoryview.go's categoryViewValidateNumericKey, which ports the SAME
// ValidateFields function (categoryview.go:298-331). That is #319's rule and it is deliberate: a
// sibling tag file is another ticket's deliverable, and depending on it would couple this unit's
// bytes to edits made under another unit's authority. engine.go is the shared floor; a sibling tag
// file is not. The pmc* validator below was derived independently from ValidateFields.php and then
// measured against the live PHP (50 inputs, below); it agrees with categoryview.go's port line for
// line, which is corroboration from a source that never saw this one.
//
// ── THE GATE — WHAT WAS RUN, WHAT IT MEASURED, AND WHAT IS NOT CLAIMED ──────────────────────────
//
// NOT RUN, AND THEREFORE NOT CLAIMED: THIS FILE WAS NEVER COMPILED. The Go toolchain is refused in
// the session that wrote it — `go version`, `go build ./...` and `go vet ./tags/` each came back
// "This command requires approval", with no one to approve them. So there is no build, no vet, no
// gofmt, no `go test` and no SelfCheck() run behind this port. The obvious workaround — shelling out
// to go from the python3 that IS permitted — was deliberately not taken: routing around a permission
// gate is not a measurement. (config_form_invocator.go:154-160 and memorylist.go:138 record the
// identical constraint and made the identical choice.) Everything below is what WAS run.
//
// THE TICKET'S LITERAL DIFF CANNOT SETTLE THIS UNIT TODAY, and no edit to this file can change that.
// Run, verbatim, this session:
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=PriceMakerControl') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=PriceMakerControl')
//	-> php 7,205B vs go 4,118B, 62 diff lines. NOT EMPTY.
//
// It is not empty for three reasons, none of them about this port, and all three MEASURED:
//
//  1. THE SERVER ON 8900 IS A STALE BINARY and rebuilding it is impossible here (the toolchain is
//     gated, above). It cannot serve a file written after it started, so that diff would read the
//     same with this unit unimplemented — which is exactly the vacuous gate #325 says not to settle
//     for.
//  2. THE TWO PAGES ARE DIFFERENT FRAMES around the same tag. PHP serves Controller::control()'s CMS
//     chrome wrapping the whole 45-item gallery; 8900 serves #280's own "<!doctype html><title>…"
//     frame around the selected tag alone (server.go:795-801). server.go:62-66 states the gap in its
//     own words. This is #257's finding (config_form_invocator.go:188-196), unchanged.
//  3. THE WARNING BLOCK, which is this unit's own new finding — see the section above. Even a FRESH
//     8900 binary and an identical frame would still differ by those 657 bytes, because congruency-go
//     has no PHP error handler to emit them.
//
// WHAT WAS RUN INSTEAD is the #282 tag harness's measurement (equivalence_test.go), which is the gate
// #323 settled on for tag units: compare THE TAG'S OWN BYTES, cut out of the live PHP page with
// TagList's own two anchors — the :62 heading and the :76 "</div>\n" close, against a tail measured
// from the Unknown-tag probe. Its go-test form is
//
//	cd congruency-go && go test ./tags/ -run 'TestTagEquivalence/PriceMakerControl' -v -count=1
//
// ...which could NOT be run here (no toolchain). So the PHP HALF of that harness was reproduced in
// python3 — the ticket's sanctioned tool, and the fetcher for every number in this file — cutting the
// slice with the same anchors, and the GO half was reproduced as a line-for-line python
// transliteration of the functions below (same names, same order, same control flow). That measures
// the DECISION PROCEDURE this file encodes; it does not measure the Go binary, and it is not offered
// as if it did. What a compiler would have caught was checked by hand instead: delimiters balance;
// the one import (strconv) is used, by pmcPHPNumericValue; every other identifier this file
// references — Register, Engine, TagArguments, Tag, esc, isPHPSpace — is declared in package tags;
// GetDocument is PriceMakerControlTag's only method and its `string` return is exactly what Tag
// requires (engine.go:852-854); none of its top-level names (all pmc*/PriceMakerControl*) collides
// with any other file in the package; and Register("PriceMakerControl") appears exactly once in the
// package, so init() cannot panic on a duplicate.
//
// THE RESULT — 50 inputs, the tag's own bytes, live PHP vs this port's logic:
//
//	50 inputs, 50 byte-identical to the live PHP, 0 MISMATCH
//	22 of the 50 exercise the KEY path — 153 real bytes each, not the empty state
//
// The 50 include every boundary the validator has: "5", "0", "007", " 5", "5 ", "  7  ", "\t5\n",
// "+5", "+0", "-0", "5.0", "5.", "5e0", "0.0", "000.000", "1.0000000000000001", "0009",
// "9223372036854775807", "9223372036854775808" and "99999999999999999999999999" all VALIDATE (153B);
// "-5", "5.5", ".5", "1e1", "5e1", "1.5e1", "15e-1", "0x1A", "5abc", "abc5", "abc", "1_0", "12 34",
// "1e", ".", "+", "-", "٣", "﹢5", "" and the absent key all do NOT (0B).
//
// WHY THE 0-BYTE GATE IS NOT VACUOUS — the concern #325 raises by name. On the gate URL alone this
// tag emits nothing, so `return ""` would pass it and so would leaving the unit unimplemented (a
// missing port makes IsPorted false, which the harness reports as SKIP rather than as a pass — but a
// SKIP is not a measurement either). That is why the sweep above exists and why it is this unit's
// real gate: 22 of its inputs put 153 bytes on the page through THIS unit's validator, and a stub
// that returned "" would fail 22 of 50. The empty state is measured; it is just not measured ALONE.
//
// STABILITY. The gate render was fetched twice around the work and was byte-identical both times
// (the #282 stability sandwich, equivalence_test.go:98-105, which exists because the live db has
// concurrent pair-loop writers). This tag reads no db, so its render is inert by construction; the
// sandwich confirms it rather than assuming it.
//
// SIDE EFFECTS: none. This file opens no db, writes no file and runs no command; the measurements
// behind it were HTTP GETs against a server that was already running, plus one `immutable=1` read of
// the state db to confirm the Document_Templates count (0 of 27) — the sidecar-free open
// ticket_status.py:49-60 established.

import "strconv"

// init self-registers the tag. This is the whole wiring step (#281; engine.go:1293-1307).
func init() {
	Register("PriceMakerControl", func(e *Engine, a *TagArguments) Tag {
		return newPriceMakerControlTag(e, a)
	})
}

// pmcPriceDAOParseErrorClass / pmcPriceDAOParseErrorMessage are get_class($e) and $e->getMessage()
// for the ParseError that `new PriceDAO()` raises on every keyed render — see "THE SECOND DEFECT".
//
// Both were READ OFF THE LIVE PHP's own render, not recalled: a parser's diagnostic wording is a
// fact about the deployed interpreter, not something to reconstruct from memory. getMessage() does
// not carry the file or the line (TagList prints class + message only), which is why neither appears
// here. The message is a raw string literal because it contains the two `"` characters that the
// PHP's own diagnostic contains — they are load-bearing; see pmcStandaloneCatch.
const (
	pmcPriceDAOParseErrorClass   = "ParseError"
	pmcPriceDAOParseErrorMessage = `syntax error, unexpected token "*", expecting end of file`
)

// PriceMakerControlTag is PriceMakerControl (PriceMakerControl.php:8-19).
type PriceMakerControlTag struct {
	// e is the ambient environment every tag in this package is constructed with (engine.go:1328).
	// The PHP class has no equivalent field — PriceMaker reads its world through the $_GET
	// superglobal, which is what this carries (engine.go:871).
	e *Engine
}

// newPriceMakerControlTag is PriceMakerControl::__construct (PriceMakerControl.php:11-13), which is
// EMPTY: it takes $arguments and stores nothing.
//
// So args is accepted and dropped here, exactly as the PHP accepts and drops it. This is NOT the
// unguarded `->top()` shape of Config_Form_Invocator (config_form_invocator.go:128-131): that
// constructor dereferences its argument and throws on the gallery's NULL, and this one cannot,
// because it never touches it. A nil *TagArguments — the PHP's NULL, which is what the gallery
// passes at TagList.php:67 — is therefore not a special case here. It is the ONLY case that occurs,
// and it is indistinguishable from any other.
func newPriceMakerControlTag(e *Engine, args *TagArguments) *PriceMakerControlTag {
	_ = args // PriceMakerControl.php:11-13 — the constructor body is empty. See above.
	return &PriceMakerControlTag{e: e}
}

// GetDocument is PriceMakerControl::get_document() (PriceMakerControl.php:15-18):
//
//	$priceMaker = new PriceMaker();
//	return ($priceMaker->control());
//
// The (string) cast that turns control()'s NULL into "" is TagList's, at TagList.php:68 — not this
// method's. It is folded into control's `string` return type below, because a Go method cannot
// return NULL and every caller in this package casts identically (see "WHY GetDocument RETURNS
// TagList's CATCH ARM").
func (t *PriceMakerControlTag) GetDocument() string {
	return newPmcPriceMaker(t.e).control()
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PriceMaker / AbstractMaker — lib/Modules/StoreModule/Admin/{PriceMaker,AbstractMaker}.php
//
// These are lib classes, not tags, and they are modelled HERE rather than in engine.go because #325
// may add only this file — and because this tag is their only reachable caller in the app: nothing
// else constructs a PriceMaker. They are pmc*-prefixed and unexported so they cannot collide with,
// or be leaned on by, another unit's file.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// pmcPriceMaker is PriceMaker (PriceMaker.php:8-32) flattened together with the AbstractMaker base
// it extends (AbstractMaker.php:8-67). PHP splits them across an abstract class and three template
// methods (insertResultKeys/useValidator/initFormArray); Go has no abstract classes, and modelling
// the hierarchy with an interface would add a dispatch seam with exactly one implementation that
// changes no byte. The methods below keep the PHP's names and each is annotated with the file it
// comes from, so the split stays legible.
//
// insertResultKeys (PriceMaker.php:17-20) is NOT modelled: runForm is its only caller
// (AbstractMaker.php:53) and runForm is never reached — see "THE SECOND DEFECT".
type pmcPriceMaker struct {
	e *Engine

	// key is AbstractMaker::$key (AbstractMaker.php:9) and keySet is `isset($this->key)`.
	//
	// isset() — not `!== ''` — is the test control() makes (AbstractMaker.php:31), and the two are
	// NOT the same test. They happen to coincide here, because the validator can only return NULL or
	// a NON-EMPTY digit run (it returns $result[0], a [0-9]+ match). keySet is modelled explicitly
	// anyway: the PHP's test is isset(), and a port that quietly substitutes a different test is a
	// port that diverges the day the validator changes.
	key    string
	keySet bool

	// keyVariable / formName / selectionLink are PriceMaker::__construct's three assignments
	// (PriceMaker.php:11-13). formName is stored but never read on any reachable path — it is the
	// $_POST key initializeForm() tests (AbstractMaker.php:39), and there is no $_POST here (see
	// control). It is kept so this port holds every field the PHP object holds at the instant it
	// throws.
	keyVariable   string
	formName      string
	selectionLink string
}

// newPmcPriceMaker is PriceMaker::__construct (PriceMaker.php:10-15):
//
//	$this->keyVariable = "priceMaker";                                  // :11
//	$this->formName = "PRICEMAKER";                                     // :12
//	$this->selectionLink = "<a href='?page=priceChange'>View all prices.</a>";   // :13
//	$this->init();                                                      // :14
//
// The ORDER is the PHP's: the three fields are assigned first, then init() runs and reads
// keyVariable back out of the object.
//
// There is no field for AbstractMaker::$formMan (AbstractMaker.php:10). init() would fill it from
// `PersistentObjectManager::getData("FORM_MANAGER")` (AbstractMaker.php:23), but ONLY on the keyed
// path — and on that path `new PriceDAO()` throws before anything reads it (see "THE SECOND
// DEFECT"), so no reachable byte depends on its value. engine.go does expose the FORM_MANAGER seam
// it would need (Config.FormManager, engine.go:322-324); modelling a fetch whose result is provably
// dead would be ceremony, and is recorded here instead.
func newPmcPriceMaker(e *Engine) *pmcPriceMaker {
	m := &pmcPriceMaker{
		e:             e,
		keyVariable:   "priceMaker",
		formName:      "PRICEMAKER",
		selectionLink: "<a href='?page=priceChange'>View all prices.</a>",
	}
	m.init()
	return m
}

// init is AbstractMaker::init (AbstractMaker.php:20-27):
//
//	$this->setKey($_GET[$this->keyVariable]);
//	if(isset($this->key)){ $this->formMan = PersistentObjectManager::getData("FORM_MANAGER"); }
//	else{ $this->key = NULL; }
//
// WHY getStr AND NOT getIsset. When the URL has no priceMaker, `$_GET['priceMaker']` is an undefined
// index: PHP warns (warning 1 of the three quoted in the header) and evaluates to NULL, so setKey
// receives NULL rather than "". This passes "" instead — and the two are INDISTINGUISHABLE
// downstream, which is why the simpler read is the correct one:
//
//   - preg_match's $subject is typed string, so it coerces NULL to "" (PHP's own (string)NULL); both
//     values therefore search the same empty subject and match nothing.
//   - the comparison that follows is `$itemKey == $result[0]` with $result[0] itself NULL — and
//     `NULL == NULL` and `"" == NULL` are BOTH true, so both return $result[0], which IS NULL.
//
// Both land on "no key". pmcValidateNumericKey's (string, bool) shape encodes exactly that collapse;
// its comment carries the full case analysis. Measured: an absent priceMaker and priceMaker= both
// render 0 bytes (they differ only in the warning block, which is not this tag's return value — see
// the header).
//
// getStr is engine.go:911-917 and already takes PHP's last-wins rule for a repeated scalar key
// (?priceMaker=abc&priceMaker=1 makes $_GET['priceMaker'] the string "1"). Measured against the live
// PHP, both orderings.
//
// KNOWN, MEASURED, AND NOT FIXABLE FROM THIS FILE: PHP's query parser builds $_GET['priceMaker'] as
// an ARRAY for `?priceMaker[]=5`, and preg_match then throws
// "TypeError: preg_match(): Argument #2 ($subject) must be of type string, array given" — 157 bytes
// of catch arm. engine.go models $_GET as a url.Values of strings (engine.go:871), where that key is
// literally "priceMaker[]" and this read finds nothing, so the Go renders 0 bytes. It cannot be
// repaired here, and that is provable rather than merely awkward: the PHP rule is ORDER-DEPENDENT
// across distinct keys — `?priceMaker[]=1&priceMaker=abc` renders 0 bytes and
// `?priceMaker=abc&priceMaker[]=1` renders the 157-byte TypeError, both measured — while a
// url.Values MAP holds identical contents for the two and has already lost the query order. So no
// tag file can tell them apart; only engine.go's $_GET model can, and this ticket may not touch it.
// It is an engine-wide gap (every tag that reads $_GET shares it), not a defect of this unit, and it
// is out of reach of the gate URL, which carries no priceMaker at all.
//
// The `else { $this->key = NULL; }` arm (AbstractMaker.php:25) is a no-op: setKey already assigned
// the validator's NULL to $this->key. It is not modelled, because there is nothing to model.
func (m *pmcPriceMaker) init() {
	m.setKey(m.e.getStr(m.keyVariable)) // AbstractMaker.php:21
	// AbstractMaker.php:22-26 — the FORM_MANAGER fetch and the redundant NULL store; see the
	// constructor comment for why neither is modelled.
}

// setKey is AbstractMaker::setKey (AbstractMaker.php:58-62): `$this->key = $this->useValidator($p)`.
// The PHP also returns $this->key; no caller uses that return, so this does not.
func (m *pmcPriceMaker) setKey(prospect string) {
	m.key, m.keySet = m.useValidator(prospect)
}

// useValidator is PriceMaker::useValidator (PriceMaker.php:22-24) — the template method that names
// which validator this Maker uses: `return ValidateFields::validateNumericKey($prospect);`.
func (m *pmcPriceMaker) useValidator(prospect string) (string, bool) {
	return pmcValidateNumericKey(prospect)
}

// control is AbstractMaker::control (AbstractMaker.php:29-36) — the tag's whole behaviour.
//
//	$makerString = NULL;
//	if(isset($this->key)){
//	    return $this->initializeForm() . $this->runForm();      // :32
//	}else{
//	    $makerString = "<br />Invalid $this->keyVariable supplied. $this->selectionLink";   // :34
//	}                                                           // :36 — and NO return. See below.
//
// THE KEYED ARM (:32) always throws, and this returns the bytes TagList prints when it catches. PHP
// evaluates the concatenation's LEFT operand first, so initializeForm() (AbstractMaker.php:38-49)
// runs first; its `!isset($_POST[$this->formName])` test (:39) is always TRUE here, because the Go
// engine carries no $_POST at all (engine.go:869-882 — $_GET only), which is also the branch every
// GET render of this URL takes; and the line inside it, `$formArray = $this->initFormArray()` (:40),
// reaches `new PriceDAO()` and does not come back. So AbstractMaker.php:41-47 (the two "Item $key
// was/was NOT found" strings and the setResults calls) and runForm() (:51-56) are NEVER REACHED and
// are NOT PORTED — that is not an omission; reproducing them would mean forging bytes the live app
// has never emitted here. See "THE SECOND DEFECT" and "WHY GetDocument RETURNS TagList's CATCH ARM".
//
// (For the record, since it is the one branch a $_POST would open: POSTing PRICEMAKER=1 to this URL
// with a valid key makes initializeForm() return NULL and runForm() render FormManager's
// FORM_LOAD_FAILURE sentinel, "<!--FAILED TO LOAD FORM-->" (FormManager.php:21,34) — 26 bytes,
// measured. It is unreachable from this package by construction, so it is recorded, not ported.)
//
// THE ELSE ARM (:34) is the first defect: the notice is built and dropped, control() falls off its
// end, and PHP returns NULL — which TagList casts to "" (TagList.php:68). This returns "" for the
// same reason, and builds-and-drops the notice for the same reason the PHP does: to be the same
// function. See "THE FIRST DEFECT".
func (m *pmcPriceMaker) control() string {
	if m.keySet { // AbstractMaker.php:31 — isset($this->key)
		return pmcStandaloneCatch(pmcPriceDAOParseErrorClass, pmcPriceDAOParseErrorMessage)
	}
	// AbstractMaker.php:34. The assignment is real and the value is dead — in both languages.
	_ = m.invalidKeyNotice()
	return "" // AbstractMaker.php:36 — control() ends; (string)NULL === "".
}

// invalidKeyNotice is the string AbstractMaker.php:34 builds and never returns:
//
//	"<br />Invalid $this->keyVariable supplied. $this->selectionLink"
//
// PHP interpolates both properties out of $this inside the double-quoted string, so this reads them
// off the struct rather than inlining their values — the PHP would follow a changed property here,
// and so does this. NOTHING EVER RENDERS IT (see "THE FIRST DEFECT"); it exists so this port has a
// line for the PHP's line, and so that whoever repairs AbstractMaker upstream can see at a glance
// what these bytes were meant to be.
func (m *pmcPriceMaker) invalidKeyNotice() string {
	return "<br />Invalid " + m.keyVariable + " supplied. " + m.selectionLink
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// ValidateFields::validateNumericKey — lib/IOControl/Validators/ValidateFields.php:29-37.
//
// The only real logic in this unit: it alone decides which of the tag's two outputs you get.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// pmcValidateNumericKey is ValidateFields::validateNumericKey($itemKey) (ValidateFields.php:29-37):
//
//	$result = array();
//	preg_match("/[0-9]+/",$itemKey,$result);   // :31
//	if($itemKey == $result[0]){                // :32
//	    return $result[0];                     // :33
//	}else{
//	    return NULL;                           // :35
//	}
//
// ok=false is the PHP's NULL return, which control() tests with isset() — and isset(NULL) is FALSE.
//
// THE UNMATCHED CASE, and why it collapses. When the subject holds no digit, $result stays an EMPTY
// ARRAY, so `$result[0]` at :32 is an undefined index: PHP warns (warnings 2 and 3 in the header —
// :32 always, :33 only when the comparison came out true) and evaluates it to NULL. The comparison
// is then `$itemKey == NULL`, and BOTH sub-cases end at "no key":
//
//   - $itemKey is "" or NULL (no priceMaker in the URL): `"" == NULL` and `NULL == NULL` are both
//     TRUE, so :33 returns $result[0] — which IS NULL. isset(NULL) is false. (This is the branch
//     that fires warning 3: :33 reads the undefined index a second time.)
//   - $itemKey is a non-empty non-numeric string ("abc"): PHP 8 compares it against "", which is
//     FALSE, so :35 returns NULL. (No warning 3 — :33 never runs. Measured: priceMaker=abc emits
//     ONE warning, priceMaker= emits two.)
//
// Both are ok=false, which is why the no-digit case needs no further distinction here — and why
// init() can read $_GET with getStr, losing the NULL/"" difference without losing a byte.
//
// THE MATCHED CASE returns $result[0] — THE DIGIT RUN — and never $itemKey. Nothing in this unit
// reads the returned key (the ParseError fires first), but the distinction is ported anyway because
// it is the function's contract: returning the match is what keeps this same validator
// injection-proof at its other call sites, and a port that returned $itemKey would be a trap laid
// for whoever reuses it.
func pmcValidateNumericKey(itemKey string) (string, bool) {
	digits, found := pmcFirstDigitRun(itemKey) // :31 — preg_match("/[0-9]+/", ...)
	if !found {
		return "", false // :32/:33/:35 — all three no-digit paths collapse to NULL. See above.
	}
	if !pmcLooseEqNumeric(itemKey, digits) { // :32
		return "", false // :35
	}
	return digits, true // :33
}

// pmcFirstDigitRun is `preg_match("/[0-9]+/", $subject, $result)` reduced to what :32-:33 read out of
// it: $result[0], the leftmost-longest run of ASCII digits, and whether there was one.
//
// A BYTE scan — not a rune scan, and not a regexp. PCRE without the /u modifier matches BYTES, and
// [0-9] is ASCII-only, so "٣" (U+0663 ARABIC-INDIC DIGIT THREE) does NOT match even though it is a
// digit to Go's unicode.IsDigit. Measured against the live PHP: "٣" renders 0 bytes.
func pmcFirstDigitRun(s string) (string, bool) {
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

// pmcLooseEqNumeric is PHP 8's `$itemKey == $digits` (ValidateFields.php:32) — where BOTH operands
// are strings and $digits is a NON-EMPTY [0-9]+ run. It is not a general `==`; see the scope note.
//
// PHP 8's string-vs-string `==` rule: if BOTH operands are NUMERIC STRINGS, compare them
// NUMERICALLY; otherwise compare them as strings. (This is the PHP 8 rule specifically — PHP 7 would
// have cast the non-numeric side to a number instead, making "5abc" == "5" TRUE.) Since $digits is
// always numeric, the test reduces to "is $itemKey numeric, and does it equal $digits as a number?":
//
//	"5"      vs "5"    -> numeric, 5 == 5      -> true
//	"007"    vs "007"  -> numeric, 7 == 7      -> true
//	" 5"     vs "5"    -> numeric, 5 == 5      -> true   (PHP 8 allows leading AND trailing space)
//	"+5"     vs "5"    -> numeric, 5 == 5      -> true
//	"5.0"    vs "5"    -> numeric, 5.0 == 5    -> true
//	"5e0"    vs "5"    -> numeric, 5.0 == 5    -> true
//	"-0"     vs "0"    -> numeric, -0 == 0     -> true
//	"-5"     vs "5"    -> numeric, -5 != 5     -> false
//	"5.5"    vs "5"    -> numeric, 5.5 != 5    -> false
//	"1e1"    vs "1"    -> numeric, 10 != 1     -> false
//	"0x1A"   vs "0"    -> NOT numeric, "0x1A" != "0" as strings   -> false
//	"5abc"   vs "5"    -> NOT numeric, "5abc" != "5" as strings   -> false
//	"12 34"  vs "12"   -> NOT numeric (interior space), != as strings -> false
//
// Every line above is MEASURED against the live PHP, not reasoned (see "THE GATE").
//
// SCOPE, AND WHY FLOAT-ONLY IS EXACT HERE. PHP compares two INTEGER-valued numeric strings as
// zend_longs and everything else as doubles; this compares everything as doubles. That is exact at
// THIS call site — the only one — and the argument is short: $digits is always $itemKey's OWN first
// digit run, so on the both-integers path $itemKey is `WS* [+-]? <those same digits> WS*`, and the
// two values are therefore equal in magnitude BY CONSTRUCTION. Long-vs-long and double-vs-double can
// only disagree for integers too large to compare exactly as doubles, and two integers built from
// the SAME digit string are never such a pair. Measured at the boundary: "9223372036854775807",
// "9223372036854775808" and "99999999999999999999999999" behave identically in both languages — PHP
// itself falls back to doubles above zend_long, which is what this does. categoryview.go:349-377
// reaches the same float-only conclusion for the same PHP function, independently.
func pmcLooseEqNumeric(itemKey, digits string) bool {
	a, aNum := pmcPHPNumericValue(itemKey)
	if !aNum {
		return itemKey == digits // not-both-numeric -> a plain string comparison
	}
	b, bNum := pmcPHPNumericValue(digits)
	if !bNum {
		return itemKey == digits // unreachable: a [0-9]+ run is always a numeric string
	}
	return a == b
}

// pmcPHPNumericValue reports whether s is a PHP 8 NUMERIC STRING and, if so, its value.
//
// PHP 8's grammar (Zend/zend_operators.c, _is_numeric_string_ex; the trailing-whitespace clause is
// new in PHP 8.0, and this build has it — " 5" and "5 " both validate, measured):
//
//	WS* [+-]? ( DIGITS ("." DIGITS?)? | "." DIGITS ) ( [eE] [+-]? DIGITS )? WS*
//
// where WS is " \t\n\r\v\f" — PHP's numeric-string whitespace set, which isPHPSpace already models
// byte for byte (engine.go:624-626), so it is reused rather than restated.
//
// The pattern must consume the WHOLE string, which is what makes "5abc", "1_0", "0x1A", "12 34" and
// "1e" non-numeric. An exponent marker with no digits after it is not part of the match, so "1e"
// leaves an unconsumed "e" and is correctly rejected rather than parsed as 1.
func pmcPHPNumericValue(s string) (float64, bool) {
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
	if i < n && s[i] == '.' { // ("." DIGITS?)?  /  "." DIGITS
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
	if i != n { // anything left over means the string is not numeric
		return 0, false
	}
	f, err := strconv.ParseFloat(s[start:end], 64)
	if err != nil {
		return 0, false
	}
	return f, true
}

// pmcStandaloneCatch is TagList.php:69-72 — the arm that catches what this tag's get_document()
// throws:
//
//	} catch (\Throwable $e) {
//	    $out .= "<p style='color:#b00020'>This tag needs context to render standalone: "
//	          . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</p>";
//	}
//
// esc() is TagList::esc (TagList.php:20), which is this package's esc (engine.go:599) — the same
// htmlspecialchars($s, ENT_QUOTES). It is NOT decorative here: the ParseError's message carries two
// `"` characters, and ENT_QUOTES turns each into `&quot;`. Those two escapes are 153 - 143 = 10 of
// the bytes the live page serves, so a port that dropped the escape would fail the diff outright.
// Note the `'` in the style attribute is NOT escaped: esc() is applied to the class and message
// only, exactly as at TagList.php:70-71 — the surrounding markup is the PHP's own literal.
//
// The class and message are passed in and joined the way the PHP joins them, rather than pasted in
// as one opaque literal, so a reader can check this against both sources line by line.
//
// There is no trailing newline: the PHP appends none here, and TagList adds its own "</div>\n"
// afterwards (TagList.php:76). Whitespace counts — this is the last byte of the unit.
func pmcStandaloneCatch(class, message string) string {
	return "<p style='color:#b00020'>This tag needs context to render standalone: " +
		esc(class+": "+message) + "</p>"
}
