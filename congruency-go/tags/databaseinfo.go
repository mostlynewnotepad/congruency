package tags

// databaseinfo.go — ticket #311, unit go-port:tags:tag:DatabaseInfo.
//
// The Go port of ONE tag: invocators/tags/dev/DatabaseInfo.php — the unified DB's self-describing
// view. It lists every non-internal table in CONGRUENCY_SQLITE with its row count and a REST browse
// link, and marks the denylisted (admin-only) tables instead of linking them. The app serves it in
// two places: standalone at ?page=tags&tag=DatabaseInfo (TagList::scan finds the file under
// TAGS_DIR), and substituted into the ?page=database template, which embeds <<<DatabaseInfo>>>.
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. The PHP is the SPEC — where the two
// disagree THIS file is wrong, and "improving" the markup here is a defect, not a fix.
//
// ── WHAT THIS FILE ADDS, AND WHAT IT DOES NOT TOUCH ─────────────────────────────────────────────
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers, and its self-registration (the init() below). Nothing in engine.go changes — the
// registry picks this tag up because Go runs every init() in a package before any other code in it
// (engine.go:1355 Register, engine.go:1393 newTag), so PortedTags()/Scan()/RenderTag() see it with
// no edit there. Every identifier defined here is dbInfo*-prefixed or DatabaseInfo*-named, so it
// cannot collide with the sibling tag ports still to land.
//
// It REUSES the package's audited PHP primitives rather than restating them: esc
// (htmlspecialchars($s, ENT_QUOTES), engine.go:599), phpString (the (string) cast over a PDO row's
// native types, engine.go:497), toInt (the (int) cast, engine.go:559), openDB/queryColumn/scalar
// (PDO::query(...)->fetchAll(PDO::FETCH_COLUMN) and ->fetchColumn(), engine.go:1173,1247,1260) and
// catchThrowable (engine.go:1715). The ONE primitive it must add is number_format — see
// dbInfoNumberFormat.
//
// ── THE WHOLE TAG (DatabaseInfo.php:14-57) ──────────────────────────────────────────────────────
//
// The constructor is EMPTY — `public function __construct($arguments) {}` (DatabaseInfo.php:16). It
// neither reads nor stores its argument, so unlike CategoryView (whose constructor dereferences
// $arguments and therefore FATALS on the gallery's `new $sel(null)`, TagList.php:67) this tag has
// no null-argument hazard at all: the NULL is accepted and discarded. The gallery path and the
// in-template <<<DatabaseInfo>>> path therefore render IDENTICAL bytes, and the tag takes no
// arguments in any form — the ?page=database template invokes it bare.
//
// ── THE DEGRADATION BRANCHES (what "degrade IDENTICALLY" means here) ────────────────────────────
//
// The whole of get_document() is wrapped in ONE try/catch (DatabaseInfo.php:20,53-55), and PDO runs
// under ERRMODE_EXCEPTION (:23), so EVERY database failure below the open lands on the same arm:
//
//	no CONGRUENCY_SQLITE   -> "<p>DatabaseInfo: no DB.</p>"                          (:21)
//	anything throwing      -> "<div class='cy-form-error'>DatabaseInfo error: …</div>" (:54)
//
// There is no third branch, and in particular THERE IS NO EMPTY-STATE TEXT: a database with zero
// listable tables is not an error and not a special case — the foreach (:38) simply never runs, and
// the tag emits its intro, an empty <table>, and "0 tables, 0 rows total." That shape falls out of
// GetDocument below with no branch of its own, which is exactly how the PHP produces it.
//
// Note the catch emits `$e->getMessage()` ALONE (:54) — NOT the `get_class($e) . ': ' .
// $e->getMessage()` that TagList.php:71 uses. Do not "harmonise" the two; see dbInfoError.
//
// ── TWO KNOWN, UNREACHABLE-UNDER-THE-GATE DIVERGENCES (declared, not hidden) ────────────────────
//
// Both are inherited from engine.go's header rather than introduced here, and neither is reachable
// on either render surface this unit gates:
//
//  1. A MISSING DB FILE. PHP's `new PDO('sqlite:' . CONGRUENCY_SQLITE)` (:22) CREATES an empty
//     database when the file is absent, so the PHP would render "0 tables, 0 rows total." against a
//     db it just brought into being (engine.go's divergence 2). openDB refuses to create anything —
//     "Missing file -> error, never creation" (engine.go:1172), enforced by the os.Stat guard at
//     engine.go:1177-1179 — so this port takes the error arm instead. That is a deliberate refusal
//     to write to disk to imitate a render, and it is the same choice every sibling port makes.
//
//  2. THE ERROR TEXT ITSELF. When the arm IS taken, the bytes inside the cy-form-error div are a
//     PDOException's message on the PHP side and a Go driver error on this side. The div, the tag
//     name and the escaping match; the message cannot, because no Go error carries PDO's wording.
//     apiRefError (apireference.go:118-124) records the identical limitation for the identical
//     reason.
//
// ── SIDE EFFECTS: this tag only READS, but the read is not file-free ────────────────────────────
//
// GetDocument runs two SELECT shapes and nothing else — it writes no byte of the db, creates no
// document, and touches no path of its own. One consequence of openDB is worth stating plainly
// rather than leaving for someone to rediscover, because it is #153's lesson and it is LIVE here:
//
// openDB opens `mode=ro` (engine.go:1180), and the live state db is journal_mode=WAL — MEASURED
// this session (#311), which CONTRADICTS equivalence_test.go's header claim that the db is
// journal_mode=delete "so the sidecars do not arise here". They do arise: a mode=ro connection to a
// WAL db materialises congruency.sqlite-wal and congruency.sqlite-shm, and because a read-only
// connection cannot checkpoint, they OUTLIVE the Go process. They are transient in practice — the
// live PHP's next request opens read-write, checkpoints, and removes them (measured: present after
// a Go render, gone after one PHP request) — but "no files" is not the guarantee here.
//
// This is engine.go's deliberate trade, not this tag's: mode=ro reads THROUGH the WAL exactly as
// PHP's handle does, and a stale read would manufacture the very byte-diffs the gate exists to
// detect (openDB's own comment: "#153's constraint was 'never create files'; #226's is equivalence,
// and they pull opposite ways"). Every ported tag shares it; nothing here makes it worse, and
// Config.Immutable still buys the zero-sidecar read for any caller that prefers it to freshness.
// The stale claim in equivalence_test.go's header is that file's to fix (#282's), not this one's —
// #311 is add-this-file-only.
//
// ── SECURITY: the htmlspecialchars recursion guard, and the one place it is deliberately absent ──
//
// Table names are DATA read out of sqlite_master, and this render flows back through
// execute_all_tags — so a table literally named `<<<TitleTag>>>` (SQLite permits it: CREATE TABLE
// "<<<TitleTag>>>") would re-enter the tag engine if it were emitted raw. The PHP escapes every
// emission of $t (:43 twice, :44 once) and so does this file; see the esc() calls in dbInfoRow.
//
// The exception is the COUNT query, where the RAW name is interpolated into SQL (:39) and this port
// interpolates it too. That is not an oversight on either side and a placeholder would be WRONG
// here — a bound parameter is a VALUE, and no SQLite dialect accepts a table name as one. The input
// is sqlite_master's own name column, i.e. names SQLite itself accepted at CREATE TABLE, not
// caller-supplied text: no argument, no $_GET key and no request byte reaches it. See dbInfoCount
// for the one name shape that still breaks it, identically, on both sides.

import (
	"database/sql"
	"strconv"
	"strings"
)

// init self-registers the tag. This is the whole wiring step (#281; engine.go:1355, 1393-1401).
func init() {
	Register("DatabaseInfo", func(e *Engine, a *TagArguments) Tag { return &DatabaseInfoTag{e: e, args: a} })
}

// DatabaseInfoTag is DatabaseInfo (DatabaseInfo.php:14-57).
//
// args mirrors the PHP constructor's $arguments (DatabaseInfo.php:16), which the PHP accepts and
// immediately DISCARDS — the constructor body is empty, so there is not even a private field to
// hold it. It is stored here (never read) to keep the factory's shape identical to its siblings'.
// A nil *TagArguments — what TagList.php:67's `new $sel(null)` passes, the shape the
// ?page=tags&tag=DatabaseInfo gate takes — is therefore harmless, which is what the PHP does with
// the NULL it is handed. e IS read: cfg.SQLite is this tag's whole dependency.
type DatabaseInfoTag struct {
	e    *Engine
	args *TagArguments
}

// dbInfoDenied is $denied (DatabaseInfo.php:25-27) — the admin-only tables this tag marks instead
// of linking. The PHP's comment at :24 ("keep in sync with the denylist in boot/rest.php") is the
// whole story of the value: it is a HAND-MAINTAINED COPY of rest.php's list, living in this tag's
// own source.
//
// NOT MERGED WITH apiRefDenylist (apireference.go:73-76), and the duplication is deliberate. That
// is a DIFFERENT PHP array literal in a DIFFERENT tag's source (ApiReference.php:29-30), and the
// two are independently maintained copies that the PHP permits to drift — collapsing them here
// would silently couple two tags the PHP does not couple, so a future edit to one PHP literal would
// wrongly move the other tag's bytes. The shapes differ for a reason too: ApiReference EMITS its
// list, so order is load-bearing there and it is a slice; DatabaseInfo only ever asks
// `isset($denied[$t])` (:41), so order is unobservable here and this is a set.
//
// isset() is exact as a set membership test here because no value in the literal is NULL — every
// one is 1 — and isset() differs from array_key_exists() only on a NULL value.
var dbInfoDenied = map[string]bool{
	"code_blobs": true, "code_refs": true, "doc_blobs": true, "doc_refs": true,
	"Login_Password": true, "User_Group_Mappings": true, "Group_Privileges": true,
	"api_keys": true,
}

// dbInfoTablesSQL is DatabaseInfo.php:28 verbatim — the listable tables, in the order the tag emits
// them.
//
// ORDER BY name is a BINARY (byte-order) sort: sqlite_master.name is declared with no COLLATE, so
// it takes SQLite's default BINARY collation on BOTH sides. That is not a cosmetic detail — it is
// why "Document_Templates" sorts BEFORE "Documents" ('_' is 0x5F, 's' is 0x73) and why every
// capitalised table precedes every lowercase one. A Go-side sort (or any collation-aware one) would
// reorder those rows and diff. The sort is left to SQLite here precisely so it cannot drift.
//
// NOT LIKE 'sqlite_%' filters SQLite's internal tables (sqlite_sequence, sqlite_stat1, …). LIKE is
// ASCII-case-insensitive by default in both engines, and neither sets case_sensitive_like.
const dbInfoTablesSQL = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"

// dbInfoIntro is DatabaseInfo.php:31-34 — four concatenated double-quoted literals, none of which
// interpolates (none contains a '$'), so the whole paragraph is a constant. The em-dash after "the
// whole site" is a literal UTF-8 U+2014 in the PHP source, not an &mdash; entity; the &lt;/&gt; in
// "?api=&lt;table&gt;" and "--to &lt;path&gt;" are hand-written entities in the source. All are
// copied byte for byte. It ends in the explicit "\n" at :34.
const dbInfoIntro = "<p>The unified SQLite database (<code>CONGRUENCY_SQLITE</code>) that backs the whole site — " +
	"every page, tag, form, ticket, and the self-hosting source/doc archive. Reads are public via " +
	"<code>?api=&lt;table&gt;</code>; writes need the admin login. Admin-only tables (the archive + " +
	"auth) are denylisted from REST.</p>\n"

// dbInfoTableHead is DatabaseInfo.php:35-36 — the <table> open and its header row. The ONLY newlines
// are the two explicit "\n" the PHP writes (after "<table>" and after "</tr>"); the PHP's own line
// break between :35 and :36 is BETWEEN the .= calls, not inside the string, so no newline separates
// the "rows" and "browse" headers.
const dbInfoTableHead = "<table>\n<tr><th style='padding-right:1.5rem'>table</th><th style='padding-right:1.5rem'>rows</th>" +
	"<th>browse</th></tr>\n"

// dbInfoDeniedBrowse is the browse cell of a denylisted table (DatabaseInfo.php:42) — marked, never
// linked, which is the tag's stated purpose (DatabaseInfo.php:11).
const dbInfoDeniedBrowse = "<span style='color:#999'>admin-only (not in REST)</span>"

// GetDocument is DatabaseInfo::get_document() (DatabaseInfo.php:19-56).
//
// The emitted shape is :31-51 in order, and every newline below is one the PHP writes explicitly:
//
//	dbInfoIntro                                   :31-34   ends "\n"
//	dbInfoTableHead                               :35-36   ends "\n"
//	dbInfoRow(...) per table, in ORDER BY name    :44-45   each ends "\n"
//	"</table>\n"                                  :47
//	dbInfoFooter(...)                             :48-51   ends "\n"
//
// So the render ENDS with a newline — the footer's — which is a byte the gate compares.
//
// catchThrowable models the PHP's catch arm for a Go PANIC; the query errors take the same arm
// explicitly through dbInfoError, because PHP reaches it by THROWING (ERRMODE_EXCEPTION, :23) where
// Go's database/sql returns an error. Same branch, two mechanisms — the pattern apireference.go:90
// establishes.
func (t *DatabaseInfoTag) GetDocument() (out string) {
	defer catchThrowable(&out, "DatabaseInfo")

	// :21 — !defined('CONGRUENCY_SQLITE'). The same mapping every sibling port uses
	// (apireference.go:92, engine.go:1742-1744).
	if t.e.cfg.SQLite == "" {
		return "<p>DatabaseInfo: no DB.</p>"
	}

	// :22-23 — new PDO(...) + ERRMODE_EXCEPTION. An unopenable db throws there and lands in the
	// catch; it lands on the same arm here. See the file header's divergence 1 for the ONE case
	// where "unopenable" means different things to the two sides (an ABSENT file, which PHP
	// creates).
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return dbInfoError(err)
	}
	defer db.Close()

	// :28-29 — fetchAll(PDO::FETCH_COLUMN) over the table list. queryColumn is that exact call
	// (engine.go:1247); it yields no rows for an empty result, which is PHP's empty array.
	names, err := queryColumn(db, dbInfoTablesSQL)
	if err != nil {
		return dbInfoError(err)
	}

	var b strings.Builder
	b.WriteString(dbInfoIntro)     // :31-34
	b.WriteString(dbInfoTableHead) // :35-36

	total := int64(0) // :37 — $total = 0
	for _, v := range names {
		// $t is the RAW PDO value. phpString is the (string) view of it that :39/:41 use unescaped
		// and :43/:44 escape — so the raw name is taken ONCE here and escaped only at the emit
		// sites, never before them.
		name := phpString(v)

		// :39 — the per-table COUNT. Any error is a PDOException on the PHP side.
		n, err := dbInfoCount(db, name)
		if err != nil {
			return dbInfoError(err)
		}
		total += n // :40

		b.WriteString(dbInfoRow(name, n)) // :41-45
	}

	b.WriteString("</table>\n")                    // :47
	b.WriteString(dbInfoFooter(len(names), total)) // :48-51
	return b.String()                              // :52
}

// dbInfoCount is DatabaseInfo.php:39:
//
//	$n = (int) $db->query('SELECT COUNT(*) FROM "' . $t . '"')->fetchColumn();
//
// The table name is interpolated into a DOUBLE-QUOTED SQL identifier, exactly as the PHP writes it
// — see the file header for why a placeholder is not an option and why this is not an injection
// site. The (int) cast is toInt (engine.go:559); COUNT(*) always yields one row, so scalar cannot
// return nil here, and toInt(nil) would be 0 in any case — the same 0 PHP's (int)FALSE gives if
// fetchColumn ever came up empty.
//
// THE ONE NAME SHAPE THAT BREAKS THIS, AND IT BREAKS BOTH SIDES IDENTICALLY: a table whose name
// contains a double quote (SQLite allows it, written CREATE TABLE "a""b"). Neither the PHP nor this
// port doubles the quote, so both emit the same malformed SQL, both get a syntax error from their
// SQLite, and both take the error arm — the PHP by throwing, this by the err return. The BRANCH
// therefore matches; only the message text inside the div differs, which is the file header's
// divergence 2 and not a new one. No such table exists in the live db.
func dbInfoCount(db *sql.DB, name string) (int64, error) {
	v, err := scalar(db, `SELECT COUNT(*) FROM "`+name+`"`)
	if err != nil {
		return 0, err
	}
	return toInt(v), nil
}

// dbInfoRow is one table's row, DatabaseInfo.php:41-45.
//
// The browse cell is the ternary at :41-43; the row is :44-45, ending in the explicit "\n".
//
// THE RAW '&' IN THE HREF IS THE PHP'S BYTE. :43 writes "?api=" . esc($t) . "&per=25" — the
// separator is a bare '&', NOT the "&amp;" that HTML would properly want, and it is emitted raw.
// Escaping it here would be a one-byte-per-linked-table diff. esc() runs on the NAME only, which is
// what makes the guard work while leaving the PHP's markup bug intact: the PHP is the spec, and its
// defects are ported faithfully (this one is cosmetic — browsers parse "&per" as the parameter
// either way — so it is not filed as a bug).
//
// The name is emitted THREE times and escaped all three (:43 twice, :44 once), matching the PHP
// call for call.
func dbInfoRow(name string, n int64) string {
	browse := dbInfoDeniedBrowse // :42
	if !dbInfoDenied[name] {     // :41 — isset($denied[$t])
		browse = "<a href='?api=" + esc(name) + "&per=25'>?api=" + esc(name) + "</a>" // :43
	}
	return "<tr><td style='padding-right:1.5rem'><code>" + esc(name) + "</code></td>" +
		"<td style='padding-right:1.5rem'>" + dbInfoNumberFormat(n) + "</td><td>" + browse + "</td></tr>\n"
}

// dbInfoFooter is DatabaseInfo.php:48-51 — the summary line.
//
// THE TWO NUMBERS ARE FORMATTED DIFFERENTLY, and that asymmetry is the PHP's, not a slip:
// count($tables) is interpolated RAW (:48), so 46 tables renders "46" and would render "1234" with
// no separator; number_format($total) (:49) groups, so 30122 rows renders "30,122". Running either
// one through the other's spelling is a byte diff the moment the table count passes 999.
//
// &rarr; is a hand-written entity in the source (:50) and is emitted as typed, not as a literal →.
func dbInfoFooter(tableCount int, total int64) string {
	return "<p style='color:#888;font-size:.9rem;margin-top:1rem'>" + strconv.Itoa(tableCount) + " tables, " +
		dbInfoNumberFormat(total) + " rows total. Export a git-viewable seed with " +
		"<code>tools/db_export.py</code> &rarr; <code>state/seed.sql</code>; rebuild with " +
		"<code>tools/db_import.py --to &lt;path&gt;</code>.</p>\n"
}

// dbInfoError is the catch(\Throwable) body (DatabaseInfo.php:53-55):
//
//	return "<div class='cy-form-error'>DatabaseInfo error: " . self::esc($e->getMessage()) . "</div>";
//
// THE MESSAGE ALONE — this tag does NOT prefix get_class($e). That distinguishes it from
// TagList.php:71 ("Error: Call to a member function …"), which DOES prefix the class, and the two
// must not be harmonised: they are different catch arms in different files emitting different
// bytes. It is spelled out here rather than left to catchThrowable because the PHP reaches this
// branch by THROWING where Go's database/sql returns an error — same branch, different mechanism
// (apireference.go:118-124 records the identical split). catchThrowable still guards the deferred
// path and produces the identical wrapper for a real panic, which is why the two spellings must
// agree, and they do: engine.go:1715-1720 emits this same "<div class='cy-form-error'>" + tag +
// " error: " + esc(...) + "</div>".
//
// No trailing newline: :54 ends at "</div>".
func dbInfoError(err error) string {
	return "<div class='cy-form-error'>DatabaseInfo error: " + esc(err.Error()) + "</div>"
}

// dbInfoNumberFormat is PHP's number_format($n) — the ONE PHP primitive this tag needs that the
// package did not already have (DatabaseInfo.php:45,49).
//
// Called with ONE argument, number_format's defaults are decimals=0, decimal_separator="." and
// thousands_separator="," (PHP manual), so the whole behaviour reduces to: group the decimal digits
// in threes from the right with commas. 421 -> "421", 20277 -> "20,277", 30122 -> "30,122" — all
// three measured off the live PHP render this session.
//
// WHY int64 AND NOT float64. number_format's parameter is a float, and PHP widens the int argument
// to one. This helper takes the int directly instead, which is EXACTLY equivalent for every value
// this tag can produce and strictly safer: both callers pass a PHP int ((int)$n at :39, and $total,
// an int accumulator at :37-40), and PHP's own int->float widening is lossless below 2^53 — a bound
// no COUNT(*) over a SQLite database approaches. Formatting the int64 directly cannot round where
// PHP would not, whereas routing through float64 could invent a rounding PHP never performs.
//
// The negative arm is UNREACHABLE from this tag — COUNT(*) is never negative and $total is a sum of
// counts — but "-1,234" is what PHP returns for -1234, so it is written rather than assumed. Note
// this is why the sign is stripped before grouping and re-attached after: grouping the "-" along
// with the digits would produce "-1,234" as "-1,2,34" for some widths.
func dbInfoNumberFormat(n int64) string {
	s := strconv.FormatInt(n, 10)
	neg := strings.HasPrefix(s, "-")
	if neg {
		s = s[1:] // safe for math.MinInt64 too: FormatInt renders its digits unsigned after the '-'
	}
	var b strings.Builder
	for i, c := range []byte(s) {
		// A comma precedes every digit whose distance from the right is a positive multiple of 3.
		if i > 0 && (len(s)-i)%3 == 0 {
			b.WriteByte(',')
		}
		b.WriteByte(c)
	}
	if neg {
		return "-" + b.String()
	}
	return b.String()
}
