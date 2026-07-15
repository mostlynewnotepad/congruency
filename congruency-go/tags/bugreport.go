package tags

// bugreport.go — ticket #252, unit go-port:tags:tag:BugReport.
//
// The Go port of invocators/tags/dev/BugReport.php — the catalog of bugs found in congruency
// itself, which the app serves standalone at ?page=tags&tag=BugReport. (No Document_Templates row
// embeds <<<BugReport>>> today, so that gallery URL is this unit's whole render surface.)
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. The PHP is the SPEC — where the two
// disagree THIS file is wrong, and "improving" the markup here is a defect, not a fix.
//
// ── WHAT THIS FILE ADDS, AND WHAT IT DOES NOT TOUCH ─────────────────────────────────────────────
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers, and its self-registration (the init() below). Nothing in engine.go changes — the
// registry picks this tag up because Go runs every init() in a package before any other code in it
// (engine.go:1309-1314). Every identifier this file defines is bugReport*-prefixed or
// BugReport*-named, so it cannot collide with the sibling tag ports still to land (#246+). Note in
// particular that the sibling BugCatalog port already owns bugSeverityColor (engine.go:1921) — a
// DIFFERENT tag with a DIFFERENT palette; this file's bugReportColour is deliberately separate and
// the two must not be merged (see bugReportColour).
//
// ── THIS TAG IS PURE: NO DB, NO ARGUMENTS, NO DEGRADATION BRANCH ────────────────────────────────
//
// Unlike every tag ported before it, BugReport reads NOTHING. Its catalog is a PHP array literal in
// the source (BugReport.php:27-62), not a query, so:
//
//   - It has no SQL, no getenv/external-db, and no repos.forge_remote — the three dependency kinds
//     tools/tag_selfcheck.py extracts — so it has NO dependency to degrade against and therefore NO
//     empty/error state to reproduce. Its render is the same 8 bugs on every request.
//   - It ignores $_GET entirely, so there is no filter/form surface.
//   - There is no openDB/queryRows/catchThrowable here, and their absence is deliberate — see
//     GetDocument's "NO ERROR ARM" note.
//
// ── NOTHING IS ESCAPED HERE, AND THAT IS THE PHP'S BEHAVIOUR ────────────────────────────────────
//
// This is the one trap in this port, and it inverts the habit every sibling port teaches. The
// sibling tags esc() every value because their values are DATA out of a database. BugReport's
// values are SOURCE LITERALS that already contain hand-written HTML entities — &mdash;, &rsquo;,
// &hellip;, &ldquo;/&rdquo;, and (BugReport.php:51) the pre-escaped tag example
// "&lt;&lt;&lt;TitleTag&gt;&gt;&gt;". BugReport::get_document() calls htmlspecialchars on NONE of
// them (BugReport.php:69-94): it interpolates each straight into the output. So this file emits
// them RAW too. Running esc() over them would turn &mdash; into &amp;mdash; and render the
// entities as visible source text — a byte diff on every one of the 8 entries.
//
// That is safe here for the reason BugReport.php:15-16 states in its own header: the output flows
// back through execute_all_tags, so any live <<<Name>>> in it would be re-parsed — which is why
// the ONE place a tag example appears (BUG-06's description) is written pre-escaped AT THE SOURCE.
// The guard is the literal, not a call. Since the catalog is a compile-time constant with no
// caller-supplied input reaching it, no untrusted byte can enter this render.
//
// ── PHP SEMANTICS REPRODUCED, NOT APPROXIMATED ──────────────────────────────────────────────────
//
// Three PHP behaviours carry real bytes and each is reproduced at the code that needs it:
//
//   - array_pad($b, 6, null) (BugReport.php:81) pads the ONE short row (BUG-08, which has 5
//     elements — BugReport.php:58-60) to 6, making its $fixed NULL. See bugReportCatalog.
//   - PHP truthiness on $fixed (BugReport.php:82-88) decides the colour, the severity word, the
//     opacity, the strike-through and the whole resolved-note line. See bugReportTruthy.
//   - isset($map[$sev]) ? ... : '#666' (BugReport.php:66) is a lookup with a default, not a
//     switch over a closed set. See bugReportColour.
//
// The dead `$gh` assigned inside catalog() (BugReport.php:28) is not ported: it is shadowed by the
// live one get_document() assigns (BugReport.php:70) and never read. Omitting an unread local
// cannot move a byte.

import "strings"

// init self-registers the tag. This is the whole wiring step (#281; engine.go:1293-1307).
func init() {
	Register("BugReport", func(e *Engine, a *TagArguments) Tag { return &BugReportTag{e: e, args: a} })
}

// BugReportTag is BugReport (BugReport.php:19-95).
//
// args mirrors the PHP constructor's $arguments (BugReport.php:21-25), which the PHP stores in a
// private field and NEVER reads — the tag takes no arguments and no template embeds it, so the bare
// <<<BugReport>>> / gallery form is the only form. A nil *TagArguments (what TagList.php:67's
// `new $sel(null)` passes, the shape the ?page=tags&tag=BugReport gate takes) is therefore stored
// and ignored, which is exactly what the PHP does with the NULL it is handed. e is likewise unread:
// this tag consults no engine state.
type BugReportTag struct {
	e    *Engine
	args *TagArguments
}

// bugReportEntry is one row of BugReport::catalog()'s array literal (BugReport.php:29-61), after
// array_pad($b, 6, null) (BugReport.php:81) and the list() destructuring it feeds.
//
// fixed MODELS PHP's null-or-string EXACTLY as a plain string, and the empty string is not a lossy
// stand-in for NULL here: $fixed is only ever (a) tested for truthiness and (b) interpolated when
// that test passed. PHP's null and "" are both falsy, so they are indistinguishable through (a),
// and (b) can never see either. See bugReportTruthy.
type bugReportEntry struct {
	id    string
	sev   string
	title string
	desc  string
	loc   string
	fixed string // "" is array_pad's NULL — the unfixed row (BUG-08)
}

// bugReportCatalog is BugReport::catalog()'s return value (BugReport.php:27-62).
//
// It is a PHP ARRAY LITERAL, so its order is fixed by the source, not by any sort, and GetDocument
// emits it in exactly this order. The strings are copied verbatim, entities and all, and they are
// SINGLE-quoted in the PHP — so `$itemKey` and `$key` in BUG-01 are literal dollar-sign text, not
// interpolations, and they must survive into the output as typed.
//
// BUG-08 is the only row the PHP writes with 5 elements instead of 6 (BugReport.php:58-60); its
// fixed is "" here, which is what array_pad(..., 6, null) makes it. It is the only row that takes
// every un-resolved branch in GetDocument, and so the only one that proves those branches.
var bugReportCatalog = []bugReportEntry{
	{
		id: "BUG-01", sev: "critical", title: "SQL injection in the product catalog",
		desc:  "select_products_by_category() validates the key into $itemKey, then guards on isset($key) and interpolates the RAW $key into SQL. The validated value is dead code one variable name away.",
		loc:   "lib/Modules/StoreModule/Catalog/DAO/CatalogDAO.php#L58",
		fixed: "FIXED &mdash; CatalogDAO now interpolates the validated $itemKey and guards isset($itemKey); malicious keys sanitise to NULL.",
	},
	{
		id: "BUG-02", sev: "high", title: "ProductDAO never opens a connection",
		desc:  "The constructor sets $this->table but omits the CreateConnection()->open() every sibling DAO has. First query dereferences null.",
		loc:   "lib/Modules/StoreModule/Catalog/DAO/ProductDAO.php#L25",
		fixed: "FIXED &mdash; the constructor now opens the STORE connection like sibling DAOs.",
	},
	{
		id: "BUG-03", sev: "high", title: "OrderDAO::updateRow calls a method that does not exist",
		desc:  "Calls $this->insert() (no such method) and passes a bare key to delete() where a WHERE-clause is expected.",
		loc:   "lib/Modules/StoreModule/Order/DAO/OrderDAO.php#L65",
		fixed: "FIXED &mdash; updateRow now uses deleteRow() (a WHERE clause) and insertRow() (the real insert).",
	},
	{
		id: "BUG-04", sev: "medium", title: "Empty result set returns null, not []",
		desc:  "returnAllBeans() inits to NULL and only fills in-loop; a zero-row query returns null and callers do current(null) -> TypeError.",
		loc:   "lib/DatabaseDrivers/MySQL/AbstractDAO.php#L86",
		fixed: "FIXED &mdash; returnAllBeans() now inits array(); a zero-row query returns [].",
	},
	{
		id: "BUG-05", sev: "medium", title: "A missing page crashes the front controller",
		desc:  "Controller::display passes a possibly-null document to setData(), which does get_class(null). Silent false in PHP 5; fatal TypeError in PHP 8.",
		loc:   "lib/PersistanceObjectManager/PersistentObjectManager.php#L75",
		fixed: "RESOLVED &mdash; setData guards get_class with is_object(); DocumentManager falls back to the invalid document for missing pages.",
	},
	{
		id: "BUG-06", sev: "medium", title: "Unbounded tag recursion (stored-content DoS)",
		desc:  "execute_all_tags recurses into a tag&rsquo;s rendered output with no depth/visited guard. A document whose Title is &lt;&lt;&lt;TitleTag&gt;&gt;&gt; loops forever.",
		loc:   "lib/TagLoader/Tag/Tag_Wrapper.php#L81",
		fixed: "FIXED &mdash; execute_all_tags now caps recursion depth at 64.",
	},
	{
		id: "BUG-07", sev: "high", title: "Config constants referenced but never defined",
		desc:  "The store/order/auth modules use MYSQL_STORE_DATABASE, ETC, &hellip; that Constants.php never defines. Undefined constants are fatal on PHP 8 &mdash; why Install.txt says &ldquo;does not execute.&rdquo;",
		loc:   "www/Constants.php",
		fixed: "RESOLVED &mdash; config-as-data (constants.default.json + configure.php) now defines MYSQL_*, ETC, &hellip;.",
	},
	{
		// The 5-element row (BugReport.php:58-60): array_pad supplies the NULL $fixed, modelled "".
		id: "BUG-08", sev: "low", title: "Command queue runs in reverse",
		desc: "execute() drains the queue with array_pop(), so commands fire last-in-first-out.",
		loc:  "lib/CommandQueues/InterfaceObject/CommandInterfaceObject.php#L38",
	},
}

// bugReportGitHub is the $gh get_document() assigns and interpolates into each entry's link
// (BugReport.php:70,89). The identically-valued $gh in catalog() (BugReport.php:28) is dead — see
// the file header.
const bugReportGitHub = "https://github.com/dudezilla/congruency/blob/main/"

// bugReportResolvedColour is the colour every RESOLVED entry gets, which overrides its severity
// colour entirely (BugReport.php:82).
const bugReportResolvedColour = "#1a7a3a"

// bugReportTruthy is PHP's truthiness test on $fixed (BugReport.php:82-88 — `$fixed ? ... : ...`
// and `if ($fixed)`).
//
// PHP's rule for the values $fixed can hold: NULL is falsy; "" is falsy; "0" is falsy; every OTHER
// string is truthy. The "0" arm is what makes this a PORT of PHP's rule rather than a `!= ""`
// convenience — no catalog entry is "0" today, so both spellings agree on the current data, but
// only this one keeps agreeing if an entry ever is. Writing the real rule costs one clause and
// removes a silent trap for whoever edits the catalog next.
func bugReportTruthy(s string) bool { return s != "" && s != "0" }

// bugReportColour is BugReport::colour() (BugReport.php:64-67):
//
//	$map = array('critical' => '#b00020', 'high' => '#b5651d', 'medium' => '#8a7a1a', 'low' => '#5a6a5a');
//	return isset($map[$sev]) ? $map[$sev] : '#666';
//
// The default arm is REACHABLE ONLY through a catalog edit — every sev in the literal today is one
// of the four keys — but it is the PHP's behaviour and is ported, not elided. isset() is exact here
// because no map value is NULL (isset returns false for a NULL value, which would otherwise make
// isset differ from array_key_exists).
//
// NOT to be merged with the sibling bugSeverityColor (engine.go:1921-1934), which serves the
// DIFFERENT tag BugCatalog: same four severity NAMES, different hex values (#c62828/#e65100/
// #b5a300/#777, default #555) — the two palettes are genuinely distinct and sharing either one
// would put the other tag's colours in this tag's bytes.
func bugReportColour(sev string) string {
	switch sev {
	case "critical":
		return "#b00020"
	case "high":
		return "#b5651d"
	case "medium":
		return "#8a7a1a"
	case "low":
		return "#5a6a5a"
	}
	return "#666"
}

// bugReportStyle is the <style> block get_document() concatenates before the loop
// (BugReport.php:71-79), ending in the "</style>\n<div class='bugs'>\n" that opens the list.
//
// The PHP builds it with eight `$out .=` of double-quoted literals; none contains a `$`, so none
// interpolates, and the concatenation is a constant. It is spelled as one constant here for the
// same reason: the bytes are fixed. The PHP's line breaks are between the .= calls, NOT in the
// string — the ONLY newlines in the whole block are the two explicit \n at its end
// (BugReport.php:79), so the CSS emits as a single unbroken line.
const bugReportStyle = "<style>" +
	".bugs{display:grid;gap:.8rem}" +
	".bug{border:1px solid #d8d2c4;border-left:5px solid #999;border-radius:6px;padding:.7rem .9rem;background:#fffdf8}" +
	".bug h3{margin:0 0 .2rem;font-size:1rem;font-weight:normal}" +
	".bug .id{font:600 .72rem/1 monospace;letter-spacing:.05em}" +
	".bug .sev{float:right;font:600 .62rem/1.6 sans-serif;text-transform:uppercase;color:#fff;padding:.1rem .45rem;border-radius:3px}" +
	".bug p{margin:.35rem 0 .3rem;font-size:.85rem;color:#444;line-height:1.45}" +
	".bug a{font:.72rem/1 monospace;color:#8a5a1a}" +
	"</style>\n<div class='bugs'>\n"

// GetDocument is BugReport::get_document() (BugReport.php:69-94).
//
// The emitted shape, per entry, is BugReport.php:83-90 in order — and the two-space indent on the
// opening div, the absence of any newline between the pieces, and the single "\n" that closes each
// entry are all load-bearing bytes:
//
//	"  <div class='bug' style='border-left-color:$c[;opacity:.72]'>"   :83
//	"<span class='sev' style='background:$c'>resolved|$sev</span>"     :84
//	"<span class='id'>$id</span>"                                      :85
//	"<h3[ style='text-decoration:line-through']>$title</h3>"           :86
//	"<p>$desc</p>"                                                     :87
//	"<p style='...'>&#10003; $fixed</p>"   (resolved entries only)     :88
//	"<a href='$gh$loc'>$loc</a>"                                       :89
//	"</div>\n"                                                         :90
//
// then one closing "</div>\n" for the list (BugReport.php:92). So the render ends with the two
// consecutive "</div>\n" — the entry's and the list's — which is the shape the gate's slice cut
// depends on (equivalence_test.go's tagOutClose).
//
// Every bracketed piece above is present IFF bugReportTruthy(fixed), and a resolved entry ALSO
// takes bugReportResolvedColour in place of its severity colour (:82) and the word "resolved" in
// place of its severity (:84). BUG-08 is the only entry that takes none of them.
//
// NO ERROR ARM, DELIBERATELY. Every tag ported before this one opens with
// `defer catchThrowable(&out, "<Tag>")`, because each of those PHP classes has its own
// `catch (\Throwable $e)` arm — the engine has no error boundary of its own (engine.go:1703-1706).
// BugReport.php has NO try/catch anywhere (BugReport.php:69-94), so there is no PHP branch for a
// catchThrowable here to mirror: adding one would invent bytes the PHP can never emit. Nothing in
// this function can produce them either — it indexes no map, dereferences no pointer, and touches
// no I/O; it concatenates constants.
func (t *BugReportTag) GetDocument() string {
	var b strings.Builder
	b.WriteString(bugReportStyle)
	for _, e := range bugReportCatalog {
		resolved := bugReportTruthy(e.fixed)

		// :82 — a resolved entry's colour REPLACES its severity colour.
		c := bugReportColour(e.sev)
		if resolved {
			c = bugReportResolvedColour
		}

		// :83
		b.WriteString("  <div class='bug' style='border-left-color:" + c)
		if resolved {
			b.WriteString(";opacity:.72")
		}
		b.WriteString("'>")

		// :84 — the severity WORD is replaced too, not just the colour.
		b.WriteString("<span class='sev' style='background:" + c + "'>")
		if resolved {
			b.WriteString("resolved")
		} else {
			b.WriteString(e.sev)
		}
		b.WriteString("</span>")

		// :85
		b.WriteString("<span class='id'>" + e.id + "</span>")

		// :86
		b.WriteString("<h3")
		if resolved {
			b.WriteString(" style='text-decoration:line-through'")
		}
		b.WriteString(">" + e.title + "</h3>")

		// :87
		b.WriteString("<p>" + e.desc + "</p>")

		// :88 — the &#10003; check mark, then a SPACE, then the note.
		if resolved {
			b.WriteString("<p style='color:#1a7a3a;font-weight:600;margin:.2rem 0'>&#10003; " + e.fixed + "</p>")
		}

		// :89 — $gh and $loc are adjacent interpolations in one href; $loc is also the link TEXT.
		b.WriteString("<a href='" + bugReportGitHub + e.loc + "'>" + e.loc + "</a>")

		// :90
		b.WriteString("</div>\n")
	}
	// :92 — the list close.
	b.WriteString("</div>\n")
	return b.String()
}
