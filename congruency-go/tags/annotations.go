// annotations.go — ticket #247, unit go-port:tags:tag:Annotations.
//
// The Go port of ONE tag: invocators/tags/dev/Annotations.php. It is a self-contained leaf in the
// sense #281 established — this file holds the tag's type, its GetDocument, its helpers and its
// self-registration, and it changes NOTHING in engine.go. Adding it moves PortedTags() from 10
// names to 11; that is the whole footprint.
//
// THE CONTRACT: byte-identical HTML. The PHP is the spec. Everything below that looks quirky is
// quirky because Annotations.php is, and where the two disagree the Go is wrong.
//
// ── WHAT THE TAG IS ─────────────────────────────────────────────────────────────────────────────
//
// One browse view over the `annotations` table — congruency's unified tagging model: a `tag`
// applied to an opaque `target` ref ("source:<hash>", "page:<DocumentID>", "doc:<hash>",
// "ticket:<id>"). It renders a tag/kind filter bar and a table of matching rows, newest first.
//
//	?page=annotations             -> everything, newest first
//	?page=annotations&tag=flag    -> one tag
//	?page=annotations&kind=page   -> one target-kind (source|page|doc|ticket)
//
// IT TAKES NO TAG ARGUMENTS. Annotations.php's constructor stores $arguments and never reads them
// again; every input arrives through $_GET. The args field below mirrors that stored-and-unused
// property so the constructor is the same shape as the PHP's, and so `new Annotations(null)` — the
// standalone/gallery shape (TagList.php:67) — is a no-op here exactly as it is there.
//
// ── THE ONE COUNTERINTUITIVE THING: ?page=tags&tag=Annotations SELF-FILTERS ─────────────────────
//
// The gallery URL feeds the tag its own name. TagList reads ?tag= to decide WHICH tag to render;
// Annotations reads the SAME ?tag= as its own row filter (Annotations.php:48). So on
// ?page=tags&tag=Annotations the tag filters for rows tagged "Annotations", finds none, and renders
// the bar plus "No annotations match that filter." — with "all" as a LINK rather than <strong>,
// because $tag is not ''. That is not a bug and not an empty state to be tidied away: it is what the
// PHP emits, byte for byte, and it is what the gallery gate below diffs. The in-page site
// (?page=annotations) carries no ?tag=, so it renders the full table. Both are exercised below.
//
// ── DEPENDENCY AND DEGRADATION (the ticket asks for this explicitly) ────────────────────────────
//
// The dependency is the `annotations` table in CONGRUENCY_SQLITE (tools/tag_selfcheck.py checks
// exactly that class of dependency: "SQL TABLES — every table name after FROM/JOIN ... verified
// against CONGRUENCY_SQLITE"). The PHP degrades in three steps, and each is reproduced:
//
//	!defined('CONGRUENCY_SQLITE')   -> "<p>Annotations: no DB.</p>"            (:41)
//	no `annotations` table          -> "<p>No annotations yet. ...</p>"        (:44-46)
//	any \Throwable                  -> "<div class='cy-form-error'>..."        (:83-85)
//
// ONE INHERITED DIVERGENCE, in the db OPEN — it is engine.go's documented divergence 2, not a
// decision this file makes. PHP's `new PDO('sqlite:'.$path)` is READ-WRITE and CREATES an empty
// database when the path is missing; the table probe then finds nothing and the PHP renders the
// "No annotations yet." branch. openDB refuses to create anything, so a MISSING db file surfaces
// here as the cy-form-error div ("database not found: <path>") where the PHP would have said "No
// annotations yet.". That is a real byte difference, on one input: db file absent. It is not
// reachable from the gate (the state db exists, and both engines are pinned to the same one), and
// re-litigating #226's package-wide open policy is out of scope for a port-ONE-tag ticket — so this
// file follows the policy its sibling CategoryBrowse follows (engine.go:1607-1610) and states the
// consequence rather than quietly widening it. A db that exists but is corrupt or unreadable is the
// PDOException path in BOTH engines, and both render the error div.
//
// ── date() IS NOT gmdate(): WHY UTC IS CORRECT HERE, AND HOW IT WAS CHECKED ─────────────────────
//
// Annotations.php:76 calls date('Y-m-d H:i', (int)$r['ts']) — LOCAL time, in whatever zone
// date_default_timezone_get() reports, whereas engine.go's gmdate is UTC. They agree only if the
// PHP's default zone is UTC, so that is a fact to measure, not assume:
//
//   - No date.timezone / date_default_timezone_set / TZ is set anywhere in this repo (grepped this
//     session, zero hits), so PHP falls back to its built-in default, which is UTC.
//   - MEASURED, not inferred: all 18 `when` cells on the live ?page=annotations page were compared
//     against their db `ts` formatted as UTC 'Y-m-d H:i'. 18/18 matched. (Three of them —
//     1783986822 -> "2026-07-13 23:53", 1783572201 -> "2026-07-09 04:43", 1783568648 ->
//     "2026-07-09 03:44" — pin the offset at +00:00 with no DST.)
//
// So gmdate is the right port TODAY. If the deployment ever sets date.timezone, this line — and
// only this line — becomes wrong, and the equivalence sweep in equivalence_test.go is what would
// catch it.
//
// `ts` is a REAL column (the schema is `ts REAL`), so PDO hands PHP a float and (int) TRUNCATES it;
// toInt(float64) truncates identically. `$r['ts'] ?` is PHP TRUTHINESS, not a null check — 0.0,
// NULL, "" and "0" are all falsy and all render an empty when-cell. annTruthy is that rule.
//
// ── ESCAPING: htmlspecialchars, NEVER urlencode ─────────────────────────────────────────────────
//
// Every DB-derived byte goes through esc() — the htmlspecialchars($s, ENT_QUOTES) recursion guard
// that keeps a stored "<<<Tag>>>" from re-entering the engine (see engine.go's header).
//
// Note the hrefs: Annotations.php:55 builds "?page=annotations&tag=" . self::esc($t['tag']) — it
// escapes, it does NOT urlencode. A tag named "setup:hashmark" therefore renders the href
// "?page=annotations&tag=setup:hashmark" with a RAW colon, and the live PHP does exactly that
// (confirmed in the rendered page). Reaching for phpURLEncode here would be tidier, more correct as
// HTML, and WRONG — it would emit %3A and diverge on the very first row.
//
// ── STRICT COMPARISON: `===`, and why phpString() would break it ────────────────────────────────
//
// Annotations.php:55 tests ($t['tag'] === $tag) — IDENTICAL, not equal. $tag is always a string
// (trim() of a $_GET value), so the test is true only when the DB value is ALSO a string and equal.
// A NULL tag column makes it FALSE (NULL === '' is false), and an INTEGER tag column makes it FALSE
// too (5 === '5' is false) — sqlite is dynamically typed, so both are storable. Comparing
// phpString(v) == tag instead would render <strong> for a NULL tag on the unfiltered page, where
// the PHP renders <a>. annIdenticalString is that `===`, and it is the reason this file does not
// just cast and compare.
//
// ── WHAT WAS AND WAS NOT RUN (read this before trusting a claim above) ──────────────────────────
//
// THIS FILE WAS NEVER COMPILED. The Go toolchain is not invocable in the session that wrote it —
// `go build`, `go vet`, `gofmt` and `go version` were each refused by the harness with "This
// command requires approval", and there was no one to approve them. So there is NO build, NO vet,
// NO gofmt, NO SelfCheck() run and NO `go test` run behind this port, and none is claimed. The
// obvious workaround (shelling out to go from the python that IS permitted) was deliberately not
// taken: routing around a permission gate is not a measurement.
//
// WHAT WAS ACTUALLY MEASURED — the PHP semantics, not the Go binary. The live PHP this repo serves
// IS up on 127.0.0.1:8899 and its state db IS readable, so the risky half of a port — "have I read
// the PHP right?" — was checked directly. A line-by-line PYTHON TRANSLITERATION of this file (same
// branches, same helpers, same literals, same order, reusing the same db) was diffed against the
// live PHP's own bytes over 16 inputs. All 16 were byte-identical:
//
//	?page=tags&tag=Annotations                   626B   (the self-filter case; cut with #282's anchors)
//	?page=annotations                          7,049B   (the full table)
//	&tag=flag | setup:hashmark | specifications          (source-link / bare-target / page-link rows)
//	&kind=source | page | doc | ticket                   (doc and ticket are the empty state)
//	&tag=flag&kind=source | &tag=flag&kind=page          (both filters; the second is empty)
//	&tag= | &tag=++flag++ | &tag=no-such-tag             (isset-vs-empty, trim(), no match)
//	&kind=no-such-kind | &tag=<script>&'"x               (no match; the escaping path)
//
// The PHP slices were cut from the live pages on the pages' own literals — TagList.php:62/76 for
// the gallery (#282's method), and for the in-page site the 165-byte `annotations` template read
// out of Document_Templates, whose text is
// "...<h1>Annotations · Congruency</h1>\n<<<Annotations>>>\n</body>\n</html>\n" — so the tag's bytes
// are exactly what lies between that <h1> and the 17-byte tail.
//
// WHAT THAT DOES AND DOES NOT ESTABLISH. It establishes that the ALGORITHM encoded here reproduces
// the live PHP byte for byte on every branch this tag has. It does NOT establish that this Go file
// compiles, nor that Go's own primitives behave as the transliteration assumed. THE FIRST THING TO
// DO WITH THIS FILE IS RUN:
//
//	cd congruency-go && go build ./... && go vet ./... && gofmt -l .
//	go test ./tags/ -run TestTagEquivalence/Annotations -v      # the real gate; needs the live 8899
//
// The second command IS this unit's gate and needs no edit anywhere to include this tag: #282's
// harness sweeps Scan()'s 45 names and measures any that IsPorted() — so registering "Annotations"
// above is exactly what flips it from "no Go port yet — SKIP" to a measured byte-diff.
//
// WHY NOT THE TICKET'S LITERAL GATE (diffing the two servers' whole pages). That diff cannot be
// empty for this or any tag, for a reason that is not this unit's: congruency-go's server does not
// reproduce the PHP CMS page chrome at all — server.go:39-66 says so and declines to forge it — so
// ?page=<p> on 8899 and 8900 differ by ~6.2 KB of nav/head/style whether or not this file exists,
// and 8900 answers ?page=annotations with the generic table-list seam rather than the tag. A diff
// that comes out identically non-empty with the unit deleted is not the unit's gate. The comparison
// above is: it isolates THIS tag's bytes and changes exactly when this file changes.
package tags

import (
	"strconv"
	"strings"
)

// init self-registers the tag (#281's add-a-file model: engine.go is untouched).
func init() {
	Register("Annotations", func(e *Engine, a *TagArguments) Tag { return &AnnotationsTag{e: e, args: a} })
}

// AnnotationsTag is Annotations (Annotations.php:19).
type AnnotationsTag struct {
	e *Engine

	// args mirrors `private $arguments` (Annotations.php:21-22): the constructor stores it and the
	// class never reads it. Kept so the Go constructor is the PHP constructor's shape — and so a
	// future reader does not "fix" a missing field that is missing on purpose.
	args *TagArguments
}

// GetDocument is Annotations::get_document() (Annotations.php:39-86).
//
// The whole body is the PHP's try block; catchThrowable is its `catch (\Throwable $e)` arm
// (:83-85), which renders the identical cy-form-error div.
func (t *AnnotationsTag) GetDocument() (out string) {
	defer catchThrowable(&out, "Annotations")

	// if (!defined('CONGRUENCY_SQLITE')) — :41
	if t.e.cfg.SQLite == "" {
		return "<p>Annotations: no DB.</p>"
	}
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		// The PDOException path. See the header for the one input (missing db FILE) where the PHP
		// takes its "No annotations yet." branch instead of this one.
		return throwableHTML("Annotations", err)
	}
	defer db.Close()

	// if (!$db->query("SELECT name FROM sqlite_master ...")->fetch()) — :44-46.
	// fetch() returns false when no row came back, so this is "no row", not "a NULL name".
	probe, err := queryRows(db, "SELECT name FROM sqlite_master WHERE type='table' AND name='annotations'")
	if err != nil {
		return throwableHTML("Annotations", err)
	}
	if len(probe) == 0 {
		return "<p>No annotations yet. Flag a source file on <a href='?page=source'>Source</a> or tag a page on <a href='?page=pages'>Pages</a>.</p>"
	}

	// $tag / $kind — :48-49. isset($_GET[k]) ? trim((string)$_GET[k]) : '' — and since trim('') is
	// '', a key that is absent and a key that is present-but-empty both land on '', which is why
	// getStr (which returns '' for absent) is the faithful read of both.
	tag := phpTrim(t.e.getStr("tag"))
	kind := phpTrim(t.e.getStr("kind"))

	// $tags — :51
	tagRows, err := queryRows(db, "SELECT tag, COUNT(*) n FROM annotations GROUP BY tag ORDER BY tag")
	if err != nil {
		return throwableHTML("Annotations", err)
	}

	bar := t.bar(tagRows, tag, kind)

	// $where / $args / $sql — :63-66
	var where []string
	var args []any
	if tag != "" {
		where = append(where, "tag=?")
		args = append(args, tag)
	}
	if kind != "" {
		where = append(where, "target LIKE ?")
		args = append(args, kind+":%")
	}
	sqlText := "SELECT tag, target, note, ts FROM annotations"
	if len(where) > 0 {
		sqlText += " WHERE " + strings.Join(where, " AND ")
	}
	sqlText += " ORDER BY ts DESC, id DESC"

	rows, err := queryRows(db, sqlText, args...)
	if err != nil {
		return throwableHTML("Annotations", err)
	}
	// if (!$rows) — :70. An empty result set is falsy in PHP.
	if len(rows) == 0 {
		return bar + "<p>No annotations match that filter.</p>"
	}

	// :72-74
	out = bar + "<table style='border-collapse:collapse;font-size:.9rem'>\n" +
		"<tr><th align='left' style='padding-right:1rem'>tag</th><th align='left' style='padding-right:1rem'>target</th>" +
		"<th align='left' style='padding-right:1rem'>note</th><th align='left'>when</th></tr>\n"
	// :75-81
	for _, r := range rows {
		// $when = $r['ts'] ? date('Y-m-d H:i', (int)$r['ts']) : '';  — :76
		when := ""
		if annTruthy(r["ts"]) {
			when = gmdate(toInt(r["ts"]))
		}
		out += "<tr><td style='padding:.15rem 1rem .15rem 0'><code>" + esc(r["tag"]) + "</code></td>" +
			"<td style='padding:.15rem 1rem .15rem 0'>" + annTargetLink(r["target"]) + "</td>" +
			"<td style='padding:.15rem 1rem .15rem 0'>" + esc(r["note"]) + "</td>" +
			"<td style='padding:.15rem 0;color:#888'>" + esc(when) + "</td></tr>\n"
	}
	return out + "</table>\n" // :82
}

// bar is the filter bar (Annotations.php:52-61).
//
// Every trailing space below is deliberate: the PHP appends " " after each entry and after the two
// "all" links, and the diff counts them.
func (t *AnnotationsTag) bar(tagRows []map[string]any, tag, kind string) string {
	var b strings.Builder

	// :52 — "all" is <strong> only when no tag filter is active.
	b.WriteString("<p style='font-size:.9rem'><strong>tag:</strong> ")
	if tag == "" {
		b.WriteString("<strong>all</strong>")
	} else {
		b.WriteString("<a href='?page=annotations'>all</a>")
	}
	b.WriteString(" ")

	// :53-56
	for _, tr := range tagRows {
		// $lab = esc($t['tag']) . " (" . (int)$t['n'] . ")"
		lab := esc(tr["tag"]) + " (" + strconv.FormatInt(toInt(tr["n"]), 10) + ")"
		b.WriteString("&middot; ")
		if annIdenticalString(tr["tag"], tag) { // $t['tag'] === $tag
			b.WriteString("<strong>" + lab + "</strong>")
		} else {
			// esc(), NOT urlencode() — see the header.
			b.WriteString("<a href='?page=annotations&tag=" + esc(tr["tag"]) + "'>" + lab + "</a>")
		}
		b.WriteString(" ")
	}

	// :57
	b.WriteString("<br><strong>kind:</strong> ")
	if kind == "" {
		b.WriteString("<strong>all</strong>")
	} else {
		b.WriteString("<a href='?page=annotations'>all</a>")
	}
	b.WriteString(" ")

	// :58-60 — the four kinds are literals, so they need no escaping and the PHP gives them none.
	for _, k := range []string{"source", "page", "doc", "ticket"} {
		b.WriteString("&middot; ")
		if k == kind {
			b.WriteString("<strong>" + k + "</strong>")
		} else {
			b.WriteString("<a href='?page=annotations&kind=" + k + "'>" + k + "</a>")
		}
		b.WriteString(" ")
	}

	b.WriteString("</p>\n") // :61
	return b.String()
}

// annTargetLink is Annotations::target_link (Annotations.php:25-37) — the opaque "<kind>:<id>" ref
// turned into a link back to wherever the target lives.
//
// THE strpos TRAP, which the PHP sidesteps and this port must too: `$pos === false` is an IDENTITY
// test, so a target beginning with ':' (pos 0) is NOT treated as "no colon" — it falls through to
// the switch with an empty $kind and lands on default. Go's strings.IndexByte returns -1 for absent
// and 0 for leading, so the distinction survives naturally; testing `pos <= 0` would break it.
//
// An unknown kind (and a target with no colon at all) renders as escaped plain text, NOT a link.
func annTargetLink(target any) string {
	s := phpString(target) // strpos((string) $target, ':')
	pos := strings.IndexByte(s, ':')
	if pos < 0 { // if ($pos === false)
		return esc(target)
	}
	kind := phpSubstr(s, 0, pos)  // substr($target, 0, $pos)
	id := phpSubstr(s, pos+1, -1) // substr($target, $pos + 1) — no length: to the end
	switch kind {
	case "source":
		return "<a href='?page=source&file=" + esc(id) + "'>source: " + esc(phpSubstr(id, 0, 12)) + "</a>"
	case "doc":
		return "<a href='?page=docs&doc=" + esc(id) + "'>doc: " + esc(phpSubstr(id, 0, 12)) + "</a>"
	case "page":
		return "<a href='?page=" + esc(id) + "'>page: " + esc(id) + "</a>"
	case "ticket":
		return "<a href='?page=tickets'>ticket #" + esc(id) + "</a>"
	default:
		return esc(target)
	}
}

// annIdenticalString is PHP's `$v === $s` where $s is known to be a string: true only when $v is
// ALSO a string and the two are equal. See the header for why phpString() would not do.
func annIdenticalString(v any, s string) bool {
	got, ok := v.(string)
	return ok && got == s
}

// annTruthy is PHP's truthiness test on a DB value — Annotations.php:76's `$r['ts'] ?`.
//
// It is NOT "not nil": PHP counts 0, 0.0, "", "0" and NULL as FALSE. A ts of exactly 0 (the epoch)
// therefore renders an EMPTY when-cell rather than "1970-01-01 00:00", and reproducing that is the
// reason this helper exists instead of a nil check.
func annTruthy(v any) bool {
	switch x := v.(type) {
	case nil:
		return false
	case bool:
		return x
	case int64:
		return x != 0
	case int:
		return x != 0
	case float64:
		return x != 0
	case float32:
		return x != 0
	case string:
		return x != "" && x != "0"
	case []byte:
		s := string(x)
		return s != "" && s != "0"
	default:
		return true
	}
}
