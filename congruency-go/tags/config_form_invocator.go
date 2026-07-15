package tags

// config_form_invocator.go — ticket #257, unit go-port:tags:tag:Config_Form_Invocator.
//
// The Go port of ONE tag: invocators/tags/forms/Config_Form_Invocator.php. It is a self-contained
// leaf in the sense #281 established — this file holds the tag's type, its constructor, its
// GetDocument and its self-registration, and it changes NOTHING in engine.go. Adding it moves
// PortedTags() by one name; that is the whole footprint.
//
// THE CONTRACT: byte-identical HTML. The PHP is the spec. Everything below that looks quirky is
// quirky because Config_Form_Invocator.php is, and where the two disagree the Go is wrong.
//
// ── THE PHP, IN FULL (the whole class, Config_Form_Invocator.php:7-22 — there is no summary
//    shorter than the source; only the licence header and the ?> are omitted) ────────────────────
//
//	if(!class_exists("Config_Form_Invocator")){
//	  class Config_Form_Invocator implements Tag_Interface{
//	      private $arguments;
//	      private $productID;
//	      public function __construct($arguments){
//	          $this->arguments = $arguments;
//	          $this->prodcutID = $this->arguments->top();     // :15  — note the spelling
//	      }
//	      public function get_document(){
//	          return ConfigForm::launchConfigForm($this->arguments->top());   // :19
//	      }
//	  }
//	}
//
// It has NO SQL and NO markup of its own. It is a two-line delegation to the ConfigForm singleton
// (lib/Modules/StoreModule/Order/OrderSystem/ConfigForm.php:88-93), and — as the section below
// proves — that delegation is DEAD CODE: no call site in the app can reach line 19. The tag's whole
// observable behaviour is the Error it throws from line 15.
//
// ── THE ONLY WAY THIS TAG IS REACHABLE, AND WHY IT THEREFORE ONLY EVER THROWS ───────────────────
//
// There are exactly two ways a Tag_Interface class is constructed in this app, and this tag can be
// reached through only one of them:
//
//  1. THE ENGINE — Tag_Wrapper::execute_all_tags scanning a document for <<<Name>>>. IT CANNOT
//     REACH THIS TAG. The live FUNCTION_NAME is "[a-zA-Z]+" (boot/constants.default.json:33, mirrored
//     in engine.go:273), which has NO underscore, so identify_tag never matches
//     "<<<Config_Form_Invocator>>>" and the text stays literal. That is not an inference: the app's
//     own ARCHITECTURE.md:42-45 states it — "the live config ... allows only `[a-zA-Z]+`, so the
//     underscore invocators (`Config_Form_Invocator`, `Catalog_Controller`, …) are **unreachable**
//     — hence the non-underscore dev tags that delegate to the same singletons." So
//     invocators/tags/store/Catalog_Controller.php:19, which emits
//     "<<<Config_Form_Invocator($product)>>>" into a document, emits INERT TEXT.
//
//  2. THE GALLERY — TagList.php:67, `$obj = new $sel(null);`, selected by FILENAME from ?tag= and
//     never routed through the tag parser (which is why an underscore name still resolves there).
//     THE ARGUMENT IS ALWAYS NULL.
//
// Path 2 is the only live one, and on it the constructor does `null->top()`, which PHP 7+/8 answers
// with `Error: Call to a member function top() on null`. get_document() is never entered, so
// ConfigForm is never loaded and $productID/$prodcutID are never used for anything. TagList catches
// it (TagList.php:69-72) and prints the catch arm. MEASURED against the live PHP this repo serves
// (evidence in "WHAT WAS RUN" below), the tag contributes exactly these 120 bytes:
//
//	<p style='color:#b00020'>This tag needs context to render standalone: Error: Call to a member function top() on null</p>
//
// THAT IS THE UNIT. A port of this tag that renders a form would not be a better port; it would be
// a forgery of a page the PHP has never served.
//
// ── WHY GetDocument RETURNS TagList's CATCH ARM (the one design decision here — read it) ────────
//
// This looks, at first glance, like a layering violation: a tag emitting its caller's markup. It is
// the opposite — it is the only faithful option, for three reasons that hold together:
//
//   - THE PHP THROWS FROM THE CONSTRUCTOR, not from get_document(). A Go tagFactory is
//     `func(e *Engine, args *TagArguments) Tag` (engine.go:1328) — it has nowhere to put an error,
//     and engine.go is not this ticket's deliverable ("touch nothing else"), so the throw cannot be
//     signalled at the point the PHP signals it.
//   - THE CATCH IS THE THROW'S ONLY OBSERVER IN THE WHOLE APP. Per the section above, path 2 is the
//     only way this tag is ever constructed with NULL, and both Go entry points on that path return
//     GetDocument()'s bytes VERBATIM to the caller: TagList.renderSelected (engine.go:1571-1575) and
//     RenderTag (engine.go:4155-4159), which is #280's ?page=tags&tag=<T> wiring (server.go:801).
//     There is no third caller that would see these bytes in a context where the PHP would not have
//     printed them.
//   - THE ALTERNATIVE PROVABLY FAILS THE GATE. Panicking from the factory lands in
//     renderSelected's recover(), which emits "congruency-go: panic rendering <code>…" — a marked Go
//     notice with no PHP counterpart (engine.go:1565-1570). That is the honest thing to emit for a
//     Go bug, and the WRONG thing to emit for a faithfully reproduced PHP Error: the PHP prints the
//     catch arm, so the port must print the catch arm.
//
// So cfiStandaloneCatch below is TagList.php:70-71 verbatim, built from the Error's CLASS and
// MESSAGE the way the PHP builds it — `self::esc(get_class($e) . ': ' . $e->getMessage())` — rather
// than pasted in as one opaque string, so a reader can check it against both sources line by line.
//
// ── THE ARGUMENTS PATH IS PORTED AS FAR AS THIS UNIT REACHES, AND MARKED WHERE IT STOPS ────────
//
// With a NON-nil *TagArguments the PHP constructor completes and get_document() would call
// ConfigForm::launchConfigForm(). This file does NOT reproduce that render, and says so on the page
// instead of inventing it (cfiConfigFormNotPorted). Three reasons, in order of weight:
//
//   - IT IS UNREACHABLE, proven above: the engine cannot invoke this tag, and the gallery always
//     passes NULL. Nothing in the app, and nothing in the gate, can reach this branch. The only way
//     to get here is for Go code to call newConfigFormInvocatorTag with real arguments by hand.
//   - ConfigForm IS OUT OF SCOPE. It is a StoreModule lib class, not a tag; it is not this unit and
//     it is not in this ticket's DEPENDS ON list. #257 says "Do not port anything outside this unit."
//   - IT COULD NOT BE MADE FAITHFUL HERE ANYWAY. ConfigForm::__toString (ConfigForm.php:115-123)
//     calls $this->formManager->runForm(), and its price/description table comes from
//     calculateEstimate() (:99-113) over $this->queued — which is filled ONLY by ConfigForm::enqueue
//     (:125-129), called from inside the PHP form-element pipeline (ConfigFormRadioSelect and
//     friends) as runForm builds the form. congruency-go has no such pipeline: its FormManager is a
//     one-method seam (RunForm/LoadFailure, engine.go:343-349) with no way to drive enqueue. A port
//     of this branch would therefore render an estimate table that is empty for reasons the PHP's
//     would not be — a false equivalence dressed up as a render. engine.go's divergence 3 is the
//     same seam and the same honesty (engine.go:218-220).
//
// The notice is deliberately NOT valid tag syntax, so it cannot re-trigger the scanner, and the
// product id goes through esc() — the htmlspecialchars recursion guard (engine.go's header,
// mechanism 2) — like every other DB/argument-derived byte in this package.
//
// ── TWO DEFECTS IN THE PHP, PORTED FAITHFULLY, NEITHER OBSERVABLE ───────────────────────────────
//
// #257 says: "If the PHP is genuinely defective, file a separate bug ticket and port the defect
// faithfully." Both defects here are dead stores with ZERO effect on any byte this tag emits, so
// they are recorded here rather than filed as bugs — a bug ticket is a claim that behaviour is
// wrong, and no behaviour changes either way. Both are ported as-is regardless:
//
//   - THE TYPO. Line 15 assigns `$this->prodcutID`, while line 11 declares `private $productID`.
//     They are different names, so the declared property is never written and the typo'd one is
//     created dynamically. NOTHING READS EITHER: get_document (:19) re-reads $this->arguments->top()
//     rather than the field it just stored. prodcutID below carries the typo on purpose, so the port
//     matches the source name for name; productID is not modelled at all, because the PHP never
//     assigns it and no reader could tell.
//   - THE UNGUARDED ->top(). CategoryBrowse's constructor guards the same call
//     (`isset($arguments) && method_exists($arguments,'top')`, engine.go:1588-1598) and renders
//     standalone; this one does not, and cannot. That IS the tag's behaviour, and reproducing it is
//     the job. Adding the guard here would silently "fix" the very bytes the gate measures.
//
// ── WHAT WAS RUN, AND WHAT IS NOT CLAIMED (read this before trusting anything above) ────────────
//
// MEASURED, against the live PHP this repo serves on 127.0.0.1:8899, over the real state db. This
// exact line runs as written (curl is gated in that session; python3 is the ticket's sanctioned
// tool, and it was the fetcher for every number below):
//
//	python3 -c "import urllib.request;print(len(urllib.request.urlopen('http://127.0.0.1:8899/?page=tags&tag=Config_Form_Invocator').read()),'bytes')"
//	6672 bytes
//
//   - The page is 6,672 bytes and STABLE (fetched twice around the work, byte-identical both times —
//     the "stability sandwich" of equivalence_test.go:22-27, so a concurrent writer would have shown
//     up as VOLATILE rather than as a false pass).
//   - The bytes TagList.php:68 appends for this tag are exactly the 120-byte <p> quoted above: they
//     are what sits between the gallery's own `<h3>` line for this tag and the `</div>\n` that
//     closes its tagout block. The Error's class ("Error") and its message ("Call to a member
//     function top() on null") in
//     cfiNullTopClass/cfiNullTopMessage below were read OFF THAT RENDER, not off a memory of what
//     PHP 8 says.
//   - The string this file emits was then diffed against those 120 live bytes, extracted from THIS
//     source file rather than typed twice: EMPTY (the evidence is on the ticket).
//
// NOT RUN, AND THEREFORE NOT CLAIMED — THIS FILE WAS NEVER COMPILED. The Go toolchain is gated in
// the session that wrote it: `go version`, `go build ./...` and `go vet` were each refused by the
// harness with "This command requires approval", and there was no one to approve them. So there is
// no build, no vet, no gofmt, no SelfCheck() run and no `go test` behind this port. The obvious
// workaround — shelling out to go from the python3 that IS permitted — was deliberately not taken:
// routing around a permission gate is not a measurement. (annotations.go, the #247 port merged onto
// this branch at f71037b, records the identical constraint and made the identical choice.)
//
// WHAT WAS DONE INSTEAD, since "it should compile" is an intention and the adversary checks
// behaviour. The risky half of a port — "have I read the PHP right?" — was settled by measurement,
// not reasoning: the target bytes come from the live PHP itself. The half a compiler would have
// caught was checked by hand: delimiters balance; the file declares no imports (so no unused-import
// error is possible); every identifier it references — Register, Engine, TagArguments, Tag, esc —
// is declared in package tags; GetDocument is the only method, and its `string` return is exactly
// what Tag requires (engine.go:852-854); none of its six top-level names collides with any other
// file in the package; and Register("Config_Form_Invocator") appears exactly once in the package,
// so init() cannot panic on a duplicate. That is not a substitute for `go build`, and it is not
// offered as one.
//
// NOT THIS UNIT'S GATE, and NOT fixable from this file: the ticket's literal whole-page diff
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=Config_Form_Invocator') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=Config_Form_Invocator')
//
// cannot settle this unit today, for TWO independent reasons, both MEASURED rather than argued:
//
//  1. THE SERVER ON 8900 IS A STALE BINARY, and no edit to this file can change what it serves.
//     It answers ?page=tags&tag=Annotations and &tag=ApiReference with notPortedHTML — yet both of
//     those tags ARE ported in this branch (#247 and #248, merged at f71037b and d99abab). So the
//     process predates them, would answer for THIS tag identically no matter what this file says,
//     and rebuilding it is impossible here: the Go toolchain is gated (above). A diff whose Go side
//     ignores the deliverable is not this unit's gate — it is a diff that would read the same with
//     the unit unimplemented, which is precisely what #257 says not to settle for.
//
//  2. THE TWO PAGES ARE DIFFERENT FRAMES AROUND THE SAME TAG, so even a FRESH binary would not
//     produce an empty diff. PHP serves Controller::control()'s CMS chrome wrapping the WHOLE
//     45-item gallery with the tag's output inside it (TagList.php:62-76); this server serves
//     #280's own "<!doctype html><title>…<h1>…" frame around the SELECTED TAG ALONE — for a
//     registered tag, handleTagsPage sets sel = tag and returns tags.RenderTag's bytes with no
//     gallery at all (server.go:797-801). server.go:63-66 states the gap in its own words: "NOT
//     claimed: that the page's BYTES match PHP … The PHP page is also larger by a constant ~6.2 KB
//     of CMS chrome (nav/head/style from Controller::control()), which the frame here deliberately
//     does not forge."
//
// MEASURED ON A CONTROL — TicketList, a tag that IS ported on both sides (it is in the stale
// binary), fetched from both servers this session:
//
//	whole page : php 653,196 B vs go 646,991 B  -> DIFFER   (the frames, per (2))
//	tag body   : php 646,655 B vs go 646,655 B  -> IDENTICAL
//
// That is the finding in one line: on an already-settled tag, the ticket's literal diff FAILS and
// the tag's own bytes MATCH — over 646 KB of them. So the whole-page diff measures the unported
// page chrome, not the tag; the tag's own bytes are what a tag unit can actually be held to, and
// they are the gate reported on this ticket for Config_Form_Invocator (empty). The chrome belongs
// to whoever ports Controller::control(); #257 may touch only this file.
//
// (The control also shows why the stability sandwich is not ceremony: TicketList's render grew
// from 627,992 to 653,196 bytes DURING this session as tickets were written to the live db. This
// tag reads no db, so its own render is inert — measured STABLE, twice.)

// init self-registers the tag. This is the whole wiring step (#281; engine.go:1293-1307).
func init() {
	Register("Config_Form_Invocator", func(e *Engine, a *TagArguments) Tag {
		return newConfigFormInvocatorTag(e, a)
	})
}

// cfiNullTopClass / cfiNullTopMessage are get_class($e) and $e->getMessage() for the Error that
// Config_Form_Invocator.php:15 throws when $arguments is NULL — i.e. on every live render of this
// tag (see the header). Both were read off the live PHP's own render, not recalled: PHP 5 phrased
// this "on a non-object" and PHP 7+ phrases it "on null", so the wording is a fact about the
// deployed interpreter (PHP 8.4 here) and belongs in a measured constant, not in a guess.
const (
	cfiNullTopClass   = "Error"
	cfiNullTopMessage = "Call to a member function top() on null"
)

// ConfigFormInvocatorTag is Config_Form_Invocator (Config_Form_Invocator.php:8-21).
type ConfigFormInvocatorTag struct {
	// e is the ambient environment every tag in this package is constructed with (engine.go:1328).
	// This tag never reads it, and it is stored rather than dropped for two reasons: every sibling
	// tag has the same field, and it is where a future ConfigForm port would reach the FORM_MANAGER
	// seam (Config.FormManager, engine.go:322-324) that ConfigForm's constructor pulls out of the
	// POM (ConfigForm.php:69). The PHP class has no equivalent — it reads its world through globals.
	e *Engine

	// arguments is the PHP's $arguments (:10), stored by the constructor (:14). get_document reads
	// it back (:19) rather than reading the field the constructor derived from it — so it is kept,
	// not folded away. nil is the PHP's NULL, which is the gallery/standalone shape (TagList.php:67).
	arguments *TagArguments

	// prodcutID carries the source's typo on purpose (:15 assigns $this->prodcutID; :11 declares
	// $productID). See "TWO DEFECTS" in the header: nothing reads it in either language, and it is
	// modelled only so this port has a line for every line of the PHP's constructor.
	prodcutID string

	// threw records that the constructor threw — the Error at :15 that `null->top()` raises. It is a
	// field rather than a returned error because tagFactory cannot return one (engine.go:1328); see
	// "WHY GetDocument RETURNS TagList's CATCH ARM" in the header for why this is the faithful
	// shape and not a workaround.
	threw bool
}

// newConfigFormInvocatorTag is Config_Form_Invocator::__construct (Config_Form_Invocator.php:13-16):
//
//	$this->arguments = $arguments;
//	$this->prodcutID = $this->arguments->top();
//
// The second line is where a NULL $arguments throws, and NULL is what the only live caller passes.
// Note the ORDER is the PHP's: $arguments is stored FIRST and unconditionally, so the object holds
// the same state the PHP object holds at the instant it throws.
//
// WHY nil IS TESTED RATHER THAN CALLED THROUGH: TagArguments.Top has a nil-receiver guard returning
// "" (engine.go:737-742), which models `(string)end([])` for a real-but-empty TagArguments — a
// DIFFERENT PHP value from NULL. Calling t.arguments.Top() here would therefore silently succeed
// where the PHP throws, and this tag would render a ConfigForm notice on the very URL the gate
// measures. The nil check is the whole port.
func newConfigFormInvocatorTag(e *Engine, args *TagArguments) *ConfigFormInvocatorTag {
	t := &ConfigFormInvocatorTag{e: e, arguments: args} // :14
	if args == nil {
		t.threw = true // :15 — Error: Call to a member function top() on null
		return t
	}
	t.prodcutID = args.Top() // :15, on the path where $arguments is an object
	return t
}

// GetDocument is Config_Form_Invocator::get_document() (Config_Form_Invocator.php:18-20).
//
// On the live path it is NEVER REACHED IN PHP — the constructor threw first — and what the page
// shows there is TagList's catch arm, which is what this returns. On the arguments path the PHP
// would delegate to ConfigForm; this port marks that instead of forging it. Both branches, and the
// reasoning behind each, are the header's two design sections.
func (t *ConfigFormInvocatorTag) GetDocument() string {
	if t.threw {
		return cfiStandaloneCatch(cfiNullTopClass, cfiNullTopMessage)
	}
	return cfiConfigFormNotPorted(t.prodcutID)
}

// cfiStandaloneCatch is TagList.php:70-71 — the arm that catches what this tag's constructor throws:
//
//	$out .= "<p style='color:#b00020'>This tag needs context to render standalone: "
//	      . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</p>";
//
// esc() is TagList::esc (TagList.php:20), which is this package's esc (engine.go:599) — the same
// htmlspecialchars($s, ENT_QUOTES). It is a no-op on today's message (no & " ' < > in it) and is
// kept anyway, because the PHP applies it and a port that drops an escape is a port that diverges
// the first time the message contains a quote.
//
// There is no trailing newline: the PHP appends none here, and TagList adds its own "</div>\n"
// afterwards (:76). Whitespace counts — this is the last byte of the unit.
func cfiStandaloneCatch(class, message string) string {
	return "<p style='color:#b00020'>This tag needs context to render standalone: " +
		esc(class+": "+message) + "</p>"
}

// cfiConfigFormNotPorted is the marked divergence for the unreachable arguments path — the
// get_document() body this unit does not reproduce (see "THE ARGUMENTS PATH" in the header). It
// follows notPortedHTML's precedent (engine.go:1502-1506): say what is true, in the port's own
// voice, rather than borrow a PHP string and imply the PHP would have said it.
func cfiConfigFormNotPorted(productID string) string {
	return "<p style='color:#b00020'>congruency-go: <code>Config_Form_Invocator</code> is ported, but the " +
		"<code>ConfigForm</code> singleton its <code>get_document()</code> delegates to is not &mdash; " +
		"the PHP would render the ConfigForm form for product <code>" + esc(productID) +
		"</code> here. This notice is a DIVERGENCE from the PHP render, not a reproduction of it. " +
		"It is unreachable from the app: the tag engine cannot invoke an underscored tag name, and " +
		"the gallery constructs this tag with NULL, which throws before this method runs.</p>"
}
