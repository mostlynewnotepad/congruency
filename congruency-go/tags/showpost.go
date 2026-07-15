package tags

// showpost.go — ticket #330, unit go-port:tags:tag:ShowPost.
//
// The Go port of ONE tag: invocators/tags/utilities/ShowPost.php — a debug probe that reports
// whether a 'loginform' key is present in $_POST and dumps $_POST's values. The app renders it
// standalone at ?page=tags&tag=ShowPost (TagList::scan finds it under TAGS_DIR, so that URL
// resolves), and no Document_Templates row embeds <<<ShowPost>>>, so that gallery URL is this
// unit's whole render surface.
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. THE PHP IS THE SPEC — where the two
// disagree THIS file is wrong.
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers and its self-registration (the init() below). Nothing in engine.go changes. engine.go's
// "NOT PORTED (35)" list names ShowPost at :197, and that entry is now stale — but that list is
// #226's prose snapshot, it is not a check, and it says so itself: PortedTags() "is the authority;
// this list is a copy" (engine.go:191-192). Several already-ported tags are stale there for the
// same reason (BugReport :194, CategoryPages/CategoryView :195, Login/Logout :196). The init()
// below is what actually puts ShowPost in PortedTags().
//
// Every identifier here is ShowPost*/showPost*-named, so it cannot collide with the sibling tag
// ports still to land. Checked this session: no other file in the package declares any of these
// names, and none declares a print_r/array_values helper this file could have reused.
//
// ── THE WHOLE TAG ───────────────────────────────────────────────────────────────────────────────
//
// ShowPost.php is 32 lines. The class (ShowPost.php:8-30) is quoted ENTIRE — nothing is elided,
// because the argument that follows turns on one line that is easy to skim past:
//
//	class ShowPost implements Tag_Interface{                           // :8
//
//	    private $command;                                              // :10 declared, never read
//
//	    public function __construct($arguments){                       // :12 body is EMPTY
//
//	    }                                                              // :14
//
//	    public function get_document(){                                // :16
//	    $result = '';                                                  // :17 dead: both arms assign
//
//	        if(isset($_POST['loginform'])){                            // :19
//	            $result = "<br>loginform data is in post<br>";          // :20
//	        }else{
//	            $result = "<br>loginform data is NOT in post<br>";      // :22
//	        }
//
//	        print_r(array_values($_POST));                             // :26  ← PRINTS. Does not return.
//
//	        return $result;                                            // :28
//	    }                                                              // :29
//	}                                                                  // :30
//
// Three facts fall straight out of the quote, and they decide the whole port:
//
//  1. THE CONSTRUCTOR IGNORES ITS ARGUMENT. Its body is empty (:12-14) and $command (:10) is never
//     read or written. So <<<ShowPost>>>, <<<ShowPost(post_42)>>> and TagList's `new $sel(null)`
//     (TagList.php:67) all produce the identical object. The tag HAS no argument forms to drive —
//     the ticket's "drive each argument form the templates use" is vacuous here, and no template
//     embeds this tag anyway. (tests/parser fixtures in the tournament tree do show a
//     "<<<ShowPost(post_42)>>>" case, but those fixture files exercise the PARSER's generic
//     argument handling; they say nothing about this class, which discards what the parser hands
//     it.)
//
//  2. IT HAS NO DEPENDENCIES. No DB, no session, no PersistentObjectManager, no constants — it
//     reads $_POST and nothing else. So it has no degraded mode to reproduce: the ticket's "a tag
//     that degrades gracefully against a missing dependency must degrade IDENTICALLY in Go" has no
//     force here because there is no dependency to miss. It also cannot throw, so TagList's
//     try/catch around get_document (TagList.php:66-72) never fires for it and its
//     "This tag needs context to render standalone" arm is unreachable for ShowPost. Correctly,
//     tools/tag_selfcheck.py names no dependency for ShowPost — it names ShowPost nowhere at all.
//
//  3. print_r PRINTS; IT DOES NOT RETURN. This is the one that decides every byte, and it gets its
//     own section.
//
// ── THE DECISIVE FACT: print_r's BYTES ARE NOT THE TAG'S BYTES ──────────────────────────────────
//
// print_r($v) with no second argument WRITES TO THE OUTPUT STREAM and returns true; it is not part
// of $result, and nothing splices it into the string this tag returns. So the tag's OWN bytes —
// the bytes the engine substitutes for <<<ShowPost>>>, and the bytes a tag port is measured on —
// are EXACTLY the :28 return value, and nothing else:
//
//	$_POST has 'loginform'  ->  "<br>loginform data is in post<br>"
//	otherwise               ->  "<br>loginform data is NOT in post<br>"
//
// That is not an inference from print_r's manual page alone; it is what the two callers do with
// this tag's return value:
//
//	TagList.php:68   $out .= (string)$obj->get_document();   // ONLY the return value is appended
//
// TagList concatenates the RETURN into the gallery's $out. print_r never touches $out. So in the
// assembled page, the tag's slice — CHROME + gallery + <the tag> + TAIL, cut between TagList's
// :62 heading and its :76 "</div>\n" close, which is precisely how the tag-equivalence harness
// measures a port (congruency-go/tags/equivalence_test.go, ticket #282) — contains the <br>
// string and NOT ONE BYTE of print_r's dump.
//
// WHERE print_r's BYTES ACTUALLY GO. They are not lost; they land somewhere else entirely, and
// tracing that is what proves they are outside the slice rather than merely assumed to be:
//
//	boot/router.php    ob_start();                       // :16 — ONE buffer; order in it is the
//	                                                     //       chronological order of the writes
//	lib/Controller/Controller.php
//	                   self::display($post_validated);   // :20 — RENDERS. get_document() runs HERE,
//	                                                     //       so print_r writes to the buffer HERE
//	                   print(self::$display_string);     // :21 — the page is written AFTER
//
// display() (:30-40) builds the string via $document->__toString() (:38) and does not print it;
// control() prints it on the next line. So print_r's dump is written to the buffer BEFORE the
// entire page, and `curl '?page=tags&tag=ShowPost'` returns a body shaped like:
//
//	Array
//	(
//	)
//	<!doctype html> ... the whole CMS page, whose gallery slice holds the <br> string ...
//
// The dump is at the TOP of the response, above the doctype — not where the tag was invoked. This
// is a PHP defect (a debug print_r left in a shipped tag emits stray text above every page that
// renders it), and per the ticket it is ported faithfully rather than "improved": nothing here
// tries to move the dump inline, suppress it, or fold it into the return value.
//
// ── HOW THIS PORT REPRESENTS THAT, AND THE ONE THING IT CANNOT ──────────────────────────────────
//
// Tag is `interface { GetDocument() string }` (engine.go:852-854). A tag can return a string. It
// has NO output stream — nothing in the interface, the Engine, or RenderTag (engine.go:4147-4160,
// which returns `tag.GetDocument()` and nothing else) can express "and also write these bytes to
// the top of the response". ShowPost is the first and only tag to need one: it is the only tag
// whose get_document prints (checked this session across every file under invocators/tags:
// ShowPost.php and SemanticSearch.php are the only two that print or echo at all, and
// SemanticSearch's three echoes — :344, :352, :364 — sit OUTSIDE its class, which closes at :336,
// in a block guarded by `php_sapi_name() === 'cli'` (:339) and headed "CLI self-test hooks"
// (:338). They cannot run under the web SAPI, and no tag's get_document reaches them).
//
// So this port splits the tag's two effects the same way the PHP does:
//
//	RETURN VALUE  -> GetDocument's string.        Measured by the gate. Reproduced exactly.
//	print_r DUMP  -> ShowPostContext.Echo(...).   An explicit, named out-of-band sink.
//
// GetDocument therefore returns ONLY the <br> string. Appending the dump to the return instead
// would be the tempting "obvious" port and it would be WRONG TWICE: it would corrupt the tag's
// slice with bytes the PHP's slice does not contain (the gate would fail on bytes the PHP never
// put there), and it would put the dump BELOW the doctype when the PHP puts it ABOVE.
//
// WHAT IS HONESTLY NOT REPRODUCED. The registry factory (init(), below) builds ShowPost with a nil
// context, which is: an empty $_POST and a nil Echo. A nil Echo DROPS the dump. So at the
// whole-response level a Go server rendering this tag emits no "Array\n(\n)\n" above its page,
// while the PHP does. That gap is real and is named here rather than papered over. Two things
// bound it, and neither is an excuse — they are the reason the gate is still meaningful:
//
//   - It cannot affect the tag-slice gate, because the dump was never in the slice.
//   - The whole-response bytes already diverge for EVERY tag, by this port's own admission and by
//     design, not because of this file: server.go's handleTagsPage wraps the engine's render in
//     its own frame and says so in the emitted HTML — "the CMS Controller::control() page chrome
//     is still not reproduced here" (server.go:820-823). Reproducing Controller's chrome is not
//     this unit's ticket, and this file must not invent it.
//
// A caller that DOES reproduce the whole response can pass an Echo that writes to the response
// prologue and get the PHP's byte order back, without this file guessing at a transport it cannot
// see. That is why the sink exists and is exported rather than being a dropped side effect.
//
// ── WHY $_POST IS NOT url.Values HERE ───────────────────────────────────────────────────────────
//
// login.go models $_POST as url.Values (login.go:328) and that is right THERE: Login only ever asks
// "isset($_POST['login'])" and reads one value, and a map answers both. ShowPost is different — it
// calls array_values($_POST) and print_r's the result, so it renders $_POST's ORDER and its SHAPE,
// and url.Values can express neither:
//
//   - ORDER. A PHP array is ordered by insertion (the order the fields arrive in the body);
//     array_values() reindexes to 0,1,2… IN THAT ORDER. Go's map has no order, and ranging one is
//     deliberately randomized — the same $_POST would print_r differently run to run.
//   - SHAPE. url.Values maps a key to []string, which conflates two DIFFERENT PHP results:
//     "a=1&a=2" gives $_POST['a'] === "2" (one key, LAST wins, a scalar), while "a[]=1&a[]=2"
//     gives $_POST['a'] === ['1','2'] (one key, a NESTED ARRAY, which print_r indents).
//
// So $_POST is modelled as what it is — an ordered list of key => (string | nested array) pairs.
// This file deliberately ships NO parser from a raw body into that shape: PHP's rules for
// "a[b][c]=1" are intricate, no caller plumbs $_POST into this package today (login.go:168 records
// the same finding for Login: "$_POST is never plumbed into this package at all, by any caller"),
// and a half-right parser nobody calls would be a liability, not a feature. A caller that has a
// real $_POST builds the pairs in request order and this file renders them exactly.
//
// ── THE GATE, AND WHAT COULD NOT BE RUN ─────────────────────────────────────────────────────────
//
// The ticket's gate is a byte diff of the PHP and Go renders of ?page=tags&tag=ShowPost on ports
// 8899/8900. IT COULD NOT BE RUN IN THIS WORKTREE, and this file does not pretend otherwise:
// there is NO php binary (tooling/congruencey-harness/php/php does not exist; `which php` finds
// none anywhere on this machine) and NO state database — both are gitignored, which is the same
// wall equivalence_test.go's header documents for every tag unit from #246 on. With no PHP process
// there is no 8899 to curl, so the diff cannot be produced, empty or otherwise. Reporting a
// contrived empty diff here would be reporting a diff that is empty for a reason that has nothing
// to do with this unit — which is exactly what the ticket forbids. What WAS run this session is
// recorded on the ticket: the package builds, and the assertions in this file's own checks pass.
//
// When a php binary and a state db are present, the gate for this unit is the #282 harness —
// `cd congruency-go && go test ./tags/ -run TestTagEquivalence -v` — which cuts ShowPost's slice
// out of the live PHP page and compares it to RenderTag's bytes. That is the diff that actually
// exercises THIS unit; the raw full-page curl diff cannot be empty for ANY tag today, ShowPost
// included, because of the server.go chrome gap named above.

import (
	"strconv"
	"strings"
)

// init registers ShowPost. This is the line that adds "ShowPost" to PortedTags(), which
// engine.go:191-192 names as the authority for what is ported.
func init() {
	Register("ShowPost", func(e *Engine, a *TagArguments) Tag { return NewShowPostTag(e, a, nil) })
}

// ShowPostPair is one entry of a PHP array: a key, and a value that is either a string or a
// nested ShowPostArray. Value nil models PHP NULL — the one value isset() reports as NOT set.
type ShowPostPair struct {
	Key   string
	Value any // string | ShowPostArray | nil
}

// ShowPostArray models a PHP array: ORDERED key => value pairs with unique keys. It is what
// $_POST is. Order is significant — it is the order array_values() reindexes into and the order
// print_r renders — so it is a slice, not a map. See "WHY $_POST IS NOT url.Values HERE" above.
type ShowPostArray []ShowPostPair

// ShowPostContext is everything ShowPost reads or writes that it does not own. Both fields are
// optional; the zero context is the gate's shape (an empty $_POST, a dropped dump).
type ShowPostContext struct {
	// Post is $_POST, in request order. Nil is an empty $_POST — which is what a GET is, and so
	// what the gallery gate at ?page=tags&tag=ShowPost renders.
	Post ShowPostArray

	// Echo receives the bytes print_r(array_values($_POST)) writes to the output stream
	// (ShowPost.php:26). It is NOT part of the tag's return value, and must not be concatenated
	// into one: in the PHP these bytes land at the TOP of the response, above the doctype, and
	// never inside the tag's slice. See "THE DECISIVE FACT" above. Nil drops them.
	Echo func(string)
}

// ShowPostTag is ShowPost.php's class. e and args are held to mirror the package's tag shape; the
// PHP reads neither (its constructor body is empty and $command is dead), so neither is read here.
type ShowPostTag struct {
	e    *Engine
	args *TagArguments
	ctx  *ShowPostContext
}

// NewShowPostTag is `new ShowPost($arguments)` (ShowPost.php:12-14) — which stores nothing,
// because the PHP constructor's body is empty. ctx may be nil.
func NewShowPostTag(e *Engine, args *TagArguments, ctx *ShowPostContext) *ShowPostTag {
	return &ShowPostTag{e: e, args: args, ctx: ctx}
}

// post is $_POST. A nil context or nil Post is the empty superglobal.
func (t *ShowPostTag) post() ShowPostArray {
	if t.ctx == nil {
		return nil
	}
	return t.ctx.Post
}

// postIsset is isset($_POST[$k]): the key exists AND its value is not NULL. The nil-Value check is
// not pedantry — isset() is the one array test that reports false for a key that IS present.
func (t *ShowPostTag) postIsset(k string) bool {
	for _, p := range t.post() {
		if p.Key == k {
			return p.Value != nil
		}
	}
	return false
}

// echo writes print_r's bytes to the out-of-band sink, or drops them when there is none.
func (t *ShowPostTag) echo(s string) {
	if t.ctx != nil && t.ctx.Echo != nil {
		t.ctx.Echo(s)
	}
}

// The two results, verbatim from ShowPost.php:20 and :22. Note "<br>" — unclosed, not "<br />" as
// login.go's form uses. That is the PHP's own inconsistency between two tags, and it is copied
// exactly rather than tidied.
const (
	showPostInPost    = "<br>loginform data is in post<br>"
	showPostNotInPost = "<br>loginform data is NOT in post<br>"
)

// GetDocument is ShowPost::get_document() (ShowPost.php:16-29).
//
// The order of the two effects is the PHP's: the dump is printed BEFORE the return, which is why
// the echo call sits below the branch and above the return, exactly as at :26 and :28. (For this
// tag the order is unobservable — the return value cannot depend on the dump — but it is free to
// keep, and a reader diffing this against the PHP should find the same sequence.)
func (t *ShowPostTag) GetDocument() string {
	// $result = ''; at :17 is dead — both arms below assign — so it is not reproduced as a write.
	result := showPostNotInPost // :22, the else arm and the gate's arm
	if t.postIsset("loginform") {
		result = showPostInPost // :20
	}

	t.echo(showPostPrintR(showPostArrayValues(t.post()))) // :26 — PRINTS, not returned

	return result // :28 — the tag's OWN bytes: this string alone
}

// showPostArrayValues is array_values($a): the values in order, reindexed to 0,1,2… as string
// keys, which is how print_r renders an integer key. It reindexes the TOP level only — a nested
// array keeps its own keys, exactly as PHP's does.
func showPostArrayValues(a ShowPostArray) ShowPostArray {
	out := make(ShowPostArray, 0, len(a))
	for i, p := range a {
		out = append(out, ShowPostPair{Key: strconv.Itoa(i), Value: p.Value})
	}
	return out
}

// showPostPrintR is print_r($v) — the string PHP writes to the output stream.
//
// This is a port of PHP's own algorithm (ext/standard/var.c: php_print_zval_r_to_buf and its
// print_hash), not an approximation of what its output "looks like", because the exact bytes are
// the contract:
//
//	array  ->  "Array\n" then print_hash at the CURRENT indent
//	scalar ->  the value cast to string, raw and UNESCAPED (print_r does not escape; $_POST values
//	           reach the page as-is, which is faithfully reproduced here). A real $_POST holds only
//	           strings, for which this is the identity; the cast is delegated to the package's own
//	           phpString (engine.go:497-523) rather than re-derived here, so a caller that supplies
//	           a NULL (-> "") or any other scalar gets THIS port's single, audited (string) cast.
//
// print_hash(indent) writes:
//
//	<indent spaces> "(\n"
//	  for each element:  <indent+4 spaces> "[" key "] => " <value at indent+8> "\n"
//	<indent spaces> ")\n"
//
// The indent+8 for a nested value, against indent+4 for its own "[key] =>" line, is what produces
// print_r's two signature oddities — a nested array's parens sit deeper than its key, and each
// nested array is followed by a BLANK line (its print_hash ends in ")\n" and the element loop then
// adds its own "\n"). Both are reproduced; both are checked by ShowPostSelfCheck below.
//
// The gate's case is the empty array, which bottoms out as "Array\n" + "(\n" + ")\n":
//
//	Array
//	(
//	)
func showPostPrintR(v any) string {
	var b strings.Builder
	showPostPrintRTo(&b, v, 0)
	return b.String()
}

func showPostPrintRTo(b *strings.Builder, v any, indent int) {
	switch x := v.(type) {
	case ShowPostArray:
		b.WriteString("Array\n")
		showPostPrintHash(b, x, indent)
	default:
		// Every non-array value, including nil (PHP NULL, which prints as nothing). print_r and
		// the (string) cast agree on scalars, so this reuses phpString rather than restating it.
		b.WriteString(phpString(x))
	}
}

func showPostPrintHash(b *strings.Builder, a ShowPostArray, indent int) {
	pad := strings.Repeat(" ", indent)
	b.WriteString(pad)
	b.WriteString("(\n")
	for _, p := range a {
		b.WriteString(strings.Repeat(" ", indent+4))
		b.WriteString("[")
		b.WriteString(p.Key)
		b.WriteString("] => ")
		showPostPrintRTo(b, p.Value, indent+8)
		b.WriteString("\n")
	}
	b.WriteString(pad)
	b.WriteString(")\n")
}

// ShowPostSelfCheck returns a non-empty slice of failure descriptions if any invariant this port
// stands on is broken. It performs NO I/O — no DB, no network, no PHP — so it runs anywhere,
// which is the point: this unit's real gate needs a php binary this worktree does not have, and
// these are the claims that CAN be checked without one. It is the mirror of engine.go's SelfCheck
// habit, kept ShowPost-local so it cannot perturb that function.
func ShowPostSelfCheck() []string {
	var fails []string
	fail := func(what, got, want string) {
		fails = append(fails, what+": got "+showPostQuote(got)+", want "+showPostQuote(want))
	}

	// 1. The gate itself: no context at all -> the else arm, byte for byte.
	if got := (&ShowPostTag{}).GetDocument(); got != showPostNotInPost {
		fail("nil-context GetDocument (the gallery gate)", got, showPostNotInPost)
	}

	// 2. An empty $_POST is the same thing — and the dump it prints is print_r(array()).
	var dump []string
	tag := NewShowPostTag(nil, nil, &ShowPostContext{Echo: func(s string) { dump = append(dump, s) }})
	if got := tag.GetDocument(); got != showPostNotInPost {
		fail("empty-$_POST GetDocument", got, showPostNotInPost)
	}
	if len(dump) != 1 {
		fails = append(fails, "empty-$_POST: print_r must be echoed exactly once")
	} else if want := "Array\n(\n)\n"; dump[0] != want {
		fail("empty-$_POST print_r", dump[0], want)
	}

	// 3. 'loginform' present -> the other arm. Its VALUE is irrelevant; only isset() is asked.
	post := ShowPostArray{{Key: "loginform", Value: ""}}
	if got := (&ShowPostTag{ctx: &ShowPostContext{Post: post}}).GetDocument(); got != showPostInPost {
		fail("loginform-present GetDocument", got, showPostInPost)
	}

	// 4. isset() is false for a PRESENT key whose value is NULL.
	nullPost := ShowPostArray{{Key: "loginform", Value: nil}}
	if got := (&ShowPostTag{ctx: &ShowPostContext{Post: nullPost}}).GetDocument(); got != showPostNotInPost {
		fail("loginform-present-but-NULL GetDocument", got, showPostNotInPost)
	}

	// 5. The dump is NEVER part of the return value. This is the invariant the whole port turns
	//    on: TagList.php:68 appends only the return, so a dump leaking into it would corrupt the
	//    tag's slice with bytes the PHP's slice does not contain.
	leak := NewShowPostTag(nil, nil, &ShowPostContext{
		Post: ShowPostArray{{Key: "loginform", Value: "x"}, {Key: "other", Value: "y"}},
	})
	if got := leak.GetDocument(); strings.Contains(got, "Array") {
		fails = append(fails, "the print_r dump leaked into GetDocument's return value: "+showPostQuote(got))
	}

	// 6. array_values reindexes in order, and print_r renders scalars at one indent level.
	var d2 []string
	t2 := NewShowPostTag(nil, nil, &ShowPostContext{
		Post: ShowPostArray{{Key: "loginform", Value: "x"}, {Key: "z", Value: "y"}},
		Echo: func(s string) { d2 = append(d2, s) },
	})
	t2.GetDocument()
	if want := "Array\n(\n    [0] => x\n    [1] => y\n)\n"; len(d2) != 1 || d2[0] != want {
		got := ""
		if len(d2) == 1 {
			got = d2[0]
		}
		fail("two-scalar print_r", got, want)
	}

	// 7. A nested array (what "a[]=1&a[]=2" makes) keeps its own keys, indents deeper than its
	//    own "[key] =>" line, and is followed by print_r's signature BLANK line.
	nested := ShowPostArray{{Key: "a", Value: ShowPostArray{{Key: "0", Value: "1"}, {Key: "1", Value: "2"}}}}
	wantNested := "Array\n(\n    [0] => Array\n        (\n            [0] => 1\n            [1] => 2\n        )\n\n)\n"
	if got := showPostPrintR(showPostArrayValues(nested)); got != wantNested {
		fail("nested-array print_r", got, wantNested)
	}

	// 8. Values are raw: print_r does not escape, so HTML in a POST value reaches the page as-is.
	raw := ShowPostArray{{Key: "k", Value: "<b>&'\""}}
	if want := "Array\n(\n    [0] => <b>&'\"\n)\n"; showPostPrintR(showPostArrayValues(raw)) != want {
		fail("unescaped print_r value", showPostPrintR(showPostArrayValues(raw)), want)
	}

	// 9. The tag ignores its arguments entirely — the PHP constructor's body is empty. Every
	//    invocation shape TagList and the parser can produce must render identically.
	bare := NewShowPostTag(nil, nil, nil).GetDocument()
	withArgs := NewShowPostTag(nil, &TagArguments{}, nil).GetDocument()
	if bare != withArgs {
		fail("arguments must not change the render", withArgs, bare)
	}

	// 10. The registry factory really does answer for this tag, and with the gate's bytes.
	if !IsPorted("ShowPost") {
		fails = append(fails, "ShowPost is not registered: init() did not add it to PortedTags()")
	}

	return fails
}

// showPostQuote renders a string for a failure message with its newlines visible, so a reader of
// a failure can see WHICH bytes differ rather than a ragged multi-line blob.
func showPostQuote(s string) string {
	return `"` + strings.ReplaceAll(s, "\n", `\n`) + `"`
}

// The interface this file promises to satisfy, checked at compile time.
var _ Tag = (*ShowPostTag)(nil)
