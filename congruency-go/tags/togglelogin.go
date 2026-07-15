package tags

// togglelogin.go — ticket #344, unit go-port:tags:tag:ToggleLogin.
//
// The Go port of ONE tag: invocators/tags/login/ToggleLogin.php — the login/logout link pair that
// flips on whether a session is authenticated. Per #281 a tag port is ADD-A-FILE-ONLY: this file
// holds the tag's type, its constructor, its GetDocument, its helpers and its self-registration (the
// init() below), and it changes NOTHING in engine.go — the registry picks the tag up because Go runs
// every init() in a package before any other code in it (Register, engine.go:1355; newTag,
// engine.go:1393). Every identifier defined here is ToggleLogin*/toggleLogin*-named, so it cannot
// collide with the sibling tag ports.
//
// THE CONTRACT: byte-identical HTML. The PHP is the SPEC. Where the two disagree THIS file is wrong.
//
// engine.go's "NOT PORTED" prose list still names ToggleLogin (engine.go:198). That list is #226's
// snapshot, it is prose and not a check, and engine.go is not this ticket's deliverable to edit.
// PortedTags() is the authority (engine.go:1406-1415), and this file's init() puts ToggleLogin in it.
// Several already-ported tags are stale in that same list for the same reason.
//
// ── THE WHOLE TAG (ToggleLogin.php:8-28, inside the file's `if(!class_exists(...))` guard) ──────
//
//	class ToggleLogin implements Tag_Interface{
//	    private $style; private $login_prompt; private $logout_prompt;
//	    public function __construct($arguments){
//	        $this->login_prompt=$arguments->pop();          // :15
//	        $this->logout_prompt = $arguments->pop();       // :16
//	        $this->style = $arguments->pop();               // :17
//	    }
//	    public function get_document(){
//	        $return_value= "<a $this->style href='?page=login'>$this->login_prompt</a>";           // :21
//	        if(UserPrivilegeSet::logged_in()){                                                     // :22
//	            $return_value= "<a $this->style href='?page=welcome'>ACCOUNT</a> | <a $this->style href='?page=logout'>$this->logout_prompt</a>";  // :23
//	        }
//	        return $return_value;                                                                  // :25
//	    }
//	}
//
// It opens no database, runs no SQL, reads no $_GET and no $_POST, and includes no file. Its only
// inputs are its three arguments and one boolean. There is no try/catch anywhere in the file.
//
// Note WHERE the work happens: all three argument reads are in the CONSTRUCTOR (:15-17), and that
// placement is the single most load-bearing fact about this tag — the constructor is what throws on
// the gate path. See THE GALLERY RENDER below.
//
// ── THE GALLERY RENDER IS AN ERROR PATH, AND THAT IS THIS UNIT'S GATE ───────────────────────────
//
// The gate URL is ?page=tags&tag=ToggleLogin. TagList renders the selected tag by constructing it
// with NULL — `$obj = new $sel(null);` (TagList.php:67). ToggleLogin.php:15 then calls
// `$arguments->pop()` on that NULL. On PHP 8 that is a fatal Error:
//
//	Error: Call to a member function pop() on null
//
// ToggleLogin has NO try/catch of its own, so the Error propagates out of the constructor into
// TagList's, which wraps `new $sel(null)` AND `$obj->get_document()` in ONE try (TagList.php:66-72):
//
//	try {
//	    $obj = new $sel(null);                        // :67  <- ToggleLogin throws HERE
//	    $out .= (string)$obj->get_document();         // :68  <- never runs
//	} catch (\Throwable $e) {                         // :69
//	    $out .= "<p style='color:#b00020'>This tag needs context to render standalone: "
//	          . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</p>";   // :70-71
//	}
//
// So the tag's bytes inside the .tagout div are EXACTLY that one <p> — no more, no less, and no
// trailing newline (:71 emits none). This is MEASURED, not inferred: see toggleLoginStandaloneHTML.
//
// This is ContentTag's situation exactly (contenttag.go:41-67, whose PHP throws the same Error one
// method name over — `top()` instead of `pop()`), and this file follows that proven shape.
//
// CONSEQUENCE THAT IS EASY TO GET WRONG: get_document() is NEVER REACHED on the gate path. The
// gallery render never asks UserPrivilegeSet anything and never emits an <a> at all — line 15 throws
// first. A port that "helpfully" rendered the logged-out link here, or returned "", would diverge on
// every byte of the gate.
//
// ── WHY THE THROW IS RE-SEATED IN GetDocument, AND WHY THAT IS BYTE-EXACT ───────────────────────
//
// A Go factory (`func(e *Engine, args *TagArguments) Tag`, engine.go:1355) CANNOT throw and CANNOT
// return an error — so a constructor-thrown PHP Error has no direct Go counterpart at the
// constructor. It is therefore represented as a value at construction (ctorThrew) and surfaced at the
// only point this file controls: GetDocument.
//
// Moving the throw from the `new` to the `get_document()` call changes NO observable byte, because
// TagList's ONE try covers BOTH statements (:67 and :68) and both land in the SAME catch producing
// the SAME <p>. That is the entire justification, and it holds for every caller that passes nil:
//
//   - TagList's gallery — renderSelected does `lookupTag(sel, nil)` then `obj.GetDocument()`
//     (engine.go:1564-1576), and has no PHP-shaped catch of its own. GetDocument returning the catch
//     <p> is what puts the PHP's bytes in the PHP's place.
//   - RenderTag — `lookupTag(name, nil)` (engine.go:4155), the entry server.go's handleTagsPage calls
//     and the entry this unit's gate measures. It returns "the TAG's own bytes", i.e. the slice
//     equivalence_test.go cuts out of the live PHP page between TagList.php:62 and :76. For
//     ToggleLogin that slice IS the catch <p>, so the same return is correct there too.
//   - SelfCheck — its registry invariants construct a tag with nil args and require a usable Tag
//     back rather than a blow-up (engine.go:4375-4379), which is exactly what deferring the throw
//     achieves. That loop names the ten tags #226 ported and does NOT reach this one — #281 made
//     those invariants subset-and-floor rather than equality precisely so a new <Tag>.go keeps them
//     green with no edit to engine.go (engine.go:4363-4371) — but the requirement it encodes is the
//     package's, and this file meets it.
//
// nil args is EXCLUSIVELY the standalone path. The template path cannot reach it: getTagWrapper
// passes `w.parser.GetTagArguments()` (engine.go:950), and TagParser.initialize always assigns
// `ArgumentFactory(p.tag)` (engine.go:784), which always returns a non-nil *TagArguments
// (engine.go:700-704). So `args == nil` <=> "PHP was handed NULL" <=> "the constructor throws".
//
// ── WHY THERE IS NO catchThrowable HERE (a deliberate difference from some sibling ports) ───────
//
// Several ported tags open GetDocument with `defer catchThrowable(&out, "<Tag>")` because THEIR PHP
// class has its own `catch (\Throwable $e)` arm emitting a cy-form-error div. ToggleLogin.php has NO
// try and NO catch — its whole body is three assignments, a branch and a return. Adding
// catchThrowable would invent a "<div class='cy-form-error'>ToggleLogin error: …</div>" branch the
// PHP can never emit, which is a divergence dressed as robustness. It is omitted on purpose, the same
// call contenttag.go, logout.go and login.go each record. Nor can anything here produce a throw: this
// file opens nothing, indexes no map and dereferences no pointer without a nil test — it
// concatenates strings. (A throw from a tag IS caught one level up, by TagList.php:69-72's "This tag
// needs context to render standalone" arm — but that is TagList's byte, not ToggleLogin's, and
// TagList is already ported.)
//
// ── THE DEPENDENCY: UserPrivilegeSet IS A SEAM, BECAUSE IT IS A DIFFERENT LAYER ─────────────────
//
// ToggleLogin reads exactly one thing it does not own: UserPrivilegeSet::logged_in()
// (ToggleLogin.php:22). It has no Engine or Config seam, and engine.go is not this ticket's
// deliverable, so it is modelled file-locally as ToggleLoginContext below — precisely what login.go
// (#316) and logout.go (#317) each did for the same static. It is the package's standing pattern for
// a dependency that belongs to another layer: engine.go declares FormManager as an interface for the
// same reason, "this file's job is the tag engine, and a form pipeline is its own layer"
// (engine.go:338-342). So is authentication.
//
//	UserPrivilegeSet::logged_in()   `return (PersistentObjectManager::getData("USER_ID") != NULL);`
//	                                (UserPrivilegeSet.php:22-25)
//
// That method reads the POM's in-memory data map and runs NO SQL — unlike its authenticate()
// sibling, which reaches UserDAO and DataConnection, and which ToggleLogin never calls. So this tag
// touches no database on ANY path, seam supplied or not. #344's DEPENDS ON list names four ENGINE
// units and no auth unit, and the ticket says "Port ONE unit of congruency to Go. ONE. … Do not port
// anything outside this unit."
//
// ── WHAT THE DEFAULT (nil) CONTEXT REPRODUCES ───────────────────────────────────────────────────
//
// The registry factory builds the tag with a nil ToggleLoginContext, which is: no session. That is
// the state of BOTH the gate and the live Go server, and it is the PHP's own `getData("USER_ID") !=
// NULL` on a POM holding no USER_ID -> false -> the :21 arm.
//
// It costs the gate NOTHING EITHER WAY, and that is worth stating precisely rather than leaving as a
// reassurance: on the gate path the constructor throws at :15, so :22 is never evaluated and no
// session is ever consulted. The nil default and a fully-wired logged-in session produce the SAME
// 120 gate bytes. A caller that has a real session reaches the branch through NewToggleLoginTag; see
// that function.
//
// ── THE NON-GALLERY PATH: <<<ToggleLogin(...)(...)(...)>>> ──────────────────────────────────────
//
// Reachable only from document content, and NO Document_Templates row mentions this tag today — so
// this path renders nowhere in production. That is measured, not assumed: the live state db's
// Document_Templates holds 27 rows and 0 of them contain the string "ToggleLogin" (probed this
// session with sqlite3 immutable=1; see SIDE EFFECTS). It is ported anyway, faithfully.
//
// THE POP ORDER IS THE WHOLE OF THIS PATH, AND IT IS EASY TO MIS-PORT. TagArguments stores its
// arguments REVERSED (TagArguments.php:47, ported at engine.go:718-721), so array_pop() — Pop() here
// — hands back the argument the AUTHOR WROTE FIRST, then the second, then the third:
//
//	<<<ToggleLogin(a)(b)(c)>>>   ->   login_prompt="a"   logout_prompt="b"   style="c"
//
// FEWER THAN THREE ARGUMENTS IS NOT AN ERROR ON EITHER SIDE. PHP's array_pop on an exhausted array
// returns NULL (and decrements $count past zero, which nothing reads), and NULL interpolates into a
// double-quoted string as "". Go's Pop returns ("", false) on the same input (engine.go:747-755), and
// "" is that same (string)NULL — engine.go:497-500 spells the cast. So <<<ToggleLogin(a)>>> gives
// login_prompt="a" and an empty logout_prompt and style, on both sides.
//
// TWO PHP DEFECTS ON THIS PATH, BOTH PORTED AS WRITTEN, NEITHER FIXED HERE:
//
//  1. THE STYLE ARGUMENT CANNOT BE A STYLE. :21 interpolates $this->style as a bare attribute —
//     "<a $this->style href=…>" — so it must arrive as attribute SOURCE like `class='nav'`. But
//     FUNCTION_ARGUMENT is /\([A-Za-z0-9]*\)/ (constants.default.json:35, ported at engine.go:286),
//     so a tag argument is ALPHANUMERIC ONLY: it can hold no '=', no quote and no space. The richest
//     thing a template can pass is a bare word, and <<<ToggleLogin(in)(out)(nav)>>> emits
//     `<a nav href='?page=login'>in</a>` — an invalid attribute. The parameter is unusable as
//     designed, from content, for every input. That is the PHP's, and it is reproduced.
//  2. THE DOUBLE SPACE. With no style — which includes the bare <<<ToggleLogin>>>, whose empty
//     TagArguments pops "" three times — :21 yields `<a  href='?page=login'></a>`: TWO spaces
//     between "<a" and "href", because the interpolated empty string sits between the two literal
//     ones. A port that trimmed it would differ on every byte after "<a".
//
// NO ESCAPING, AND NONE IS MISSING. ToggleLogin.php calls htmlspecialchars NOWHERE, and this file
// calls esc() on nothing but the measured error message below. That is not the XSS login.go carries
// (login.go:44-73, which reflects $_POST raw): the only values interpolated here are tag arguments,
// which the FUNCTION_ARGUMENT charset has already restricted to [A-Za-z0-9]. Nothing escapable can
// reach these strings from any live surface. Adding esc() would be identity today and a divergence
// the moment it was not — so it is absent, matching the PHP.
//
// For the same reason this tag's output can embed no other tag: "<<<" is not alphanumeric, so no
// argument can carry a tag invocation into the re-parse execute_all_tags performs on tag output.
// That is the ticket's "TAGS THIS TAG DEPENDS ON: none", grounded in the charset rather than assumed.
//
// ── WHAT WAS MEASURED, AND WHAT WAS NOT ─────────────────────────────────────────────────────────
//
// MEASURED this session against the live PHP on 127.0.0.1:8899 (the app the gate compares against),
// slicing the page with TagList.php's own :62/:76 anchors and a run-time-measured 17B page tail —
// i.e. reproducing equivalence_test.go's cut exactly:
//
//	?page=tags&tag=ToggleLogin  ->  120B, and this file's GetDocument returns those same 120 bytes
//	                                on the same (nil-args) path. Stable across three consecutive
//	                                fetches, so the slice is not volatile.
//	the tagout anchor for "ToggleLogin" occurs EXACTLY ONCE in that page — so the tag is in
//	                                TagList::scan's whitelist and :61's in_array holds; the gallery
//	                                really does select it, and the slice is unambiguous.
//	Document_Templates             27 rows, 0 mentioning ToggleLogin (the ticket's claim, confirmed).
//
// NOT MEASURED, AND SAID PLAINLY RATHER THAN IMPLIED: the go toolchain and the repo's php binary are
// both outside this sandbox's permitted command set, so `go build`, `go vet`, `gofmt` and THE GATE
// ITSELF (`go test ./tags/ -run TestTagEquivalence`) could NOT be executed from this worktree. What
// is asserted above is the PHP side, which was driven directly, plus this file's own returned bytes
// where they are literal constants a reader can compare by eye. The gate is the ticket's settlement
// condition and it remains to be run.
//
// The two argument-path renders are DERIVED FROM THE SOURCE, not measured, because no live surface
// constructs this tag with arguments (0 of 27 template rows, above) and the gallery path throws
// before get_document(). They are stated so the derivation is checkable rather than hidden:
//
//	<<<ToggleLogin(in)(out)()>>>, logged out -> <a  href='?page=login'>in</a>
//	<<<ToggleLogin(in)(out)()>>>, logged in  -> <a  href='?page=welcome'>ACCOUNT</a> | <a  href='?page=logout'>out</a>
//
// ── SIDE EFFECTS: NONE, AND THE TAG CANNOT HAVE ANY ─────────────────────────────────────────────
//
// docs/PLAYBOOK.md Theme 3 says prove it, before/after, in isolation — do not assume the happy path.
// This tag opens no database, reads no file and runs no SQL: it has no openDB call, and its only
// data plane is the ToggleLoginContext its caller hands it, whose single method reads the POM's
// in-memory map. With the nil context the registry supplies, it concatenates constants.
//
// The one read this session that COULD have written was the Document_Templates probe above, and it
// was performed with sqlite3's `immutable=1` URI flag rather than `mode=ro` — the distinction
// Theme 3 was harvested from (#153): mode=ro on a WAL database spawns -wal/-shm sidecars. Proven in
// isolation rather than assumed: the state directory was listed with sizes BEFORE and AFTER the
// probe and is byte-for-byte the same six entries (README.md, STATE.json, component.json,
// congruency.sqlite, manifest.json, state.lock) — no sidecar appeared, and nothing was written.

// init self-registers the tag. This is the whole wiring step (#281; Register, engine.go:1355;
// newTag, engine.go:1393-1401). PortedTags() is registry-derived (engine.go:1406-1415), so it picks
// this up with no edit there, and equivalence_test.go stops skipping ToggleLogin with no edit to it.
//
// The factory passes a nil ToggleLoginContext — see "WHAT THE DEFAULT (nil) CONTEXT REPRODUCES" in
// the file header for exactly what that is faithful to, and why the gate cannot see the difference.
func init() {
	Register("ToggleLogin", func(e *Engine, a *TagArguments) Tag { return NewToggleLoginTag(e, a, nil) })
}

// ToggleLoginSession is UserPrivilegeSet's static surface as ToggleLogin uses it
// (lib/UserAuthentication/UserPrivilegeSet.php). It is an interface, not a port, because the class
// behind it belongs to the authentication layer — a different unit. See "THE DEPENDENCY" in the file
// header.
//
// ONE method, because ToggleLogin calls exactly one. This is the same shape logout.go's
// LogoutSession has, and the compile-time proof at the foot of this file pins that any session a
// caller already has for those tags works here too.
type ToggleLoginSession interface {
	// LoggedIn is UserPrivilegeSet::logged_in() (UserPrivilegeSet.php:22-25):
	// `return (PersistentObjectManager::getData("USER_ID") != NULL);`
	//
	// It reads the POM's in-memory data map and runs NO SQL — unlike its authenticate() sibling,
	// which ToggleLogin never calls.
	LoggedIn() bool
}

// ToggleLoginContext is the ambient per-request state ToggleLogin reads and neither Engine nor
// Config carries: the POM-backed UserPrivilegeSet. A nil *ToggleLoginContext is the honest "no
// session" state — which is what the gate and the live Go server both are.
//
// There is no Post field (unlike login.go's LoginContext) and no command hooks (unlike logout.go's
// LogoutContext): ToggleLogin reads no $_POST, no $_GET, and enqueues nothing. Its only input beyond
// its three arguments is whether a session is logged in.
//
// It is a struct rather than a Config field because engine.go is not #344's deliverable to edit; a
// caller reaches it through NewToggleLoginTag.
type ToggleLoginContext struct {
	// Session is UserPrivilegeSet. A nil Session is "no session", so LoggedIn is false — the PHP's
	// own `getData("USER_ID") != NULL` on a POM that holds no USER_ID.
	Session ToggleLoginSession
}

// ToggleLoginTag is ToggleLogin (ToggleLogin.php:8).
//
// The PHP's three properties are carried one-for-one. $arguments itself is NOT carried: unlike
// ContentTag.php:14 the constructor never even stores it — it only pops from it — so a field for it
// would be a field no code reads.
//
// e is carried for the package's uniform <Tag>{e: …} shape and is deliberately unread: this tag
// consults no engine state, no $_GET and no database.
type ToggleLoginTag struct {
	e   *Engine
	ctx *ToggleLoginContext

	// ctorThrew records that the PHP constructor throws before it assigns anything —
	// `$arguments->pop()` on NULL (ToggleLogin.php:15). True exactly when args == nil, which is
	// exactly the standalone/gallery path. See the file header.
	ctorThrew bool

	// loginPrompt is $this->login_prompt (ToggleLogin.php:15) — the FIRST-written argument.
	loginPrompt string

	// logoutPrompt is $this->logout_prompt (ToggleLogin.php:16) — the SECOND-written argument.
	logoutPrompt string

	// style is $this->style (ToggleLogin.php:17) — the THIRD-written argument. See "THE STYLE
	// ARGUMENT CANNOT BE A STYLE" in the file header for why this parameter is unusable as designed.
	style string
}

// NewToggleLoginTag is ToggleLogin::__construct (ToggleLogin.php:14-18) over ctx. ctx may be nil,
// which is the registry's default and the state of both live surfaces (see the file header).
//
// It must never panic: the package's registry invariant is that a factory CONSTRUCTS on nil args
// rather than blowing up, which SelfCheck asserts by doing exactly that (engine.go:4375-4379).
//
// This constructor is also the seam a caller with a real session uses. The registry path cannot carry
// one — RenderTag builds its own Engine and passes nil (engine.go:4148,4155) — so a caller drives it
// through the engine's documented Lookup override (engine.go:878-881), which stands in for swapping
// TAG_LOADER in the POM:
//
//	e := tags.NewEngineWithQuery(cfg, get)
//	e.Lookup = func(e *tags.Engine, n string, a *tags.TagArguments) (tags.Tag, bool) {
//	    if n == "ToggleLogin" {
//	        return tags.NewToggleLoginTag(e, a, &tags.ToggleLoginContext{Session: mySession}), true
//	    }
//	    return nil, false // fall back to the registry via your own dispatch
//	}
//
// Nothing in engine.go changes to allow that; the seam already exists.
func NewToggleLoginTag(e *Engine, args *TagArguments, ctx *ToggleLoginContext) *ToggleLoginTag {
	t := &ToggleLoginTag{e: e, ctx: ctx}
	if args == nil {
		// `$arguments->pop()` on NULL -> Error. Nothing after :15 runs — :16 and :17 never happen,
		// and get_document() is never called at all, because the throw leaves the constructor.
		t.ctorThrew = true
		return t
	}
	// :15-17, in the PHP's order — and the order is the whole of the argument mapping. Pop hands
	// back the FIRST-written argument first (the arguments are stored reversed; see "THE POP ORDER"
	// in the file header).
	//
	// Pop's second result is discarded on all three: it reports "the array was empty", where PHP's
	// array_pop returns NULL, and every use below interpolates the value into a double-quoted
	// string, where NULL and "" are the same bytes. Go's zero value is already that "".
	t.loginPrompt, _ = args.Pop()  // :15
	t.logoutPrompt, _ = args.Pop() // :16
	t.style, _ = args.Pop()        // :17
	return t
}

// toggleLoginNullArgError is get_class($e).': '.$e->getMessage() for the Error ToggleLogin.php:15
// throws when $arguments is NULL.
//
// This is not a guess about PHP's wording: it is the exact text the LIVE PHP server returns for this
// tag, read back off the wire this session — see toggleLoginStandaloneHTML. It differs from
// contenttag.go's otherwise identical constant by one method name (pop, not top), because that is the
// method each PHP constructor calls first.
const toggleLoginNullArgError = "Error: Call to a member function pop() on null"

// toggleLoginStandaloneHTML is TagList.php:70-71's catch body, verbatim:
//
//	"<p style='color:#b00020'>This tag needs context to render standalone: "
//	  . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</p>"
//
// MEASURED, not derived: fetching http://127.0.0.1:8899/?page=tags&tag=ToggleLogin from the live PHP
// server this session and cutting the slice between TagList.php:62's heading anchor and its :76
// close — the same cut equivalence_test.go makes — yields EXACTLY these 120 bytes, three fetches
// running:
//
//	<p style='color:#b00020'>This tag needs context to render standalone: Error: Call to a member function pop() on null</p>
//
// The message is run through esc() — this package's htmlspecialchars($s, ENT_QUOTES) port
// (engine.go:599) — rather than hand-escaped, because that is the IDENTICAL call TagList::esc
// (TagList.php:20) makes on the IDENTICAL value, so the two cannot drift apart. (This particular
// message happens to contain no escapable byte, so esc is identity on it today; calling esc anyway is
// what keeps that a fact rather than an assumption.)
//
// There is NO trailing newline: TagList.php:71 ends at "</p>".
func toggleLoginStandaloneHTML() string {
	return "<p style='color:#b00020'>This tag needs context to render standalone: " +
		esc(toggleLoginNullArgError) + "</p>"
}

// toggleLoginLoggedIn is UserPrivilegeSet::logged_in() (UserPrivilegeSet.php:22-25) through the seam.
// No Session is no USER_ID in the POM, which is the PHP's own `getData("USER_ID") != NULL` -> false.
func (t *ToggleLoginTag) toggleLoginLoggedIn() bool {
	if t.ctx == nil || t.ctx.Session == nil {
		return false
	}
	return t.ctx.Session.LoggedIn()
}

// GetDocument is ToggleLogin::get_document() (ToggleLogin.php:20-26) PLUS the constructor throw
// (:15) that a Go factory cannot raise. See the file header for why re-seating the throw here moves
// no byte.
//
// The PHP assigns the logged-OUT link FIRST, unconditionally (:21), and then OVERWRITES it when
// logged in (:23) — it is not an if/else. That shape is kept rather than inverted into a two-armed
// return, because a reader diffing this function against ToggleLogin.php should find the same shape.
// It costs nothing: the discarded :21 string is never observable.
//
// LOAD-BEARING BYTES A REFORMAT WOULD SILENTLY BREAK, in both arms:
//
//   - the SPACE after "<a" and the SPACE before "href" are both literal, so an empty $this->style
//     leaves TWO spaces ("<a  href=") — see "THE DOUBLE SPACE" in the file header;
//   - every attribute is SINGLE-quoted;
//   - the separator between the two logged-in links is exactly "</a> | <a" — space, pipe, space;
//   - "ACCOUNT" is a LITERAL, not $this->login_prompt: the logged-in arm ignores login_prompt
//     entirely, and prints an uncustomisable English word where the other two texts are arguments.
//     That asymmetry is the PHP's, and reproducing it is the job;
//   - there is no newline anywhere in either arm, leading or trailing.
//
// It deliberately has NO `defer catchThrowable(...)` — ToggleLogin.php has no catch arm to model.
// See the file header.
func (t *ToggleLoginTag) GetDocument() string {
	// ToggleLogin.php:15 — the constructor threw; TagList's catch supplies the bytes. This is the
	// gate's arm, and the only arm any live surface reaches today.
	if t.ctorThrew {
		return toggleLoginStandaloneHTML()
	}

	// :21 — assigned unconditionally, before the test.
	returnValue := "<a " + t.style + " href='?page=login'>" + t.loginPrompt + "</a>"

	// :22-24 — logged in: the assignment above is DISCARDED and replaced.
	if t.toggleLoginLoggedIn() {
		returnValue = "<a " + t.style + " href='?page=welcome'>ACCOUNT</a> | " +
			"<a " + t.style + " href='?page=logout'>" + t.logoutPrompt + "</a>"
	}

	return returnValue // :25
}

// Compile-time proofs, not tests — these cost nothing at run time and fail the BUILD if the shapes
// drift.
//
// The first pins that *ToggleLoginTag satisfies Tag (engine.go:852-854), which is what Register's
// factory must return. The second and third pin that this tag's session seam is a SUBSET of the two
// that landed before it: LoginSession (login.go) and LogoutSession (logout.go) both have LoggedIn(),
// so a caller that already built a session for either tag can hand the SAME value to this one. If
// either ever renames or drops that method, this breaks HERE, at compile time, rather than leaving a
// caller quietly unable to wire all three.
var (
	_ Tag                = (*ToggleLoginTag)(nil)
	_ ToggleLoginSession = (LoginSession)(nil)
	_ ToggleLoginSession = (LogoutSession)(nil)
)
