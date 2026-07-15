package tags

// bodytag.go — ticket #249, unit go-port:tags:tag:BodyTag.
//
// The Go port of ONE tag: invocators/tags/document/BodyTag.php. Per #281 a tag port is
// ADD-A-FILE-ONLY: this file holds the tag's type, its constructor, its GetDocument, its helpers and
// its self-registration (the init() below), and it changes NOTHING in engine.go — the registry picks
// the tag up because Go runs every init() in a package before any other code in it
// (engine.go:1355 Register, engine.go:1393 newTag). Every identifier it defines is bodyTag*-prefixed
// or BodyTag*-named, so it cannot collide with the sibling tag ports.
//
// THE CONTRACT: byte-identical HTML. The PHP is the SPEC. Where the two disagree THIS file is wrong.
//
// ── THE WHOLE TAG (BodyTag.php:9-22, verbatim but for the `if (!class_exists("BodyTag"))` guard at
//    :8/:23 that wraps every class in this codebase) ──────────────────────────────────────────────
//
//	class BodyTag implements Tag_Interface {
//	    private $arguments;
//	    private $body;
//	    public function __construct($arguments) {
//	        $this->arguments = $arguments;                                   // :14
//	        $document = PersistentObjectManager :: getData('WORKING_PAGE');  // :15
//	        $this->body = $document->get_content_outline();                  // :16
//	    }
//	    public function get_document() {
//	        return "<<<ContentTag(" . $this->body . ")>>>";                  // :20
//	    }
//	}
//
// Four lines of work. It touches no database of its own, emits no markup, and has no empty state and
// no error state of its own: its ENTIRE output is one ContentTag INVOCATION STRING — the same
// `<<<Tag(arg)>>>` syntax an author writes in a template. BodyTag is a tag that emits a tag.
//
// ── THE TRAP: `new BodyTag(null)` DOES NOT THROW ────────────────────────────────────────────────
//
// The gallery renders every tag with `$obj = new $sel(null);` (TagList.php:67), and the sibling port
// ContentTag.php:15 dereferences that NULL immediately (`$arguments->top()`), so ContentTag's gallery
// render is an ERROR PATH whose bytes are TagList's catch <p> (contenttag.go's header, and its
// contentTagStandaloneHTML). It is tempting to assume BodyTag is the same shape. IT IS NOT.
//
// BodyTag.php:14 STORES $arguments and NEVER READS IT AGAIN — there is no ->top(), no ->pop(), no
// method call on it anywhere in the class. A NULL argument is therefore inert: nothing dereferences
// it, nothing throws, and the tag renders its normal output standalone. $arguments is a dead field,
// exactly as it is in ContentTag (ContentTag.php:14), and like contenttag.go this port does not carry
// it — a field no code reads is not part of the behaviour.
//
// So BodyTag takes NO arguments in any meaningful sense: `<<<BodyTag>>>` and `<<<BodyTag(x)>>>`
// render IDENTICALLY, because the argument is stored and dropped. The ticket says to "drive each
// argument form the templates above actually use". No template uses any: no Document_Templates row
// mentions BodyTag at all — the ticket asserts this and it was RE-CHECKED against the live db this
// session (`SELECT DocumentID FROM Documents d JOIN Document_Templates t ON d.TemplateID=t.TemplateID
// WHERE t.Content LIKE '%BodyTag%'` returns zero rows). And even a template that did pass an argument
// could not change a byte of the output, because the class never reads it.
//
// ── WHAT IT ACTUALLY DEREFERENCES: WORKING_PAGE, WHICH IS ALWAYS SET ────────────────────────────
//
// The one thing BodyTag CAN throw on is :16 — `$document->get_content_outline()` when $document is
// NULL. $document is `PersistentObjectManager::getData('WORKING_PAGE')` (:15), which returns NULL for
// a key that was never set (PersistentObjectManager.php:67-74; note getData itself cannot throw — it
// guards with isset()).
//
// WORKING_PAGE is set on EVERY rendered page, BEFORE any tag runs. Controller::display
// (Controller.php:30-39) is the only writer and it is unconditional:
//
//	public static function display($document_id){
//	    $document = DocumentManager::get_document( $document_id );   // :31
//	    PersistentObjectManager::setData('WORKING_PAGE',$document);  // :37  <- set HERE
//	    self::set_display_string($document->__toString());           // :38  <- tags run HERE
//	}
//
// :37 precedes :38, and :38 is what reaches Tag_Wrapper::execute_all_tags (Document.php:84-86). The
// harness router calls Controller::control() on every request (router.php:50, "mirrors
// bin/Execute.php"), so there is no served page on which a tag runs with WORKING_PAGE unset. The
// NULL-deref at :16 is UNREACHABLE from the web. That is why this port does not model it — see
// bodyTagNoWorkingPageDivergence for what it does instead, and why forging that Error would be a lie.
//
// So WORKING_PAGE is, by construction, THE DOCUMENT FOR THIS REQUEST'S PAGE KEY — the very document
// Controller::display looked up from `$_GET['page']` (defaulting to "catalog" when the key is absent,
// Controller.php:15-19). Go has no POM (engine.go's divergence 3) and engine.go:4124-4125 records
// that setData('WORKING_PAGE') has no counterpart there, so this file RE-DERIVES the document the
// same way the Controller did — from $_GET and the same DAO. See bodyTagWorkingPage.
//
// `$document->get_content_outline()` (Document.php:71-73) returns $this->content_outline, which
// Document::sql_assoc_array set from the row's ContentID column (Document.php:29). That is Document
// .ContentID here (engine.go:1129), already through phpString — the same (string) coercion BodyTag.php
// :20's concat applies to it, so an INTEGER ContentID lands as the same digits on both sides.
//
// ── WHAT THIS RENDERS TODAY, MEASURED AGAINST THE LIVE DB ───────────────────────────────────────
//
// Read this session out of checkouts/current/state/congruency.sqlite. That file is what
// boot/configure.php:42 resolves CONGRUENCY_SQLITE to for the app root checkouts/current/congruency
// ("state is a SIBLING of the app root, not a child"), it is what DefaultConfig computes for
// Config.SQLite from the same rule (engine.go:367), and doclist.go:104-105 names it as the live
// server's db — i.e. it is the file the ticket's gate means by "the SAME database". (The Go server
// then overrides Config.SQLite with its own -db path, server.go:760-763, so pointing both servers at
// this file is the operator's job, not something this port can assert.) Opened read-only with
// immutable=1: zero sidecar files created (docs/PLAYBOOK.md Theme 3 — directory listing identical
// before and after):
//
//	Documents row 'tags'  ->  ContentID = 14   (an sqlite INTEGER)
//
// so on the gate URL BodyTag's own get_document() returns EXACTLY these 20 bytes:
//
//	<<<ContentTag(14)>>>
//
// AND THEN THE ENGINE EATS IT. That string is a live tag invocation, and Tag_Wrapper::execute_all_tags
// re-scans every tag's output (Tag_Wrapper.php:66-72, ported at engine.go:1027-1037): the frame that
// rendered TagList takes TagList's returned HTML — BodyTag's bytes now embedded in it — runs
// identify_tag over it, finds <<<ContentTag(14)>>>, renders ContentTag(14) at the next depth, and
// str_replaces it in. Verified this session with a transliteration of the chain driven against that
// same db: the pattern `/<<<[a-zA-Z]+(\([A-Za-z0-9]*\))*\>>>/` (Constants_patched.php:167-170,
// engine.go:283) MATCHES "<<<ContentTag(14)>>>", and the child's top() argument parses back to "14".
//
// ContentTag(14) then renders the EMPTY STRING, because the shared state db has no Content_Blocks
// table at all (measured: 47 tables, Store_Content_Blocks among them, Content_Blocks NOT). The SELECT
// fails, PDO's ERRMODE_SILENT (DataConnection.php:34) turns that into `false` rather than a throw,
// and the whole chain degrades silently to "" — that is #310's unit and contenttag.go documents it
// end to end.
//
// NET, on the live db: the tag's own bytes inside the .tagout div are "" — nothing. This tag's whole
// visible output today is the absence of output, and BOTH sides must produce that absence THE SAME
// WAY: by emitting the invocation and letting the engine expand it to nothing.
//
// ── WHY THIS TAG MUST NOT EXPAND ITS OWN OUTPUT (the one real design decision here) ─────────────
//
// Since the expansion collapses to "" anyway, a port could be tempted to "help" — to render
// ContentTag itself, or to just return "", and make the numbers come out. That is WRONG, and not on
// taste grounds. It is provably wrong, at the depth cap:
//
//	if ($depth >= 64) { return $result_string; }   // Tag_Wrapper.php:65 (BUG-06), engine.go:1024
//
// The cap is checked AFTER get_document() and BEFORE the re-scan, so a BodyTag rendered at depth 64
// emits <<<ContentTag(14)>>> and the engine leaves it LITERAL — those 20 bytes reach the page
// verbatim. Confirmed in the same transliteration: at depth 64 the output is '<<<ContentTag(14)>>>',
// at depth 1 it is ''. Only the ENGINE knows the depth; a tag that expanded its own output would emit
// "" there and differ from the PHP by 20 bytes. The same argument holds for a ContentID that is not
// alphanumeric — FUNCTION_ARGUMENTS is `(\([A-Za-z0-9]*\))*`, so a ContentID of "a-b" or "3.5" makes
// "<<<ContentTag(a-b)>>>" match NOTHING and survive as literal text (verified this session), while a
// self-expanding port would have rendered it.
//
// So: get_document() returns the invocation string, and ExecuteAllTags does the rest. That is what the
// PHP does, and the Go engine already mirrors it faithfully (engine.go:1022-1039). This file adds a
// tag; it does not do the engine's job.
//
// ── THE GATE — WHAT THE TICKET ASKS, WHAT IS RUNNABLE, AND WHAT WAS RUN ─────────────────────────
//
// The ticket's gate is ONE byte-diff, PHP:8899 vs Go:8900, over the same db:
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=BodyTag') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=BodyTag')
//
// IT WAS NOT RUN, IT CANNOT BE RUN FROM THIS WORKTREE, AND EVEN WITH BOTH SERVERS UP IT WOULD NOT
// MEASURE THIS UNIT. Saying so is what the ticket asks for — "if you cannot make a diff here run
// against THIS unit, say so on the ticket rather than settling on a diff that would be empty even
// with the unit unimplemented". Three separate reasons, each independently sufficient:
//
//  1. NO PHP, NO TOOLCHAIN HERE. This worktree has no php binary (the harness documents one at
//     tooling/congruencey-harness/php/php in its README's "Pieces", but php/ is gitignored and the
//     directory does not exist) and no `php` on PATH. equivalence_test.go:9-13 records this same wall
//     as the reason #226 landed 10 tags "ported-not-measured". The `go` toolchain is likewise refused
//     in this sandbox before it starts — see THE COMPILE GAP below.
//
//  2. THE WHOLE-PAGE DIFF IS CONFOUNDED FOR EVERY TAG, PORTED OR NOT. The PHP returns a full CMS page
//     (chrome, gallery, tag, tail). The Go server does not reproduce the page frame and says so in its
//     own bytes: handleTagsPage emits `<!doctype html>\n<title>tag: BodyTag</title>\n<h1>…</h1>` plus
//     an HTML comment admitting "the CMS Controller::control() page chrome is still not reproduced
//     here" (server.go:820-823). So this diff is non-empty for every tag, always, for reasons that
//     have nothing to do with this unit — it would look exactly as broken with this file deleted.
//
//  3. AND FOR THIS TAG THERE IS A SECOND, DEEPER CONFOUND THAT IS NEW WITH #249. The Go server answers
//     ?page=tags&tag=T with tags.RenderTag (server.go:801), which is `new $sel(null)` + get_document()
//     and NOTHING ELSE (engine.go:4147-4160) — it never runs ExecuteAllTags over the result. For the
//     tags ported so far that was harmless: they emit HTML, and their DB-derived text goes out through
//     esc(), which turns any stored `<<<Tag>>>` into `&lt;&lt;&lt;Tag&gt;&gt;&gt;` — bytes tagPattern
//     cannot match, so nothing they return re-triggers the scanner (engine.go:398). BODYTAG IS THE
//     FIRST TAG WHOSE OUTPUT IS, BY DESIGN, AN UNESCAPED TAG INVOCATION. So:
//
//	PHP page  ->  the tag's slice is ""                    (engine expanded ContentTag(14))
//	Go server ->  the tag's slice is "<<<ContentTag(14)>>>" (RenderTag never re-scans)
//
//     Both are CORRECT for what they compute; the two entry points are not the same function. The Go
//     path that does mirror the PHP is tags.Render — the document render, which runs ExecuteAllTags
//     (engine.go:1061-1063, 4126-4137) and therefore expands ContentTag(14) to "" exactly as PHP does.
//     server.go deliberately calls RenderTag instead, for reasons it documents (server.go:774-781), and
//     changing that is an edit to server.go, which this ticket forbids ("touch nothing else").
//
// THE SAME CONFOUND HITS #282'S HARNESS, and this is worth a ticket of its own rather than a silent
// expectation of red:
//
//	cd congruency-go && go test ./tags/ -run TestTagEquivalence/BodyTag -v
//
// It cuts the tag's bytes out of the live PHP page with TagList.php's own anchors and compares them to
// RenderTag's (equivalence_test.go:28-33). Its founding assumption is that "the tag's bytes are a
// SLICE of that page" — TRUE for every tag whose output the engine does not rewrite, FALSE for this
// one. It will compare "" (PHP, expanded) against "<<<ContentTag(14)>>>" (Go, unexpanded) and report a
// FAILURE THAT IS NOT THIS PORT'S DEFECT. Do not "fix" this file to make it green: pre-expanding is
// the divergence proved above. The harness needs a BodyTag-shaped answer (compare against
// tags.Render's page slice, or expand RenderTag's output through ExecuteAllTags before comparing),
// which is an edit to equivalence_test.go — again, not this ticket's file.
//
// WHAT WAS ACTUALLY RUN THIS SESSION — two python3 runs against the REAL state db (read-only,
// immutable=1, no files created). Both test my READING OF THE PHP and the LOGIC below; NEITHER
// compiles this Go — see THE COMPILE GAP:
//
//  1. A transliteration of the whole chain — Controller::display's WORKING_PAGE, BodyTag's
//     constructor and get_document, Tag_Wrapper::execute_all_tags' recursion with its depth cap, and
//     ContentDAO::lookupContent's SELECT. It CONFIRMED, as behaviour rather than as assertion: the
//     'tags' row's ContentID is 14; `new BodyTag(null)` constructs and renders WITHOUT THROWING;
//     get_document() returns '<<<ContentTag(14)>>>'; identify_tag matches those bytes and the child
//     parses top() back to "14"; the SELECT fails with "no such table: Content_Blocks" so the
//     expansion is ''; at depth 64 the invocation survives LITERAL; and a non-alphanumeric ContentID
//     ("a-b", "3.5", "x_y") matches the pattern NOT AT ALL and also survives literal.
//
//  2. A side-by-side cross-check of PHP BodyTag::get_document() against a transliteration of THIS
//     FILE's GetDocument, over EVERY DocumentID in the live Documents table (26 keys) plus four
//     edge inputs. Result: byte-identical on 27/27 reachable cases — including the gate's
//     page=tags -> '<<<ContentTag(14)>>>', and no-?page= -> '<<<ContentTag(1)>>>' where both sides
//     default to "catalog". The other three (?page= empty, an unknown key, a key failing
//     [A-Za-z]{2,}) are the documented unreachable divergence: PHP fatals in Controller::display
//     before BodyTag runs, Go emits bodyTagNoWorkingPageDivergence. Zero real mismatches.
//
// THE COMPILE GAP — THIS GO CODE WAS NOT COMPILED OR EXECUTED, AND THAT IS A REAL GAP IN THIS
// DELIVERABLE. It must be said plainly rather than left for a reader to discover. This sandbox
// permits no `go` invocation at all — even `go version` is refused before it starts — so the usual
// floor ("RUN your own work before reporting done") could not be met: the Go below is reviewed against
// the sibling ports' shapes, not run. A compile error or a panic in it is a live defect that no step
// in this session could have caught. The FIRST thing to do with this file is:
//
//	cd congruency-go && go build ./... && go vet ./tags/
//
// This is the same wall #310/#311/#312 hit and recorded (doclist.go:132-141); it is not new here.

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there.
func init() {
	Register("BodyTag", func(e *Engine, a *TagArguments) Tag { return newBodyTagTag(e, a) })
}

// BodyTagTag is BodyTag (BodyTag.php:9-22). The doubled "Tag" is the package convention
// (<TagName>Tag) applied to a tag whose own name already ends in "Tag" — the same shape
// contenttag.go's ContentTagTag has.
//
// The PHP's two properties are $arguments and $body. NEITHER is carried, and both omissions are
// deliberate:
//
//   - $arguments (:14) is assigned and never read — see THE TRAP in the header. A field no code reads
//     is not behaviour; contenttag.go drops the identical dead field for the identical reason.
//   - $body (:16) is the WORKING_PAGE document's ContentID, which the PHP resolves in the CONSTRUCTOR.
//     A Go factory (`func(e *Engine, args *TagArguments) Tag`, engine.go:1355) cannot report failure,
//     and resolving the document means a DB read — so that work is deferred to GetDocument, the only
//     point this file controls.
//
//     MOVING THE WORK CHANGES NO OBSERVABLE BYTE. Unlike ContentTag, whose deferred constructor work
//     is what THROWS (contenttag.go's header), BodyTag's constructor cannot fail on any reachable
//     path — WORKING_PAGE is always set, see the header — so there is no PHP-side exception whose
//     POSITION could be observed. And neither PHP call site could tell the two points apart even if
//     there were: the gallery wraps `new $sel(null)` AND `$obj->get_document()` in ONE try
//     (TagList.php:66-72), so both land in the same catch; the template path wraps NEITHER
//     (Tag_Wrapper.php:31 constructs, :64 calls get_document, no try anywhere), so a throw from
//     either fatals the page identically.
type BodyTagTag struct {
	e *Engine
}

// newBodyTagTag is BodyTag::__construct (BodyTag.php:13-17), minus the document lookup that
// GetDocument now does.
//
// It must never panic, and must construct on ANY input — nil args, an engine with an empty Config{}
// and no db. Every entry point calls the factory before anything else can intervene: renderSelected's
// `lookupTag(sel, nil)` (engine.go:1571), RenderTag's (engine.go:4155), and getTagWrapper's on the
// template path (engine.go:950). The first two do set up a recover() first, so a panic here would be
// caught rather than crash the server — but it would surface as a marked panic notice
// (engine.go:1564-1570), which is a divergence, not a render. Hence: this constructor does no work
// that can fail. (Note SelfCheck's nil-args construction loop covers only the 10 names #226 ported —
// engine.go:4371-4379 iterates that fixed list, not PortedTags() — so it does NOT exercise this tag;
// that is by design, since those checks are deliberately additive-safe.)
func newBodyTagTag(e *Engine, args *TagArguments) *BodyTagTag {
	// BodyTag.php:14 — `$this->arguments = $arguments;` and that is the last the class ever sees of
	// it. NULL args (the gallery's `new $sel(null)`, TagList.php:67) are inert here; this tag has no
	// argument-shaped behaviour to port. See THE TRAP in the header.
	_ = args
	return &BodyTagTag{e: e}
}

// bodyTagWorkingPage is `PersistentObjectManager::getData('WORKING_PAGE')` (BodyTag.php:15).
//
// There is no POM in Go (engine.go's divergence 3; engine.go:4124-4125 notes setData('WORKING_PAGE')
// has no counterpart), so the document is RE-DERIVED rather than read out of a session bag. That is
// sound because WORKING_PAGE is not free-form state: Controller::display is its ONLY writer and it
// stores precisely the document it just looked up from the request's page key —
//
//	if (isset($_GET['page'])) $post_validated = ValidateFields::validatePageKey($_GET['page']);
//	else                      $post_validated = "catalog";                    // Controller.php:15-19
//	$document = DocumentManager::get_document($post_validated);               // Controller.php:31
//	PersistentObjectManager::setData('WORKING_PAGE',$document);               // Controller.php:37
//
// — so "the WORKING_PAGE" and "the document for this request's page key" are the SAME OBJECT, and
// re-deriving it from the same $_GET and the same DAO reproduces it exactly. The lines below are that
// quote, in order: the isset/default, then the lookup.
//
// This is deliberately the same derivation Render performs (engine.go:4127-4132) — same key, same
// default, same last-value rule for a repeated ?page= (getIsset, engine.go:923-932) — so on a
// tags.Render page this tag resolves the IDENTICAL *Document the render is already walking, which is
// what makes the reconstruction faithful rather than merely similar. validatePageKey runs inside
// GetDocumentByKey (engine.go:1103), which is the same order Controller uses: validate, then look up.
//
// WHY A SECOND DB READ IS ACCEPTABLE. PHP's getData is a hash lookup, not a query — but the object it
// hands back was itself built from this very row moments earlier in the same request
// (Controller.php:31), so the values are the same either way. Re-reading costs one extra SELECT
// against a row that is static page furniture. Caching it instead would mean holding it on the Engine,
// i.e. an engine.go edit, which is exactly what #281 keeps a tag port from needing.
//
// ok=false is the "no document" case — see GetDocument and bodyTagNoWorkingPageDivergence.
func (t *BodyTagTag) bodyTagWorkingPage() (*Document, bool) {
	page := "catalog" // Controller.php:18 — the default when ?page= is absent
	if v, ok := t.e.getIsset("page"); ok {
		page = v // Controller.php:16 — isset($_GET['page'])
	}
	doc, err := t.e.GetDocumentByKey(page)
	if err != nil {
		return nil, false
	}
	return doc, true
}

// bodyTagNoWorkingPageDivergence is emitted when the WORKING_PAGE document cannot be resolved — no
// sqlite path configured, an unreadable db, a page key validatePageKey rejects, or a key with no
// Documents row.
//
// THE PHP CANNOT BE IN THIS STATE WHILE BODYTAG RENDERS, which is exactly why this notice exists
// instead of a reproduction. Every one of those failures happens in Controller::display BEFORE any tag
// runs, and kills the page there rather than reaching BodyTag:
//
//	$document = DocumentManager::get_document($post_validated);   // Controller.php:31 -> NULL
//	PersistentObjectManager::setData('WORKING_PAGE',$document);   // :37  stores the NULL
//	self::set_display_string($document->__toString());            // :38  FATAL on NULL, no tag runs
//
// PHP's own comment at Controller.php:32-35 concedes that branch was never thought through ("under
// what conditions does DocumentManager not return a document? seemingly never WHY DID I PUT THIS
// IN?"). So there are no PHP bytes to match here — the PHP emits a fatal, or nothing.
//
// It is therefore NOT modelled as BodyTag.php:16's NULL-deref Error ("Call to a member function
// get_content_outline() on null"), even though that is the Error the class would throw if $document
// were somehow NULL, and even though TagList's catch would dress it as "This tag needs context to
// render standalone: …". Emitting that string would be a FORGERY: it claims the PHP produced a
// message that, on this input, the PHP never produces — the failure happened a layer above BodyTag
// and took the page with it. This port refuses to invent it, the same choice notPortedHTML
// (engine.go:1497-1506) and contentTagNoSQLiteDivergence (contenttag.go) make: a MARKED divergence
// notice that says what is true.
//
// Unreachable on the gate: the 'tags' row and its ContentID are both present — measured, see the
// header. What CAN reach it is a misconfigured Go server (an empty or wrong Config.SQLite, i.e. a bad
// -db path, server.go:762) or a ?page= key with no Documents row. It returns a string rather than
// panicking because a panic would be dressed as a marked panic notice by the recover in renderSelected
// (engine.go:1564-1570) / RenderTag (engine.go:4149-4153) — the same divergence, but blamed on a
// crash instead of naming the cause.
func bodyTagNoWorkingPageDivergence() string {
	return "<p style='color:#b00020'>congruency-go: BodyTag cannot resolve WORKING_PAGE; " +
		"the PHP would have fatalled in Controller::display before this tag ran. " +
		"This notice is a DIVERGENCE from the PHP render, not a reproduction of it.</p>"
}

// GetDocument is BodyTag::get_document() (BodyTag.php:19-21) PLUS the constructor's document lookup
// (:15-16) that a Go factory cannot perform:
//
//	return "<<<ContentTag(" . $this->body . ")>>>";
//
// The returned string is a TAG INVOCATION, not markup, and this function deliberately does not expand
// it — ExecuteAllTags does (engine.go:1027-1037), exactly as Tag_Wrapper.php:66-72 does for the PHP.
// Expanding it here would diverge at the depth cap and on a non-alphanumeric ContentID; the header
// proves both. On the live db this returns "<<<ContentTag(14)>>>", which the engine then expands to
// "" because Content_Blocks does not exist (contenttag.go).
//
// doc.ContentID is already phpString'd (engine.go:1129) — the same (string) coercion PHP's concat
// applies at :20 — so an INTEGER ContentID of 14 concatenates to "14" on both sides.
//
// It deliberately has NO `defer catchThrowable(...)`: BodyTag.php has no try and no catch arm to
// model, so inventing a cy-form-error div would be a branch the PHP can never emit — the same
// reasoning contenttag.go states for the same omission. A Go panic here surfaces through
// renderSelected's recover as a marked panic notice (engine.go:1564-1570).
func (t *BodyTagTag) GetDocument() string {
	// BodyTag.php:15-16 — getData('WORKING_PAGE') then $document->get_content_outline().
	doc, ok := t.bodyTagWorkingPage()
	if !ok {
		return bodyTagNoWorkingPageDivergence()
	}

	// BodyTag.php:20 — the concat, verbatim.
	return "<<<ContentTag(" + doc.ContentID + ")>>>"
}
