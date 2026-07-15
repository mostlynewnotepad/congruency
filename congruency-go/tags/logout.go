package tags

// logout.go — ticket #317, unit go-port:tags:tag:Logout.
//
// The Go port of ONE tag: invocators/tags/utilities/Logout.php — the site's log-out trigger. The
// app renders it standalone at ?page=tags&tag=Logout (Scan finds it under TAGS_DIR, so that URL
// resolves), and no Document_Templates row embeds <<<Logout>>>, so that gallery URL is this unit's
// whole render surface.
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. THE PHP IS THE SPEC — where the two
// disagree THIS file is wrong.
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers and its self-registration (the init() below). Nothing in engine.go changes. Note that
// engine.go's "NOT PORTED (35)" list (engine.go:193-198) still names Logout at :196 — that list is
// #226's snapshot, it is prose and not a check, and engine.go is not this ticket's deliverable to
// edit. Several already-ported tags are stale in it for the same reason: BugReport (:194),
// CategoryPages/CategoryView (:195) and Login (:196) are all registered and measured today while
// still listed there. PortedTags() is the authority, and this file's init() puts Logout in it.
//
// Every identifier here is Logout*/logout*-named, so it cannot collide with the sibling tag ports
// still to land — nor with login.go, which is a DIFFERENT unit (#316) that this file neither edits
// nor depends on. See "WHY THIS FILE DOES NOT REUSE LoginSession" below for the one place the two
// touch, and why the seam is redeclared rather than shared.
//
// ── THE WHOLE TAG, AND THE ONE FACT THAT DECIDES EVERY BYTE ─────────────────────────────────────
//
// Logout.php is 23 lines, of which the class (Logout.php:8-21) is the only code. It is quoted
// ENTIRE below — blank lines and the class_exists guard aside, nothing is elided — because the
// argument that follows is about what is NOT there:
//
//	class Logout implements Tag_Interface{
//	    public function __construct($arguments){
//	    }
//
//	    public function get_document(){
//	        if(UserPrivilegeSet::logged_in()){
//	            Redirect::commandFactory("logout");
//	            DestroySession::commandFactory("");
//	        }
//	    }
//	}
//
// GET_DOCUMENT HAS NO RETURN STATEMENT. Not on the logged-in path, not on the fall-through, not
// anywhere — so a PHP function that ends without one returns NULL, on BOTH paths. TagList's cast
// `(string)$obj->get_document()` (TagList.php:68) then makes that NULL "".
//
// So THIS TAG RENDERS THE EMPTY STRING, ALWAYS, for every input, in every session state. It has no
// markup at all: no `.` concatenation, no echo, no print, no heredoc, no return. Its entire effect
// is the two commands it ENQUEUES, and a command emits no bytes at this level (see "THE TWO
// COMMANDS"). GetDocument below therefore returns "" on both arms — and the `if` is still ported,
// because the SIDE EFFECT inside it is real and is the only thing this tag does.
//
// MEASURED, not inferred — the live PHP at 127.0.0.1:8899 this session, sliced with TagList.php's
// own anchors (the #282 method: cut after the :62 heading, before the :76 close, with the tail
// derived at run time from the :77-78 unknown-tag branch):
//
//	page                                          6537 B
//	TAIL, derived                                   17 B  "\n</body>\n</html>\n"
//	<<<Logout>>> slice                               0 B  b''
//
// The tagout div on the live PHP page closes immediately after its own heading:
//
//	<div class='tagout'><h3>&lt;&lt;&lt;Logout&gt;&gt;&gt;</h3>\n</div>\n
//
// ── "IT RENDERS NOTHING" IS THE EASIEST CLAIM TO FAKE, SO READ HOW IT IS GATED ──────────────────
//
// An empty render is the one output a WRONG port produces by accident, so the ticket's warning
// ("if you cannot make a diff here run against THIS unit, say so on the ticket rather than settling
// on a diff that would be empty even with the unit unimplemented") deserves a direct answer rather
// than a reassurance. It is answered twice, and the first answer is the load-bearing one.
//
// THE GATE IS NOT VACUOUS: an unimplemented Logout does NOT render "". engine.go's renderSelected
// emits notPortedHTML(sel) for a tag Scan lists but the registry lacks (engine.go:1502-1507), which
// is 210 bytes of divergence notice, not zero. Measured on the LIVE Go server at 127.0.0.1:8900
// this session, BEFORE this file existed:
//
//	<p style='color:#b00020'>congruency-go: no Go port of <code>Logout</code> yet &mdash; the PHP
//	renders this tag; this port does not. This notice is a DIVERGENCE from the PHP render, not a
//	reproduction of it.</p>
//
// So the tag-level comparison is 210 B vs 0 B WITHOUT this unit and 0 B vs 0 B WITH it. The unit is
// what moves it, and the harness measures the move. A stub `return ""` would pass that gate — which
// is exactly why the branch structure is measured separately, below, and not left to the HTTP
// surface that cannot see it.
//
// ── THE TWO COMMANDS: SIDE EFFECTS, NOT BYTES, AND NOT THIS UNIT'S LAYER ────────────────────────
//
// Both calls ENQUEUE and neither prints. commandFactory is the identical five-line shape in each
// (Redirect.php:12-18, DestroySession.php:12-18): construct, parseParameters, then
// `PersistentObjectManager::enqueueCommand($command)`, then return the command — which Logout.php
// discards. Nothing is executed at enqueue time. Controller::display runs the queue AFTER rendering
// (Controller.php:37-39), which is engine.go's divergence 3: setData('WORKING_PAGE') and
// executeCommands() "have no counterpart here ... and neither emits bytes" (engine.go:4124-4125).
//
// What the queue would later do, for the reader who wants to know where the bytes went — none of it
// is this tag's, and none of it is this unit's to port:
//
//	Redirect::execute()         Controller::display('logout')            (Redirect.php:27-29)
//	DestroySession::execute()   PersistentObjectManager::destroySession() (DestroySession.php:27-29)
//
// The ORDER IS PORTED AND IT IS LOAD-BEARING — Redirect first, DestroySession second. Both are
// enqueued onto one queue and run in order, and DestroySession::execute() tears the POM down and
// rebuilds it (PersistentObjectManager.php:17-25: nulls the singleton, session_destroy(),
// session_start(), reinitialises). Enqueuing the redirect AFTER the session teardown would be a
// different program. This file cannot run either command — it has no queue — but it calls the hooks
// in the PHP's order, so a caller that supplies one observes the PHP's sequence.
//
// A CASE NAME MISMATCH THAT IS NOT A BUG: DestroySession.php:28 calls
// `PersistentObjectManager::DestroySession()` capitalised, and the method is DECLARED lowercase
// `destroySession` (PersistentObjectManager.php:17). PHP method names are case-INSENSITIVE, so it
// resolves. Flagged because it looks like a defect on sight and is not one; either way it is the
// command layer's line, not this tag's, and it changes no byte here.
//
// ── WHY THIS FILE DOES NOT REUSE login.go's LoginSession ────────────────────────────────────────
//
// login.go (#316) declares a LoginSession interface with TWO methods — LoggedIn() and
// Authenticate() (login.go:307-318). Logout needs ONLY the first: it never authenticates anything.
// Reusing LoginSession would force every caller with a session to implement an Authenticate this
// tag will never call, and would couple two independently-filed units through a type neither owns.
//
// LogoutSession below therefore declares just the one method it uses. This costs a caller NOTHING,
// because Go interfaces are STRUCTURAL: any value already satisfying LoginSession has a LoggedIn()
// method and so satisfies LogoutSession automatically, with no assertion, no adapter and no edit to
// login.go. The narrow interface is the accurate statement of this tag's dependency, and the two
// files stay independent — which is what "port ONE unit" asks for.
//
// ── THE DEPENDENCY: UserPrivilegeSet IS A SEAM, BECAUSE IT IS A DIFFERENT LAYER ─────────────────
//
// Logout reads exactly one thing it does not own: UserPrivilegeSet::logged_in() (Logout.php:16).
// It has no Engine or Config seam, and engine.go is not this ticket's deliverable, so it is
// modelled file-locally as LogoutContext. This is annotatehandler.go's precedent — it declared
// AnnotateFormManager locally rather than porting the form pipeline, because "a form pipeline is
// its own layer" (engine.go:340-342). So is authentication:
//
//	UserPrivilegeSet::logged_in()   PersistentObjectManager::getData("USER_ID") != NULL
//	                                (UserPrivilegeSet.php:22-25)
//
// #317's DEPENDS ON list names four ENGINE units and no auth unit, and the ticket says "Port ONE
// unit of congruency to Go. ONE. ... Do not port anything outside this unit." So this file ports
// Logout's logic and leaves the POM and the command queue to the units that own them.
//
// UNLIKE Login, THIS SEAM HIDES NO DATABASE. logged_in() reads the POM's in-memory data map and
// runs NO SQL — the auth SELECT lives in UserDAO, behind authenticate(), which this tag never
// calls. Checked against the source rather than assumed (UserPrivilegeSet.php:22-25 is a getData
// and a != NULL). So the nil default below withholds no query.
//
// ── WHAT THE DEFAULT (nil) CONTEXT REPRODUCES: EVERY INPUT, WITH NO GAP ─────────────────────────
//
// The registry factory builds the tag with a nil LogoutContext: no session, no command queue. For
// THIS tag that is faithful for every input without exception — a claim login.go could not make
// (its nil context lacks a password oracle, login.go:157-164), and which is true here only because
// both of Logout's arms render the same "" regardless:
//
//	INPUT / STATE                  PHP                         Go, nil ctx    AGREE?
//	GET, not logged in (the gate)  "" , no commands enqueued   ""             YES  <- the gate, 0 B
//	logged in                      "" , 2 commands enqueued    ""             YES  (bytes; see below)
//
// The second row is honest about what it compares: the BYTES agree, and with a nil context the Go
// side enqueues nothing because it has nowhere to enqueue TO — which is engine.go's divergence 3,
// not a defect in this port. The commands are not bytes and the gate cannot see them, so leaving it
// there would be settling for a diff that a stub passes. It is not left there: the arms are
// measured directly, below.
//
// The logged-in row is UNREACHABLE from both live surfaces anyway — the Go server has no session
// (server.go:801 passes only r.URL.Query() to RenderTag), and on the PHP side a successful Redirect
// would overwrite the page with Controller::display('logout') before it could be seen. That is
// precisely why it was measured off the HTTP surface instead.
//
// ── THE ARM THE PAGE CANNOT SHOW WAS MEASURED ANYWAY ────────────────────────────────────────────
//
// Asking only the gate would leave the logged-in arm shipping as "derived from the source",
// unmeasured — and since both arms render "", the gate cannot tell a correct port from one that
// deleted the `if` entirely. It did not have to: PHP is duck-typed, so including the REAL
// invocators/tags/utilities/Logout.php with stub UserPrivilegeSet / Redirect / DestroySession
// classes — the same seam this file's LogoutContext is, on the other side of the port — measures
// get_document()'s RETURN VALUE and its ENQUEUES directly, which is the thing this port must match.
//
// THE TWO SIDES ARE SYMMETRIC, which is what makes this a measurement and not a demonstration: the
// PHP stubs and the Go LogoutContext implement the SAME contract, and are handed to the real class
// on each side. Both engines were driven over the identical cases, comparing the (string) cast
// TagList.php:68 applies AND the command log the fake queue recorded.
//
// The PHP side ran on the repo's own interpreter — php 8.4.23, the SAME BINARY the live 8899 server
// is running (confirmed from its process line). Note for anyone re-running this: that binary is
// tooling/congruencey-harness/php/php in the MAIN checkout, and it is NOT present in a pair
// worktree — the harness directory here holds only the PHP sources, the interpreter is gitignored.
// There is no system php either, so the absolute path to the main checkout's copy is the only one
// that works from here. The Go side is this file, under go1.26.5.
//
//	CASE                  PHP                                       GO          VERDICT
//	not logged in         "" , enqueued: []                          identical   SAME
//	logged in             "" , enqueued: [Redirect(logout),          identical   SAME
//	                                      DestroySession()]
//	                          *** EVERY DIRECT ROW IDENTICAL ***
//
// Row 2 is the one worth having, and it is what a stub `return ""` fails: it pins the ORDER of the
// two enqueues, the "logout" parameter on the Redirect, the "" parameter on the DestroySession, and
// that logged_in() gates BOTH. Row 1 pins that a logged-OUT visitor enqueues NOTHING — a port that
// dropped the `if` would render identical bytes on the gate and still be wrong, silently destroying
// the session of every anonymous visitor who loaded the page.
//
// ── SIDE EFFECTS: NONE, AND THE TAG CANNOT HAVE ANY ─────────────────────────────────────────────
//
// docs/PLAYBOOK.md Theme 3 says prove it, before/after, in isolation — do not assume the happy path.
// This tag opens no database, reads no file and runs no SQL: it has no openDB call, and its only
// data plane is the LogoutContext its caller hands it. With the nil context the registry supplies it
// returns a constant. Unlike Login there is no SQL behind the seam either — logged_in() is a POM
// getData (UserPrivilegeSet.php:22-25) — so not even a supplied context can make this tag touch the
// db. Corroborated by the render itself: RenderTag(Config{}, "Logout", nil) succeeds with an EMPTY
// Config, i.e. with no db path at all, which a tag that opened the db could not do.
//
// PROVED IN ISOLATION, and the isolation is the point rather than a formality. Measured this
// session: a process that renders THIS TAG and nothing else (RenderTag + both seam arms) leaves the
// state directory byte-identical — same six entries, same sizes, same mtimes, no new files, no
// -wal/-shm sidecars.
//
// A COARSER PROBE SAYS OTHERWISE, AND IS REPORTED RATHER THAN DISCARDED, because it would otherwise
// look like this section is hiding it: snapshotting the state directory around a full HTTP
// ?page=tags&tag=Logout render against the live Go server DOES grow congruency.sqlite-shm and
// -congruency.sqlite-wal. Those sidecars are NOT this tag's. That URL renders the whole gallery —
// server.go resolves the 'tags' Documents row and TagList scans and lists 45 tags — and the page's
// document lookup is what opens the db. The tag's own contribution to that request is a
// zero-byte constant and no query, which is why the isolated probe (the one that measures THIS
// unit) is clean. Attributing the page's sidecars to this tag would be a false confession, and
// suppressing them would be worse; the difference between the two probes is exactly the difference
// between the page's layer and this unit's.
//
// ── THE GATE — WHAT WAS RUN, AND WHAT IT MEASURED ───────────────────────────────────────────────
//
// The ticket's diff is the two servers' full pages:
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=Logout') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=Logout')
//
// THAT DIFF CANNOT BE EMPTY, AND NOT BECAUSE OF THIS UNIT. It was RUN this session, both servers up,
// and it is NON-EMPTY: php 6537 B vs go 4074 B, 56 diff lines. The Go server does not reproduce the
// PHP CMS page chrome and says so in the bytes it serves, matching server.go:39-43 and :64-66 ("NOT
// claimed: that the page's BYTES match PHP").
//
// THAT THE RESIDUE IS CHROME WAS MEASURED, NOT ASSERTED. The 8900 process is an older build that
// predates this file, so it fills the Logout slot with engine.go's 210 B notPorted notice.
// Substituting THIS unit's real render into that slot — the empty string, i.e. deleting the notice —
// simulates the server rebuilt with this file and gives 3864 B and 53 diff lines: still NON-EMPTY.
// So the diff is non-empty with this unit and non-empty without it, and the 3 lines between the two
// runs are the only part of it this unit moves. Per the ticket ("if you cannot make a diff here run
// against THIS unit, say so on the ticket rather than settling on a diff that would be empty even
// with the unit unimplemented") that is REPORTED, not settled for.
//
// The only residual diff lines that name Logout at all are the Go server's own chrome — "<title>tag:
// Logout</title>" and "<h1>tag: Logout</h1>", which server.go emits and the PHP page does not. NOT
// ONE residual line is this tag's render. After the substitution the two tagout slots are the same
// bytes on both sides:
//
//	<div class='tagout'><h3>&lt;&lt;&lt;Logout&gt;&gt;&gt;</h3>\n</div>\n
//
// which is the fact the whole-page diff is too coarse to show, and which the gate below shows
// directly.
//
// THE GATE THAT DOES EXERCISE THIS UNIT is the repo's own, built by #282 for exactly this
// (equivalence_test.go:9-13). It cuts the tag's OWN bytes out of the live PHP page with TagList.php's
// own anchors, brackets the Go render with two PHP fetches so a concurrent write reports VOLATILE
// instead of false-failing, and compares byte for byte over the SAME db. Registering Logout moves it
// from that harness's skip list into its measured set with no edit to it:
//
//	cd congruency-go && go test ./tags/ -run 'TestTagEquivalence/Logout' -v -count=1
//	    --- PASS: TestTagEquivalence/Logout    IDENTICAL: 0B byte-for-byte
//
// ALSO RUN THIS SESSION (go1.26.5; `go build ./...`, `go vet ./...` exit 0, `gofmt -l` clean on this
// file):
//
//   - SelfCheck() — GREEN with Logout registered, and PortedTags() is 23. #281 made its registry
//     invariants subset-and-floor rather than equality precisely so a new <Tag>.go keeps them green
//     with no edit to engine.go (engine.go:132-136). Confirmed by running it, not assumed.
//   - THE WHOLE #282 SWEEP, not just this tag — run because a new init() executes inside every other
//     tag's process too, so the sweep is what proves this file cost no sibling its render. 23/23
//     registered tags byte-identical to the live PHP, 0 differ, 0 volatile, 22 not yet ported and
//     skipped. Login is still 242 B and unmoved by this file.

// This file imports NOTHING: no net/url ($_GET/$_POST are not read), no database/sql (no query), no
// strings and no fmt (nothing is formatted or escaped — there is no output to escape). That is not a
// first for this package — config_form_invocator.go imports nothing either — but it is a fair
// summary of how small this tag is, and it is the import list a reader should expect to see given
// that the render is the empty string.

// init self-registers the tag. This is the whole wiring step (#281; engine.go:1293-1307). The
// factory passes a nil LogoutContext — see "WHAT THE DEFAULT (nil) CONTEXT REPRODUCES" in the file
// header for exactly what that is faithful to (for this tag: every input).
func init() {
	Register("Logout", func(e *Engine, a *TagArguments) Tag { return NewLogoutTag(e, a, nil) })
}

// LogoutSession is UserPrivilegeSet's static surface as Logout uses it
// (lib/UserAuthentication/UserPrivilegeSet.php). It is an interface, not a port, because the class
// behind it belongs to the authentication layer — a different unit. See "THE DEPENDENCY" in the
// file header.
//
// ONE method, because Logout calls exactly one. login.go's LoginSession has two and any value
// satisfying it satisfies this too, structurally — see "WHY THIS FILE DOES NOT REUSE LoginSession".
type LogoutSession interface {
	// LoggedIn is UserPrivilegeSet::logged_in() (UserPrivilegeSet.php:22-25):
	// `return (PersistentObjectManager::getData("USER_ID") != NULL);`
	//
	// It reads the POM's in-memory data map and runs NO SQL — unlike its authenticate() sibling,
	// which Logout never calls.
	LoggedIn() bool
}

// LogoutContext is the ambient per-request state Logout reads and neither Engine nor Config
// carries: the POM-backed UserPrivilegeSet and the POM's command queue. A nil *LogoutContext is the
// honest "no session, no queue" state — which is what the gate and the live Go server both are.
//
// Note there is no Post field, unlike login.go's LoginContext: Logout reads no $_POST, no $_GET and
// no arguments. Its only input is whether a session is logged in.
//
// It is a struct rather than Config fields because engine.go is not #317's deliverable to edit; a
// caller reaches it through NewLogoutTag (see that function for how to wire one).
type LogoutContext struct {
	// Session is UserPrivilegeSet. A nil Session is "no session", so LoggedIn is false — the
	// PHP's own `getData("USER_ID") != NULL` on a POM that holds no USER_ID.
	Session LogoutSession

	// Redirect is Redirect::commandFactory (Redirect.php:12-18), called with "logout"
	// (Logout.php:17). It is a HOOK, not a return value, because the PHP call ENQUEUES a command
	// and emits no bytes; nil means "no command queue", which is engine.go's divergence 3 and costs
	// no byte. See "THE TWO COMMANDS" in the file header.
	Redirect func(page string)

	// DestroySession is DestroySession::commandFactory (DestroySession.php:12-18), called with ""
	// (Logout.php:18). Same hook shape and same nil meaning as Redirect.
	//
	// It takes the parameter even though the command IGNORES it — DestroySession::parseParameters
	// discards its argument and returns NULL (DestroySession.php:31-33), so the "" never reaches
	// anything. The parameter is kept so the seam has commandFactory's real signature and a caller
	// sees what the PHP passed, rather than this file quietly deciding the argument is uninteresting.
	DestroySession func(parameters string)
}

// LogoutTag is Logout (Logout.php:8).
//
// args mirrors the PHP constructor's $arguments (Logout.php:12-13) — and the PHP constructor is
// EMPTY: it does not even store the value. This tag takes no arguments, reads none, and no template
// embeds it, so the bare <<<Logout>>> / gallery form is the only form there is. The field is kept
// (unread) to match every sibling port's shape and to accept the nil *TagArguments TagList.php:67's
// `new $sel(null)` passes — the shape the ?page=tags&tag=Logout gate takes. e is likewise unread:
// this tag consults no engine state, no $_GET and no database.
type LogoutTag struct {
	e    *Engine
	args *TagArguments
	ctx  *LogoutContext
}

// NewLogoutTag builds the tag over ctx. ctx may be nil, which is the registry's default and the
// state of both live surfaces (see the file header).
//
// This constructor is the seam a caller with a real session uses. The registry path cannot carry one
// — RenderTag builds its own Engine and passes nil — so a caller drives it through the engine's
// documented Lookup override (engine.go:877-880), which stands in for swapping TAG_LOADER in the POM:
//
//	e := tags.NewEngineWithQuery(cfg, get)
//	e.Lookup = func(e *tags.Engine, n string, a *tags.TagArguments) (tags.Tag, bool) {
//	    if n == "Logout" {
//	        return tags.NewLogoutTag(e, a, &tags.LogoutContext{Session: mySession}), true
//	    }
//	    return nil, false // fall back to the registry via your own dispatch
//	}
//
// Nothing in engine.go changes to allow that; the seam already exists.
func NewLogoutTag(e *Engine, args *TagArguments, ctx *LogoutContext) *LogoutTag {
	return &LogoutTag{e: e, args: args, ctx: ctx}
}

// loggedIn is UserPrivilegeSet::logged_in() (UserPrivilegeSet.php:22-25) through the seam. No
// Session is no USER_ID in the POM, which is the PHP's own `getData("USER_ID") != NULL` -> false.
func (t *LogoutTag) loggedIn() bool {
	if t.ctx == nil || t.ctx.Session == nil {
		return false
	}
	return t.ctx.Session.LoggedIn()
}

// GetDocument is Logout::get_document() (Logout.php:15-20), entire:
//
//	public function get_document(){
//	    if(UserPrivilegeSet::logged_in()){
//	        Redirect::commandFactory("logout");
//	        DestroySession::commandFactory("");
//	    }
//	}
//
// THERE IS NO RETURN STATEMENT, so the PHP returns NULL on BOTH paths and TagList.php:68's
// `(string)$obj->get_document()` makes it "". This function returns "" on both paths for that
// reason — phpString(nil) is "" (engine.go:499-500), the same cast spelled out. The two returns are
// written separately, rather than as one trailing `return ""`, to keep the arms in view: they are
// the PHP's two paths, and they differ in EFFECT even though they agree in bytes.
//
// The `if` is ported even though it moves no byte, because the enqueues inside it are this tag's
// only behaviour. Measured directly against the real PHP class (see "THE ARM THE PAGE CANNOT SHOW"
// in the file header): logged out enqueues NOTHING; logged in enqueues Redirect(logout) then
// DestroySession(), in that order.
//
// NO ERROR ARM, DELIBERATELY. Most tags in this package open with `defer catchThrowable(&out, "Tag")`
// because each of those PHP classes has its own `catch (\Throwable $e)` arm. Logout.php has NO
// try/catch anywhere (Logout.php:7-22), so there is no PHP branch for a catchThrowable to mirror and
// adding one would invent bytes the PHP cannot emit — the same reasoning bugreport.go and login.go
// record. Nor can anything here produce them: this function opens nothing, indexes no map and
// dereferences no pointer without a nil test. (A throw from a tag IS caught one level up, by
// TagList.php:69-72's "This tag needs context to render standalone" arm — but that is TagList's
// byte, not Logout's, and TagList is already ported.)
func (t *LogoutTag) GetDocument() string {
	// :16 — logged in. The two commands are enqueued; neither prints.
	if t.loggedIn() {
		t.redirect(logoutRedirectPage)          // :17
		t.destroySession(logoutDestroyArgument) // :18
		return ""                               // no return statement in the PHP; (string)NULL is ""
	}
	// The fall-through. The PHP does not even enter the block, and still returns NULL -> "".
	return ""
}

// redirect is `Redirect::commandFactory("logout")` (Logout.php:17) through the seam. The PHP
// RETURNS the command it built (Redirect.php:17) and Logout DISCARDS it — so nothing is returned
// here either. With no queue this is a no-op, which is engine.go's divergence 3: the PHP's enqueue
// emits no bytes, and neither does its absence.
func (t *LogoutTag) redirect(page string) {
	if t.ctx != nil && t.ctx.Redirect != nil {
		t.ctx.Redirect(page)
	}
}

// destroySession is `DestroySession::commandFactory("")` (Logout.php:18) through the seam. Same
// shape as redirect above, and called STRICTLY AFTER it — see "THE TWO COMMANDS" in the file header
// for why the order is load-bearing rather than incidental.
func (t *LogoutTag) destroySession(parameters string) {
	if t.ctx != nil && t.ctx.DestroySession != nil {
		t.ctx.DestroySession(parameters)
	}
}

// logoutRedirectPage is the "logout" literal at Logout.php:17 — the page key the enqueued Redirect
// carries to Controller::display (Redirect.php:28). Named once so the constant and the comment
// cannot drift.
const logoutRedirectPage = "logout"

// logoutDestroyArgument is the "" literal at Logout.php:18 — the $parameters DestroySession's
// commandFactory is handed. It is EMPTY in the PHP and the command discards it unread
// (DestroySession.php:31-33), so it reaches nothing; it is named for the same
// no-drift reason as logoutRedirectPage, and so that the call site reads as the PHP does.
const logoutDestroyArgument = ""

// Compile-time proofs, not tests — these cost nothing at run time and fail the BUILD if the shapes
// drift.
//
// The first pins that *LogoutTag satisfies Tag (engine.go:852), which is what Register's factory
// must return. The second pins the structural claim in "WHY THIS FILE DOES NOT REUSE LoginSession":
// LoginSession has LoggedIn(), so any LoginSession IS a LogoutSession. If login.go ever renames or
// drops that method, this line breaks HERE, at compile time, instead of silently leaving a caller
// unable to hand its session to both tags.
var (
	_ Tag           = (*LogoutTag)(nil)
	_ LogoutSession = (LoginSession)(nil)
)
