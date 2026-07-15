package tags

// telemetrybeacon.go — ticket #337, unit go-port:tags:tag:TelemetryBeacon.
//
// The Go port of ONE tag: invocators/tags/dev/TelemetryBeacon.php. Per #281 a tag port is
// ADD-A-FILE-ONLY: this file holds the tag's type, its constructor, its GetDocument and its
// self-registration (the init() below), and it changes NOTHING in engine.go — the registry picks the
// tag up because Go runs every init() in a package before any other code in it (Register,
// engine.go:1355; newTag, engine.go:1393). Every identifier it defines is telemetryBeacon*-prefixed
// or TelemetryBeacon*-named, so it cannot collide with the sibling tag ports.
//
// THE CONTRACT: byte-identical HTML. The PHP is the SPEC. Where the two disagree THIS file is wrong.
//
// ── THE WHOLE TAG (TelemetryBeacon.php:19-57) ───────────────────────────────────────────────────
//
//	if (!class_exists("TelemetryBeacon")) {
//	    class TelemetryBeacon implements Tag_Interface {
//	        public function __construct($arguments = null) {}      // :21  — an EMPTY body
//	        public function get_document() {
//	            return <<<'BEACON'                                 // :23  — a NOWDOC
//	<script>
//	... 30 lines of inline JS ...
//	</script>
//	BEACON;                                                        // :54
//	        }
//	    }
//	}
//
// That is the entire class. There is NOTHING else to port:
//
//   - NO arguments. The constructor's $arguments is DEFAULTED to null, is never assigned to a
//     property, and is never read. There is no TagArguments::top() call to reproduce and no
//     argument form any template could pass that would change one byte of the output.
//   - NO SQL, no DAO, no DataConnection, no PDO, no CONGRUENCY_SQLITE. This tag touches no database,
//     so t.e is never dereferenced by GetDocument below.
//   - NO dependency to degrade against. The ticket asks that a tag which degrades gracefully against
//     a missing dependency degrade IDENTICALLY in Go; this tag HAS no dependency — its own PHP
//     header calls the payload "SELF-CONTAINED inline <script> (no external deps, no server data
//     interpolated)" (TelemetryBeacon.php:10-11). Its output is therefore the same bytes with the db
//     absent, the app root absent, and every other tag unregistered. There is no empty state and no
//     error state, because there is no input and no I/O that could fail.
//   - NO try/catch. See "WHY THERE IS NO catchThrowable HERE" below.
//
// ── WHY THE NOWDOC IS A RAW STRING LITERAL, AND WHY THAT IS EXACT ───────────────────────────────
//
// `<<<'BEACON'` (note the QUOTED delimiter) is a NOWDOC, PHP's single-quoted heredoc: NO variable
// interpolation and NO escape sequences are processed inside it. Its value is the bytes between the
// opening line and the closing `BEACON;` line, VERBATIM, with the final newline before the closing
// delimiter excluded. So get_document() returns TelemetryBeacon.php lines 24-53 joined with "\n",
// starting at "<script>" and ending at "</script>" with NO trailing newline.
//
// Go's raw string literal (backquoted) is the exact analogue: no escape processing, newlines kept as
// written. It is usable here because the payload contains no backquote — checked, along with the
// rest of this comment's byte claims, by the measurement below. A Go interpreted string would have
// to escape every one of the payload's single quotes' neighbours and its newlines by hand, which is
// exactly the transcription error this literal cannot make.
//
// ── MEASURED, NOT DERIVED ───────────────────────────────────────────────────────────────────────
//
// The bytes in telemetryBeaconScript were taken from the LIVE PHP server this session, not typed
// from the source. Fetching http://127.0.0.1:8899/?page=tags&tag=TelemetryBeacon and cutting the
// slice the #282 harness cuts — between TagList.php:62's heading anchor
// ("<div class='tagout'><h3>&lt;&lt;&lt;TelemetryBeacon&gt;&gt;&gt;</h3>\n") and its :76 close
// ("</div>\n") plus the page tail measured off the Unknown-tag probe (TagList.php:77-78; 17 bytes,
// "\n</body>\n</html>\n") — yields EXACTLY 1227 bytes. Those 1227 bytes were then confirmed
// byte-for-byte equal to lines 24-53 of TelemetryBeacon.php joined with "\n", which is what proves
// the NOWDOC reading above rather than assuming it. The payload is pure ASCII: no CR, no tab, no
// byte outside [0x20,0x7E] besides the newlines.
//
// ── THE GALLERY RENDER IS THE HAPPY PATH (unlike ContentTag) ────────────────────────────────────
//
// The gate URL is ?page=tags&tag=TelemetryBeacon, and TagList renders the selected tag by
// constructing it with NULL — `$obj = new $sel(null);` (TagList.php:67) — then calling
// get_document() (:68), both inside ONE try (:66-72).
//
// For this tag NEITHER statement throws: the constructor's parameter is optional AND its body is
// empty, so NULL is simply ignored, and get_document() returns a literal. TagList's catch arm
// (:69-72, the "This tag needs context to render standalone: …" <p>) is therefore UNREACHABLE for
// TelemetryBeacon — this port must NOT emit it. That is the opposite of ContentTag, whose
// constructor dereferences the NULL and whose gallery slice IS that catch <p> (contenttag.go's
// header); the two tags differ because ContentTag.php:15 calls `$arguments->top()` and this one
// calls nothing. Reading across from the sibling port and reproducing its ctorThrew branch here
// would diverge on all 1227 bytes.
//
// So the slice the harness cuts is the script itself, and nil args is not a special case at all:
// GetDocument returns the same string for nil args, for empty args, and for any args a template
// could supply.
//
// ── WHY THERE IS NO catchThrowable HERE (a deliberate difference from the sibling ports) ────────
//
// Some ported tags open GetDocument with `defer catchThrowable(&out, "<Tag>")` because THEIR PHP
// class has its own `catch (\Throwable $e)` arm emitting a cy-form-error div (ApiReference.php:42-44
// is one). TelemetryBeacon.php has NO try and NO catch — its whole body is one return of a literal.
// Adding catchThrowable would invent a
// "<div class='cy-form-error'>TelemetryBeacon error: …</div>" branch the PHP can never emit, which
// is a divergence dressed as robustness. It is omitted on purpose, the same call contenttag.go makes
// for the same reason. Nothing in GetDocument can panic regardless: it dereferences no pointer,
// indexes nothing, and does no I/O.
//
// ── THE NON-GALLERY PATH: <<<TelemetryBeacon>>> ─────────────────────────────────────────────────
//
// No Document_Templates row mentions this tag today, so the engine substitutes it nowhere in
// production and this ticket's page list is empty. Its PHP header describes an INTENT for that to
// change — "Emitted ONCE per served page (spliced by <<<Style>>>, which every page template embeds
// in its <head>)" (TelemetryBeacon.php:8-9) — but that splice lives in Style, not here, and Style is
// its own unit. Nothing about it changes this file: the tag returns the identical literal from every
// call site, argument-bearing or not, so the substitution path is already ported by the same return.

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags()/IsPorted() are registry-derived (engine.go:1406-1421), so registering here is what
// flips IsPorted("TelemetryBeacon") to true and makes the #282 harness MEASURE this tag instead of
// skipping it — with no edit to equivalence_test.go. Register is the registry's only writer and it
// PANICS on a duplicate name, so this is the file's one and only registration.
func init() {
	Register("TelemetryBeacon", func(e *Engine, a *TagArguments) Tag {
		return &TelemetryBeaconTag{e: e, args: a}
	})
}

// TelemetryBeaconTag is TelemetryBeacon (TelemetryBeacon.php:20-56).
//
// The PHP class has NO properties: its constructor discards $arguments (:21). e and args are carried
// only to match the package's factory shape (`func(e *Engine, args *TagArguments) Tag`,
// engine.go:1355) and the sibling ports' struct shape; NEITHER is read by GetDocument, and a nil
// args — what TagList.php:67's `new $sel(null)` passes, and what the ?page=tags&tag=TelemetryBeacon
// gate takes — is stored and ignored exactly as the PHP ignores the NULL it is handed. SelfCheck
// constructs every registered tag with nil args (engine.go:4377), which this trivially survives.
type TelemetryBeaconTag struct {
	e    *Engine
	args *TagArguments
}

// telemetryBeaconScript is the NOWDOC of TelemetryBeacon.php:23-54 — its 1227 bytes verbatim, from
// the "<script>" of :24 to the "</script>" of :53, with NO trailing newline (the NOWDOC excludes the
// newline before its closing delimiter). See MEASURED, NOT DERIVED in the file header.
//
// Do not reformat, re-indent, or "tidy" the JS inside: every byte is compared. It is a Go raw string
// literal for the same reason it is a NOWDOC in PHP — neither language processes an escape inside
// one, so what is written here is what is emitted.
const telemetryBeaconScript = `<script>
(function(){
  var EP='/?route=telemetry.record';
  function beacon(p){
    try{
      var b=JSON.stringify(p);
      if(navigator&&typeof navigator.sendBeacon==='function'){navigator.sendBeacon(EP,b);}
      else{fetch(EP,{method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:b});}
    }catch(err){}
  }
  function route(){return location.search||location.pathname;}
  document.addEventListener('DOMContentLoaded',function(){beacon({kind:'pageview',route:route()});});
  window.addEventListener('error',function(e){
    beacon({kind:'error',message:(e&&e.message)?String(e.message):'error',route:route(),detail:((e&&e.filename)||'')+':'+((e&&e.lineno)||0)+':'+((e&&e.colno)||0)});
  });
  window.addEventListener('unhandledrejection',function(e){
    beacon({kind:'error',message:'unhandledrejection: '+String(e&&e.reason),route:route(),detail:''});
  });
  var last=0;
  document.addEventListener('click',function(e){
    var now=(new Date()).getTime();
    if(now-last<500){return;}
    last=now;
    var el=e.target||{};
    var tag=(el.tagName||'').toLowerCase();
    var id=el.id?('#'+el.id):'';
    beacon({kind:'event',route:route(),detail:'click:'+tag+id});
  },true);
})();
</script>`

// GetDocument is TelemetryBeacon::get_document() (TelemetryBeacon.php:22-55): `return <<<'BEACON' …
// BEACON;` and nothing else. One statement in PHP, one statement here.
//
// It takes no arguments, reads no state and performs no I/O, so it returns the identical bytes on
// every call and on every path — the gallery's `new $sel(null)` (TagList.php:67-68), RenderTag
// (engine.go:4155), renderSelected (engine.go:1571-1575) and a template's <<<TelemetryBeacon>>>
// substitution alike. It deliberately has NO `defer catchThrowable(...)`: TelemetryBeacon.php has no
// catch arm to model. See the file header.
func (t *TelemetryBeaconTag) GetDocument() string {
	return telemetryBeaconScript
}
