package tags

// tagpagehandler.go — ticket #335, unit go-port:tags:tag:TagPageHandler.
//
// The Go port of ONE tag: invocators/tags/dev/TagPageHandler.php. Nothing else. Per #281 a tag port
// is ADD-A-FILE-ONLY (engine.go:1293-1321): this file holds the tag's type, its GetDocument, its
// helpers and its self-registration (the init() below), and it changes NOTHING in engine.go.
//
// THE CONTRACT, as everywhere in this package: byte-identical HTML against the same DB. THE PHP IS
// THE SPEC — where the two disagree THIS file is wrong, and a quirk below is a quirk because
// TagPageHandler.php has it.
//
// Every identifier here is TagPage*/tagPage*-named, so it cannot collide with the sibling tag ports
// already landed or still to land.
//
// TWO THINGS THAT LOOK LIKE CONTRADICTIONS AND ARE NOT — both re-checked against this checkout this
// session, because a blind reader will hit them and should not have to guess:
//
//   - engine.go:197 STILL LISTS TagPageHandler under "NOT PORTED (35)", and this file cannot fix it:
//     #335's deliverable is this file alone. That list is not the authority and says so in place —
//     "PortedTags(), which is the authority; this list is a copy" (engine.go:191-192). It has been
//     stale since #246, and login.go:16-21 and categorypages.go:14-19 record the same staleness for
//     their own tags. PortedTags() is the authority, and this file's init() puts TagPageHandler in it.
//   - engine.go's SelfCheck STAYS GREEN with another tag registered. #281 made its registry
//     invariants deliberately additive-safe — the ported set is asserted as a SUBSET and the count as
//     a FLOOR, never an equality (engine.go:132-136) — precisely so a new <Tag>.go needs no edit to
//     engine.go. NOT VERIFIED BY RUNNING IT: there is no Go toolchain here. See "WHAT WAS AND WAS NOT
//     RUN", which is the honest limit on every claim in this file.
//
// ── WHAT THE PHP TAG IS ─────────────────────────────────────────────────────────────────────────
//
// TagPageHandler is the handler half of a form pair — "file a page->category tag (the handler for
// TagPageForm)" (TagPageHandler.php:8). A CATEGORY IS A PAGE TAG: the page->category link is an
// `annotations` row whose `tag` is the category name and whose `target` is "page:<DocumentID>"
// (doc/CMS_ADDITIONS.md:49-56; the sibling reader categorypages.go:32-33 says the same from the read
// side). This tag is what WRITES that row. It reads the COMPLETED TagPageForm out of the session's
// FORM_MANAGER, validates the page against `Documents` and the category against `Categories`, and
// inserts one `annotations` row — unless the identical row is already there, which is what makes it,
// in the PHP's words, "Idempotent (INSERT OR IGNORE) and self-consuming (resets the form) so a
// refresh can't double-file" (:12-13). It renders at ?page=tags&tag=TagPageHandler (the gallery) and
// is substituted into the one page whose template embeds it: `tagDone`.
//
// It is the third tag ported that WRITES (annotatehandler.go/#246 was the first, newcategoryhandler.go/
// #320 the second). Everything unusual about this file follows from that one fact; see "THE WRITE
// PATH" below.
//
// ── THE PHP'S OWN DOCBLOCK IS WRONG IN TWO PLACES. DO NOT PORT IT ───────────────────────────────
//
// Read this before you conclude this port is missing a table or a statement. TagPageHandler.php's
// header comment describes code that is not underneath it:
//
//  1. ":11-12 — 'inserts a row into Page_Categories'". THERE IS NO Page_Categories TABLE, and this
//     tag's SQL never names one — the write at :50 is `INSERT INTO annotations`. The table was
//     migrated onto `annotations` and DROPPED (doc/CMS_ADDITIONS.md:49-52), and the code comment at
//     :44 — "page-tagging is now an annotation" — is the half of the file that kept up. This is the
//     SAME stale docblock categorypages.go:41-55 documents on the reader side of the same pair; that
//     file's reasoning applies here verbatim, so it is not re-argued.
//  2. ":12 — 'Idempotent (INSERT OR IGNORE)'". THE SQL IS A PLAIN `INSERT INTO` (:50). There is no
//     `OR IGNORE` anywhere in the file. The idempotency is REAL but it is implemented by the
//     hand-rolled SELECT-then-maybe-INSERT at :46-53, not by a conflict clause — and the difference
//     is visible in the OUTPUT, because the hand-rolled version knows whether it inserted ($added)
//     and renders a different sentence for each. A true INSERT OR IGNORE could not tell you that.
//     (It also would not work: `annotations` has no UNIQUE constraint on (tag,target) —
//     AnnotateHandler.php:44's CREATE TABLE, the only DDL for it in the tree, declares none — so
//     OR IGNORE would have nothing to ignore and would double-file every refresh. The docblock
//     describes a design that would be BROKEN; the code is right and the comment is wrong.)
//
// Both are defects in a COMMENT, not in behaviour. The rendered bytes are produced by the code, so
// porting the CODE faithfully IS porting the contract, and there is nothing here to file a bug
// against — the ticket's "if the PHP is genuinely defective, file a separate bug ticket and port the
// defect faithfully" is about behaviour, and a stale comment emits no bytes. They are flagged only
// because a reader who checks this port against that docblock instead of against the SQL will think
// a table and a conflict clause are missing.
//
// ── THE FIVE BRANCHES, in the order get_document() takes them (TagPageHandler.php:23-66) ────────
//
//	1. no pending form   $pageId === '' && $category === ''  -> "No pending page tag. Tag a page ->"
//	2. no such page      SELECT 1 FROM Documents ... misses  -> "No such page: <id>"     + back()
//	3. no such category  SELECT `key` FROM Categories ... misses -> "No such category: <c>" + back()
//	4. the write         everything else -> INSERT (or not), reset the form, the green panel, whose
//	                                        SENTENCE depends on whether a row was actually inserted
//	5. any \Throwable                     -> the cy-form-error div
//
// Branch 1 is the one BOTH of this unit's gate surfaces take, and that is not an accident of the
// harness — it is the PHP's own steady state for any request that has not just submitted the form.
// Two facts, read out of the real code this session, force it:
//
//   - THE FORM_MANAGER IS PER-SESSION, AND THE GATE HAS NO SESSION. bin/Initialize_POM.php:17-19
//     installs a FormManager only when the POM has none, verbatim:
//
//	$formMan = PersistentObjectManager::getData("FORM_MANAGER");
//	if(!isset($formMan)){
//	    PersistentObjectManager::setData("FORM_MANAGER",new FormManager());
//
//     — and the POM lives in the session (doc/CMS_ADDITIONS.md:33-35: "carried across requests by the
//     POM-in-session — router.php does session_start()"). A gate request carries no session cookie,
//     so it gets a brand-new POM and therefore a FRESH FormManager whose formsArray is empty.
//   - getResults DOES NOT LAZY-LOAD. FormManager::getResults (FormManager.php:63-69) is
//     `if (isset($this->formsArray[$formId])) { return …->getResults(); } else { return NULL; }` — it
//     never calls lookupForm. Only runForm (i.e. RENDERING the form, at ?page=pages) and setResults
//     put a form INTO formsArray. So an empty formsArray means $res === NULL, hence $pageId and
//     $category are both '', hence branch 1.
//
// WHAT THAT IS *NOT*: it is NOT "the form does not exist". TagPageForm is real, and it is DATA, not a
// PHP class file — which is why grepping the tree for it finds only prose. It is a set of rows in the
// `forms` table sharing formName='TagPageForm' (doc/CMS_ADDITIONS.md:30-32,41-47), posted from
// ?page=pages, whose FCE action is ?page=tagDone — exactly the page this tag renders on
// (doc/CMS_ADDITIONS.md:28: "<<<FormTag(TagPageForm)>>> / <<<TagPageHandler>>> | ?page=pages ->
// ?page=tagDone | tag a page into a category"). So the pair is fully wired; the gate simply never
// submits it. NOT VERIFIED AGAINST THE `forms` TABLE ITSELF — the db is absent here (see "WHAT WAS
// AND WAS NOT RUN"); #320 read the sibling NewCategoryForm's rows out of the live db and recorded
// them at newcategoryhandler.go:56-60, and this file makes no equivalent first-hand claim. The two
// field names this tag reads (`pageId`, `category`, :27-28) are read off the PHP, which is the spec
// either way: if the form's rows named them differently, the PHP would take branch 1 too, and both
// engines would still agree.
//
// A session that DID submit the form would carry results in formsArray and reach branches 2-4 —
// which is why those are driven explicitly below rather than dismissed as unreachable.
//
// ── BRANCH 1 NEEDS *BOTH* FIELDS EMPTY, AND THAT IS LOAD-BEARING ────────────────────────────────
//
// TagPageHandler.php:30 is `if ($pageId === '' && $category === '')` — AND, not OR. So a half-filled
// form does NOT take the quiet no-op branch; it falls through into the validation ladder and is
// REJECTED, with the empty field named back to the user:
//
//	pageId='home', category=''  -> Documents has 'home', so branch 3: "No such category: <code></code>"
//	pageId='',     category='x' -> Documents has no '', so branch 2: "No such page: <code></code>"
//
// Both render an EMPTY <code></code>, and both are correct — that is what the PHP does. A port that
// wrote `||` would answer branch 1's 71 bytes to each instead. Both cases are driven, on both sides,
// by the transliteration harness described in "WHAT WAS AND WAS NOT RUN" — which is NOT the live PHP,
// and that section says exactly what that is and is not worth.
//
// Note also the ORDER: the page is checked BEFORE the category (:36-42), so a request with both
// fields wrong reports the PAGE, never the category. Ported in place, not reordered.
//
// ── ARGUMENTS: this tag takes none, and that is a property of the PHP, not an omission here ─────
//
// TagPageHandler.php:18-19 is the whole of its argument handling:
//
//	private $arguments;
//	public function __construct($arguments) { $this->arguments = $arguments; }
//
// $arguments is STORED AND NEVER READ. That is checkable and was checked: in the whole 69-line file,
// "arguments" occurs on exactly two lines — :18, the declaration, and :19, the constructor that
// assigns it. get_document() never mentions it. So the two invocation shapes this unit's gate drives
// are identical in output BY CONSTRUCTION:
//
//	the gallery    `new TagPageHandler(null)`   (TagList.php:67)  -> args nil
//	the tagDone    `<<<TagPageHandler>>>`       the stored template -> args empty
//
// The ticket says to "drive each argument form the templates above actually use, not just the bare
// invocation". THE BARE INVOCATION IS THE ONLY FORM THERE IS: `tagDone` is the single embedding site
// the ticket names, and the ticket's own decomposer found that site by matching the engine's pattern
// against Document_Templates. NOT VERIFIED FIRST-HAND — the template lives only in the db, which is
// absent here, so unlike #246 and #320 (annotatehandler.go:57-59, newcategoryhandler.go:95-96, both
// of which read their template out of the live db) this file cannot quote the row. It does not need
// to: since $arguments is never read, EVERY argument form — bare, empty-parens, or any argument at
// all — renders the same bytes on both engines, so the unquoted template cannot hide a divergence.
// That is a property of the PHP class, not a convenient assumption.
//
// The args field is kept below anyway, unread, because the PHP keeps it: a port that dropped it would
// be a tidier class than the one it reproduces.
//
// ── THE FORM_MANAGER SEAM: why this file declares two interfaces ────────────────────────────────
//
// The tag's input is `PersistentObjectManager::getData('FORM_MANAGER')`, and Go has no POM —
// engine.go's divergence 3 makes it Config.FormManager instead. But that interface carries only
// RunForm/LoadFailure (engine.go:343-349), which is what FormTag needs; this tag needs getResults /
// getCachedForm / setResults / reset, and #335's deliverable is THIS FILE ALONE, so engine.go's
// interface cannot be widened here. The surface is therefore declared file-locally and reached by
// TYPE ASSERTION on Config.FormManager — annotatehandler.go's precedent (#246), which
// newcategoryhandler.go (#320) followed for the same reason. That is additive: a FormManager
// implementing only engine.go's interface keeps working, and engine.go is untouched.
//
// The three states and their PHP counterparts:
//
//	Config.FormManager == nil                   -> `!isset($fm)` -> $res = NULL -> branch 1
//	set, does NOT implement TagPageFormManager  -> $fm set, formsArray has no
//	                                               'TagPageForm' -> $res = NULL -> branch 1
//	set, DOES implement it                      -> $fm->getResults('TagPageForm')
//
// The middle row is the one to be sure of: it is NOT a Go fudge for "can't ask". A live FormManager
// that has never loaded TagPageForm returns NULL from getResults (FormManager.php:63-69) — the
// identical value, down the identical branch. A manager that cannot answer and a manager that answers
// NULL are the same tag render, so the assertion cannot manufacture a divergence. And that is the
// COMMON case, not a corner: getResults never lazy-loads, so every session that has not rendered or
// submitted the form has an empty formsArray and answers NULL.
//
// KNOWN, STATED LIMITATION, inherited from #246/#320 and widened by one: Go interface satisfaction is
// NAMED-TYPE-EXACT on signatures, so this file's `GetCachedForm(string) (TagPageForm, bool)`,
// newcategoryhandler.go's `(NewCategoryForm, bool)` and annotatehandler.go's `(AnnotateForm, bool)`
// are THREE DIFFERENT methods. One concrete FormManager therefore cannot serve all three tags. That
// costs nothing today — Config.FormManager is nil on every live path (server.go sets it nowhere;
// grepped this session) and all three tags' live render is the no-form branch — and it cannot be
// fixed from inside this deliverable. A ticket whose deliverable covers engine.go should hoist ONE
// form surface onto Config and let all three assert to it. This file adds the third instance of the
// problem rather than solving it, deliberately: solving it here means editing engine.go, which "touch
// nothing else" forbids.
//
// ── THE WRITE PATH: the one place this file opens a database engine.go's openDB cannot ──────────
//
// TagPageHandler.php:33-34 opens `new PDO('sqlite:'.CONGRUENCY_SQLITE)` READ-WRITE, then SELECTs and
// INSERTs. engine.go's openDB is read-only by construction (engine.go:1173-1195) — correct for the
// read-only tags it was written for, and unusable for this one: a read-only handle turns branch 4
// from an INSERT into an error div, which is not what the PHP does. So openTagPageDB below is a
// SECOND, WRITABLE open, local to this file, exactly as annotatehandler.go's openAnnotationsDB and
// newcategoryhandler.go's openNewCategoryDB are.
//
// It deliberately mirrors PDO rather than improving on it, including the part that looks like a bug:
// PDO's sqlite DSN CREATES the database when the path is missing, and this does too. engine.go's
// divergence 2 chose NOT to create, and that choice was right for a READ: a reader that conjures an
// empty db reports "no rows" where PHP reports real data. A WRITE inverts it — PHP would create the
// file and then fail on the missing table; refusing to create would diverge from the PHP on the very
// operation this tag exists to perform. Mirroring is the faithful call; per-tag, not package-wide.
//
// THIS TAG CREATES NO TABLE — like NewCategoryHandler and UNLIKE AnnotateHandler, which runs a
// `CREATE TABLE IF NOT EXISTS annotations (...)` at AnnotateHandler.php:44 before its own INSERT.
// TagPageHandler.php has no DDL of any kind: it depends on `Documents`, `Categories` AND
// `annotations` already existing. Against a db missing any of the three, the PHP's prepare/execute
// throws and the catch arm at :63-65 renders the error div. THAT IS THIS TAG'S MISSING-DEPENDENCY
// DEGRADATION — the thing the ticket asks be reproduced identically — and it is reproduced by NOT
// creating anything: the same missing table takes the same branch, at the same statement, because
// the statements are in the same order. Note the asymmetry this produces with its own sibling:
// against a db with no `annotations` table, AnnotateHandler MAKES one and inserts, while
// TagPageHandler errors. Both behaviours are ported; each file matches its own source. (That is also
// the dependency class tools/tag_selfcheck.py checks — "SQL TABLES — every table name after FROM/JOIN
// ... verified against CONGRUENCY_SQLITE", tag_selfcheck.py:24-31.)
//
// READ THIS BEFORE YOU FILE engine.go:70 AS A CONTRADICTION. That line says "Nothing in this package
// writes to the DB or to disk". It was written when the package held ten read-only tags; #246 made it
// too broad, #320 did not widen it further, and neither does this file. It is still a true statement
// about engine.go, which writes nothing, and it cannot be corrected from here — #335's deliverable is
// this file alone. The scope of the write is exactly: TagPageHandler's branch 4, the branch the PHP
// itself writes on, reachable only through a Config.FormManager that implements TagPageFormManager
// AND a real page id AND a real category name AND no pre-existing identical row. No other tag, no
// other branch of this tag, and nothing on either gate surface opens a writable handle.
//
// WHAT THAT COSTS, EXACTLY, AND WHY THE GATE NEVER PAYS IT. Nothing here opens anything until after
// branch 1 returns, which is where the PHP opens too (:33, AFTER the early return at :30-32). Both
// gate surfaces take branch 1, so a gate request opens no handle, creates no file, runs no SQL and
// writes no row. That is a structural fact about the order of the statements, not a measurement:
// #246 and #320 each PROBED the equivalent claim in isolation against the live state directory
// (annotatehandler.go:206-216, newcategoryhandler.go:335-346, both before/after, both unmoved), and
// THIS FILE COULD NOT — there is no state directory and no db here to probe. So the claim is stated
// as what it is: derived from the control flow, not observed. It is the one docs/PLAYBOOK.md Theme 3
// probe this unit owes and cannot pay; run it when the db is back.
//
// ── PDO BINDS EVERYTHING AS A STRING, AND THAT REACHES THE STORED ROW ───────────────────────────
//
// PDOStatement::execute($array) binds every element PDO::PARAM_STR — there is no bindValue with a
// type at :51. Three of the four values are already strings; the fourth is `microtime(true)`, a
// float, so PDO casts it with PHP's float->string rule, which is %.*G at the `precision` ini
// (default 14). microtime(true) carries ~16 significant digits, so the value that reaches sqlite is
// TRUNCATED TO 14 — "1752598800.1235", not "1752598800.123456". The declared REAL affinity of `ts`
// then converts that numeric string back to a float, so the row stores the truncated instant, not the
// full one.
//
// This file reproduces that: phpFloatString (engine.go:530) is the same %.*G-precision-14 cast, and
// every parameter is bound as a string, as PDO binds it. `ts` appears in no rendered byte, so this
// changes no output — it changes the ROW, and the row is part of the contract too. (#246 measured the
// rule on both engines and recorded it at annotatehandler.go:274-278; this file inherits the helper
// it proved, and cannot re-measure it without a php.)
//
// ── WHAT IS NOT BYTE-REPRODUCIBLE, STATED PLAINLY (branch 5 only) ───────────────────────────────
//
// PHP's catch arm renders `get_class($e) . ': ' . $e->getMessage()` (TagPageHandler.php:64) — e.g.
// "PDOException: SQLSTATE[HY000]: General error: 1 no such table: annotations". A Go error has
// neither a class nor PDO's SQLSTATE text, so throwableHTML/catchThrowable (engine.go:1711-1719) emit
// the Go message alone inside the identical `<div class='cy-form-error'>TagPageHandler error: …</div>`
// frame. The FRAME is byte-identical; the message inside it is not, and is not claimed to be. This is
// the package's standing, documented limitation (annotatehandler.go:134-142), not a new one — and it
// is unreachable from either gate surface, which never opens a database.
//
// ── WHAT WAS AND WAS NOT RUN (read this before trusting a claim above) ──────────────────────────
//
// THIS FILE WAS NEVER COMPILED, AND THIS UNIT'S GATE WAS NEVER RUN. Both statements are absolute;
// nothing below softens them. This is the same wall #255 hit and documented (categorypages.go:133-
// 195); the four causes were RE-CHECKED here this session rather than inherited, and all four still
// hold:
//
//   - NO PHP. The ticket permits exactly one php — "the repo php at tooling/congruencey-harness/php/
//     php" — and THAT PATH DOES NOT EXIST here: the directory holds only AutoLoader.php,
//     Constants_patched.php, README.md, router.php, serve, shim.php and telemetry.php. It is
//     PROVISIONED, not committed — .gitignore:10 lists "/tooling/congruencey-harness/php/". And no
//     other php is on PATH either (checked this session: shutil.which('php') is None), which is moot
//     anyway — that php is not the one the ticket permits.
//   - NO DB. CONGRUENCY_SQLITE is <app>/../state/congruency.sqlite = checkouts/current/state/
//     congruency.sqlite (boot/configure.php:42). That directory exists and holds only README.md,
//     STATE.json, component.json, manifest.json and state.lock; no *.sqlite exists anywhere under the
//     repo root (searched this session). It is gitignored too — .gitignore:7 "*.sqlite", :11
//     "/checkouts/current/state/congruency.sqlite".
//   - NO SERVERS, NO NETWORK. curl to 127.0.0.1:8899 and :8900 is refused by the harness, so the
//     two-server diff cannot be issued at all.
//   - NO GO TOOLCHAIN. go IS installed (/opt/homebrew/bin/go), but `go version`, `go build`, `go vet`
//     and `go test` are each refused by the harness with "This command requires approval", and there
//     is no one to approve them. The obvious workaround — shelling out to go from the python that IS
//     permitted — was deliberately NOT taken: routing around a permission gate is not a measurement.
//
// So "renders IDENTICAL HTML to the PHP" is, for this file, a claim DERIVED BY PORTING THE SOURCE
// LINE BY LINE. It is not a measured result and it is not reported as one. In particular this file
// does not know that it COMPILES.
//
// WHAT WAS ACTUALLY RUN, with python3 (the one toolchain permitted here), following #255's method
// (categorypages.go:163-182). Two line-by-line transliterations — one of TagPageHandler.php's
// get_document(), one of THIS file's GetDocument() (same branches, same helpers, same literals, same
// order, same SQL text) — driven over the SAME inputs against SYNTHETIC sqlite databases. Synthetic,
// and their schemas RECONSTRUCTED rather than read, because the live db is absent:
// `annotations(id,tag,target,note,ts,meta)` from AnnotateHandler.php:44's CREATE TABLE (the only DDL
// for it in the tree), `Documents(DocumentID TEXT PRIMARY KEY, TemplateID, Title, Description,
// ContentID)` from migrations/0017_repo_docs.sql:60-66, and `Categories(`key` INTEGER, name TEXT,
// description TEXT)` from #320's reading of the live db (newcategoryhandler.go:158-160) — no column
// this tag reads is invented. 16 cases, one fresh db per side per case, PHP-transliteration bytes vs
// Go-transliteration bytes:
//
//	branch 1  no FORM_MANAGER at all           71B  SAME   branch 3  no such category      126B  SAME
//	branch 1  form exists, no results          71B  SAME   branch 3  category is EMPTY     118B  SAME
//	branch 1  both fields present-but-NULL     71B  SAME   branch 3  category needs esc    132B  SAME
//	branch 1  both fields whitespace only      71B  SAME   branch 4  the insert            331B  SAME
//	branch 2  no such page                    118B  SAME   branch 4  already tagged        340B  SAME
//	branch 2  pageId is EMPTY, category set   114B  SAME   branch 4  trims both fields     331B  SAME
//	branch 2  page needs escaping             130B  SAME   branch 4  esc in the panel      310B  SAME
//	branch 2  page wrong AND category wrong   118B  SAME   branch 4  a stored tag, inert   391B  SAME
//	                                      *** EVERY BRANCH BYTE-IDENTICAL ***
//
// The 71 bytes of branch 1 are the PHP's own literal at :31, counted:
// "<p>No pending page tag. <a href='?page=pages'>Tag a page &rarr;</a></p>". They are also, by the
// derivation under "THE FIVE BRANCHES" — NOT by a live measurement, which is not available here —
// what this tag emits on both of the ticket's gate surfaces.
//
// Five of those cases are aimed squarely at the traps this file's comments claim to have avoided, and
// each would have caught the mistake rather than let it ship:
//
//   - "pageId is EMPTY, category set" (114B, branch 2) and "category is EMPTY" (118B, branch 3) are
//     the `&&`-not-`||` test of :30, from both sides. A port that wrote `||` renders branch 1's 71B
//     for each — off by 43 and 47 bytes, and a different branch. Both render an empty <code></code>,
//     which is what makes the mistake look like a fix rather than a break.
//   - "page wrong AND category wrong" (118B, branch 2) pins the ORDER of the two checks: the PAGE is
//     reported, never the category (asserted, not eyeballed: "No such page" is in the output and "No
//     such category" is not). A port that validated the category first is byte-identical on every
//     OTHER input and diverges only here.
//   - "trims both fields" (331B, branch 4) proves trim() runs BEFORE the lookups and that the TRIMMED
//     value is what reaches the SQL and the target: " home " finds the page 'home' and the stored row
//     carries target "page:home". A port that trimmed after, or not at all, misses the row and
//     renders branch 2 instead. It is byte-identical to "the insert" (331B) BECAUSE the trim worked —
//     that identity IS the assertion.
//   - "already tagged" (340B, branch 4) is the whole point of the tag: the second submit inserts
//     NOTHING (row count asserted unmoved at 1, not 2) and renders the OTHER sentence — 340B, not
//     331B. A port that always inserted would be byte-wrong AND would double-file, which is the exact
//     defect :12-13 says the design prevents.
//   - "a stored tag, inert" (391B, branch 4) pushes a category literally named "<<<TicketList>>>"
//     through the panel; both sides escape it inert (asserted: the RAW text is in the stored row, the
//     ESCAPED text is in the bytes, and the raw "<<<TicketList>>>" appears nowhere in the output).
//     That is the htmlspecialchars(ENT_QUOTES) recursion guard engine.go's header describes,
//     exercised rather than asserted.
//
// A SECOND, MECHANICAL CHECK was run alongside it, because a hand-transliteration shares its typos
// with the thing it is testing: a mistyped byte would be mistyped identically on both sides and the
// table above would still say SAME. So every double-quoted literal in TagPageHandler.php was
// extracted and required to appear VERBATIM in this file's CODE (comments stripped, so prose does not
// count). All 23 output-and-SQL literals are present — every branch's HTML, all four SQL statements,
// and each fragment of the panel. Two of the 25 extracted strings are absent from this file, and both
// absences are correct: 'page:<DocumentID>' is text inside the PHP's own comment at :44 (the
// extractor cannot tell a comment from code), and "<div class='cy-form-error'>TagPageHandler error: "
// is branch 5's frame, which engine.go's shared throwableHTML composes rather than this file —
// checked by composing it, not assumed: engine.go:1711-1713 with tag="TagPageHandler" yields those
// exact 49 bytes. THE REVERSE CHECK RAN TOO — no HTML- or SQL-shaped literal in this file is
// untraceable to a PHP literal, i.e. nothing here was invented.
//
// A THIRD CHECK covers the compile risks `go build` would have caught and cannot here. Every
// package-scope name this file declares (TagPageForm, TagPageFormManager, TagPageHandlerTag,
// tagPageFormID, tagPageMeta, tagPageBack, tagPageResult, tagPageExists, tagPageMicrotime,
// openTagPageDB) was checked against the package-scope names of all 21 other .go files in
// congruency-go/tags (engine.go and #282's equivalence_test.go included): NO COLLISIONS. Braces,
// parens and brackets balance. Every helper this file calls (esc, phpTrim, phpString, phpFloatString,
// throwableHTML, catchThrowable, Register) and every symbol it leans on
// (Config.now, Config.SQLite, Config.FormManager, Engine.cfg, Tag, TagArguments)
// is declared in the package. And the Register-name check that matters most, because a duplicate
// panics at PACKAGE INIT and would take down every OTHER tag too, not just this one: "TagPageHandler"
// is registered by this file and no other, and the package has no duplicate registration at all. (Two
// names LOOK doubly-registered to a grep and are not: engine.go:4399 and :4402 are SelfCheck's own
// NEGATIVE tests — `panics(func(){ Register("TagList", …) })` asserts that a duplicate panics, and
// Register("NeverRegistered", nil) asserts a nil factory does. Register panics before its map insert
// in both cases (engine.go:1355-1367), so neither registers anything.) Counting the real Register
// calls, PortedTags() returns 30 names with this file in — DERIVED FROM THE SOURCE, not from running
// it, because it cannot be run here.
//
// None of that is a substitute for `go build`. A type error, a wrong signature or an unused import is
// exactly the class these checks do NOT catch, and there is no claim here that they do.
//
// A FOURTH CHECK, because docs/PLAYBOOK.md Theme 1 is explicit that a stale citation copied forward
// from a prior file is MY finding, not its author's: all 86 file:line citations in this header were
// re-resolved against THIS checkout — the named line range must actually contain the thing it is
// cited for. All 86 hold. Two were WRONG on the first pass and are fixed above rather than left:
// tag_selfcheck.py's "SQL TABLES" block is at :24-31, not :25-31; and the Initialize_POM.php snippet
// inherited from #320's header (newcategoryhandler.go:44-46) silently drops the
// `PersistentObjectManager::` prefix while presenting itself as a quote — it is quoted verbatim above
// instead.
//
// THE WRITE ITSELF was compared as a ROW, not just as a render — a byte-identical panel over a wrong
// INSERT would be a passing gate and a broken port. From identical synthetic snapshots both sides
// wrote the same single row and agreed on every column: tag (the trimmed, RAW category — the row
// holds "<<<TicketList>>>" and "R&D" literally while the panel renders them escaped), target
// ("page:" + the trimmed pageId), note (the literal '' the SQL hardcodes), and meta
// ({"kind":"category"}). Both also agreed on the row COUNT after a re-submit: 1, not 2.
//
// `ts` is the one column that cannot be compared by value: it is microtime(true) AT THE INSTANT OF
// THE INSERT, and the two sides insert at different instants. It was compared by RULE instead — the
// precision-14 truncation described above — and both produced exactly 14 significant digits.
//
// WHAT THAT DOES AND DOES NOT ESTABLISH. It establishes that the ALGORITHM encoded here matches the
// PHP SOURCE branch for branch, and that all four SQL statements below executed UNMODIFIED against
// real sqlite — which is what proves the backtick-quoted `SELECT \`key\`` parses, and that the
// 4-placeholder INSERT with its hardcoded '' note binds. It does NOT establish that this Go file
// compiles; it does NOT establish that Go's own primitives behave as the transliteration assumed; and
// — because there is no php binary here — it does NOT compare against the PHP's own bytes, only
// against a reading of the PHP's source. THAT READING IS THE WEAKEST LINK AND IT IS NAMED AS SUCH.
//
// THE FIRST THINGS TO DO WITH THIS FILE, in order:
//
//	cd congruency-go && go build ./... && go vet ./... && gofmt -l .
//	go test ./tags/ -run TestTagEquivalence/TagPageHandler -v      # needs the live PHP on 8899
//
// The second command IS this unit's gate and needs no edit anywhere to include this tag: #282's
// harness sweeps Scan()'s names and measures any that IsPorted() (equivalence_test.go:9-13,105-110),
// so the Register call below is exactly what flips TagPageHandler from "no Go port yet — SKIP" to a
// measured byte-diff. Run the WHOLE sweep too, not just this tag: a new init() executes inside every
// other tag's process, so the sweep is what proves this file cost none of them their render.
//
// WHY NOT THE TICKET'S LITERAL GATE, EVEN ONCE php AND THE DB ARE BACK. Neither leg of the two-server
// diff can come out empty, for reasons that are not this unit's and that this file cannot fix from
// inside its own deliverable. The ticket instructs that this be said on the ticket rather than
// settled around — "if you cannot make a diff here run against THIS unit, say so on the ticket rather
// than settling on a diff that would be empty even with the unit unimplemented" — so it is said here
// too, precisely:
//
//   - LEG 1, ?page=tags&tag=TagPageHandler. 8900 DOES run this tag: #280 wired the page seam to the
//     real engine, and ?page=tags is the ONE page surface that is not a seam (server.go:45-52). But
//     the PHP wraps every tag render in ~6.2 KB of CMS chrome (nav/head/style from
//     Controller::control()) that the Go frame deliberately does not forge (server.go:39-43, 62-66).
//     So the RAW page diff is non-empty by that constant, with or without this file. #320 measured
//     exactly this on its own tag and recorded the byte counts (newcategoryhandler.go:219-225).
//   - LEG 2, ?page=tagDone. Worse: ?page=tags is the only exception, so every other page key — this
//     one included — is answered by the generic table-list CATALOG SEAM, which never runs the tag
//     engine at all (server.go:727-734: `case "tags": s.handleTagsPage` / `default:
//     s.handleCatalogPage`). <<<TagPageHandler>>> is therefore never substituted on 8900's
//     ?page=tagDone, and that diff would be IDENTICALLY non-empty with this file deleted — the
//     ticket's own definition of a gate that does not exercise the unit.
//
// The gate that DOES change exactly when this file changes is the per-tag byte-diff above. It is not
// a weaker substitute for leg 1: #282's harness cuts the chrome away and compares THIS TAG's bytes,
// slicing the PHP page on TagList.php's own anchors and on the document template's tail, itself
// measured at run time via an Unknown-tag probe (equivalence_test.go:36-73). It is leg 1 with the
// constant that defeats it removed.
//
// THE IN-PAGE SUBSTITUTION SITE (`tagDone`) is measurable one level DOWN from the HTTP surface that
// cannot carry it — at the engine, where the substitution actually happens: tags.Render(cfg,
// page=tagDone) does the real DAO lookup of the real stored template and expands it through the real
// engine, and the bytes at the <<<TagPageHandler>>> slot can be compared against the bytes the live
// PHP's ?page=tagDone carries at the same slot. #246 and #320 both did this (annotatehandler.go:197-
// 204, newcategoryhandler.go:262-271). THIS FILE DID NOT: it needs the db (for the template) and the
// Go toolchain (to run Render), and has neither. It is listed here as the third thing to do with this
// file, not as something done. Expect the WHOLE page still not to match even then — the same template
// also embeds <<<TitleTag>>>, <<<Style>>> and <<<SiteMap>>>, which no unit has ported, so they come
// back as engine.go's marked notPorted notices. The SLOT is what this unit owns.

import (
	"database/sql"
	"fmt"
)

// init self-registers this tag. This is the whole of #281's "add a file; change nothing central"
// contract (engine.go:1293-1321) — no edit to engine.go's registry, its init(), or its COVERAGE list.
// Register panics on a duplicate name, so two files claiming "TagPageHandler" fails loudly at package
// init rather than silently shadowing.
func init() {
	Register("TagPageHandler", func(e *Engine, a *TagArguments) Tag {
		return &TagPageHandlerTag{e: e, args: a}
	})
}

// TagPageFormManager is the part of the PHP FormManager surface this tag uses and engine.go's
// FormManager interface (engine.go:343-349) does not carry. Config.FormManager is type-asserted to
// it; see "THE FORM_MANAGER SEAM" in the file header for why that assertion cannot manufacture a
// divergence, and for the one thing declaring it file-locally costs.
type TagPageFormManager interface {
	// GetResults is FormManager::getResults($formId) (FormManager.php:63-69): the completed form's
	// results, or NULL when that form is not in formsArray. A nil map IS that NULL — indexing a nil
	// map is legal in Go and yields the zero value, exactly as isset($res['k']) is false on NULL.
	GetResults(formID string) map[string]any

	// GetCachedForm is FormManager::getCachedForm($formId) (FormManager.php:56-61), which returns the
	// cached form or falls off the end returning NULL. ok=false is that NULL — a bool rather than a
	// nil interface because a typed-nil pointer in an interface is non-nil in Go, and this reads
	// `isset($f)` on the PHP side.
	GetCachedForm(formID string) (TagPageForm, bool)
}

// TagPageForm is the part of StandardForm this tag touches — the two calls at TagPageHandler.php:55,
// which clear the completed form so that, in the PHP's own words, "a refresh can't double-file"
// (:12-13).
type TagPageForm interface {
	// SetResults is StandardForm::setResults($formResults); the tag passes array().
	SetResults(results map[string]any)
	// Reset is StandardForm::reset().
	Reset()
}

// tagPageFormID is the form key the tag reads and resets. It is a literal in the PHP, repeated at :26
// and :55; named once here so the two cannot drift.
//
// It is a `forms`.formName value in the db, not a PHP class — see "WHAT THE PHP TAG IS" in the file
// header, which also states exactly how far that claim was verified here (not against the table).
const tagPageFormID = "TagPageForm"

// TagPageHandlerTag is TagPageHandler (TagPageHandler.php:16).
type TagPageHandlerTag struct {
	e *Engine

	// args is `private $arguments` (:18) — stored by the constructor (:19) and never read, here or in
	// the PHP. See "ARGUMENTS" in the file header for why that makes every invocation form of this tag
	// render the same bytes.
	args *TagArguments
}

// tagPageBack is `private static function back()` (TagPageHandler.php:21), verbatim.
//
// Note it points at ?page=pages — the page that HOSTS TagPageForm — not at ?page=forms, which is
// where its two siblings' back() links go (annotatehandler.go:343, newcategoryhandler.go:422). The
// three differ because their sources differ; each matches its own.
func tagPageBack() string {
	return "<p><a href='?page=pages'>&larr; back to tag a page</a></p>"
}

// tagPageResult is the ternary TagPageHandler.php:27-28 repeats for each of its two fields:
// isset($res[k]) ? trim((string) $res[k]) : <the empty string>.
//
// PHP's isset() is FALSE for a key that is PRESENT with a NULL value, so a form that stored
// pageId => NULL takes the empty-string path and never reaches the (string) cast. The nil test below
// is that isset(), transcribed.
//
// HONESTY ABOUT WHAT THAT NIL TEST BUYS, because the neighbouring comments claim traps and this one
// is not: for THIS tag it cannot change a single byte. The only value isset() rejects but `v, ok :=`
// accepts is NULL, and phpString(nil) is "" (engine.go:499-500) which phpTrim leaves "" — the same
// empty string the isset()-false arm returns. So both spellings agree on every input this tag can
// see, and the measured "both fields present-but-NULL" case is 71B on both sides either way. The nil
// test stays because it is what :27 SAYS, and a transcription that happens to be equivalent is still
// the right transcription — not because dropping it would be a bug here. (This mirrors
// newcategoryhandler.go:432-439 exactly; annotatehandler.go:350-353 makes the STRONGER claim for
// AnnotateHandler, where a NULL genuinely does change the branch. The difference is real: that tag's
// branch 1 is an AND over three fields feeding an in_array whitelist, so the empty string and a NULL
// land in different arms. Here both land in the same one.)
//
// phpTrim is trim()'s real charlist " \t\n\r\0\x0B" (engine.go:630); strings.TrimSpace is not, and
// THAT one is load-bearing: it decides branch 1 for whitespace-only fields (measured).
func tagPageResult(res map[string]any, key string) string {
	v, ok := res[key]
	if !ok || v == nil {
		return ""
	}
	return phpTrim(phpString(v))
}

// GetDocument is TagPageHandler::get_document() (TagPageHandler.php:23-66).
//
// The deferred catchThrowable is the `catch (\Throwable $e)` arm at :63-65. Every tag in this package
// has one because the engine has no error boundary of its own (engine.go:1703-1706) — a panic here
// would otherwise take the page down, which the PHP explicitly does not do.
func (t *TagPageHandlerTag) GetDocument() (out string) {
	defer catchThrowable(&out, "TagPageHandler")

	// :25-26 — $fm = PersistentObjectManager::getData('FORM_MANAGER');
	//          $res = isset($fm) ? $fm->getResults('TagPageForm') : null;
	fm, hasFM := t.tagPageFormManager()
	var res map[string]any
	if hasFM {
		res = fm.GetResults(tagPageFormID)
	}

	// :27-28 — the two fields, each isset-guarded and trimmed.
	pageID := tagPageResult(res, "pageId")
	category := tagPageResult(res, "category")

	// :30-32 — BRANCH 1. The test is `&&`: BOTH must be empty. A half-filled form falls THROUGH into
	// the validation ladder and is rejected there, naming the empty field back in an empty
	// <code></code>. See "BRANCH 1 NEEDS *BOTH* FIELDS EMPTY" in the file header — this is the single
	// easiest byte to get wrong in this file.
	if pageID == "" && category == "" {
		return "<p>No pending page tag. <a href='?page=pages'>Tag a page &rarr;</a></p>"
	}

	// ── Nothing above this line opened anything. ──

	// :33-34 — new PDO('sqlite:'.CONGRUENCY_SQLITE); setAttribute(ERRMODE_EXCEPTION).
	// A Go error from here on lands in the same cy-form-error div PHP's catch arm renders; see "WHAT
	// IS NOT BYTE-REPRODUCIBLE" in the file header for the one part of it that differs.
	db, err := openTagPageDB(t.e.cfg.SQLite)
	if err != nil {
		return throwableHTML("TagPageHandler", err)
	}
	defer db.Close()

	// :36-38 — BRANCH 2. $st = prepare("SELECT 1 FROM Documents WHERE DocumentID=?");
	//                    execute(array($pageId)); if (!$st->fetch()) { ... }
	//
	// This is the FIRST statement to touch the db, so a db lacking `Documents` throws HERE and
	// degrades into the error div — the PHP's own missing-dependency behavior, reproduced by creating
	// nothing. See "THE WRITE PATH".
	//
	// The comparison is SQL's `DocumentID=?`, whose default collation is BINARY, so it is exact and
	// case-sensitive on both engines. QueryRow+Scan is `fetch()` truthiness: sql.ErrNoRows is fetch()
	// returning false, a scanned row is fetch() returning an array. The scanned VALUE is discarded in
	// both engines — the PHP never looks inside the array either.
	if err := tagPageExists(db, "SELECT 1 FROM Documents WHERE DocumentID=?", pageID); err != nil {
		if err == sql.ErrNoRows {
			return "<p style='color:#b00020'>No such page: <code>" + esc(pageID) + "</code></p>" +
				tagPageBack()
		}
		return throwableHTML("TagPageHandler", err)
	}

	// :40-42 — BRANCH 3. $st = prepare("SELECT `key` FROM Categories WHERE name=?");
	//                    execute(array($category)); if (!$st->fetch()) { ... }
	//
	// THE SELECTED `key` IS NEVER USED — not here and not in the PHP, which discards the fetched array
	// exactly as this discards the scanned value. Only ROW EXISTENCE decides the branch. That matters
	// more than it looks: PDO's fetch() returns a non-empty ARRAY, and a non-empty array is TRUTHY in
	// PHP regardless of what is in it, so a Categories row whose `key` is NULL or 0 still PASSES this
	// check. The scan below therefore lands in an `any`, which accepts NULL; scanning into an int
	// would turn that row into "converting NULL to int is unsupported" — an error div where the PHP
	// renders the panel. `key` is a plain nullable INTEGER column (no PRIMARY KEY, no NOT NULL — see
	// the schema note in "WHAT WAS ACTUALLY RUN"), so a NULL there is storable, not hypothetical.
	//
	// The backticks around `key` are the PHP's, kept verbatim: sqlite accepts MySQL-style backtick
	// quoting, and this is the same statement text on both engines.
	if err := tagPageExists(db, "SELECT `key` FROM Categories WHERE name=?", category); err != nil {
		if err == sql.ErrNoRows {
			return "<p style='color:#b00020'>No such category: <code>" + esc(category) + "</code></p>" +
				tagPageBack()
		}
		return throwableHTML("TagPageHandler", err)
	}

	// ── BRANCH 4: the write (or the deliberate non-write). ──

	// :44-45 — // page-tagging is now an annotation: tag=<category name>, target="page:<DocumentID>"
	//          $target = 'page:' . $pageId;
	// Built from the TRIMMED pageId, which is the only form that exists by now.
	target := "page:" + pageID

	// :46-53 — the idempotency check and the conditional INSERT. This is the hand-rolled
	// SELECT-then-maybe-INSERT the PHP's docblock miscalls "INSERT OR IGNORE" (see "THE PHP'S OWN
	// DOCBLOCK IS WRONG"); $added is what it buys, and $added is what picks the sentence at :57-59.
	added := false
	err = tagPageExists(db, "SELECT 1 FROM annotations WHERE tag=? AND target=?", category, target)
	switch {
	case err == sql.ErrNoRows:
		// :50-52 — the prepared INSERT. NOTE THE PLACEHOLDER COUNT: the SQL is
		// `VALUES (?,?,'',?,?)` — `note` is a HARDCODED empty string literal in the statement, not a
		// bound parameter, so there are FIVE columns and FOUR binds. Every bind is a STRING because
		// PDOStatement::execute($array) binds PDO::PARAM_STR; the microtime float therefore goes in
		// through PHP's precision-14 float->string cast. See "PDO BINDS EVERYTHING AS A STRING".
		if _, err := db.Exec("INSERT INTO annotations (tag,target,note,ts,meta) VALUES (?,?,'',?,?)",
			category, target, phpFloatString(tagPageMicrotime(t.e.cfg)), tagPageMeta); err != nil {
			return throwableHTML("TagPageHandler", err)
		}
		added = true
	case err != nil:
		return throwableHTML("TagPageHandler", err)
	}

	// :55 — if (isset($fm)) { $f = $fm->getCachedForm('TagPageForm');
	//                         if (isset($f)) { $f->setResults(array()); $f->reset(); } }
	//
	// Clearing the completed form is what stops a refresh re-running this handler. It is OUTSIDE the
	// `if (!$chk->fetch())` above, so it runs on BOTH arms — the row was inserted just now, or it was
	// already there; either way the form is consumed. It runs AFTER the insert, so a failed insert
	// leaves the form intact — ported in place, not hoisted.
	if hasFM {
		if f, ok := fm.GetCachedForm(tagPageFormID); ok {
			f.SetResults(map[string]any{}) // setResults(array()) — the empty PHP array
			f.Reset()
		}
	}

	// :57-59 — the sentence. TWO DIFFERENT SENTENCES, and which one you get is the whole observable
	// difference between "I wrote a row" and "the row was already there". Both are pre-escaped here,
	// as the PHP pre-escapes them, before the <strong> wraps them at :61.
	msg := "Page <code>" + esc(pageID) + "</code> was already tagged <code>" + esc(category) + "</code>."
	if added {
		msg = "Tagged page <code>" + esc(pageID) + "</code> as <code>" + esc(category) + "</code>."
	}

	// :60-62 — the green panel. Byte-for-byte the PHP's concatenation, in its order, including the
	// "\n" between the closing </div> and the pages link.
	//
	// The href is `?page=pages&category=` . esc($category) — it ESCAPES, it does NOT urlencode, the
	// same choice its reader sibling makes (categorypages.go:123-131, CategoryPages.php:44). A
	// category named "R&D" therefore renders href='?page=pages&category=R&amp;D' with no percent-
	// encoding anywhere. Reaching for a URL encoder here would be tidier, more correct as HTML, and
	// WRONG — it would diverge on the first category whose name is not [A-Za-z0-9-_.].
	return "<div style='border:1px solid #1a7a3a;border-left:5px solid #1a7a3a;border-radius:6px;padding:.7rem .9rem;background:#f3fbf5'>" +
		"<p style='margin:.2rem 0'><strong>" + msg + "</strong></p></div>\n" +
		"<p><a href='?page=pages&category=" + esc(category) + "'>&rarr; see pages in " + esc(category) +
		"</a></p>"
}

// tagPageExists is `$st = $db->prepare($sql); $st->execute($args); $st->fetch()` reduced to the one
// question all three of this tag's SELECTs ask: DID A ROW COME BACK? Named once because the PHP asks
// it three times in the same shape, and because the answer is a three-way one that the call sites
// must not flatten:
//
//	nil            -> fetch() returned a row  (the array; PHP discards its contents, so this does too)
//	sql.ErrNoRows  -> fetch() returned false
//	any other err  -> PDO would have thrown -> the caller renders the error div
//
// The destination is an `any`, not an int: `SELECT \`key\`` can return NULL, and PHP's fetch() is
// truthy on the ARRAY, not on the value inside it. See the branch-3 comment in GetDocument.
func tagPageExists(db *sql.DB, query string, args ...any) error {
	var discard any
	return db.QueryRow(query, args...).Scan(&discard)
}

// tagPageMeta is json_encode(array('kind' => 'category')) (TagPageHandler.php:51).
//
// Precomputed as the literal it always encodes to: the input is a fixed single-pair map of ASCII with
// no character json_encode's default flags would escape, so PHP emits exactly these bytes on every
// call. Spelling the constant out makes the stored `meta` value readable here instead of requiring
// the reader to run PHP's encoder in their head. (Its sibling annotatehandler.go:470 does the same
// for its own, different literal — {"source":"annotate-form"}. The two tags stamp different meta on
// the same table by design: doc/CMS_ADDITIONS.md:49-56 describes `annotations` as one layer over
// several writers.)
const tagPageMeta = `{"kind":"category"}`

// tagPageMicrotime is microtime(true) — the current unix time in SECONDS as a float, to microsecond
// resolution.
//
// It reads the engine's clock seam (Config.Now, engine.go:334-335) rather than time.Now directly, so
// a caller driving branch 4 can pin the instant; nil Now is time.Now, which is the live path.
func tagPageMicrotime(cfg Config) float64 {
	return float64(cfg.now().UnixNano()) / 1e9
}

// openTagPageDB is `new PDO('sqlite:'.$path)` + setAttribute(ATTR_ERRMODE, ERRMODE_EXCEPTION)
// (TagPageHandler.php:33-34): a WRITABLE handle, which is why this exists next to engine.go's
// read-only openDB rather than calling it. See "THE WRITE PATH" in the file header for why mirroring
// PDO's create-on-missing is the faithful choice for a writing tag, and why no gate request reaches
// this function.
//
// IT IS A NEAR-DUPLICATE of openAnnotationsDB (annotatehandler.go:493) and openNewCategoryDB
// (newcategoryhandler.go:570), and that is the established shape rather than an oversight: #281's
// contract is one self-contained file per tag that edits nothing central, and hoisting one shared
// opener would be an edit to engine.go, which "touch nothing else" forbids. #320 made the same call
// with the same two files already in front of it. A ticket whose deliverable covers engine.go should
// collapse all three.
//
// ERRMODE_EXCEPTION needs no counterpart: database/sql returns an error from every call already, and
// each caller above turns it into the same cy-form-error div PHP's catch arm produces.
//
// The sqlite driver is registered by engine.go's blank import of modernc.org/sqlite (engine.go:243),
// which is the same driver openDB uses — both handles speak to the same file through the same
// implementation.
func openTagPageDB(path string) (*sql.DB, error) {
	// PHP would build the DSN 'sqlite:' . CONGRUENCY_SQLITE and, with the constant undefined, throw an
	// Error that its catch arm renders. There is no such constant in Go: an empty Config.SQLite is the
	// same "no path was configured" state, reported the same way — through the error return, into the
	// same div. (Unreachable live: boot/configure.php:42 always defines it, and server.go pins the
	// field from DBPath.)
	if path == "" {
		return nil, fmt.Errorf("no database path configured (CONGRUENCY_SQLITE)")
	}
	// NB: NO os.Stat guard, deliberately — openDB has one because a READ of a missing db must not
	// invent an empty one, whereas PDO CREATES the file here and this tag's whole purpose is the write
	// that follows. Mirroring means letting the driver create it, exactly as PDO does.
	db, err := sql.Open("sqlite", "file:"+path)
	if err != nil {
		return nil, err
	}
	// One connection, as PDO has one. It also serializes this handle's three SELECTs and its INSERT
	// onto the same sqlite connection, which is what makes the duplicate check at :46-49 and the
	// INSERT at :50-51 see the same state — the same property server.go:25-30 documents for its
	// per-request PDO handle.
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, err
	}
	return db, nil
}

// tagPageFormManager is `$fm = PersistentObjectManager::getData('FORM_MANAGER')` narrowed to the
// surface this tag calls. ok=false is `!isset($fm)` for this tag's purposes — either there is no
// FormManager at all, or the one configured answers only engine.go's narrower interface, which is
// indistinguishable in output from a FormManager holding no TagPageForm. The header's three-state
// table spells that equivalence out.
func (t *TagPageHandlerTag) tagPageFormManager() (TagPageFormManager, bool) {
	if t.e.cfg.FormManager == nil {
		return nil, false
	}
	fm, ok := t.e.cfg.FormManager.(TagPageFormManager)
	return fm, ok
}
