package tags

// style.go — ticket #333, unit go-port:tags:tag:Style.
//
// The Go port of ONE tag: invocators/tags/dev/Style.php — the site's single stylesheet. Every page
// template embeds <<<Style>>> in its <head> beside <<<TitleTag>>> (grounded below), so the whole
// look lives in one place; the app also serves it standalone at ?page=tags&tag=Style, because
// TagList::scan finds it under TAGS_DIR (TagList.php:22-37).
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. The PHP is the SPEC — where the two
// disagree THIS file is wrong, and "improving" the CSS here is a defect, not a fix.
//
// ── WHAT THIS FILE ADDS, AND WHAT IT DOES NOT TOUCH ─────────────────────────────────────────────
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// constant, and its self-registration (the init() below). Nothing in engine.go changes — the
// registry picks this tag up because Go runs every init() in a package before any other code in it
// (Register at engine.go:1355, newTag at engine.go:1393). Every identifier this file defines is
// style*-prefixed or Style*-named; audited this session against every sibling (see WHAT WAS RUN).
//
// (engine.go's COVERAGE header still lists Style under "NOT PORTED (35)", at engine.go:197. That
// list is a hand-maintained COPY; its own text names PortedTags() as "the authority"
// (engine.go:189-192), and PortedTags is registry-derived (engine.go:1406-1415), so it answers
// correctly the moment this file's init() runs. Correcting the copy means editing engine.go, which
// this ticket forbids ("touch nothing else") — the same stale-copy state #312, #316, #319 and #327
// left behind for DocList, Login, MemoryList and RepoDocs. It is a comment, not behaviour.)
//
// ── THIS TAG IS PURE: NO DB, NO ARGUMENTS, NO $_GET, NO DEGRADATION BRANCH ──────────────────────
//
// The ticket asks for this unit's "empty/error state (a tag that degrades gracefully against a
// missing dependency must degrade IDENTICALLY in Go; see tools/tag_selfcheck.py for what each tag
// depends on)". Read against that tool, the answer is that THIS TAG HAS NO DEPENDENCY AND THEREFORE
// NO SUCH STATE, and inventing one would be markup the PHP can never emit.
//
// tag_selfcheck.py extracts exactly three dependency kinds (tag_selfcheck.py:12-31): external
// sqlite dbs via the `getenv('X') ?: $HOME/<default>` pattern; SQL tables named after FROM/JOIN in
// the tag's SQL string literals; and DB-stored disk paths (repos.forge_remote). Style.php has none
// of the three — it contains no PDO, no query, no getenv, no filesystem call. Its get_document()
// (Style.php:16-29) is a concatenation of 12 double-quoted literals and nothing else. So:
//
//   - There is no openDB, no queryRows and no error arm here, and their absence is deliberate.
//   - It ignores $_GET entirely, so there is no filter/parameter surface. The ticket's "if this tag
//     takes arguments, drive each argument form" therefore has no argument form to drive beyond the
//     bare <<<Style>>> — which is the only form any template writes (grounded below).
//   - Its render is the same 485 bytes on every request, against any db or none. BugReport
//     (bugreport.go) is the sibling with this same shape; its header makes the same point.
//
// NO ERROR ARM, DELIBERATELY. Every DB-backed tag opens with `defer catchThrowable(&out, "<Tag>")`
// because each of those PHP classes has its own `catch (\Throwable $e)` arm — the engine has no
// error boundary of its own (FormTag.php:53-55). Style.php has NO try/catch anywhere, so there is
// no PHP branch for a catchThrowable here to mirror: adding one would invent bytes the PHP cannot
// emit. Nothing in GetDocument can produce them either — it returns a constant.
//
// NOTHING IS ESCAPED HERE, AND THAT IS THE PHP'S BEHAVIOUR. Style.php calls htmlspecialchars on
// nothing, because it has no data: every byte is a source literal. Running esc() over the constant
// would turn `<style>` into `&lt;style&gt;` and every page's CSS into visible text. The sibling
// BugReport port documents the same inversion of the usual esc-everything habit (bugreport.go:35-50).
//
// ── THE ONE THING IN THIS PORT THAT IS NOT A CONSTANT: <<<TelemetryBeacon>>> ────────────────────
//
// Style::get_document() ENDS by returning the literal text "<<<TelemetryBeacon>>>" (Style.php:28).
// That is not decoration and it is not this tag's output to expand: it is a TAG INVOCATION that the
// ENGINE substitutes after Style returns. TelemetryBeacon.php:8-9 states the arrangement from the
// other side — "Emitted ONCE per served page (spliced by <<<Style>>>, which every page template
// embeds in its <head>)". So Style is the splice point for the front-end telemetry beacon, and the
// beacon's <script> reaches every page THROUGH this tag.
//
// THE ENGINE REALLY DOES EXPAND IT, on both surfaces, and the reachability is worth spelling out
// because this unit's whole gate turns on it:
//
//   - FUNCTION_NAME is [a-zA-Z]+ (engine.go:273) and "TelemetryBeacon" is all letters, so tagPattern
//     MATCHES "<<<TelemetryBeacon>>>" — unlike Catalog_Controller, which its underscore makes
//     uninvokable (engine.go:200-204). Checked mechanically this session by rebuilding the pattern
//     from engine.go's own constants and matching it against the fragment (see WHAT WAS RUN).
//   - Nothing escapes Style's output before the engine rescans it. In a PAGE render,
//     execute_all_tags takes Style's return as $result_substring and str_replaces it into the
//     template (engine.go:1022-1039); the beacon is then expanded in the frame that owns Style's
//     output. In the GALLERY render, TagList.php:68 splices the selected tag's bytes in RAW —
//     `$out .= (string)$obj->get_document();`, no esc() — so the beacon invocation flows out with
//     TagList's own output and the engine expands it there too.
//   - Depth is not a factor: <<<Style>>> sits at depth 1 from a page template and the beacon at
//     depth 2, far under the 64 cap (engine.go:276, Tag_Wrapper.php:65).
//
// SO THIS FILE EMITS THE LITERAL "<<<TelemetryBeacon>>>", exactly as the PHP does, and DOES NOT
// inline the beacon's <script>. Inlining it would be wrong three times over: it would port a second
// unit inside this one's deliverable; it would make Style's own bytes differ from Style.php's at the
// get_document() seam the #282 harness measures; and it would emit the beacon TWICE the moment
// TelemetryBeacon is itself ported.
//
// THE CONSEQUENCE, STATED UP FRONT BECAUSE IT IS THIS UNIT'S CENTRAL FACT: TelemetryBeacon HAS NO GO
// PORT TODAY. Checked this session — there is no tags/telemetrybeacon.go, and no
// Register("TelemetryBeacon") anywhere in the package (engine.go:197 lists it under NOT PORTED; the
// registry sweep under WHAT WAS RUN confirms it is still absent). So in a Go PAGE render the engine
// finds the beacon invocation, newTag returns ok=false, and ExecuteAllTags substitutes
// unknownTagHTML — "<!-- congruency-go tags: no Go port for &lt;&lt;&lt;Telemetry… -->"
// (engine.go:990-993) — where the PHP substitutes the beacon's <script>. THAT DIVERGENCE IS REAL AND
// IT IS NOT THIS UNIT'S TO FIX: it is the unported TelemetryBeacon, and it will clear when that unit
// lands, with no edit to this file.
//
// This unit's ticket lists four dependencies, all engine units (engine_tag_wrapper,
// engine_tag_parser, engine_tagarguments, engine_tag_interface). It does NOT list
// go-port:tags:tag:TelemetryBeacon, and on the evidence above it should: the decomposer
// (tools/go_port_decomposer.py) derives dependencies from a tag's class/require graph, and this edge
// is not in that graph — it is a tag name inside a STRING LITERAL that only the tag engine resolves.
// Style cannot render byte-identically on any surface that expands its output until TelemetryBeacon
// is ported. That is a finding about the DECOMPOSITION, filed here rather than worked around,
// because working around it would mean writing another unit's file.
//
// ── WHERE <<<Style>>> IS EMBEDDED (the ticket's in-page substitution sites) ─────────────────────
//
// The ticket names 25 pages. The stored templates live in Document_Templates, which is in the state
// db — absent here (see THE GATE), so the rows could not be read directly. They are grounded instead
// in the MIGRATIONS that install them, which are in the worktree: `<<<Style>>>` occurs in 11 of them
// (0007, 0016, 0017, 0018, 0019, 0021, 0022, 0023, 0025, 0027, 0028), once each. Every occurrence is
// the BARE form — no page writes <<<Style(x)>>> — and every one sits in <head> beside <<<TitleTag>>>,
// e.g. migrations/0016_tree_page.sql:23-26:
//
//	<head>
//	<<<TitleTag>>>
//	<<<Style>>>
//	</head>
//
// That is what makes "drive each argument form the templates above actually use" a no-op for this
// unit: the only form in use is the bare one, and StyleTag ignores arguments exactly as Style.php
// does (see StyleTag). The 11 migrations do not account for all 25 pages the ticket lists — later
// pages' templates were installed by routes/tools rather than by a migration, and without the db
// those rows cannot be read here. The 11 that ARE readable are unanimous, and no mechanism exists by
// which an argument form would change this tag's output anyway (the constructor discards it).
//
// ── THE GATE — WHAT THE TICKET ASKS, WHAT IS RUNNABLE HERE, AND WHAT WAS RUN ───────────────────
//
// THE GATE IS UNMET, AND NOTHING BELOW SHOULD BE READ AS MEETING IT. The ticket's gate is two
// byte-diffs, PHP:8899 vs Go:8900, over the same db. NEITHER CAN BE RUN FROM THIS WORKTREE. Saying
// so is what the ticket asks for — "if you cannot make a diff here run against THIS unit, say so on
// the ticket rather than settling on a diff that would be empty even with the unit unimplemented".
//
// WHY IT CANNOT BE RUN HERE. Probed this session, not assumed:
//
//   - THERE IS NO PHP. `which php` finds nothing. The ticket names tooling/congruencey-harness/php/php;
//     that directory does not exist — the harness tree holds only .php sources (router.php, shim.php,
//     AutoLoader.php, Constants_patched.php, telemetry.php, serve), because its .gitignore ignores
//     `php/`. So no PHP server can be booted on 8899 and the golden side of every diff is absent.
//   - THERE IS NO DB. CONGRUENCY_SQLITE is <app>/../state/congruency.sqlite (configure.php:42) =
//     checkouts/current/state/congruency.sqlite. That directory exists and holds no .sqlite at all
//     (README.md, STATE.json, component.json, manifest.json, state.lock). Both sides of the diff must
//     read the SAME db; there is none.
//   - curl and lsof are not permitted commands in this session, so the two diffs could not even be
//     attempted against a server someone else might be running. With no php binary and no db in this
//     worktree, such a server would not be serving this checkout in any case.
//
// AND BOTH DIFFS ARE CONFOUNDED ON THEIR OWN TERMS — each would be non-empty for reasons that are
// not this unit, so neither measures Style even with the servers up:
//
//	diff 1  ?page=tags&tag=Style   The PHP returns a FULL CMS page; the Go server does not reproduce
//	                               the page frame and says so itself (server.go:39-43, 62-66: "NOT
//	                               claimed: that the page's BYTES match PHP … larger by a constant
//	                               ~6.2 KB of CMS chrome"). The tag's own bytes are a SLICE of that
//	                               page (equivalence_test.go:28-33). It is ALSO confounded by the
//	                               unported TelemetryBeacon, above.
//	diff 2  the 25 embedding pages server.go's handlePage routes EVERY page key except "tags" to
//	                               handleCatalogPage, the table-list seam that never invokes the tag
//	                               engine (server.go:727-735, 831-833). So ?page=about etc. on the Go
//	                               server cannot reach Style at all. Wiring it is an edit to
//	                               server.go, which this ticket forbids. Those pages further embed
//	                               <<<TitleTag>>> and <<<SiteMap>>> (migrations/0016_tree_page.sql:24,28),
//	                               NEITHER of which is ported — so page-level diffs are dominated by
//	                               other units' gaps regardless of Style.
//
// THE REAL GATE for a tag unit is #282's harness — and #323 settled that this, not the two
// curl-diffs, is how a tag unit is measured:
//
//	cd congruency-go && go test ./tags/ -run TestTagEquivalence/Style -v
//
// It cuts the tag's own bytes out of the live PHP page with TagList.php's own anchors and compares
// them to RenderTag's, with a stability sandwich against concurrent writers. It needs the live 8899
// and the shared state db; absent either it SKIPS (its four guards) — and here it would skip on
// guard 2, the absent db. It requires NO edit to run this tag: it sweeps Scan(TAGS_DIR) and measures
// whatever IsPorted reports, so the init() below is the whole wiring.
//
// AND IT WILL REPORT A BYTE MISMATCH FOR Style WHEN IT DOES RUN, WHICH MUST BE SAID IN ADVANCE
// RATHER THAN LEFT AS A SURPRISE. The harness compares RenderTag's bytes to the PHP page slice, and
// the two sides do not treat the beacon alike:
//
//	Go  side: RenderTag returns tag.GetDocument() DIRECTLY — it never runs ExecuteAllTags
//	          (engine.go:4147-4160). So it yields the literal "…</style><<<TelemetryBeacon>>>".
//	PHP side: the slice is cut from a rendered PAGE, where the engine has ALREADY expanded the
//	          beacon inside TagList's output (TagList.php:68 splices raw). So it yields
//	          "…</style><script>…</script>".
//
// Those differ, and NEITHER side is wrong about Style: the 485 bytes below are byte-exact against
// Style.php's own literals (measured; see WHAT WAS RUN). The mismatch is the unported TelemetryBeacon
// meeting the harness's no-engine path. A reader who sees that red must NOT "fix" it by inlining the
// script here; see the beacon section. It clears when TelemetryBeacon is ported.
//
// ── WHAT WAS ACTUALLY RUN THIS SESSION, AND WHAT WAS NOT ───────────────────────────────────────
//
// THIS GO CODE WAS NOT COMPILED AND NOT EXECUTED, AND THAT IS A REAL GAP IN THIS DELIVERABLE. It
// must be said plainly rather than left for the reader to discover. `go` IS on PATH here (unlike the
// #226/#281/#327 sessions, which record it as absent), but every `go` invocation — `go build`,
// `go vet`, `gofmt`, `go test` — is refused by this session's permission layer; each was attempted.
// So the usual floor ("RUN your own work before reporting done") could not be met: the Go below is
// audited, not run, and a compile error in it would be a live defect that no step in this session
// could have caught. THE FIRST THING TO DO WITH THIS FILE IS:
//
//	cd congruency-go && go build ./... && go vet ./tags/
//
// That risk is why this file is deliberately MINIMAL — a const, a struct, a one-line method and an
// init(). It imports NOTHING (so no unused-import error is possible), declares no helper, and
// contains no control flow. An earlier draft carried a styleSelfCheck() invariant helper; it was cut
// precisely because it was ~40 lines of unwired, uncompilable code whose only possible effect on this
// package was to break the build for EVERY tag in it. Register's signature and the Tag interface were
// matched by eye against engine.go:1355 and engine.go:852, and against the sibling bugreport.go:70-72,
// which uses the identical shape.
//
// WHAT WAS RUN — python3 only (it is permitted; `go` is not). Two mechanical audits, not a render:
//
//   - THE PROVENANCE EXTRACTION. Style.php's return value was extracted MECHANICALLY from the PHP
//     source by a lexer, so the constant below is DERIVED FROM THE PHP rather than hand-typed. The
//     lexer skips `//` comments — load-bearing, because Style.php:26's comment contains an apostrophe
//     in "class='prose'", which naive quote-scanning turns into an open string that swallows the rest
//     of the file (repodocs.go's header records the identical trap on RepoDocs.php:19). It also finds
//     the statement-terminating `;` by lexing rather than by index(';'), because the CSS literals
//     contain `;` themselves — a first draft used index(';') and silently truncated the extraction to
//     TWO literals. The TOOL was broken, not the source; both bugs were fixed before it was trusted.
//     Result: 12 literals, no interpolation ($), no escape sequence (\), joining to 485 bytes with no
//     newline.
//   - THE LITERAL / SKELETON AUDIT. Both sides lexed (skipping comments on the Go side too, since
//     this header quotes the PHP's literals verbatim and they would otherwise be counted as code) and
//     compared fragment by fragment: all 12 IDENTICAL and IN ORDER, joining to a byte-identical 485B
//     skeleton. Order is what a per-literal check alone cannot prove — that no fragment is dropped,
//     reordered or emitted twice.
//   - THE BEACON REACHABILITY CHECK. tagPattern was REBUILT from engine.go's own FunctionName /
//     FunctionArguments constants and matched against "<<<TelemetryBeacon>>>": it matches. So the
//     fragment this file emits is one the engine resolves, not inert text. The CSS fragments were
//     also swept for any other invocation the pattern would catch: none.
//   - THE REGISTRATION / COLLISION AUDIT. Register("Style") has exactly ONE call site in the package
//     (a duplicate PANICS at package init and would take every render down, engine.go:1355);
//     Register("TelemetryBeacon") is absent from all 25 files, which is the beacon claim above
//     measured rather than asserted; and none of the identifiers this file declares (StyleTag,
//     styleDocument) collides with any of the 24 sibling files' top-level names.
//
// These audits see BYTES AND NAMES. They cannot see a type error, a nil deref or a control-flow
// mistake — there is no control flow here, which is the point.
//
// NOT run, and therefore NOT claimed: the Go, at all; any byte-diff against a live PHP render, for
// this tag or any other; the #282 harness. No PHP executed anywhere in this session — no php binary
// exists here. The 485 bytes are proved equal to the PHP SOURCE's literals, which is a strictly
// weaker claim than proved equal to a PHP RENDER, and the difference is exactly the gate that
// remains open.

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there,
// and TestTagEquivalence starts measuring this tag with no edit either.
func init() {
	Register("Style", func(e *Engine, a *TagArguments) Tag { return &StyleTag{e: e, args: a} })
}

// StyleTag is Style (Style.php:13-31).
//
// args mirrors the PHP constructor's $arguments (Style.php:15) — and note the PHP constructor's body
// is EMPTY: `public function __construct($arguments) {}`. It does not even store the value, let alone
// read it. So this tag can no more be influenced by <<<Style(x)>>> than by a nil, and no template
// writes an argument form anyway (see the file header). A nil *TagArguments — what TagList.php:67's
// `new $sel(null)` passes, the shape the ?page=tags&tag=Style gate takes — is therefore stored and
// ignored, which is exactly what the PHP does with the NULL it is handed.
//
// This constructor CANNOT throw on nil args (contrast CategoryView, categoryview.go): Style.php:15
// dereferences nothing. So the gallery render is not an error path — it is the tag's only path.
// There is no ctorThrew here and there must not be one.
//
// e is likewise unread: this tag consults no engine state, no $_GET and no db. Both fields exist to
// match the registry's factory shape (engine.go:1355) and the sibling ports' struct shape.
type StyleTag struct {
	e    *Engine
	args *TagArguments
}

// styleDocument is Style::get_document()'s return value (Style.php:17-28).
//
// The PHP builds it with 12 concatenated double-quoted literals. NONE contains a `$`, so none
// interpolates, and none contains a backslash escape — both verified mechanically, see the file
// header — so the concatenation is a COMPILE-TIME CONSTANT and is spelled as one here. The 12
// fragments below are split on exactly the PHP's 12 boundaries, in the PHP's order, so a reader can
// set the two side by side and match them line for line. That correspondence is not a courtesy: it
// is what the skeleton audit checks.
//
// THERE ARE NO NEWLINES IN THIS OUTPUT. The PHP's line breaks are BETWEEN the `.` concatenations,
// not inside the strings, so the whole stylesheet emits as a single unbroken line and the render
// carries no trailing newline. That is why the fragments are joined with `+` and nothing else: a
// "\n" added for readability would be a byte diff on every page that embeds this tag.
//
// THE `// reading pages opt in…` TEXT AT Style.php:26 IS A PHP COMMENT, NOT OUTPUT. It sits after
// the ".prose{max-width:70ch}" literal on the same source line, so the literal ends at `}` and the
// comment contributes nothing. (It is also why this file's provenance check needed a real lexer —
// the comment's "class='prose'" apostrophe breaks naive quote-scanning.)
//
// THE TRAILING "<<<TelemetryBeacon>>>" IS A LIVE TAG INVOCATION, NOT TEXT. It is the last fragment
// (Style.php:28) and the engine substitutes the beacon's <script> for it after this tag returns. Do
// NOT inline the script here, and do NOT escape this fragment — escaping it would make the engine
// unable to match it (engine.go's header, mechanism 2) and would silently strip the telemetry beacon
// from every page in the app. See the file header's beacon section for the whole argument.
const styleDocument = "<style>" +
	"body{font-family:Georgia,serif;margin:1.5rem 2.5rem;line-height:1.6;color:#222;background:#f7f4ee}" +
	"a{color:#8a5a1a}" +
	"h1,h2{font-weight:normal}" +
	"code{background:#eae5d8;padding:1px 4px}" +
	"pre{background:#f4f1e8;border:1px solid #d8d2c4;padding:.6rem;overflow:auto}" +
	"nav{margin:0 0 1.5rem;padding-bottom:.75rem;border-bottom:1px solid #ccc;text-transform:uppercase;letter-spacing:.04em}" +
	"table{border-collapse:collapse}" +
	"th,td{text-align:left}" +
	".prose{max-width:70ch}" +
	"</style>" +
	"<<<TelemetryBeacon>>>"

// GetDocument is Style::get_document() (Style.php:16-29).
//
// The PHP returns a constant and so does this: there is no db, no $_GET, no argument and no error arm
// to branch on (see the file header). The strings.Builder every sibling port opens with would be
// noise here — there is nothing to build.
func (t *StyleTag) GetDocument() string {
	return styleDocument
}
