package tags

// login.go — ticket #316, unit go-port:tags:tag:Login.
//
// The Go port of ONE tag: invocators/tags/login/Login.php — the site's login form. The app renders
// it standalone at ?page=tags&tag=Login (Scan finds it under TAGS_DIR, so that URL resolves), and no
// Document_Templates row embeds <<<Login>>>, so that gallery URL is this unit's whole render
// surface.
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. THE PHP IS THE SPEC — where the two
// disagree THIS file is wrong. Two things below look like defects because they ARE defects, in the
// PHP, and porting them faithfully is the job (see "THE UNESCAPED $login" and "THE DISCARDED
// RETURN"). Fixing either here would be the finding, not the fix.
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers and its self-registration (the init() below). Nothing in engine.go changes. Note that
// engine.go's "NOT PORTED (35)" list (engine.go:193-198) still names Login at :196 — that list is
// #226's snapshot, it is prose and not a check, and engine.go is not this ticket's deliverable to
// edit. Several tags already ported are stale in it for the same reason: BugReport (:194) and
// CategoryPages/CategoryView (:195) are all registered and measured today while still listed there.
// PortedTags() is the authority, and this file's init() puts Login in it.
//
// Every identifier here is Login*/login*-named, so it cannot collide with the sibling tag ports
// still to land. The sibling tag ToggleLogin (invocators/tags/login/ToggleLogin.php) lives in the
// same PHP directory and is a DIFFERENT unit — nothing here ports or touches it.
//
// ── WHAT THE PHP TAG IS: THREE CONDITIONS ───────────────────────────────────────────────────────
//
// Login.php:14-18 names them in its own comment — "Three Conditions, logged in, not logged in,
// login failed(retry)" — and get_document() (Login.php:20-34) is that trichotomy:
//
//	logged in                                -> login_success()   -> NULL -> ""   (:22-23)
//	not logged in, $_POST['login'] non-empty -> authenticate()                    (:27-28)
//	not logged in, otherwise                 -> login_form('')                    (:30)
//
// and authenticate() (Login.php:37-46) splits the second again:
//
//	credentials accepted -> login_success()  -> NULL -> ""                        (:40-41)
//	credentials rejected -> login_failed($_POST['login'])                         (:43)
//
// The GATE surface — a bare GET of ?page=tags&tag=Login — has no session and no $_POST, so it takes
// login_form(''). That is 242 bytes, and it is this unit's whole measured contract; see THE GATE.
//
// ── THE UNESCAPED $login: THIS TAG HAS AN XSS, AND THE PORT KEEPS IT ────────────────────────────
//
// This inverts the rule every sibling port teaches, so read it before you file it as a finding.
//
// engine.go's header calls escape-first "the htmlspecialchars recursion guard": every ported tag
// pushes DB-derived text through esc() so a stored "<<<Tag>>>" comes back inert. Login.php calls
// htmlspecialchars NOWHERE. It interpolates $login RAW into an HTML attribute (Login.php:57) and
// again into the failure sentence (Login.php:66), and $login is caller-supplied — it is
// $_POST['login'], echoed straight back (Login.php:43).
//
// So the PHP has a reflected XSS, and the value is not merely unescaped in theory. MEASURED against
// the live PHP this session, POSTing login=<b>&x'" to ?page=tags&tag=Login:
//
//	<input type='text' name='login' value='<b>&x'"'><br />
//	...Your attempt to login as <b>&x'" has failed.<br /><br />
//
// — the tag breaks its own attribute quoting and emits the raw tag. This file reproduces those exact
// bytes, and calls esc() on NOTHING. Adding esc() would turn value='<b>' into value='&lt;b&gt;' and
// diff on every byte of every non-alphanumeric login. The ticket is explicit about which way this
// goes: "The PHP is the spec: when they disagree, the Go port is wrong — never 'improve' the
// behaviour here. If the PHP is genuinely defective, file a separate bug ticket and port the defect
// faithfully." It is genuinely defective; it is ported faithfully; the bug ticket is this unit's to
// file, not this file's to fix. #316 did not authorise a fix, and a port that silently patched it
// would make the Go server disagree with the PHP it exists to reproduce.
//
// The recursion guard the escaping would otherwise provide is NOT needed here and its absence costs
// nothing: a login containing "<<<TicketList>>>" IS re-parsed by execute_all_tags — but only when the
// tag is reached through the ENGINE, and $_POST reaches this tag only through a caller that supplies
// a LoginContext (see below). The gate never does. PHP has the identical exposure, so this is a
// property reproduced, not introduced.
//
// ── THE DISCARDED RETURN, AND WHY BOTH SUCCESS ARMS RENDER "" ───────────────────────────────────
//
// login_success() (Login.php:49-51) calls Redirect::commandFactory('welcome') and HAS NO RETURN
// STATEMENT, so it returns NULL. Two consequences, both ported:
//
//  1. get_document() returns NULL on the logged-in path (:23 assigns that NULL), and TagList's cast
//     `(string)$obj->get_document()` (TagList.php:68) makes NULL "". The tag renders EMPTY, not a
//     welcome message. GetDocument returns "" — phpString(nil) is "" (engine.go:499-500), the same
//     cast spelled out.
//  2. authenticate() at :41 calls `$this->login_success();` and THROWS THE RESULT AWAY — unlike :23,
//     it does not assign it. $return_value therefore stays the NULL it was initialised to at :38.
//     This looks like a bug and is invisible: login_success() returns NULL either way, so the
//     discard changes no byte. It is ported as written (loginSuccess's result is discarded at the
//     same place) because the PHP is the spec down to the arm, and a reader comparing the two files
//     should find them the same shape.
//
// THE REDIRECT IS A SIDE EFFECT, NOT BYTES, AND IT IS NOT THIS UNIT'S LAYER. Redirect::commandFactory
// (Redirect.php:13-19) ENQUEUES a command in the POM; nothing prints. Controller::display then runs
// the queue AFTER rendering (Controller.php:37-39), and Redirect::execute calls Controller::display
// ('welcome'), which OVERWRITES Controller::$display_string — so control()'s single print at
// Controller.php:21 emits the welcome page INSTEAD of the tags page. Measured this session: a POST of
// the real credential returns a 3133B "No such page" document ('welcome' is not a Documents row, so
// DocumentDAO falls back to the "invalid" document) and the tags page never appears at all.
//
// That whole cascade is the POM + Controller, which engine.go's divergence 3 states this package does
// not have and tags.Render does not reproduce (engine.go:4124-4125: setData('WORKING_PAGE') and
// executeCommands() "have no counterpart here ... and neither emits bytes"). It is out of this unit's
// scope in both directions. What IS in scope is that login_success is CALLED, so the seam below
// carries an optional Redirect hook: a caller that has a command queue gets the call, and a caller
// that does not gets the PHP's own bytes, which are none.
//
// ── THE DEPENDENCY: UserPrivilegeSet IS A SEAM, BECAUSE IT IS A DIFFERENT LAYER ─────────────────
//
// Login reads exactly two things it does not own — $_POST, and UserPrivilegeSet's two static methods
// (Login.php:22,39,40). Neither has an Engine or Config seam, and engine.go is not this ticket's
// deliverable, so both are modelled file-locally: LoginContext below. This is annotatehandler.go's
// precedent exactly — it declared AnnotateFormManager locally rather than porting the form pipeline,
// because "a form pipeline is its own layer" (engine.go:340-342). So is authentication:
//
//	UserPrivilegeSet::logged_in()          PersistentObjectManager::getData("USER_ID") != NULL
//	                                       (UserPrivilegeSet.php:22-25)
//	UserPrivilegeSet::authenticate($l,$p)  new UserDAO(); authenticateUser($l,$p); and, only when
//	                                       that returns non-NULL, setData("USER_ID", $privileges)
//	                                       (UserPrivilegeSet.php:14-20)
//
// UserDAO is lib/UserAuthentication/UserDAO.php and DataConnection is
// lib/DatabaseDrivers/MySQL/DataConnection.php — the auth and MySQL-driver layers, NOT invocators/
// tags/. #316's DEPENDS ON list names four ENGINE units and no auth unit, and the ticket says "Port
// ONE unit of congruency to Go. ONE. ... Do not port anything outside this unit." So this file ports
// Login's LOGIC and leaves UserDAO's SQL to the unit that owns it.
//
// WHAT THAT LAYER ACTUALLY DOES, MEASURED — because "it's a seam" must not hide a live dependency.
// It is NOT the dead MySQL path it reads like. DataConnection::open (DataConnection.php:30-35) is:
//
//	if (defined('CONGRUENCY_SQLITE')) { $this->pdo = new PDO('sqlite:' . CONGRUENCY_SQLITE); }
//	else                              { $this->pdo = new PDO('mysql:host=' . MYSQL_SERVER . ...); }
//
// boot/configure.php:42 ALWAYS defines CONGRUENCY_SQLITE, so UserDAO's MySQL-flavoured SELECT
// (UserDAO.php:20-24) runs against the STATE SQLITE — the same congruency.sqlite every other ported
// tag reads. Probed this session (immutable=1, zero sidecar files): all three tables it joins are
// PRESENT, the statement PARSES AND RUNS, and Login_Password holds ONE row — admin/congruency. So the
// accept arm is genuinely reachable on the live app, and the reject arm is a zero-row SELECT, not a
// failed one. That is why the two are documented as measured facts below and not as a dead branch.
//
// ── WHAT THE DEFAULT (nil) CONTEXT REPRODUCES, AND THE ONE INPUT IT DOES NOT ────────────────────
//
// The registry factory builds every tag with a nil LoginContext, which is: no $_POST, and no
// authenticator. That is the state of BOTH the gate and the live Go server, and it is faithful for
// every input this session drove EXCEPT one. Stated exactly, so nothing is claimed that was not
// measured (each row was run against the live PHP on 127.0.0.1:8899, sliced with TagList's own
// anchors):
//
//	INPUT                          PHP                       Go, nil ctx        AGREE?
//	GET (the gate)                 login_form('')  242B      login_form('')     YES  <- the gate
//	POST login=alice password=x    login_failed    313B      login_failed       YES
//	POST login=admin password=x    login_failed    313B      login_failed       YES
//	POST login=0    password=p     login_failed    305B      login_failed       YES
//	POST login=' '  password=p     login_failed    305B      login_failed       YES
//	POST login=<b>&x'"             login_failed    317B      login_failed       YES  (raw, unescaped)
//	POST login=bob  (no password)  login_failed    309B      login_failed       YES
//	POST login=''   password=x     login_form('')  242B      login_form('')     YES
//	POST password=x (no login)     login_form('')  242B      login_form('')     YES
//	POST login=admin password=congruency   "" + redirect     login_failed       *** NO ***
//
// THE LAST ROW IS THE ONE HONEST GAP, and it is the auth layer's, not this tag's: with no ported
// UserDAO there is nothing to check a password against, so the nil authenticator rejects every
// credential. That is exactly what the live PHP does for every credential but one — the reject arm
// is a real, constantly-taken PHP branch, not a Go fudge — but for admin/congruency the PHP accepts
// and this file, alone, cannot. A LoginContext with a Session closes it with no edit here; that is
// what the seam is for, and porting UserDAO to fill it is a separate unit.
//
// The gap is UNREACHABLE from both of this unit's live surfaces, which is why it does not move the
// gate: the gate is a GET, and server.go's handleTagsPage passes only r.URL.Query() to RenderTag
// (server.go:801) — $_POST is never plumbed into this package at all, by any caller, today. A POST to
// the GO server's ?page=tags&tag=Login therefore renders login_form('') where PHP renders
// login_failed. That is a server.go wiring gap, not a defect in this port: fixing it means teaching
// handleTagsPage to parse a form and build a LoginContext, and server.go is not this ticket's
// deliverable ("touch nothing else"). Reported here rather than papered over.
//
// ── PHP WARNINGS ARE REAL BYTES, AND THEY LAND OUTSIDE THIS UNIT'S SLICE ────────────────────────
//
// Login.php:39 reads $_POST['password'] with NO isset guard — the isset at :27 covers 'login' only,
// and the comment at :26 ("try removing the isset portion, see what happens") is the author noticing.
// On PHP 8 a POST carrying login but no password therefore raises:
//
//	Warning: Undefined array key "password" in .../invocators/tags/login/Login.php on line 39
//
// and passes NULL to authenticate(), which (string)-casts to "". postStr below returns "" for an
// absent key, which is that same value.
//
// The warning IS emitted with display_errors on, and it is really in the response — measured, the
// page grows from 6849B to 7056B. But it is printed the INSTANT it happens, whereas the page is
// buffered into Controller::$display_string and printed once at the end (Controller.php:21), so the
// warning lands ABOVE <!DOCTYPE html> — OUTSIDE the tagout slice, and outside this tag's bytes.
// Confirmed by measurement: the sliced body for `POST login=bob` is 309B of clean login_failed. Go
// has no counterpart to a PHP warning and this file emits none; that divergence is real at the PAGE
// level and empty at THIS unit's level, which is the level the gate measures.
//
// ── THE GATE — WHAT WAS RUN, AND WHAT IT MEASURED ───────────────────────────────────────────────
//
// The ticket's diff is the two servers' full pages:
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=Login') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=Login')
//
// THAT DIFF CANNOT BE EMPTY, AND NOT BECAUSE OF THIS UNIT. It was RUN this session, both servers up,
// and it is NON-EMPTY: php 6778B vs go 4070B, 64 diff lines. The Go server does not reproduce the PHP
// CMS page chrome and says so in the bytes it serves — "the CMS Controller::control() page chrome is
// still not reproduced here" (its own #280 banner), matching server.go:39-43 and :64-66 ("NOT
// claimed: that the page's BYTES match PHP").
//
// The residue is chrome, and that was measured rather than asserted. The 8900 process is an older
// build that predates this file, so it fills the Login slot with engine.go's notPorted notice;
// substituting THIS unit's real 242 bytes into that slot and re-diffing gives 4103B and 53 diff
// lines — still NON-EMPTY. So the diff is non-empty with this unit and non-empty without it: the 11
// lines between the two runs are the only part it measures here, and no possible render of this tag
// empties it. Per the ticket ("if you cannot make a diff here run against THIS unit, say so on the
// ticket rather than settling on a diff that would be empty even with the unit unimplemented") that
// is reported, not settled for. This unit's 242 bytes ARE present, byte-identical, on both sides of
// that patched comparison — which is the fact the diff is too coarse to show, and which the gate
// below shows directly.
//
// THE GATE THAT DOES EXERCISE THIS UNIT is the repo's own, built by #282 for exactly this
// (equivalence_test.go:9-13). It cuts the tag's OWN bytes out of the live PHP page with TagList.php's
// own anchors, brackets the Go render with two PHP fetches so a concurrent write reports VOLATILE
// instead of false-failing, and compares byte for byte over the SAME db. Registering Login moves it
// from that harness's skip list into its measured set with no edit to it:
//
//	cd congruency-go && go test ./tags/ -run 'TestTagEquivalence/Login' -v -count=1
//	    --- PASS: TestTagEquivalence/Login    IDENTICAL: 242B byte-for-byte
//
// The 242 bytes are login_form(''), and they are the whole of this tag's live render:
//
//	\n<form method='POST'>\n<label for='login'>Login: </label>\n
//	<input type='text' name='login' value=''><br />\n<label for='password'>Password: </label>\n
//	<input type='password' name='password'><br />\n<input type='submit' value='login'><br />\n</form>\n
//
// ALSO RUN THIS SESSION (go1.26.5; `go build ./...`, `go vet ./...` exit 0, `gofmt -l` clean on this
// file):
//
//   - SelfCheck() — GREEN with Login registered. #281 made its registry invariants subset-and-floor
//     rather than equality precisely so a new <Tag>.go keeps them green with no edit to engine.go
//     (engine.go:132-136). Confirmed by running it, not assumed.
//   - THE WHOLE #282 SWEEP, not just this tag — run because a new init() executes inside every other
//     tag's process too, so the sweep is what proves this file cost no sibling its render. 18/18
//     registered tags byte-identical, 0 differ, 0 volatile.
//   - The nine PHP-vs-Go rows in the table above, driven over the SAME live db: all nine SAME.
//
// THE TWO ARMS THE PAGE CANNOT SHOW WERE MEASURED ANYWAY, and they had to be: a successful login's
// Redirect overwrites the page (above), so ?page=tags&tag=Login can never display the bytes the
// logged-in arm returns — there is no tagout in the response to slice. Asking the HTTP surface would
// have left login_success() shipping as "derived from the source", unmeasured. It did not have to:
// PHP is duck-typed, so including the REAL invocators/tags/login/Login.php with stub UserPrivilegeSet
// and Redirect classes — the same seam this file's LoginContext is, on the other side of the port —
// measures get_document()'s RETURN VALUE directly, which is the thing this port must match. Both
// engines were then driven over the identical five cases (php 8.4.23 vs go1.26.5), comparing the
// (string) cast TagList.php:68 applies, the Redirect enqueues, and the authenticate calls.
//
// THE TWO SIDES ARE SYMMETRIC, which is what makes this a measurement and not a demonstration: the
// PHP stub and the Go LoginSession implement the SAME contract (store USER_ID only for the one
// credential the live Login_Password row holds) and are handed to the real class on each side. So
// this table drives the seam DELIBERATELY SUPPLIED — it is not the nil-context table above and does
// not contradict it. It isolates exactly the thing that is this unit's: Login's own branch logic,
// with the auth layer held identical on both sides rather than absent from one.
//
//	CASE                            PHP                              GO            VERDICT
//	GET, not logged in              242B, no redirect, no auth       identical     SAME
//	already logged in               NULL->"", redirect, NO auth call identical     SAME
//	POST admin/congruency (accept)  NULL->"", redirect, auth once    identical     SAME
//	POST admin/wrong    (reject)    313B, no redirect, auth once     identical     SAME
//	POST while logged in            NULL->"", redirect, NO auth call identical     SAME
//	                                *** EVERY DIRECT ROW IDENTICAL ***
//
// Read together with the nil-context table, the two say something stronger than either alone: the
// ONLY thing the nil default lacks is a password oracle. Given one, every branch — including the two
// the HTTP surface cannot show — is byte-identical to the PHP, and the "*** NO ***" row above closes.
//
// Row 2 and row 5 are the ones worth having: they pin that logged_in() SHORT-CIRCUITS the whole POST
// branch (Login.php:22 wins before :27 is reached), so a session that is already authenticated never
// re-authenticates however the request is posted. A port that tested $_POST first would pass every
// other row here and fail those two, silently re-running authenticate on every page load.
//
// ── SIDE EFFECTS: NONE, AND THE TAG CANNOT HAVE ANY ─────────────────────────────────────────────
//
// docs/PLAYBOOK.md Theme 3 says prove it, before/after, in isolation — do not assume the happy path.
// This tag opens no database, reads no file and runs no SQL: it has no openDB call, and its only
// data plane is the LoginContext its caller hands it. With the nil context the registry supplies, it
// concatenates constants. Probed in isolation this session: the state directory listed before and
// after a ?page=tags&tag=Login render holds the same entries with the same sizes and mtimes (no
// -wal/-shm), and Login_Password/User_Group_Mappings/Group_Privileges are unmoved at one row each.
// The auth SELECT that WOULD touch the db lives behind the seam, in the layer this unit does not
// port; even a caller that supplies one only ever makes it SELECT (UserDAO.php:17-28 reads).

import "net/url"

// init self-registers the tag. This is the whole wiring step (#281; engine.go:1293-1307). The
// factory passes a nil LoginContext — see "WHAT THE DEFAULT (nil) CONTEXT REPRODUCES" in the file
// header for exactly what that is faithful to, and the one input it is not.
func init() {
	Register("Login", func(e *Engine, a *TagArguments) Tag { return NewLoginTag(e, a, nil) })
}

// LoginSession is UserPrivilegeSet's static surface as Login uses it
// (lib/UserAuthentication/UserPrivilegeSet.php). It is an interface, not a port, because the class
// behind it reaches UserDAO and the MySQL DataConnection — a different layer, and a different unit.
// See "THE DEPENDENCY" in the file header.
//
// The two methods are ORDER-DEPENDENT and that is the PHP's shape, not a convenience: Authenticate
// MUTATES the state LoggedIn reads (it setData()s USER_ID), so Login.php:39-40 calls Authenticate and
// then immediately asks LoggedIn again. An implementation whose Authenticate does not affect its
// LoggedIn will always take the failure arm — which is precisely what the live PHP does for a
// credential that does not match a row, so that is a faithful implementation, not a broken one.
type LoginSession interface {
	// LoggedIn is UserPrivilegeSet::logged_in() (UserPrivilegeSet.php:22-25):
	// `return (PersistentObjectManager::getData("USER_ID") != NULL);`
	LoggedIn() bool

	// Authenticate is UserPrivilegeSet::authenticate($login,$password)
	// (UserPrivilegeSet.php:14-20). It returns NOTHING in the PHP — its whole effect is the
	// conditional setData("USER_ID", $userPrivileges), which is why this returns nothing either and
	// the caller re-reads LoggedIn. A rejected credential leaves the state untouched: the PHP's
	// isset($userPrivileges) guard means a zero-row SELECT stores nothing at all.
	Authenticate(login, password string)
}

// LoginContext is the ambient per-request state Login reads and neither Engine nor Config carries:
// PHP's $_POST superglobal and the POM-backed UserPrivilegeSet. A nil *LoginContext is the honest
// "no POST, no authenticator" state — which is what the gate and the live Go server both are.
//
// It is a struct rather than three Config fields because engine.go is not #316's deliverable to
// edit; a caller reaches it through NewLoginTag (see that function for how to wire one).
type LoginContext struct {
	// Post is $_POST. A nil Values is an empty $_POST, which is exactly what a GET is.
	Post url.Values

	// Session is UserPrivilegeSet. A nil Session is "no authenticator": LoggedIn is false and
	// Authenticate does nothing — the live PHP's own behaviour for every credential that misses.
	Session LoginSession

	// Redirect is Redirect::commandFactory (Redirect.php:13-19), called by login_success with
	// 'welcome'. It is a HOOK, not a return value, because the PHP call ENQUEUES a command and emits
	// no bytes; nil means "no command queue", which is engine.go's divergence 3 and costs no byte.
	// See "THE DISCARDED RETURN" in the file header for what the PHP's queue does with it later.
	Redirect func(page string)
}

// LoginTag is Login (Login.php:8).
//
// args mirrors the PHP constructor's $arguments (Login.php:11-12) — and the PHP constructor is
// EMPTY: it does not even store the value. This tag takes no arguments, reads none, and no template
// embeds it, so the bare <<<Login>>> / gallery form is the only form there is. The field is kept
// (unread) to match every sibling port's shape and to accept the nil *TagArguments TagList.php:67's
// `new $sel(null)` passes — the shape the ?page=tags&tag=Login gate takes. e is likewise unread:
// this tag consults no engine state, no $_GET and no database.
type LoginTag struct {
	e    *Engine
	args *TagArguments
	ctx  *LoginContext
}

// NewLoginTag builds the tag over ctx. ctx may be nil, which is the registry's default and the state
// of both live surfaces (see the file header).
//
// This constructor is the seam a caller with a real session uses. The registry path cannot carry one
// — RenderTag builds its own Engine and passes nil — so a caller drives it through the engine's
// documented Lookup override (engine.go:877-880), which stands in for swapping TAG_LOADER in the POM:
//
//	e := tags.NewEngineWithQuery(cfg, get)
//	e.Lookup = func(e *tags.Engine, n string, a *tags.TagArguments) (tags.Tag, bool) {
//	    if n == "Login" {
//	        return tags.NewLoginTag(e, a, &tags.LoginContext{Post: r.PostForm, Session: mySession}), true
//	    }
//	    return nil, false // fall back to the registry via your own dispatch
//	}
//
// Nothing in engine.go changes to allow that; the seam already exists.
func NewLoginTag(e *Engine, args *TagArguments, ctx *LoginContext) *LoginTag {
	return &LoginTag{e: e, args: args, ctx: ctx}
}

// postIsset is `isset($_POST[k])` plus the value — the $_POST twin of engine.go's getIsset
// (engine.go:923-932), and deliberately the same rule, because $_POST and $_GET are populated by the
// same PHP machinery and read by the same idiom.
//
// A key present with an EMPTY value IS still set in PHP (login= makes isset($_POST['login']) true
// with the value ""), and Login.php:27 branches on exactly that distinction — which is why isset and
// the emptiness test are two separate conditions there, and two separate steps here.
//
// PHP takes the LAST value for a repeated scalar key (login=1&login=2 makes $_POST['login'] the
// string "2", since each assignment overwrites), so this returns the last value, as PHP does.
//
// NOT MODELLED, deliberately, because it cannot reach this function: PHP's ARRAY post (login[]=x)
// makes $_POST['login'] an array, and Login.php's raw interpolation renders it "Array" plus an
// "Array to string conversion" warning — measured on the live PHP this session, 313B. Go's
// url.Values keys that body under "login[]", not "login", so this branch is unreachable through this
// type rather than mis-rendered by it. Closing it would need a $_POST model richer than url.Values,
// which is the auth/request layer's shape to choose, not this tag's.
func (t *LoginTag) postIsset(k string) (string, bool) {
	if t.ctx == nil || t.ctx.Post == nil {
		return "", false
	}
	vs, ok := t.ctx.Post[k]
	if !ok || len(vs) == 0 {
		return "", false
	}
	return vs[len(vs)-1], true
}

// postStr is the read Login.php:39 makes for 'password': the value when set, "" when not.
//
// The "" is not a convenience default — it is PHP's own value. :39 reads $_POST['password'] with NO
// isset guard, so an absent key yields NULL (plus the warning quoted in the file header) and NULL
// (string)-casts to "" on the way into authenticate(). engine.go:499-500 spells the same cast.
func (t *LoginTag) postStr(k string) string {
	v, _ := t.postIsset(k)
	return v
}

// loggedIn is UserPrivilegeSet::logged_in() (UserPrivilegeSet.php:22-25) through the seam. No
// Session is no USER_ID in the POM, which is the PHP's own `getData("USER_ID") != NULL` -> false.
func (t *LoginTag) loggedIn() bool {
	if t.ctx == nil || t.ctx.Session == nil {
		return false
	}
	return t.ctx.Session.LoggedIn()
}

// GetDocument is Login::get_document() (Login.php:20-34):
//
//	$return_value=NULL;
//	if(UserPrivilegeSet::logged_in()){
//	    $return_value=$this->login_success();
//	}else{
//	    //try removing the isset portion, see what happens.
//	    if(isset($_POST['login']) && $_POST['login'] != '' ){
//	        $return_value = $this->authenticate();
//	    }else{
//	        $return_value = $this->login_form('');
//	    }
//	}
//	return $return_value;
//
// The `$return_value=NULL` initialiser at :21 is the empty string here: every arm assigns before the
// return, so the initialiser is dead in both languages, and Go's zero value for a string is already
// "". The NULL the logged-in arm assigns is NOT dead, and IS "" — see "THE DISCARDED RETURN".
//
// The emptiness test at :27 is ported as `!= ""`, which is exact rather than approximate. PHP 8's
// loose != compares two strings numerically ONLY when BOTH are numeric strings; the empty string is
// not numeric, so this is always a string comparison, and Go's != is the same comparison. The two
// edges were driven against the live PHP this session to be sure rather than merely reasoned: a
// login of "0" takes the AUTHENTICATE arm (305B of login_failed — so PHP holds "0" to be unequal to
// the empty string, which is the trap a TRUTHINESS port would fall into, since PHP's "0" is falsy),
// a login of one space takes it too (305B), and an empty login takes the FORM arm (242B).
//
// NO ERROR ARM, DELIBERATELY. Most tags in this package open with `defer catchThrowable(&out, "Tag")`
// because each of those PHP classes has its own `catch (\Throwable $e)` arm. Login.php has NO
// try/catch anywhere (Login.php:7-69), so there is no PHP branch for a catchThrowable to mirror and
// adding one would invent bytes the PHP cannot emit — the same reasoning bugreport.go records. Nor
// can anything here produce them: this function opens nothing, indexes no map unguarded and
// dereferences no pointer without a nil test; it concatenates constants and one caller-supplied
// string. (A throw from a tag IS caught one level up, by TagList.php:69-72's "This tag needs context
// to render standalone" arm — but that is TagList's byte, not Login's, and TagList is already ported.)
func (t *LoginTag) GetDocument() string {
	// :22-23 — logged in. login_success() returns NULL; (string)NULL is "".
	if t.loggedIn() {
		return t.loginSuccess()
	}
	// :27 — isset($_POST['login']) && $_POST['login'] != ''
	if login, ok := t.postIsset("login"); ok && login != "" {
		return t.authenticate() // :28
	}
	return t.loginForm("") // :30 — the gate's arm
}

// authenticate is Login::authenticate() (Login.php:37-46):
//
//	$return_value = NULL;
//	UserPrivilegeSet::authenticate($_POST['login'],$_POST['password']);
//	if(UserPrivilegeSet::logged_in()){
//	    $this->login_success();
//	}else{
//	    $return_value=$this->login_failed($_POST['login']);
//	}
//	return $return_value;
//
// Two ported quirks, neither of which moves a byte, both of which keep this the same shape as the
// PHP a reader will diff it against:
//
//  1. :41 DISCARDS login_success()'s result, where :23 assigns it. Reproduced by discarding here.
//     It cannot matter — login_success returns NULL and $return_value is already NULL — but the
//     PHP is the spec down to the arm. See "THE DISCARDED RETURN" in the file header.
//  2. :39 re-reads $_POST['login'] rather than taking the value the caller at :27 already tested,
//     and :43 reads it a third time. Reproduced (postStr is called again) — with no way to mutate
//     $_POST between the reads, all three see the same value, so this too is shape, not behaviour.
//
// The password read at :39 has no isset guard; see "PHP WARNINGS" in the file header for the byte
// that costs and where it lands.
func (t *LoginTag) authenticate() string {
	// :39 — the seam call. With no Session this is a no-op, which is the PHP's own behaviour for a
	// credential that matches no row: authenticateUser returns NULL and the isset() guard at
	// UserPrivilegeSet.php:16 stores nothing.
	if t.ctx != nil && t.ctx.Session != nil {
		t.ctx.Session.Authenticate(t.postStr("login"), t.postStr("password"))
	}
	// :40 — re-read, because :39 may have changed it.
	if t.loggedIn() {
		t.loginSuccess() // :41 — result DISCARDED, exactly as the PHP discards it
		return ""        // $return_value is still the NULL from :38; (string)NULL is ""
	}
	return t.loginFailed(t.postStr("login")) // :43
}

// loginSuccess is Login::login_success() (Login.php:49-51):
//
//	private function login_success(){
//	    Redirect::commandFactory('welcome');
//	}
//
// It returns "" because the PHP returns NULL — there is no return statement — and (string)NULL is "".
// The Redirect is enqueued, not printed; see "THE DISCARDED RETURN" in the file header for the whole
// cascade and why none of it is bytes at this level.
func (t *LoginTag) loginSuccess() string {
	if t.ctx != nil && t.ctx.Redirect != nil {
		t.ctx.Redirect(loginRedirectPage) // :50
	}
	return ""
}

// loginRedirectPage is the 'welcome' literal at Login.php:50 — the page key login_success redirects
// to. Named once so the constant and the comment cannot drift.
//
// Worth knowing, though it is the Controller's business and not this tag's: there is NO Documents row
// keyed 'welcome' in the live db, so the redirect resolves to DocumentDAO's "invalid" document and
// the user is shown "No such page" (measured this session — the 3133B page a successful login
// actually returns). That is a real defect in the PHP, in a layer this unit does not port; it changes
// no byte of THIS tag, whose successful render is "" either way.
const loginRedirectPage = "welcome"

// loginForm is Login::login_form($login) (Login.php:53-63), byte for byte:
//
//	"\n<form method='POST'>\n".
//	"<label for='login'>Login: </label>\n".
//	"<input type='text' name='login' value='$login'><br />\n".
//	"<label for='password'>Password: </label>\n".
//	"<input type='password' name='password'><br />\n".
//	"<input type='submit' value='login'><br />\n".
//	"</form>\n";
//
// Load-bearing bytes a reformat would silently break: the LEADING "\n" before <form>; the trailing
// space inside "Login: </label>"; every attribute SINGLE-quoted; the space in "<br />"; and the
// closing "\n" after </form> with none after the final <br /> of login_failed. With $login empty this
// is the 242 bytes the gate measures.
//
// $login IS NOT ESCAPED. That is the PHP's defect, ported deliberately — see "THE UNESCAPED $login"
// in the file header before changing this line. There is no esc() here and there must not be one.
func (t *LoginTag) loginForm(login string) string {
	return "\n<form method='POST'>\n" +
		"<label for='login'>Login: </label>\n" +
		"<input type='text' name='login' value='" + login + "'><br />\n" +
		"<label for='password'>Password: </label>\n" +
		"<input type='password' name='password'><br />\n" +
		"<input type='submit' value='login'><br />\n" +
		"</form>\n"
}

// loginFailed is Login::login_failed($login) (Login.php:65-67):
//
//	return $this->login_form($login) . "<br /><br />Your attempt to login as $login has failed.<br /><br />";
//
// So the form is re-rendered with the attempted login PRE-FILLED, then the notice appended. Note
// there is no newline between "</form>\n" and "<br />", and none at the end — the render simply
// stops. Measured: 313B for login=alice.
//
// $login is interpolated raw HERE TOO, and this is the second half of the same XSS: the value lands
// in element text as well as in the attribute above. Unescaped, deliberately.
func (t *LoginTag) loginFailed(login string) string {
	return t.loginForm(login) +
		"<br /><br />Your attempt to login as " + login + " has failed.<br /><br />"
}
