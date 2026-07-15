package tags

// apireference.go — ticket #248, unit go-port:tags:tag:ApiReference.
//
// The Go port of invocators/tags/dev/ApiReference.php — the standardized, data-driven API
// reference the app serves at ?page=api and at ?page=tags&tag=ApiReference.
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. The PHP is the SPEC. Everything
// below that looks odd is odd because ApiReference.php is odd; where the two disagree THIS file is
// wrong. Two of its behaviours are load-bearing quirks that a "cleaner" port would silently
// break, and each is called out at the function that reproduces it:
//
//   - table() emits the UNTRIMMED params when params is non-blank, though it TRIMS to decide
//     blankness (ApiReference.php:87).
//   - splitTop() appends every intermediate field unconditionally but drops a blank FINAL one
//     (ApiReference.php:150).
//
// ── WHAT THIS FILE ADDS, AND WHAT IT DOES NOT TOUCH ─────────────────────────────────────────────
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers, and its self-registration (the init() below). Nothing in engine.go changes — the
// registry picks this tag up because Go runs every init() in a package before any other code in
// it (engine.go:1309-1314). Every identifier this file defines is apiRef*-prefixed or
// ApiReference*-named, so it cannot collide with the sibling tag ports still to land (#246+).
//
// It REUSES the package's PHP primitives rather than restating them, because those are the audited
// byte-exact ones: esc (htmlspecialchars($s, ENT_QUOTES), engine.go:599), phpString (PHP's (string)
// cast over a PDO row's native types — NULL becomes "", engine.go:497), phpTrim (trim()'s charlist
// " \t\n\r\0\x0B", engine.go:630), isPHPSpace (PCRE's \s = [ \t\n\r\f\v], engine.go:624),
// asciiLower (PHP 8 strtolower, engine.go:3217), isAlnumASCII (engine.go:833), openDB/queryRows
// (PDO::query(...)->fetchAll(PDO::FETCH_ASSOC), engine.go:1173,1241) and catchThrowable (the
// catch(\Throwable) block, engine.go:1715).
//
// trim() vs \s IS NOT INTERCHANGEABLE HERE and the difference is deliberate throughout: PHP's
// trim() strips \0 and \v but NOT \f, while PCRE's \s matches \f and \v but NOT \0. So a trim()
// in the PHP is phpTrim here, and a \s in a PHP regex is isPHPSpace here — never the other way,
// and never strings.TrimSpace (which also strips Unicode spaces PHP's trim does not).
//
// SECURITY — the htmlspecialchars recursion guard (engine.go's file header, mechanism 2). A route's
// name/sql/params/meta are DATA read from api_routes, and this render flows back through
// execute_all_tags. Every one of them is esc()'d before it is emitted, exactly as the PHP escapes
// it, so a stored "<<<Tag>>>" comes back as "&lt;&lt;&lt;Tag&gt;&gt;&gt;" and stays inert. Note
// WHERE the escape happens for the derived shape: deriveShape splices the RAW name and the RAW
// column names into its string (ApiReference.php:103-110), and table() esc()'s the finished shape
// (ApiReference.php:93). That is escape-once at the emit site, and it is what the PHP does — do
// not "fix" it by escaping inside deriveShape, which would double-escape every shape cell.

import (
	"strconv"
	"strings"
)

// init self-registers the tag. This is the whole wiring step (#281; engine.go:1293-1307).
func init() {
	Register("ApiReference", func(e *Engine, a *TagArguments) Tag { return &ApiReferenceTag{e: e, args: a} })
}

// ApiReferenceTag is ApiReference (ApiReference.php:22-181).
//
// args mirrors the PHP constructor's $arguments (ApiReference.php:25). The tag never reads them —
// it takes no arguments, and the one template that embeds it invokes it bare as <<<ApiReference>>>
// — so a nil *TagArguments (what TagList.php:67's `new $sel(null)` passes, the shape the
// ?page=tags&tag=ApiReference gate takes) is stored and ignored, which is what the PHP does with
// the NULL it is handed.
type ApiReferenceTag struct {
	e    *Engine
	args *TagArguments
}

// apiRefDenylist is ApiReference::$denylist (ApiReference.php:29-30) — the admin-only tables kept
// off the public REST surface. It is a PHP ARRAY LITERAL, so its order is fixed by the source, not
// by any sort, and crudSection emits it in exactly this order.
var apiRefDenylist = []string{
	"code_blobs", "code_refs", "doc_blobs", "doc_refs",
	"Login_Password", "User_Group_Mappings", "Group_Privileges", "api_keys",
}

// GetDocument is ApiReference::get_document() (ApiReference.php:32-45).
//
// The three degradation branches are distinct strings and must stay distinct — a tag that degrades
// gracefully against a missing dependency has to degrade IDENTICALLY here:
//
//	no CONGRUENCY_SQLITE  -> "<p>ApiReference: no DB.</p>"                   (:34)
//	no api_routes table   -> "<p>No <code>api_routes</code> table yet.</p>"  (:38, NO trailing \n)
//	anything throwing     -> "<div class='cy-form-error'>ApiReference error: …</div>"  (:43)
//
// cfg.SQLite == "" is `!defined('CONGRUENCY_SQLITE')` — the same mapping TreeView's port uses
// (engine.go:1742-1744).
func (t *ApiReferenceTag) GetDocument() (out string) {
	defer catchThrowable(&out, "ApiReference")
	if t.e.cfg.SQLite == "" {
		return "<p>ApiReference: no DB.</p>"
	}
	// PHP reaches its catch through `new PDO(...)` throwing (:35); an unopenable db lands on the
	// same branch here.
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return apiRefError(err)
	}
	defer db.Close()

	// ApiReference.php:37 — `if (!$db->query(...)->fetch())`. fetch() returns FALSE on no rows, so
	// the test is exactly "the SELECT returned no row", which is len(rows) == 0.
	probe, err := queryRows(db, "SELECT name FROM sqlite_master WHERE type='table' AND name='api_routes'")
	if err != nil {
		return apiRefError(err)
	}
	if len(probe) == 0 {
		return "<p>No <code>api_routes</code> table yet.</p>"
	}
	rows, err := queryRows(db, "SELECT name, method, sql, auth, params, meta FROM api_routes ORDER BY name")
	if err != nil {
		return apiRefError(err)
	}
	return apiRefIntro(rows) + apiRefGroups(rows) + apiRefCrudSection()
}

// apiRefError is the catch(\Throwable) body (ApiReference.php:42-44). It is spelled out rather than
// left to catchThrowable because the PHP reaches this branch by THROWING (PDO::ERRMODE_EXCEPTION,
// :36) where Go's database/sql returns an error — same branch, different mechanism. catchThrowable
// still guards the deferred path and produces the identical wrapper for a real panic.
func apiRefError(err error) string {
	return "<div class='cy-form-error'>ApiReference error: " + esc(err.Error()) + "</div>"
}

// apiRefIntro is ApiReference::intro (ApiReference.php:47-55). The count is `(int) $n` over
// count($rows) — the number of api_routes rows.
func apiRefIntro(rows []map[string]any) string {
	n := len(rows)
	return "<p>The data-driven API surface &mdash; <strong>" + strconv.Itoa(n) + "</strong> named routes, each a row in " +
		"<code>api_routes</code>. Call one as <code>?route=&lt;name&gt;</code>: it runs that row's parameterized " +
		"SQL with your declared <code>:params</code> bound. A <code>SELECT</code> route replies " +
		"<code>{&quot;route&quot;:&hellip;,&quot;rows&quot;:[&hellip;]}</code>; a write route replies " +
		"<code>{&quot;route&quot;:&hellip;,&quot;affected&quot;:n,&quot;rowid&quot;:id}</code>. " +
		"<code>auth</code> is <em>public</em> for reads, <em>token</em>/<em>admin</em> for writes.</p>\n"
}

// apiRefGroupOrder is ApiReference::groups' $order (ApiReference.php:70) — a PHP array literal, so
// the sections render in THIS order regardless of what the data contains.
var apiRefGroupOrder = []string{"Tickets", "Provenance", "Repos & Docs", "Process / Other"}

// apiRefGroupOf is ApiReference::groupOf (ApiReference.php:57-67): bucket a route by the lowercased
// run of ASCII LETTERS its name starts with.
//
// The prefix is `preg_match('/^[a-zA-Z]+/', $name, $m)` — letters only, so it stops at the first
// non-letter. That is a real distinction, not a detail: "authorize_process" yields "authorize"
// (stops at '_') and "process_status" yields "process", neither of which is in any list, so both
// land in Process / Other. A name starting with a non-letter matches nothing, $p stays '', and ''
// is in no list — Process / Other again, which is why this needs no not-found guard.
//
// The lookups are EXACT: "ticket" is a Tickets route but "tickets" is NOT in any list, so
// tickets.recent renders under Process / Other while ticket.create renders under Tickets. That
// asymmetry is the PHP's (:60-62 list "ticket", never "tickets"); it is preserved, not corrected.
func apiRefGroupOf(name string) string {
	p := ""
	i := 0
	for i < len(name) && apiRefIsASCIILetter(name[i]) {
		i++
	}
	if i > 0 {
		p = asciiLower(name[:i]) // strtolower — ASCII-only in PHP 8, and the run is [a-zA-Z] anyway
	}
	switch p {
	case "ticket", "mandate", "guarantee", "binding":
		return "Tickets"
	case "run", "journey", "artifact", "edge", "children", "policy", "agent":
		return "Provenance"
	case "repo", "source", "doc":
		return "Repos & Docs"
	}
	return "Process / Other"
}

// apiRefGroups is ApiReference::groups (ApiReference.php:69-80). An EMPTY bucket emits nothing —
// `if (!$buckets[$g]) { continue; }` (:76), PHP's empty-array-is-falsy test.
func apiRefGroups(rows []map[string]any) string {
	buckets := make(map[string][]map[string]any, len(apiRefGroupOrder))
	for _, r := range rows {
		g := apiRefGroupOf(phpString(r["name"]))
		buckets[g] = append(buckets[g], r)
	}
	out := ""
	for _, g := range apiRefGroupOrder {
		if len(buckets[g]) == 0 {
			continue
		}
		// esc($g) matters: "Repos & Docs" must emit "Repos &amp; Docs" (:77).
		out += "<h2>" + esc(g) + "</h2>\n" + apiRefTable(buckets[g])
	}
	return out
}

// apiRefTable is ApiReference::table (ApiReference.php:82-98).
//
// THE params QUIRK (:87): `trim((string)$r['params']) === '' ? '{}' : (string)$r['params']`. The
// blankness test is TRIMMED but the emitted value is the ORIGINAL, UNTRIMMED string. So a params
// of "  {\"a\":1}  " renders with its surrounding spaces intact. Trimming it here would be a
// silent one-byte-per-row divergence.
func apiRefTable(rows []map[string]any) string {
	out := "<table class='api-ref' border='1' cellspacing='0' cellpadding='4'>\n" +
		"<thead><tr><th>route</th><th>method</th><th>auth</th><th>params</th><th>response shape</th><th>meta</th></tr></thead>\n<tbody>\n"
	for _, r := range rows {
		shape := apiRefDeriveShape(phpString(r["name"]), phpString(r["sql"]))
		params := phpString(r["params"])
		if phpTrim(params) == "" {
			params = "{}"
		}
		// esc() over each cell is the recursion guard; meta is NULL for several live routes and
		// phpString(nil) is "", which is PHP's (string)NULL.
		out += "<tr>" +
			"<td><code>" + esc(r["name"]) + "</code></td>" +
			"<td>" + esc(r["method"]) + "</td>" +
			"<td>" + esc(r["auth"]) + "</td>" +
			"<td><code>" + esc(params) + "</code></td>" +
			"<td><code>" + esc(shape) + "</code></td>" +
			"<td>" + esc(r["meta"]) + "</td>" +
			"</tr>\n"
	}
	return out + "</tbody>\n</table>\n"
}

// apiRefDeriveShape is ApiReference::deriveShape (ApiReference.php:100-110) — the response shape
// DERIVED from the route SQL, mirroring boot/rest.php's dispatch:
//
//	SELECT …    -> {"route":"…","rows":[ <the SELECTed columns> ]}
//	anything else -> {"route":"…","affected":<n>,"rowid":<id>}
//
// The SELECT test is `stripos(ltrim($sql), 'select') === 0` (:104) — case-insensitive, on the
// LEFT-trimmed sql, and === 0 means "at position 0", i.e. a prefix. Note the asymmetry with
// selectCols, which is handed the RAW $sql and trims it itself (:115): the two do NOT share a
// trimmed string, and reproducing that split is why apiRefSelectCols re-trims below.
//
// implode(', ', array()) is "", so a SELECT whose columns all parse away renders "rows":[].
func apiRefDeriveShape(name, sqlText string) string {
	if apiRefStartsWithSelect(apiRefLTrim(sqlText)) {
		cols := apiRefSelectCols(sqlText)
		q := make([]string, 0, len(cols))
		for _, c := range cols {
			q = append(q, `"`+c+`"`)
		}
		return `{"route":"` + name + `","rows":[` + strings.Join(q, ", ") + `]}`
	}
	return `{"route":"` + name + `","affected":<n>,"rowid":<id>}`
}

// apiRefLTrim is ltrim($s) with PHP's DEFAULT charlist " \t\n\r\0\x0B" — the left-hand half of
// phpTrim (engine.go:630). strings.TrimLeft(s, cutset) trims a byte set, which is what ltrim's
// charlist is.
func apiRefLTrim(s string) string { return strings.TrimLeft(s, " \t\n\r\x00\x0B") }

// apiRefStartsWithSelect is `stripos($s, 'select') === 0`. stripos returns FALSE (never 0) when the
// haystack is shorter than the needle, so a string under 6 bytes is not a SELECT.
func apiRefStartsWithSelect(s string) bool {
	return len(s) >= 6 && asciiLower(s[:6]) == "select"
}

// apiRefSelectCols is ApiReference::selectCols (ApiReference.php:112-138): the output column names
// of a SELECT — the top-level comma list between SELECT and FROM, each item's AS-alias or trailing
// identifier.
//
// It is a BYTE scanner, not a SQL parser, and it is faithful to being one: it tracks paren depth
// and NOTHING else — not string literals, not quoted identifiers, not comments. A "from" inside a
// top-level string literal would end the column list early. That is the PHP's behaviour on the
// same input, so it is this port's behaviour; it is not a bug to be fixed here.
//
// Paren depth is what makes the live data parse right: bug.stats' UNION ALL stops at the FIRST
// top-level FROM, and ticket.stops' FROM inside a `IN (WITH RECURSIVE …)` subquery is at depth > 0
// and correctly ignored.
func apiRefSelectCols(sqlText string) []string {
	s := phpTrim(sqlText) // :115 — trim((string)$sql)
	// :116 — preg_match('/^select\s+(distinct\s+)?/i') then substr($s, strlen($m[0])). A sql that
	// does NOT match (e.g. "SELECTx …", which stripos still called a SELECT) is left UNSTRIPPED,
	// exactly as the PHP leaves it.
	s = s[apiRefSelectPrefixLen(s):]

	// :117-127 — find the first top-level "from" that stands as a WORD.
	depth := 0
	length := len(s)
	fromPos := -1
	for i := 0; i < length; i++ {
		ch := s[i]
		if ch == '(' {
			depth++
		} else if ch == ')' {
			depth--
		} else if depth == 0 && i+4 <= length && asciiLower(s[i:i+4]) == "from" {
			// :123-124 — the PHP substitutes a SPACE for the missing neighbour at either edge, so
			// a leading/trailing "from" still passes the word test.
			before := byte(' ')
			if i != 0 {
				before = s[i-1]
			}
			after := byte(' ')
			if i+4 < length {
				after = s[i+4]
			}
			// :125 — both neighbours must be non-alnum and non-underscore, so "fromage" and
			// "x_from" are not the FROM keyword.
			if !isAlnumASCII(before) && before != '_' && !isAlnumASCII(after) && after != '_' {
				fromPos = i
				break
			}
		}
	}
	colPart := s // :128 — no FROM found: the whole (stripped) sql is the column list
	if fromPos >= 0 {
		colPart = s[:fromPos]
	}

	var names []string
	for _, c := range apiRefSplitTop(colPart) {
		c = phpTrim(c)
		if c == "" {
			continue
		}
		// :133-135, in order. The `$c !== '*'` guard is why "SELECT * FROM bugs" yields ["*"]
		// rather than parsing an identifier out of it.
		if alias, ok := apiRefAsAlias(c); ok {
			names = append(names, alias)
		} else if id, ok := apiRefTrailingIdent(c); c != "*" && ok {
			names = append(names, id)
		} else {
			names = append(names, c) // an unparseable expression is emitted VERBATIM
		}
	}
	return names
}

// apiRefSelectPrefixLen is strlen($m[0]) for `preg_match('/^select\s+(distinct\s+)?/i', $s, $m)`,
// or 0 when the pattern does not match — which is exactly what ApiReference.php:116 strips.
//
// WHY NO BACKTRACKING IS NEEDED for the greedy `\s+`. If the first \s+ consumed every space, the
// next byte is a non-space; "distinct" also starts with a non-space, so giving whitespace back
// could only put a SPACE where 'd' must be, which can never help the optional group match.
// Consuming maximally is therefore the only viable split, and this straight-line scan is exact.
//
// The optional group is all-or-nothing: `(distinct\s+)?` needs its OWN trailing \s+, so
// "SELECT distinctive …" does NOT strip "distinct" — the group fails, matches empty, and the
// prefix is just "SELECT ". Hence the `w > k` test below.
func apiRefSelectPrefixLen(s string) int {
	if len(s) < 6 || asciiLower(s[:6]) != "select" {
		return 0
	}
	i := 6
	j := i
	for j < len(s) && isPHPSpace(s[j]) {
		j++
	}
	if j == i {
		return 0 // \s+ needs at least one space: no match at all, so nothing is stripped
	}
	i = j
	if i+8 <= len(s) && asciiLower(s[i:i+8]) == "distinct" {
		k := i + 8
		w := k
		for w < len(s) && isPHPSpace(s[w]) {
			w++
		}
		if w > k {
			i = w
		}
	}
	return i
}

// apiRefSplitTop is ApiReference::splitTop (ApiReference.php:140-152): split on top-level commas,
// parens-aware, so a column expression like COUNT(DISTINCT repo||'/'||path) stays one field.
//
// THE FINAL-FIELD QUIRK (:147 vs :150): an intermediate field is pushed UNCONDITIONALLY, even when
// blank ("a,,b" yields three fields, the middle one empty), but the LAST buffer is pushed only if
// `trim($buf) !== ''` — so a trailing comma contributes nothing. The two are not symmetric and the
// asymmetry is reproduced. (A blank intermediate field is then dropped by selectCols' own `if ($c
// === '') { continue; }` at :132, which is a SEPARATE test — this function still returns it.)
//
// The blankness test at :150 is trim(), not \s — so phpTrim, not isPHPSpace.
func apiRefSplitTop(s string) []string {
	var out []string
	var buf strings.Builder
	depth := 0
	for i := 0; i < len(s); i++ {
		ch := s[i]
		switch {
		case ch == '(':
			depth++
			buf.WriteByte(ch)
		case ch == ')':
			depth--
			buf.WriteByte(ch)
		case ch == ',' && depth == 0:
			out = append(out, buf.String())
			buf.Reset()
		default:
			buf.WriteByte(ch)
		}
	}
	if phpTrim(buf.String()) != "" {
		out = append(out, buf.String())
	}
	return out
}

// apiRefAsAlias is `preg_match('/\s+as\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*$/i', $c, $m)` returning $m[1]
// (ApiReference.php:133) — the AS-alias of a column expression.
//
// WHY A BACKWARD SCAN IS THE SAME AS THE REGEX. The pattern is anchored at $, so `\s*$` must eat
// ALL trailing whitespace and the alias must be the maximal trailing run of [a-zA-Z0-9_]. The
// alias's start cannot sit INSIDE that run either: the byte before it must satisfy `\s+`, and a
// byte inside the run is [a-zA-Z0-9_], never \s. So the alias is precisely that whole run, its
// first byte must be [a-zA-Z_], and what precedes it must be \s+ "as" \s+. Each step below is one
// of those clauses, right to left. preg_match's leftmost rule cannot pick a different $m[1]: only
// the single position proved here can match at all.
func apiRefAsAlias(c string) (string, bool) {
	i := len(c)
	for i > 0 && isPHPSpace(c[i-1]) { // \s*$
		i--
	}
	j := i
	for j > 0 && apiRefIsIdentChar(c[j-1]) { // [a-zA-Z0-9_]* , greedy
		j--
	}
	if j == i || !apiRefIsIdentStart(c[j]) { // the run is empty, or starts with a digit
		return "", false
	}
	k := j
	for k > 0 && isPHPSpace(c[k-1]) { // the \s+ between "as" and the alias
		k--
	}
	if k == j {
		return "", false
	}
	if k < 2 || asciiLower(c[k-2:k]) != "as" { // "as", case-insensitive per /i
		return "", false
	}
	if k-2 == 0 || !isPHPSpace(c[k-3]) { // the leading \s+
		return "", false
	}
	return c[j:i], true
}

// apiRefTrailingIdent is `preg_match('/([a-zA-Z_][a-zA-Z0-9_]*)\s*$/', $c, $m)` returning $m[1]
// (ApiReference.php:134) — the trailing identifier of a column expression, which is how "e.child_id"
// becomes "child_id" and "COUNT(*)" matches nothing.
//
// THE LEFTMOST RULE BITES HERE, and this is the one place the two regexes genuinely differ. This
// pattern has NO leading context, so unlike apiRefAsAlias the match may start INSIDE the trailing
// run: preg_match scans positions left to right and takes the FIRST that matches, so for a run
// beginning with a digit the regex still matches from the run's first LETTER-or-underscore. On
// "COALESCE(x,0) 2abc" the run is "2abc" and $m[1] is "abc", not a failure. The loop below is that
// leftmost-start search; stopping at the run's first byte instead would wrongly report no match.
//
// A match must still END at the string's end (modulo `\s*$`), so the candidate run is only ever
// the trailing one — a run followed by any non-identifier, non-space byte (a ')' , say) cannot
// match at all, which is why "COUNT(*)" falls through to selectCols' verbatim else-branch.
func apiRefTrailingIdent(c string) (string, bool) {
	i := len(c)
	for i > 0 && isPHPSpace(c[i-1]) { // \s*$
		i--
	}
	j := i
	for j > 0 && apiRefIsIdentChar(c[j-1]) { // the maximal trailing [a-zA-Z0-9_] run
		j--
	}
	for p := j; p < i; p++ {
		if apiRefIsIdentStart(c[p]) {
			return c[p:i], true
		}
	}
	return "", false
}

// apiRefIsASCIILetter is the [a-zA-Z] of groupOf's prefix pattern (ApiReference.php:59).
func apiRefIsASCIILetter(b byte) bool {
	return b >= 'A' && b <= 'Z' || b >= 'a' && b <= 'z'
}

// apiRefIsIdentStart is [a-zA-Z_] — an identifier's first byte.
func apiRefIsIdentStart(b byte) bool { return apiRefIsASCIILetter(b) || b == '_' }

// apiRefIsIdentChar is [a-zA-Z0-9_] — an identifier's subsequent bytes.
func apiRefIsIdentChar(b byte) bool { return isAlnumASCII(b) || b == '_' }

// apiRefCrudRows is crudSection's $crud array literal (ApiReference.php:161-168). Source order,
// emitted as-is.
var apiRefCrudRows = [][2]string{
	{"GET ?api=tables", "list the reachable tables"},
	{"GET ?api=<table>[&<col>=<v>&order=<c>.<dir>&limit=&p=&per=]", "filtered / paginated rows"},
	{"GET ?api=<table>&id=<pk>", "a single row by primary key"},
	{"POST ?api=<table>", "create a row from the JSON body (real columns only)"},
	{"PUT|PATCH ?api=<table>&id=<pk>", "update a row by primary key"},
	{"DELETE ?api=<table>&id=<pk>", "delete a single row by primary key"},
}

// apiRefCrudSection is ApiReference::crudSection (ApiReference.php:154-180) — the generic
// ?api=<table> CRUD layer plus the admin denylist. It is static markup; the only computed bytes are
// the esc()'d literals, which matter because the calls carry raw '<', '>' and '&' (so
// "GET ?api=<table>&id=<pk>" must emit "GET ?api=&lt;table&gt;&amp;id=&lt;pk&gt;").
//
// NOTE the tail: the function returns `$out . "</ul>\n"` (:179) — the <li> loop's own \n plus that
// close, and NOTHING after it. The tag's last byte is the "\n" of "</ul>\n".
func apiRefCrudSection() string {
	out := "<h2>Generic <code>?api=&lt;table&gt;</code> CRUD</h2>\n"
	out += "<p>Beyond the named routes, every non-denylisted table is reachable through a generic CRUD layer " +
		"(the fast internal path). Table and column names are validated against the schema; reads are public, " +
		"writes need a token / admin session:</p>\n"
	out += "<table class='api-ref' border='1' cellspacing='0' cellpadding='4'>\n" +
		"<thead><tr><th>call</th><th>does</th></tr></thead>\n<tbody>\n"
	for _, c := range apiRefCrudRows {
		out += "<tr><td><code>" + esc(c[0]) + "</code></td><td>" + esc(c[1]) + "</td></tr>\n"
	}
	out += "</tbody>\n</table>\n"
	out += "<h3>Admin denylist &mdash; not in REST</h3>\n"
	out += "<p>These tables &mdash; the self-hosting archive plus the auth / key tables &mdash; are " +
		"<strong>admin-only</strong> and never reachable through <code>?api=</code> or generic writes:</p>\n<ul class='denylist'>\n"
	for _, tbl := range apiRefDenylist {
		out += "<li><code>" + esc(tbl) + "</code> &mdash; admin-only, not in REST</li>\n"
	}
	return out + "</ul>\n"
}
