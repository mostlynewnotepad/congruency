package tags

// testtaga.go — ticket #338, unit go-port:tags:tag:TestTagA.
//
// The Go port of ONE tag: invocators/tags/test_tags/TestTagA.php. Per #281 a tag port is
// ADD-A-FILE-ONLY: this file holds the tag's type, its constructor, its GetDocument, its helpers and
// its self-registration (the init() below), and it changes NOTHING in engine.go — the registry picks
// the tag up because Go runs every init() in a package before any other code in it (engine.go:1355
// Register, engine.go:1393 newTag). Every identifier it defines is testTagA*-prefixed or
// TestTagA*-named, so it cannot collide with the sibling tag ports.
//
// THE CONTRACT: byte-identical HTML. The PHP is the SPEC. Where the two disagree THIS file is wrong.
//
// ── THE WHOLE TAG (TestTagA.php:7-36) ───────────────────────────────────────────────────────────
//
//	class TestTagA implements Tag_Interface{
//	    private $arguments; private $document; private $calls;
//	    public function __construct($arguments){
//	        $this->arguments = $arguments;                  // :14  (stored, never read again)
//	        $this->calls = $arguments->top();               // :15
//	    }
//	    public function get_document(){
//	        $this->process_tag();                           // :19
//	        return $this->document;                         // :20
//	    }
//	    private function process_tag(){
//	        return
//	        $this->document = "<br><hr>TestTagA Has been Called with value $this->calls "
//	                          . $this->call_to_self();      // :24-25
//	    }
//	    private function call_to_self(){
//	        if($this->calls > 0){                           // :29
//	            return " <<<TestTagA(" . --$this->calls . ")>>> ";   // :30
//	        }else{
//	            return "The base case.";                    // :32
//	        }
//	    }
//	}
//
// It is a self-recursive demo tag: its output embeds its OWN invocation with the counter one lower,
// and the ENGINE — not this file — expands that. It touches no database, no DAO and no constant, so
// it has no dependency to degrade against; its only inputs are its argument and PHP's own operator
// semantics. That is the whole reason the two paths below are the entire port.
//
// ── THE GALLERY RENDER IS AN ERROR PATH, AND THAT IS THIS UNIT'S GATE ───────────────────────────
//
// The gate URL is ?page=tags&tag=TestTagA. TagList renders the selected tag by constructing it with
// NULL — `$obj = new $sel(null);` (TagList.php:67). TestTagA.php:15 then calls `$arguments->top()`
// on that NULL. On PHP 8 that is a fatal Error:
//
//	Error: Call to a member function top() on null
//
// TestTagA has NO try/catch of its own, so the Error propagates out of the constructor into
// TagList's, which wraps `new $sel(null)` AND `$obj->get_document()` in ONE try (TagList.php:66-72):
//
//	try {
//	    $obj = new $sel(null);                        // :67  <- TestTagA throws HERE
//	    $out .= (string)$obj->get_document();         // :68  <- never runs
//	} catch (\Throwable $e) {                         // :69
//	    $out .= "<p style='color:#b00020'>This tag needs context to render standalone: "
//	          . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</p>";   // :70-71
//	}
//
// So the tag's bytes inside the .tagout div are EXACTLY that one <p> — no more, no less, and no
// trailing newline (:71 emits none). This is not inferred: it was MEASURED off the live PHP server
// on 127.0.0.1:8899 this session, cutting the slice with the SAME two anchors equivalence_test.go
// uses (TagList.php:62's heading and :76's close, with the page tail measured via the Unknown-tag
// probe at :77-78, 17B). The slice is 120B — see testTagAStandaloneHTML.
//
// CONSEQUENCE THAT IS EASY TO GET WRONG: NOTHING in process_tag(), call_to_self() or the counter
// arithmetic below is reached on the gate path — line 15 throws first, so :19-33 never run. A port
// that "helpfully" rendered the base-case string here ("<br><hr>TestTagA Has been Called with value
// The base case.") would diverge on every byte of the diff.
//
// ── WHY THE THROW IS RE-SEATED IN GetDocument, AND WHY THAT IS BYTE-EXACT ───────────────────────
//
// A Go factory (`func(e *Engine, args *TagArguments) Tag`, engine.go:1355) CANNOT throw and CANNOT
// return an error — so a constructor-thrown PHP Error has no direct Go counterpart at the
// constructor. It is therefore represented as a value at construction (ctorThrew) and surfaced at
// the only point this file controls: GetDocument. This mirrors contenttag.go, whose PHP constructor
// throws on the identical `$arguments->top()`-on-NULL line.
//
// Moving the throw from the `new` to the `get_document()` call changes NO observable byte, because
// TagList's ONE try covers BOTH statements (:67 and :68) and both land in the SAME catch producing
// the SAME <p>. That is the entire justification, and it holds for every caller that passes nil:
//
//   - TagList's gallery — renderSelected does `lookupTag(sel, nil)` then `obj.GetDocument()`
//     (engine.go:1571-1575), and has no PHP-shaped catch of its own. GetDocument returning the catch
//     <p> is what puts the PHP's bytes in the PHP's place.
//   - RenderTag — `lookupTag(name, nil)` (engine.go:4155), documented to return "the TAG's own
//     bytes", i.e. the slice equivalence_test.go cuts out of the live PHP page. For TestTagA that
//     slice IS the catch <p>, so the same return is correct there too.
//
// Those two are the whole list, and the factory must CONSTRUCT rather than blow up for both of them
// — which is exactly what deferring the throw achieves.
//
// NOT a third caller, despite appearances: SelfCheck's nil-args construction loop
// (`newTag(NewEngine(Config{}), n, nil)`, engine.go:4377) iterates a HARDCODED list of #226's ten
// tags (engine.go:4371-4372), not the registry, so it does NOT exercise this factory and registering
// here does not add a case to it. (contenttag.go:86-87 lists SelfCheck among the callers that pass
// nil, and :177-178 states the loop "constructs every registered tag". It does not — it walks the
// hardcoded ten, and ContentTag is no more in that list than TestTagA is. Verified this session; the
// claim is not carried forward. The factory below still must not panic on nil — the reason is the
// two REAL callers above, which is enough.)
//
// nil args is EXCLUSIVELY the standalone path. The template path cannot reach it: getTagWrapper
// passes `w.parser.GetTagArguments()` (engine.go:950), and TagParser.initialize always assigns
// `ArgumentFactory(p.tag)` (engine.go:784), which always returns a non-nil *TagArguments
// (engine.go:699-703). So `args == nil` <=> "PHP was handed NULL" <=> "the constructor throws".
//
// ── WHY THERE IS NO catchThrowable HERE (a deliberate difference from the sibling ports) ────────
//
// Some ported tags open GetDocument with `defer catchThrowable(&out, "<Tag>")` because THEIR PHP
// class has its own `catch (\Throwable $e)` arm emitting a cy-form-error div. TestTagA.php has NO
// try and NO catch — its whole body is two assignments, a concatenation and an if/else. Adding
// catchThrowable would invent a "<div class='cy-form-error'>TestTagA error: …</div>" branch the PHP
// can never emit, which is a divergence dressed as robustness. It is omitted on purpose.
//
// ── THE NON-GALLERY PATH: <<<TestTagA(n)>>> ─────────────────────────────────────────────────────
//
// Reachable only from document content, and per this ticket NO Document_Templates row mentions this
// tag today — so this path renders nowhere in production, and the #282 harness (which measures the
// ARGUMENT-LESS gallery render only) does not exercise it. It is ported anyway, faithfully.
//
// HONEST PROVENANCE, because this file's claims must not outrun what it checked: the gate slice
// above is MEASURED. Everything in this section is DERIVED from the PHP source plus PHP's
// documented operator semantics, and could NOT be measured this session — no php binary is
// reachable from this worktree (tooling/congruencey-harness/php/ does not exist here, and the
// checkout's copy is outside the sandbox). Where the derivation is subtle it is spelled out below
// rather than asserted, so a reader with a php binary can check each step directly.
//
// The argument is `$arguments->top()` = TagArguments::top() = end($this->arguments) — the FIRST
// argument the author wrote, because setArguments stores them reversed (engine.go:686-688). So
// <<<TestTagA(3)>>> yields "3". PHP's end([]) on an EMPTY argument list returns FALSE where Go's
// Top() returns "" (engine.go:735-742); the two agree in outcome on BOTH uses this tag makes of the
// value, so the difference is not observable here:
//
//   - interpolation: (string)false === "" and (string)"" === "" — the same zero bytes.
//   - the `> 0` test: `false > 0` compares as bool (0 casts to false, false > false is false), and
//     `"" > 0` compares as string (see testTagAGreaterThanZero) giving strcmp("", "0") < 0 — also
//     false. Both take the base-case arm, so the decrement is never reached with either value.
//
// The self-recursion is the ENGINE's work, not this file's: ExecuteAllTags renders this tag, scans
// its output with identify_tag, finds the emitted <<<TestTagA(n)>>>, builds a CHILD wrapper for it
// and recurses depth-first, replacing the invocation with the child's render (engine.go:1022-1039).
// Two consequences worth knowing while reading call_to_self below, both of which this port inherits
// for free because it reproduces the string and nothing else:
//
//   - a NUMERIC argument terminates: each level emits n-1, and n reaches 0, whose base case emits no
//     invocation.
//   - a NON-NUMERIC argument does NOT terminate on its own: `--` is a no-op on it (see
//     testTagADecrement), so every level re-emits the SAME invocation. Both engines then stop at the
//     same place — the BUG-06 depth cap, `if ($depth >= 64)` (Tag_Wrapper.php:65, ported at
//     engine.go:276-277, 1024-1026) — leaving the depth-64 invocation literal.
//
// This tag does NO escaping: TestTagA.php interpolates $this->calls raw (:25) and concatenates the
// decremented value raw (:30). That is faithfully reproduced — an esc() this file added would be a
// divergence, not a hardening. It is also harmless, because FUNCTION_ARGUMENT is /\([A-Za-z0-9]*\)/
// (boot/constants.default.json:35, ported at engine.go:286), so an argument is ALPHANUMERIC ONLY
// and cannot carry a quote, an angle bracket or an ampersand.
//
// (contenttag.go:309 cites this same constant as "Constants_patched.php:171". That file does not
// exist in checkouts/current/congruency — the checkout boot/router.php actually serves — and the
// constant is read from boot/constants.default.json:35 there, which is what engine.go:285-286 cites
// too. Verified this session; the stale citation is not carried forward here.)

import "strconv"

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there —
// and registering is what flips IsPorted("TestTagA") to true, which is what makes
// equivalence_test.go MEASURE this tag instead of skipping it.
func init() {
	Register("TestTagA", func(_ *Engine, a *TagArguments) Tag { return newTestTagATag(a) })
}

// TestTagATag is TestTagA (TestTagA.php:8-35).
//
// The PHP's three properties are $arguments, $document and $calls. Only $calls is carried:
//
//   - $arguments is assigned at :14 and NEVER read again — porting it would be a field no code
//     reads. (contenttag.go drops its identical dead $arguments for the same reason.)
//   - $document is a scratch slot: process_tag() writes it (:25) and get_document() immediately
//     reads it back (:20). Nothing else ever touches it, and no caller can observe it between those
//     two statements, so the pair collapses into GetDocument's return value.
//
// The *Engine is not carried either: this tag reads no config, no $_GET and no database, so a stored
// engine would be a second field no code reads. The factory above still takes one — that signature
// is the registry's (engine.go:1355) — and discards it.
type TestTagATag struct {
	// ctorThrew records that the PHP constructor throws before it assigns anything usable —
	// `$arguments->top()` on NULL (TestTagA.php:15). True exactly when args == nil, which is
	// exactly the standalone/gallery path.
	ctorThrew bool

	// calls is $this->calls (TestTagA.php:15) — the raw, unvalidated argument.
	//
	// It is MUTABLE and mutated in place, because the PHP's is: `--$this->calls` (:30) writes the
	// property, so a second get_document() on the SAME instance counts down again. Using a local
	// would silently make this port idempotent where the PHP is not. Nothing in the engine calls
	// GetDocument twice per wrapper today (ExecuteAllTags calls it once, engine.go:1023, and each
	// emitted <<<TestTagA(n)>>> gets a FRESH wrapper and a fresh instance), so this is fidelity to
	// an unobserved behavior rather than a live requirement — which is exactly when a port is most
	// tempted to drift.
	calls string
}

// newTestTagATag is TestTagA::__construct (TestTagA.php:13-16). It must never panic on nil args:
// both callers that pass nil — renderSelected (engine.go:1571) and RenderTag (engine.go:4155) —
// construct first and call GetDocument after, so a panic here would surface as a marked panic notice
// instead of the PHP's catch <p>. See the file header.
func newTestTagATag(args *TagArguments) *TestTagATag {
	t := &TestTagATag{}
	if args == nil {
		// `$arguments->top()` on NULL -> Error. Nothing after :15 runs.
		t.ctorThrew = true
		return t
	}
	t.calls = args.Top()
	return t
}

// testTagANullArgError is get_class($e).': '.$e->getMessage() for the Error TestTagA.php:15 throws
// when $arguments is NULL — the same line, and so the same message, contenttag.go records for
// ContentTag.php:15. Confirmed against the live PHP server this session: it is what the gate URL
// actually returns (see testTagAStandaloneHTML).
const testTagANullArgError = "Error: Call to a member function top() on null"

// testTagAStandaloneHTML is TagList.php:70-71's catch body, verbatim:
//
//	"<p style='color:#b00020'>This tag needs context to render standalone: "
//	  . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</p>"
//
// MEASURED, not derived: fetching http://127.0.0.1:8899/?page=tags&tag=TestTagA from the live PHP
// server this session and cutting the slice between TagList.php:62's heading anchor and its :76
// close — the same cut equivalence_test.go makes — yields EXACTLY these 120 bytes:
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
func testTagAStandaloneHTML() string {
	return "<p style='color:#b00020'>This tag needs context to render standalone: " +
		esc(testTagANullArgError) + "</p>"
}

// GetDocument is TestTagA::get_document() (TestTagA.php:18-21):
//
//	$this->process_tag();
//	return $this->document;
//
// It deliberately has NO `defer catchThrowable(...)` — TestTagA.php has no catch arm to model.
// See the file header.
func (t *TestTagATag) GetDocument() string {
	// TestTagA.php:15 — the constructor threw; TagList's catch supplies the bytes. This is the
	// gate path, and it is the ONLY path the #282 harness measures.
	if t.ctorThrew {
		return testTagAStandaloneHTML()
	}
	return t.testTagAProcessTag()
}

// testTagAProcessTag is TestTagA::process_tag() (TestTagA.php:23-26) fused with get_document()'s
// `return $this->document` (:20) — see the type's comment on why $document is not a field.
//
//	$this->document = "<br><hr>TestTagA Has been Called with value $this->calls " . $this->call_to_self();
//
// THE STATEMENT ORDER IS LOAD-BEARING AND IS THE ONE THING A ONE-LINER WOULD BREAK. PHP's `.`
// evaluates its LEFT operand first, so the interpolated "$this->calls" is rendered BEFORE
// call_to_self() runs — and call_to_self() DECREMENTS $this->calls (:30). The heading therefore
// shows the value as it arrived and the nested invocation shows one less: <<<TestTagA(3)>>> renders
//
//	<br><hr>TestTagA Has been Called with value 3  <<<TestTagA(2)>>>
//
// (with the literal's trailing space and call_to_self's leading space meeting as the double space
// after "3", and one trailing space after ">>>").
//
// Writing this as the single Go expression
//
//	return "…value " + t.calls + " " + t.testTagACallToSelf()
//
// would be a real bug, not a style choice: the Go spec fixes the left-to-right order of FUNCTION
// CALLS but leaves the order of other operands — here the `t.calls` field read — unspecified
// relative to them, so the heading could legally print the DECREMENTED value. Reading the field
// into `head` first makes the PHP's order explicit and non-negotiable.
func (t *TestTagATag) testTagAProcessTag() string {
	head := "<br><hr>TestTagA Has been Called with value " + t.calls + " "
	return head + t.testTagACallToSelf()
}

// testTagACallToSelf is TestTagA::call_to_self() (TestTagA.php:28-34):
//
//	if($this->calls > 0){ return " <<<TestTagA(" . --$this->calls . ")>>> "; }
//	else                { return "The base case."; }
//
// `--$this->calls` is a PRE-decrement: it writes the property and yields the NEW value, so the
// emitted invocation carries calls-1. Both spaces in the returned literal are the PHP's own — one
// before " <<<" and one after ">>> " — and "The base case." carries neither.
func (t *TestTagATag) testTagACallToSelf() string {
	if testTagAGreaterThanZero(t.calls) {
		t.calls = testTagADecrement(t.calls) // --$this->calls, property write included
		return " <<<TestTagA(" + t.calls + ")>>> "
	}
	return "The base case."
}

// testTagAGreaterThanZero is PHP 8's `$this->calls > 0` (TestTagA.php:29) for a STRING left operand.
//
// PHP 8 changed this comparison (RFC: saner string to number comparisons), and the PHP 7 rule would
// give different bytes here, so the version matters:
//
//   - if the string IS numeric, the two are compared NUMERICALLY;
//   - if it is NOT, the int is cast to string and the two are compared AS STRINGS (PHP 7 would have
//     cast the string to int instead, making "abc" > 0 false where PHP 8 makes it true).
//
// Go's `>` on strings is byte-wise lexicographic, which is strcmp's rule, so `calls > "0"` is the
// second arm exactly. (The string-vs-string arm needs no numeric special-case of its own: PHP only
// compares two strings numerically when BOTH are numeric, and this arm runs only when `calls` is
// not.)
//
// DERIVED, not measured (see the header's provenance note). Worked through for every shape the
// ALPHANUMERIC argument charset admits — these are all of them:
//
//	"3"     numeric   -> 3 > 0            -> true  -> recurse
//	"0"     numeric   -> 0 > 0            -> false -> base case
//	"00"    numeric   -> 0 > 0            -> false -> base case
//	"05"    numeric   -> 5 > 0            -> true  -> recurse
//	"1e2"   numeric   -> 100.0 > 0        -> true  -> recurse   (exponent form IS alphanumeric)
//	"0e0"   numeric   -> 0.0 > 0          -> false -> base case
//	""      string    -> strcmp("","0")<0 -> false -> base case  (the empty/false argument list)
//	"abc"   string    -> strcmp("abc","0")>0 -> true  -> recurse
//	"0abc"  string    -> strcmp("0abc","0")>0 -> true  -> recurse (equal prefix, longer wins)
//
// The last two are the counter-intuitive ones and they are why this is a function rather than an
// inline `calls != "0"`: EVERY non-empty non-numeric alphanumeric string is > 0 under PHP 8, because
// every byte in [A-Za-z0-9] is >= '0' (48), so such a string either leads with a byte above '0' or
// leads with '0' and is longer than "0". Only "" falls the other way.
func testTagAGreaterThanZero(calls string) bool {
	if testTagAIsNumeric(calls) {
		f, ok := testTagAToFloat(calls)
		if ok {
			return f > 0
		}
	}
	// PHP 8: the int is cast to "0" and a string comparison is performed.
	return calls > "0"
}

// testTagADecrement is PHP's `--$s` (TestTagA.php:30) for a STRING operand, returning the bytes the
// concatenation at :30 then sees.
//
// PHP manual, Incrementing/Decrementing Operators: "The increment/decrement operators only affect
// numbers and strings", and of the Perl-style character convention: character variables "can be
// incremented but not decremented". So:
//
//   - NUMERIC string -> converted to int or float, then decremented. The result is a NUMBER, and
//     :30 concatenates it, so PHP's (string) cast on that number decides the bytes.
//   - NON-NUMERIC string -> NO EFFECT; the string is returned unchanged. (This is what makes a
//     non-numeric argument recurse to the depth cap — see the file header.)
//
// int vs float follows PHP's numeric-string rule: integer syntax that fits in an int is an int,
// everything else (exponent form, or an overflowing digit run) is a float. ParseInt-then-ParseFloat
// reproduces that split — ParseInt rejects "1e2" and overflows exactly where PHP does — and
// phpFloatString (engine.go:530-547) is PHP's precision-14 (string) cast for the float arm, so
// "1e2" decrements to float 99.0 and renders "99", not Go's "%v" of 99.
//
// DERIVED, not measured (see the header's provenance note). Reachable shapes:
//
//	"3"    -> int 2      -> "2"
//	"05"   -> int 4      -> "4"        (leading zeros are lost; PHP's (int)"05" is 5)
//	"1e2"  -> float 99   -> "99"
//	"abc"  -> unchanged  -> "abc"
//	"3abc" -> unchanged  -> "3abc"     (not numeric, so the no-op arm — NOT (int)"3abc")
//
// Only shapes with `calls > 0` true reach here, so "0"/"00"/"0e0"/"" never do.
//
// PHP 8.3 may additionally raise a DEPRECATION for the non-numeric arm. That cannot change these
// bytes: a diagnostic is written to PHP's own output stream by the error handler, never into the
// string :30 concatenates, so this tag's return value is the same with or without it.
func testTagADecrement(s string) string {
	if !testTagAIsNumeric(s) {
		return s // "-- has no effect on a non-numeric string"
	}
	core := testTagATrimPHPSpace(s)
	if i, err := strconv.ParseInt(core, 10, 64); err == nil {
		return strconv.FormatInt(i-1, 10) // the int arm: (string)(int) is base-10, no fraction
	}
	f, ok := testTagAToFloat(s)
	if !ok {
		return s // unreachable: testTagAIsNumeric already accepted it
	}
	return phpFloatString(f - 1) // the float arm: PHP's precision-14 (string) cast
}

// testTagAToFloat is PHP's numeric-string -> number conversion, narrowed to the float64 both callers
// need (a `> 0` test and a decrement). It is only ever called on a string testTagAIsNumeric accepted,
// so the parse failing is a bug in this file, not an input case — hence the bool rather than a
// silent 0, which would turn such a bug into a wrong base-case render.
func testTagAToFloat(s string) (float64, bool) {
	f, err := strconv.ParseFloat(testTagATrimPHPSpace(s), 64)
	if err != nil {
		return 0, false
	}
	return f, true
}

// testTagATrimPHPSpace strips the leading/trailing whitespace PHP's numeric-string grammar allows
// (the WS* at both ends — see testTagAIsNumeric), so the surviving core is what Go's parsers accept.
//
// It uses isPHPSpace (engine.go:624-628) — " \t\n\r\v\f", PCRE's \s — NOT strings.TrimSpace, whose
// Unicode space set is wider than PHP's, and NOT phpTrim, whose charlist is trim()'s (it includes
// \0 and excludes \f) rather than the numeric grammar's.
//
// Unreachable in practice: FUNCTION_ARGUMENT is [A-Za-z0-9]*, so no argument can carry whitespace.
// It exists because the grammar it completes is the spec.
func testTagATrimPHPSpace(s string) string {
	i, j := 0, len(s)
	for i < j && isPHPSpace(s[i]) {
		i++
	}
	for j > i && isPHPSpace(s[j-1]) {
		j--
	}
	return s[i:j]
}

// testTagAIsNumeric is PHP 8's is_numeric($value) for a STRING argument — the predicate BOTH of
// PHP's rules above branch on (the `> 0` comparison at :29 and the `--` at :30).
//
// PHP 8's numeric-string grammar (the trailing-whitespace clause is new in PHP 8.0):
//
//	WS* [+-]? ( DIGITS ("." DIGITS?)? | "." DIGITS ) ( [eE] [+-]? DIGITS )? WS*
//
// where WS is " \t\n\r\v\f" — PCRE's \s set, which isPHPSpace already models (engine.go:624-628).
// An exponent marker with no digits after it does NOT match, and since the pattern must consume the
// WHOLE string, "1e" is correctly reported non-numeric rather than parsed as 1. Hex ("0x1A") is not
// numeric in PHP 7+.
//
// It is the FULL grammar even though FUNCTION_ARGUMENT ([A-Za-z0-9]*) can only deliver a subset of
// it — no sign, no ".", no whitespace — for the same reason contenttag.go ports quote()'s whole
// rule: the grammar is the spec, and a port trimmed to today's reachable inputs is a port that
// breaks silently the day the reachable set widens.
//
// This duplicates contentTagIsNumeric (contenttag.go:383-425) rather than calling it. That is
// deliberate: #281's add-a-file-only discipline forbids this unit from editing engine.go to host a
// shared helper, and reaching into a SIBLING tag port's contentTag*-prefixed internals would couple
// two units that are meant to land, and be reverted, independently. If a later ticket lifts a
// phpIsNumeric into engine.go, both copies should collapse into it.
func testTagAIsNumeric(s string) bool {
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
