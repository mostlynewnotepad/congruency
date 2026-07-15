package tags

// memorylist.go — ticket #319, unit go-port:tags:tag:MemoryList.
//
// The Go port of ONE tag: invocators/tags/MemoryList.php — the controller (Claude) tool-use log,
// reflecting the state of the MCP. The app serves it standalone at ?page=tags&tag=MemoryList, and
// the `memories` page's stored template embeds <<<MemoryList>>> (the in-page substitution site named
// by this unit's ticket; doc/CMS_ADDITIONS.md:20 documents the same pair).
//
// THE CONTRACT is engine.go's contract: byte-identical HTML. The PHP is the SPEC — where the two
// disagree THIS file is wrong, and "improving" the markup or the merge here is a defect, not a fix.
// Several behaviours below are quirks; each is reproduced at the code that needs it and named in a
// comment, so a later reader does not "correct" one back into a divergence.
//
// ── WHAT THIS FILE ADDS, AND WHAT IT DOES NOT TOUCH ─────────────────────────────────────────────
//
// Per #281 a tag port is ADD-A-FILE-ONLY: this file holds the tag's type, its GetDocument, its
// helpers, and its self-registration (the init() below). Nothing in engine.go changes — the registry
// picks this tag up because Go runs every init() in a package before any other code in it
// (engine.go:1309-1314; Register at engine.go:1355, newTag at engine.go:1393). Every identifier this
// file defines is memList*-prefixed or MemoryList*-named, so it cannot collide with the sibling tag
// ports.
//
// (engine.go's COVERAGE header still lists MemoryList under "NOT PORTED (35)". That list is a
// hand-maintained COPY; its own text names PortedTags() as "the authority" (engine.go:189-192), and
// PortedTags is registry-derived (engine.go:1406-1415), so it answers correctly the moment this
// file's init() runs. Correcting the copy means editing engine.go, which this ticket forbids
// ("touch nothing else") — the same stale-copy state #312 and #316 left behind for DocList and
// Login. It is a comment, not behaviour.)
//
// It REUSES engine.go's audited PHP primitives rather than restating them: esc
// (htmlspecialchars($s, ENT_QUOTES), engine.go:599), phpHTMLSpecialChars (engine.go:407), phpString
// (PHP's (string) cast over a PDO row's native types — NULL becomes "", engine.go:497),
// phpFloatString (PHP's precision-14 float cast, reached through phpString, engine.go:530),
// openDB/queryRows (PDO::query(...)->fetchAll(PDO::FETCH_ASSOC), engine.go:1173,1241) and
// catchThrowable (engine.go:1715).
//
// It reuses engine.go's toInt for NOTHING, and that is a deliberate, measured exception rather than
// an oversight: toInt does not saturate on overflow where PHP's (int) does, which costs real bytes on
// this tag's one input. memListInt says exactly what differs and what was measured.
//
// It deliberately does NOT reuse a sibling UNIT's helpers (doclist.go's docListTruthy models a
// related PHP rule): those files are other tickets' deliverables, and depending on them would couple
// this unit's bytes to edits made under another unit's authority. engine.go is the shared floor; a
// sibling tag file is not.
//
// ── WHY THIS TAG IS UNLIKE ITS SIBLINGS: TWO SOURCES, MERGED ────────────────────────────────────
//
// Every other ported tag reads ONE store. MemoryList reads TWO and merges them (MemoryList.php:13-17
// says why: "so the view is always current"):
//
//	1. the durable `memories` table in CONGRUENCY_SQLITE, where the gate persists.
//	   tracker/store.py:58-60 creates it:
//	       memories(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT,
//	                tool TEXT, intent TEXT, note TEXT)
//	   ...and the tag SELECTs four of those six columns. (`note` is a DB column the DB arm never
//	   reads — only the MCP arm has a note fallback. That asymmetry is the PHP's, not a mis-port.)
//	2. the live gate log $HOME/.MCP/gate-memories.json — what the RUNNING gate is writing right now,
//	   before it has been restarted onto the DB path.
//
// Rows are de-duped on (ts, tool) with the DB row preferred (it is appended first), then sorted
// newest-first. THE MERGE IS WHY THE TYPE MODELLING BELOW IS LOAD-BEARING and not pedantry: the two
// sources hand PHP DIFFERENT TYPES for the same field. `session` from sqlite's TEXT column is a
// string; `session` from json_decode is whatever JSON said — an int, a float, a bool. Both then land
// in the SAME PHP array as a KEY (:67), where PHP normalizes them, and `count($sessions)` is a
// rendered byte. Confirmed as behaviour this session (see "WHAT WAS ACTUALLY RUN"): a DB row with
// session "7" and a log entry with session 7 are counted as ONE session, because PHP casts the
// canonical numeric string key "7" to the int key 7. A port that flattened both to strings would
// print 2 where the PHP prints 1.
//
// ── THE DEPENDENCIES, AND HOW THEY DEGRADE (the ticket's "degrade IDENTICALLY") ─────────────────
//
// This tag has TWO dependencies and it degrades on BOTH — independently, and in both cases SILENTLY.
// That silence is the single most important thing about this port, and it is the opposite of the
// sibling tags' behaviour:
//
//	CONGRUENCY_SQLITE undefined -> the DB arm is SKIPPED (`if (defined(...))`, :29). No message.
//	the DB throws (missing table, unopenable file, bad SQL)
//	                            -> CAUGHT AND IGNORED (:37 — the comment there reads
//	                               "ignore, fall through to the live log"). No message.
//	$HOME unset, or the log absent/unreadable/not-JSON/not-an-array
//	                            -> the MCP arm contributes NOTHING. No message.
//	BOTH unavailable            -> a fully-formed, VALID render: "<strong>0</strong> controller
//	                               actions", 0 sessions, page 1 of 1, and an EMPTY <div class='mem'>.
//
// SO: THERE IS NO "MemoryList: no DB." ARM, AND ADDING ONE WOULD BE A DIVERGENCE. DocList opens with
// `if (!defined('CONGRUENCY_SQLITE')) return "<p>DocList: no DB.</p>"` (DocList.php:36) and
// TreeView/others do the same; MemoryList pointedly does not — its DB read is one OPTIONAL source of
// two, so a missing DB is not an error here, it is just an empty source. Reading this tag's
// degradation off a sibling's would be wrong in exactly that way.
//
// The `catch (\Throwable)` at :102-104 is therefore NOT the DB's error path — collect() already
// swallowed those. It is reachable essentially only from the array-key write at :67; see
// memListArrayKey.
//
// ── WHAT IS NOT BYTE-REPRODUCIBLE, STATED PLAINLY ───────────────────────────────────────────────
//
// ONE branch, and it is not the DB one. PHP's catch renders get_class($e).': '.$e->getMessage()
// (:103). memListError reproduces the ONE message that branch can actually carry — "TypeError:
// Illegal offset type", from :67 — as a literal, because PHP 8 determines it exactly and it is
// input-independent. THAT STRING IS READ OFF PHP 8's DOCUMENTED SEMANTICS, NOT MEASURED HERE: no php
// binary exists in this worktree to run it against (see "THE GATE"). It is unreachable from any real
// gate log — it needs a session field that is a JSON array or object — and it is flagged again at
// memListArrayKey rather than hidden.
//
// The deferred catchThrowable guards a Go panic and emits the identical
// "<div class='cy-form-error'>MemoryList error: …</div>" frame, but with no class prefix, because a
// Go panic has no exception class. The FRAME is byte-identical; the message inside is not, and is not
// claimed to be. This is the package's standing, documented limitation (annotatehandler.go:134-142),
// not a new one, and it only fires when something is already broken.
//
// ── THE GATE — WHAT THE TICKET ASKS FOR, WHAT IS RUNNABLE HERE, AND WHAT WAS RUN ────────────────
//
// The ticket's gate is two byte-diffs, PHP:8899 vs Go:8900, over the same db:
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=MemoryList') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=MemoryList')
//	for p in memories; do
//	  diff <(curl -s "http://127.0.0.1:8899/?page=$p") <(curl -s "http://127.0.0.1:8900/?page=$p") \
//	    || echo "DIVERGES: $p"; done
//
// NEITHER CAN BE RUN FROM THIS WORKTREE, and both are additionally confounded on their own terms.
// Stating this rather than settling on a green-looking diff is what the ticket asks for — "if you
// cannot make a diff here run against THIS unit, say so on the ticket rather than settling on a diff
// that would be empty even with the unit unimplemented".
//
// WHY IT CANNOT BE RUN HERE — three independent walls, each checked this session:
//
//	NO PHP.  The ticket names tooling/congruencey-harness/php/php. That path does not exist (the
//	         whole php/ directory is absent) and `php` is not on PATH. It is PROVISIONED, not
//	         committed — tools/provision_php.py:5-8 places it and the binary is git-ignored; its
//	         local sources are two /home/notificationsforsteven/... paths (provision_php.py:36-39)
//	         that do not exist on this macOS host, so provisioning would need a network fetch.
//	NO DB.   Both engines must read the SAME congruency.sqlite (configure.php:42 puts it at
//	         checkouts/current/state/congruency.sqlite). That directory holds only README/STATE/
//	         manifest json; a find for *.sqlite and *.db across the whole worktree returns NOTHING.
//	         Without the shared db there is no "same database" for a diff to be over.
//	NO GO.   `go` is refused before it starts in this sandbox — `go build`, `go vet` and even
//	         `go version` are each blocked — so the :8900 side of every diff above cannot be built,
//	         let alone served.
//
// WHY BOTH DIFFS ARE CONFOUNDED EVEN WITH THE SERVERS UP — each would be exactly as non-empty with
// this file deleted, so neither measures this unit:
//
//	diff 1  ?page=tags&tag=MemoryList   The PHP returns a FULL CMS page; the Go server does not
//	                                    reproduce the page frame and says so itself (server.go:39-43,
//	                                    62-66: "NOT claimed: that the page's BYTES match PHP … larger
//	                                    by a constant ~6.2 KB of CMS chrome"). The tag's own bytes are
//	                                    a SLICE of that page (equivalence_test.go:28-33).
//	diff 2  ?page=memories              server.go's handlePage routes EVERY page key except "tags" to
//	                                    handleCatalogPage, the table-list seam that never invokes the
//	                                    tag engine (server.go:731-734, 831-833). So ?page=memories on
//	                                    the Go server cannot reach MemoryList at all. Wiring it is an
//	                                    edit to server.go, which this ticket forbids.
//
// THE REAL GATE, which exists precisely because of diff 1's confound, is #282's harness:
//
//	cd congruency-go && go test ./tags/ -run TestTagEquivalence/MemoryList -v
//
// It cuts the tag's own bytes out of the live PHP page with TagList.php's own anchors and compares
// them to RenderTag's, with a stability sandwich against concurrent writers. It needs the live 8899
// and the shared state db; absent either it SKIPS (its four guards, equivalence_test.go:115-120). It
// requires NO edit to run this tag — it sweeps Scan(TAGS_DIR) and measures whatever IsPorted reports,
// so registering MemoryList in the init() below is the whole wiring. That is the command to run on a
// host that has the server, and it is the measurement this unit's claim should ultimately rest on.
//
// ONE CAVEAT SPECIFIC TO THIS TAG, which whoever runs that harness must know: the two engines must
// also share $HOME. The MCP arm reads $HOME/.MCP/gate-memories.json (:40-41), so a PHP process and a
// Go process running as different users — or with different HOME — read DIFFERENT log files and will
// differ on data, not on engine. That is the same class of confound #227's header warns about ("a
// divergence is a data difference, not an engine difference"). The live log is also written by a
// RUNNING gate, so it is volatile in exactly the way the harness's php1/go/php2 sandwich exists to
// absorb.
//
// THIS GO CODE WAS NOT COMPILED OR EXECUTED, AND THAT IS A REAL GAP IN THIS DELIVERABLE. It must be
// said plainly rather than left for the reader to discover. So the usual floor ("RUN your own work
// before reporting done") could not be met here: the Go below is reviewed, not run, and a compile
// error or a runtime panic in it would be a live defect that no step in this session could have
// caught. The FIRST thing to do with this file is:
//
//	cd congruency-go && go build ./... && go vet ./tags/
//
// WHAT WAS ACTUALLY RUN THIS SESSION — one thing, and it tests my READING OF THE PHP, not the Go:
//
//	A Python transliteration of MemoryList.php's collect() and get_document(), modelling PHP's
//	array-key normalization, the strict !== guards, the (int)/(string) casts, PHP 8's STABLE usort,
//	and array_slice/ceil pagination. A quirk suite over it passed 58/58 and CONFIRMED, as behaviour
//	rather than as my assertion, each quirk documented below: the DB row wins a (ts,tool) collision;
//	a DB session "7" and a log session 7 count as ONE session while "5" and "05" count as two; an
//	int-0 session counts but '' and NULL do not; a NULL session renders "-" where an '' session
//	renders EMPTY; equal timestamps keep insertion order; ?p=99/-5/abc/(empty) all clamp and ?p=2xyz
//	is page 2; 0 rows still render "page 1 of 1" with an empty <div class='mem'> and the pager TWICE;
//	a stored "<<<MemoryList>>>" comes back escaped and inert; the intent/note ?? chain prefers intent,
//	falls back to note, and treats a NULL intent as absent; non-object log entries collapse to a
//	single all-empty row; and an array-valued session turns the whole tag into the TypeError div.
//
//	Separately, a transliteration of engine.go's toInt ALONGSIDE PHP's (int) over 10 inputs. This is
//	the one check that changed the code rather than confirming it: the two AGREE on 8 inputs and
//	DIVERGE on overflow, where toInt yields 0 and PHP saturates — so ?p=99999999999999999999 against
//	25 rows would have rendered page 1 where the PHP renders page 3. memListInt exists because of
//	that measurement, and the NBSP case below it for the same reason.
//
//	And a MECHANICAL LITERAL DIFF of the markup — the highest byte-risk part of any port and the one
//	thing eyeballing reliably misses. It extracts every string literal from MemoryList.php and from
//	the non-comment lines of THIS file and compares them: 26 of the PHP's 27 markup literals appear
//	here VERBATIM. The 27th is :89's interpolated " page <strong>$pg</strong> of $pages ", which Go
//	must split around strconv — so it is reconstructed with concrete values and compared to the PHP's
//	interpolation of the SAME values, together with both href links and the whole pager assembled in
//	all four of its arms (pg=1/1, 1/3, 2/3, 3/3). All byte-identical.
//
//	It is NOT the PHP interpreter (no PHP exists here to run), it is NOT this file's Go, and it is
//	NOT the gate. It raises confidence that the SPEC ENCODED BELOW is the spec MemoryList.php
//	actually implements; it says nothing about whether the Go transcribes it correctly.
//
// SO, PLAINLY: this unit is PORTED and its spec is CHECKED, but the Go is UNBUILT and the tag is NOT
// byte-measured against PHP. The gate is UNMET. The two commands that would move it — the build
// above, then the #282 harness — are both named here, and both need a host this session did not have.

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"math"
	"os"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"
)

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there, and
// TestTagEquivalence starts measuring this tag with no edit either.
func init() {
	Register("MemoryList", func(e *Engine, a *TagArguments) Tag { return &MemoryListTag{e: e, args: a} })
}

// MemoryListTag is MemoryList (MemoryList.php:19-107).
//
// args mirrors the PHP constructor's $arguments (:23), which the PHP stores in a private field and
// NEVER reads — the tag takes no TAG arguments (its one input is $_GET['p']), and the `memories`
// template invokes it bare as <<<MemoryList>>>. A nil *TagArguments (what TagList.php:67's
// `new $sel(null)` passes, the shape the ?page=tags&tag=MemoryList gate takes) is therefore stored
// and ignored, which is exactly what the PHP does with the NULL it is handed.
//
// Like DocList and unlike CategoryView, this constructor CANNOT throw on nil args: :23 only assigns
// the field, it never dereferences it. So the gallery render is not an error path — it runs the tag's
// real merge. There is no ctorThrew here and there must not be one.
type MemoryListTag struct {
	e    *Engine
	args *TagArguments
}

// memListRow is one entry of collect()'s $rows (:34-35, :46-48).
//
// ts/tool/intent are STRINGS because the PHP casts them with (string) at the point of collection;
// session is `any` because the PHP does NOT — it stores the source's native value and casts only at
// the very end (:96). That asymmetry is verbatim from the source and it is the whole reason the
// session count works out; see the file header on the merge.
type memListRow struct {
	ts      string
	session any
	tool    string
	intent  string
	src     string
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PHP semantics this tag needs. Deliberately unit-local — see the file header.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// memListString is PHP's (string) cast over the types the TWO sources can hand this tag. It is
// phpString (engine.go:497) plus the ONE type phpString cannot see, because only json_decode
// produces it: an ARRAY.
//
// PHP 8 casts an array to the literal string "Array" (with an "Array to string conversion" warning,
// which is not fatal and emits no bytes into the render). phpString's default arm would render a Go
// slice as "[1 2]" via fmt, which is not what PHP writes. Reached whenever the gate log holds e.g.
// {"tool": ["a"]}.
func memListString(v any) string {
	switch v.(type) {
	case []any, *memListObject:
		return "Array"
	}
	return phpString(v)
}

// memListEsc is self::esc($s) (:24) — htmlspecialchars((string)$s, ENT_QUOTES) — over a value that
// may have come from json_decode, so the (string) cast is memListString's, not phpString's. For every
// type engine.go's esc already handles the two are identical; this only differs on an array.
func memListEsc(v any) string { return phpHTMLSpecialChars(memListString(v)) }

// memListTruthyString is PHP's truthiness on a STRING — the `$home ? … : ''` test at :41.
//
// It is NOT "not empty": PHP counts BOTH "" and the one-character string "0" as FALSE. So HOME=0
// disables the MCP arm entirely, exactly as an unset HOME does. That is a genuine PHP quirk, it is
// the PHP's behaviour, and it is reproduced rather than tidied away.
func memListTruthyString(s string) bool { return s != "" && s != "0" }

// memListIsEmptyString is PHP's `$v === ''` (:67) — STRICT, so it is true only when $v is ALSO a
// string. An int 0, a float 0.0 and a bool false all pass the guard and ARE counted as sessions;
// only the actual empty string (and NULL, tested separately) is excluded. Confirmed as behaviour.
func memListIsEmptyString(v any) bool {
	s, ok := v.(string)
	return ok && s == ""
}

// memListInt is PHP's `(int)$_GET['p']` (:73) — and it is deliberately NOT engine.go's toInt.
//
// THE DIFFERENCE IS OVERFLOW, AND IT IS A REAL RENDERED-BYTE DIFFERENCE, measured this session
// against a transliteration of both casts. toInt runs leadingInt() through strconv.ParseInt and
// DISCARDS the result when ParseInt errors (engine.go:571-574), so an out-of-range literal becomes 0.
// PHP's (int) on a numeric string SATURATES instead:
//
//	?p=99999999999999999999   toInt -> 0                      PHP -> 9223372036854775807
//	                          ...so with 25 rows (3 pages), toInt clamps UP to page 1 where the
//	                          PHP clamps DOWN to page 3. Different rows, different bytes.
//	?p=-99999999999999999999  toInt -> 0                      PHP -> -9223372036854775808
//	                          ...which happens to agree, since both then clamp to page 1 at :74.
//
// Every other input the two agree on ("5", "2xyz", "abc", "", "+5", " 5", "-5", "0" — all checked),
// so this is toInt PLUS the saturation, not a reimplementation. It is unit-local because #319 may not
// edit engine.go; toInt's overflow arm looks like a genuine defect in the shared floor, but
// correcting it is another ticket's authority and would move other tags' bytes.
//
// THE LEADING-WHITESPACE SKIP USES isPHPSpace, NOT strings.TrimSpace, for the same class of reason.
// PHP skips exactly " \t\n\r\v\f" before a numeric string; TrimSpace also strips UNICODE spaces, so
// it would read ?p=<NBSP>5 as 5 where PHP reads it as 0. isPHPSpace (engine.go:624-626) is already
// that exact set, so this reuses it rather than restating it.
func memListInt(s string) int64 {
	i := 0
	for i < len(s) && isPHPSpace(s[i]) {
		i++
	}
	numStart := i
	if i < len(s) && (s[i] == '-' || s[i] == '+') {
		i++
	}
	digitsStart := i
	for i < len(s) && s[i] >= '0' && s[i] <= '9' {
		i++
	}
	if i == digitsStart {
		return 0 // no digits at all: (int)"abc" === 0, (int)"" === 0, (int)"-" === 0
	}
	n, err := strconv.ParseInt(s[numStart:i], 10, 64)
	if err == nil {
		return n
	}
	// ParseInt can only fail on RANGE here — the digits were already validated above.
	if s[numStart] == '-' {
		return math.MinInt64
	}
	return math.MaxInt64
}

// memListError is the catch(\Throwable) body (:102-104):
//
//	return "<div class='cy-form-error'>MemoryList error: "
//	     . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</div>";
//
// NOTE THE get_class PREFIX. TreeView's catch prints only getMessage() (engine.go:1747-1748) and
// DocList's likewise; MemoryList's prints "Class: message". Borrowing a sibling's frame here would be
// a byte diff.
func memListError(class, message string) string {
	return "<div class='cy-form-error'>MemoryList error: " + esc(class+": "+message) + "</div>"
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PHP array keys — the mechanism the session count rests on (:67).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// memListArrayKey models `$sessions[$v] = 1` — PHP's normalization of a value used as an array KEY.
// It returns a canonical tag ("i:<n>" for an integer key, "s:<str>" for a string key) whose EQUALITY
// is what decides count($sessions), and ok=false where PHP throws instead.
//
// A Go map keyed on the raw value would be WRONG IN BOTH DIRECTIONS: it would keep int64(7) and
// "7" apart where PHP merges them, and (being `any`-keyed) it would panic on an unhashable slice
// where PHP throws a catchable TypeError. The "i:"/"s:" prefixes are what let one Go map express
// PHP's two distinct key spaces without letting them collide.
//
// PHP's rules, each exercised by the quirk suite:
//
//	null            -> the "" STRING key      (guarded out at :67 before reaching here)
//	bool            -> int 0 / int 1
//	int             -> itself
//	float           -> int, TRUNCATED toward zero (7.9 -> 7; a lossy cast is deprecated in 8.1+
//	                   but still converts, and a deprecation emits no bytes)
//	string          -> int IFF it is a CANONICAL decimal integer in int range, else the string
//	array / object  -> TypeError("Illegal offset type")
//
// THE FLOAT ARM HAS AN UNMODELLED EDGE, NAMED RATHER THAN HIDDEN: a float outside int64's range
// (only producible by a hand-written 1e300 in the gate log) is converted by PHP 8 with modular
// wrapping, where int64(math.Trunc(f)) in Go is implementation-defined. No gate writer emits such a
// value, and both sides would still render SOME session count; the bytes are simply not claimed to
// match for that input.
func memListArrayKey(v any) (string, bool) {
	switch x := v.(type) {
	case nil:
		return "s:", true
	case bool:
		if x {
			return "i:1", true
		}
		return "i:0", true
	case int:
		return "i:" + strconv.Itoa(x), true
	case int32:
		return "i:" + strconv.FormatInt(int64(x), 10), true
	case int64:
		return "i:" + strconv.FormatInt(x, 10), true
	case float32:
		return "i:" + strconv.FormatInt(int64(math.Trunc(float64(x))), 10), true
	case float64:
		return "i:" + strconv.FormatInt(int64(math.Trunc(x)), 10), true
	case string:
		if n, isInt := memListCanonicalInt(x); isInt {
			return "i:" + strconv.FormatInt(n, 10), true
		}
		return "s:" + x, true
	default:
		// []any, *memListObject, and anything else PHP would refuse as an offset.
		return "", false
	}
}

// memListCanonicalInt is PHP's "does this string array key become an int?" test: the string must be a
// decimal integer that ROUND-TRIPS through (string)(int)$s, i.e. /^(0|-?[1-9][0-9]*)$/ within int64.
//
// strconv.ParseInt ALONE WOULD BE WRONG — it happily accepts "+1", " 1", "-0" and "007", none of
// which PHP converts. Each of those stays a STRING key in PHP, so "007" and 7 are two sessions while
// "7" and 7 are one. All four are pinned by the quirk suite.
func memListCanonicalInt(s string) (int64, bool) {
	if s == "" {
		return 0, false
	}
	i := 0
	if s[0] == '-' {
		i = 1
		if len(s) == 1 {
			return 0, false // "-"
		}
	}
	if s[i] == '0' {
		// "0" is the only canonical form starting with a zero digit: "-0", "00" and "01" are not.
		if i == 0 && len(s) == 1 {
			return 0, true
		}
		return 0, false
	}
	for j := i; j < len(s); j++ {
		if s[j] < '0' || s[j] > '9' {
			return 0, false
		}
	}
	n, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		return 0, false // out of int64 range -> PHP keeps it a string key
	}
	return n, true
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// json_decode($s, true) — the live gate log. Modelled, not delegated to encoding/json.
//
// A plain json.Unmarshal into `any` DIFFERS FROM PHP ON THREE POINTS THAT EACH CHANGE RENDERED BYTES,
// which is why this section exists rather than a one-line Unmarshal:
//
//  1. NUMBERS. Go decodes EVERY JSON number to float64. PHP decodes an integer literal that fits in
//     int64 to an INT, and only then falls back to float. The casts differ: a log ts of
//     123456789012345 is "123456789012345" in PHP but phpString(float64) renders the same value as
//     "1.2345678901234E+14" (precision-14 %G, engine.go:527-529). memListNumber makes the PHP choice.
//  2. OBJECT ORDER. json_decode(…, true) yields an ORDERED PHP array, and a TOP-LEVEL JSON OBJECT is
//     iterable — `is_array($data)` is true for it (:44), so foreach walks its VALUES in document
//     order. A Go map has no order, so iterating one would shuffle the rows, which changes both which
//     row wins a (ts,tool) de-dupe and the order equal timestamps keep under a STABLE sort. Hence
//     memListObject keeps its keys in a slice.
//  3. INVALID UTF-8. PHP's json_decode FAILS with JSON_ERROR_UTF8 and returns NULL — the whole MCP
//     arm contributes nothing. Go's encoding/json instead SUBSTITUTES U+FFFD and decodes happily, so
//     it would render rows PHP never renders. memListJSONDecode rejects the input first.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// memListObject is a JSON object as json_decode($s, true) yields it: an ORDERED, last-value-wins PHP
// assoc array.
//
// PHP casts an object's numeric-string keys to int keys just as it does any array key, but this tag
// only ever looks keys up by the fixed names "timestamp"/"session"/"tool"/"intent"/"note", none of
// which is numeric — and no two DISTINCT strings normalize to the same PHP key. So string-keyed
// storage is exactly equivalent here, and memListArrayKey is not needed on this path.
type memListObject struct {
	keys []string
	vals map[string]any
}

// set mirrors a PHP array write: a REPEATED key keeps its ORIGINAL position and takes the NEW value.
// (A duplicate key in one JSON object is legal and last-wins in both PHP and Go.)
func (o *memListObject) set(k string, v any) {
	if _, dup := o.vals[k]; !dup {
		o.keys = append(o.keys, k)
	}
	o.vals[k] = v
}

// memListJSONDecode is json_decode((string)@file_get_contents($log), true) (:43). ok=false is PHP's
// NULL return — a syntax error, invalid UTF-8, or trailing garbage — which :44's is_array() then
// rejects.
func memListJSONDecode(raw []byte) (any, bool) {
	// JSON_ERROR_UTF8: PHP refuses the whole document. See point 3 above.
	if !utf8.Valid(raw) {
		return nil, false
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber() // point 1: decide int-vs-float the way PHP does, not the way Go does
	v, err := memListDecodeValue(dec)
	if err != nil {
		return nil, false
	}
	// json_decode rejects trailing content ("{} {}" is NULL, not an array); a clean parse leaves the
	// decoder at EOF. Trailing WHITESPACE is fine on both sides — the tokenizer skips it.
	if _, err := dec.Token(); !errors.Is(err, io.EOF) {
		return nil, false
	}
	return v, true
}

func memListDecodeValue(dec *json.Decoder) (any, error) {
	tok, err := dec.Token()
	if err != nil {
		return nil, err
	}
	return memListDecodeFrom(dec, tok)
}

func memListDecodeFrom(dec *json.Decoder, tok json.Token) (any, error) {
	switch t := tok.(type) {
	case json.Delim:
		switch t {
		case '{':
			o := &memListObject{vals: map[string]any{}}
			for dec.More() {
				kt, err := dec.Token()
				if err != nil {
					return nil, err
				}
				k, isStr := kt.(string)
				if !isStr {
					return nil, errors.New("non-string object key")
				}
				v, err := memListDecodeValue(dec)
				if err != nil {
					return nil, err
				}
				o.set(k, v)
			}
			if _, err := dec.Token(); err != nil { // the closing '}'
				return nil, err
			}
			return o, nil
		case '[':
			arr := []any{}
			for dec.More() {
				v, err := memListDecodeValue(dec)
				if err != nil {
					return nil, err
				}
				arr = append(arr, v)
			}
			if _, err := dec.Token(); err != nil { // the closing ']'
				return nil, err
			}
			return arr, nil
		}
		return nil, errors.New("unexpected delimiter")
	case json.Number:
		return memListNumber(t), nil
	default:
		return tok, nil // nil, bool, string — already the PHP types
	}
}

// memListNumber is PHP's json_decode number rule: a literal with no fraction and no exponent that
// fits in int64 becomes an INT; everything else becomes a FLOAT. (Without JSON_BIGINT_AS_STRING, an
// integer literal too large for int64 degrades to float on both sides — and phpFloatString then
// renders it the same way PHP's (string) does.)
func memListNumber(n json.Number) any {
	s := n.String()
	if !strings.ContainsAny(s, ".eE") {
		if i, err := strconv.ParseInt(s, 10, 64); err == nil {
			return i
		}
	}
	f, err := n.Float64()
	if err != nil {
		return float64(0) // unreachable: the tokenizer already validated the literal
	}
	return f
}

// memListIterable is `is_array($data)` (:44) plus the foreach that follows (:45). BOTH a JSON array
// and a JSON object satisfy is_array once assoc=true has flattened objects into PHP arrays, and
// foreach walks the VALUES either way — for an object, in document order. Every other decoded type
// (a bare string, number, bool or null) fails is_array and contributes nothing.
func memListIterable(v any) ([]any, bool) {
	switch x := v.(type) {
	case []any:
		return x, true
	case *memListObject:
		out := make([]any, 0, len(x.keys))
		for _, k := range x.keys {
			out = append(out, x.vals[k])
		}
		return out, true
	}
	return nil, false
}

// memListOffset is `$e[$k] ?? …` — one link of the null-coalescing chains at :46-48. ok=false is
// "?? takes the right-hand side".
//
// TWO PHP RULES ARE FOLDED IN HERE, and both were confirmed as behaviour:
//
//   - ?? IS isset()-BASED, so it treats a key present with a NULL VALUE exactly like a MISSING key.
//     {"intent": null, "note": "N"} therefore yields the NOTE, not "".
//   - EVERY NON-OBJECT ENTRY YIELDS THE DEFAULT for every key. A JSON list entry has integer keys, so
//     $e['timestamp'] is undefined; on a STRING, isset($str['timestamp']) is false because the offset
//     is not numeric; on an int/float/bool/null, the offset is simply NULL. None of these is a fatal
//     — ?? suppresses the diagnostics — so such an entry becomes an all-default row (ts "", session
//     NULL, tool "", intent "") and is APPENDED, not skipped. Several of them de-dupe to ONE row on
//     the shared key "|".
func memListOffset(e any, k string) (any, bool) {
	o, isObj := e.(*memListObject)
	if !isObj {
		return nil, false
	}
	v, present := o.vals[k]
	if !present || v == nil {
		return nil, false
	}
	return v, true
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// collect — MemoryList::collect() (:26-61).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// memListCollect is MemoryList::collect() (:26-61): read both sources, de-dupe, sort newest-first.
func (t *MemoryListTag) memListCollect() []memListRow {
	var rows []memListRow

	// :29-38 — source 1, the durable DB projection. `if (defined('CONGRUENCY_SQLITE'))` is the
	// cfg.SQLite == "" mapping every sibling port uses (doclist.go:338, engine.go:1742-1744) — but
	// note this is a SKIP, not an early return with a message. See the file header.
	if t.e.cfg.SQLite != "" {
		rows = append(rows, memListDBRows(t.e.cfg)...)
	}

	// :40-51 — source 2, the live MCP gate log.
	rows = append(rows, memListLogRows()...)

	// :53-57 — de-dupe on (ts, tool). BOTH halves of the key are already (string), so this is plain
	// concatenation and no cast is hiding in it. The FIRST occurrence wins and the DB rows were
	// appended first, which is exactly the PHP's comment: "prefer the DB row (seen first)".
	seen := make(map[string]bool, len(rows))
	uniq := make([]memListRow, 0, len(rows))
	for _, r := range rows {
		k := r.ts + "|" + r.tool
		if !seen[k] {
			seen[k] = true
			uniq = append(uniq, r)
		}
	}

	// :59 — usort($uniq, fn($a,$b) => strcmp($b['ts'], $a['ts'])): reverse chronological.
	//
	// SliceStable, NOT Slice, AND THAT IS NOT A STYLE CHOICE. PHP 8.0 made sorting STABLE (the
	// "Make sorting stable" RFC), so rows with EQUAL ts keep the order they were collected in —
	// which is DB-before-MCP, and within the DB, sqlite's row order. sort.Slice is explicitly
	// unstable and would be free to permute those ties, changing the rendered bytes for any two
	// actions sharing a timestamp. (A PHP 7 target would need the opposite reasoning; the harness php
	// is 8.x — provision_php.py:40 pins 8.4.23.)
	//
	// strings.Compare is strcmp: a BYTE comparison, not a locale- or number-aware one. ts is a TEXT
	// column holding "2026-07-15T09:16:00" stamps (tracker/store.py:66-67), which sort correctly as
	// bytes — that is why the PHP can get away with strcmp, and the port must do the same thing
	// rather than parse the timestamps.
	sort.SliceStable(uniq, func(i, j int) bool {
		return strings.Compare(uniq[j].ts, uniq[i].ts) < 0
	})
	return uniq
}

// memListDBRows is :29-38 — the `memories` table, or nothing.
//
// THE WHOLE FUNCTION IS THE PHP'S try/catch, AND ITS ERROR ARM IS DELIBERATELY SILENT (:37 —
// "ignore, fall through to the live log"). A missing table, an unopenable file, a locked db: each
// contributes zero rows and NO message, and the render proceeds on the log alone. Setting
// PDO::ERRMODE_EXCEPTION (:32) is what routes those into the catch — it is not, as in DocList
// (doclist.go:70-73), a choice to surface them.
//
// TWO DIVERGENCES, BOTH INHERITED AND BOTH INVISIBLE HERE:
//
//   - PHP's `new PDO('sqlite:'.$path)` opens READ-WRITE and CREATES an empty db when the path is
//     missing; openDB returns an error and never creates (engine.go's divergence 2). PHP then throws
//     on the missing `memories` TABLE and lands in this same catch. So the branch agrees and the row
//     count agrees — only PHP's stray file differs, and this port refuses to inherit it.
//   - PHP appends rows as it iterates, so a throw PART-WAY through the fetch would KEEP the rows
//     already appended, where the error return below discards them. queryRows executes the statement
//     and drains it in one call, so the realistic failures (no such table, cannot open) all raise
//     before any row exists and the two agree at zero. A mid-fetch failure against a healthy sqlite
//     file is not a state this schema produces.
func memListDBRows(cfg Config) []memListRow {
	db, err := openDB(cfg, cfg.SQLite)
	if err != nil {
		return nil // catch (\Throwable $e) { /* ignore, fall through to the live log */ }
	}
	defer db.Close()

	// :33 — the query, verbatim. No ORDER BY: the row order is sqlite's own, and it is observable
	// (it breaks ties under the stable sort at :59 and decides which row wins a de-dupe). Both engines
	// run the same SQL over the same file, so both see the same order.
	got, err := queryRows(db, "SELECT ts, session, tool, intent FROM memories")
	if err != nil {
		return nil
	}

	out := make([]memListRow, 0, len(got))
	for _, r := range got {
		// :34-35 — note WHICH fields are cast. ts/tool/intent get (string); session does NOT, and
		// keeps the column's native type all the way to :67 and :96.
		out = append(out, memListRow{
			ts:      phpString(r["ts"]),
			session: r["session"],
			tool:    phpString(r["tool"]),
			intent:  phpString(r["intent"]),
			src:     "db",
		})
	}
	return out
}

// memListLogRows is :40-51 — the live MCP gate log, or nothing.
//
// $HOME, not os.UserHomeDir(): the PHP reads getenv('HOME') (:40), and os.UserHomeDir consults $HOME
// but falls BACK to the OS user database when it is unset — where PHP's getenv just returns false and
// the arm is skipped. This path is not in Config because Config has no HOME field and #319 may not
// edit engine.go to add one; os.Getenv is the exact counterpart of the call the PHP makes.
//
// rtrim($home, '/') strips EVERY trailing slash, not just one — strings.TrimRight, not
// strings.TrimSuffix.
//
// `$log && is_readable($log)` (:42) then `(string)@file_get_contents($log)` (:43) collapse to one
// ReadFile: every way is_readable can say no (absent, unreadable) and every way the suppressed read
// can fail (a directory, a race) reaches the SAME place — @file_get_contents returns false,
// (string)false is "", json_decode("") is NULL, and is_array(NULL) is false, so the arm contributes
// nothing. A Go read error contributes nothing too.
func memListLogRows() []memListRow {
	home := os.Getenv("HOME")
	log := ""
	if memListTruthyString(home) {
		log = strings.TrimRight(home, "/") + "/.MCP/gate-memories.json"
	}
	if log == "" {
		return nil
	}
	raw, err := os.ReadFile(log)
	if err != nil {
		return nil
	}
	data, ok := memListJSONDecode(raw)
	if !ok {
		return nil
	}
	entries, isArr := memListIterable(data) // :44 — is_array($data)
	if !isArr {
		return nil
	}

	out := make([]memListRow, 0, len(entries))
	for _, e := range entries {
		// :46 — (string)($e['timestamp'] ?? '')
		ts := ""
		if v, ok := memListOffset(e, "timestamp"); ok {
			ts = memListString(v)
		}
		// :46 — $e['session'] ?? null. NOT cast; the native value flows on, as in the DB arm.
		session, _ := memListOffset(e, "session")
		// :47 — (string)($e['tool'] ?? '')
		tool := ""
		if v, ok := memListOffset(e, "tool"); ok {
			tool = memListString(v)
		}
		// :48 — (string)($e['intent'] ?? ($e['note'] ?? '')). The chain is nested, so a NULL or
		// missing intent falls through to note, and a NULL or missing note lands on "".
		intent := ""
		if v, ok := memListOffset(e, "intent"); ok {
			intent = memListString(v)
		} else if v, ok := memListOffset(e, "note"); ok {
			intent = memListString(v)
		}
		out = append(out, memListRow{ts: ts, session: session, tool: tool, intent: intent, src: "mcp"})
	}
	return out
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// GetDocument — MemoryList::get_document() (:63-105).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// memListPerPage is `$per = 10` (:71) — the page size, and the only tuning constant this tag has.
const memListPerPage = 10

// GetDocument is MemoryList::get_document() (:63-105).
//
// EVERYTHING IS INSIDE THE try (:64), collect() included — but collect() already swallowed the DB
// errors itself, so the catch arm is NOT the database's error path. See the file header.
func (t *MemoryListTag) GetDocument() (out string) {
	defer catchThrowable(&out, "MemoryList")

	rows := t.memListCollect() // :65

	// :66-67 — the distinct-session count.
	//
	// `if ($r['session'] !== null && $r['session'] !== '') { $sessions[$r['session']] = 1; }`
	//
	// Both tests are STRICT. `!== ''` compares TYPES too, so only the actual empty string is
	// excluded: an int 0 and a bool false both pass and are counted. The write itself is where PHP
	// normalizes the key — and where an array session throws.
	//
	// This loop walks ALL rows, not the page's slice, so the count reflects the whole log — and so an
	// array-valued session ANYWHERE turns the ENTIRE tag into the error div, whether or not that row
	// would have been rendered.
	sessions := make(map[string]bool)
	for _, r := range rows {
		if r.session == nil || memListIsEmptyString(r.session) {
			continue
		}
		k, ok := memListArrayKey(r.session)
		if !ok {
			// PHP 8: `$a[[]] = 1` throws TypeError("Illegal offset type"), which :102's catch turns
			// into the error div. See the file header — this exact string is read off PHP 8's
			// semantics and was NOT measured against a php binary, because none exists here.
			return memListError("TypeError", "Illegal offset type")
		}
		sessions[k] = true
	}

	// :70-76 — pagination. Reverse chronological, so page 1 is the NEWEST.
	total := len(rows) // :70 — count($rows): ALL rows, not the slice. It is a rendered byte.
	// :72 — max(1, (int)ceil($total / $per)). The max() is what makes an EMPTY log render "of 1"
	// rather than "of 0": ceil(0/10) is 0.
	pages := int(math.Ceil(float64(total) / float64(memListPerPage)))
	if pages < 1 {
		pages = 1
	}
	// :73 — isset($_GET['p']) ? (int)$_GET['p'] : 1. getIsset draws the isset distinction
	// (engine.go:923-932) — and it matters here in a way it does not for most tags: ?p= with an EMPTY
	// value IS set, so it takes the cast arm and yields (int)"" === 0, which :74 then clamps to 1.
	// The unset arm yields 1 directly. Both land on page 1, so the distinction is invisible in the
	// bytes — but via the else-arm, not because the two are the same expression.
	//
	// memListInt, NOT toInt: see memListInt for the overflow divergence that costs real bytes.
	// "abc" and "" are 0 (then clamped to 1), "2xyz" is 2 — all confirmed as behaviour.
	//
	// PHP would also accept ?p[]=1 as an ARRAY and cast it to int 1; Go's url.Values parses that key
	// as the literal "p[]", so $_GET['p'] is never an array on this side. The two parsers differ, no
	// tag can observe it through getIsset, and no template emits such a link.
	//
	// pg is clamped in int64 space and narrowed only AFTER :74-75 have bounded it to [1, pages]. A
	// saturated PHP_INT_MAX narrowed to `int` first would be a no-op on a 64-bit build and would
	// become -1 on a 32-bit one — i.e. the clamp, not the cast, is what makes the narrowing safe.
	pgv := int64(1)
	if v, isSet := t.e.getIsset("p"); isSet {
		pgv = memListInt(v)
	}
	if pgv < 1 { // :74
		pgv = 1
	}
	if pgv > int64(pages) { // :75
		pgv = int64(pages)
	}
	pg := int(pgv)
	slice := memListSlice(rows, (pg-1)*memListPerPage, memListPerPage) // :76

	// :78-83 — the <style> block, verbatim. The trailing "\n" is inside the PHP's double-quoted
	// string and is a rendered byte.
	var b strings.Builder
	b.WriteString("<style>.mem{display:grid;gap:.55rem}" +
		".m{border:1px solid #d8d2c4;border-left:5px solid #8a5a1a;border-radius:6px;padding:.5rem .8rem;background:#fffdf8}" +
		".m .top{font:.7rem/1.4 monospace;color:#666}.m .tool{color:#8a5a1a;font-weight:600}" +
		".m .src{float:right;font:600 .58rem/1.6 sans-serif;text-transform:uppercase;color:#fff;background:#8a7a1a;padding:.05rem .4rem;border-radius:3px}" +
		".m .intent{margin:.25rem 0 0;font-size:.9rem;color:#333}" +
		".pager{margin:1rem 0;font-size:.85rem}.pager a{margin:0 .5rem}</style>\n")

	// :84-85 — the summary line. $total and count($sessions) are INTs concatenated into the string,
	// so they are NOT escaped and must not be: strconv, not esc.
	b.WriteString("<p style='font-size:.85rem;color:#555'><strong>" + strconv.Itoa(total) +
		"</strong> controller actions &middot; <strong>" + strconv.Itoa(len(sessions)) +
		"</strong> session(s) &middot; reverse chronological, reflecting the MCP.</p>\n")

	// :87-91 — the pager. Built ONCE and emitted TWICE (:93 and :100), so it is a variable here for
	// the same reason it is one in the PHP.
	//
	// The links are hardcoded to ?page=memories (:88, :90) — NOT to the current page key. So the
	// pager rendered at ?page=tags&tag=MemoryList links AWAY to ?page=memories, losing the tag
	// selection. That is a real wart in the PHP and it is ported as-is; the ticket is explicit that a
	// defect gets a separate bug ticket and a faithful port, never a fix here.
	pager := "<div class='pager'>"
	if pg > 1 { // :88
		pager += "<a href='?page=memories&p=" + strconv.Itoa(pg-1) + "'>&larr; newer</a>"
	} else {
		pager += "<span style='color:#aaa'>&larr; newer</span>"
	}
	// :89 — " page <strong>$pg</strong> of $pages ", both leading and trailing space included.
	pager += " page <strong>" + strconv.Itoa(pg) + "</strong> of " + strconv.Itoa(pages) + " "
	if pg < pages { // :90
		pager += "<a href='?page=memories&p=" + strconv.Itoa(pg+1) + "'>older &rarr;</a>"
	} else {
		pager += "<span style='color:#aaa'>older &rarr;</span>"
	}
	pager += "</div>\n" // :91

	b.WriteString(pager + "<div class='mem'>\n") // :93

	// :94-99 — one card per row. THERE IS NO EMPTY-STATE ARM and adding one would be a divergence:
	// an empty $slice emits "<div class='mem'>\n</div>\n" with nothing between, and no sentence.
	for _, r := range slice {
		// :96 — esc($r['session'] !== null ? $r['session'] : '-'). STRICT !== null, so the '-'
		// placeholder is for NULL ONLY: an EMPTY-STRING session renders as nothing at all, leaving
		// "session  &middot;" with two spaces. Both confirmed as behaviour.
		var sess any = "-"
		if r.session != nil {
			sess = r.session
		}
		// EVERY value here is escaped exactly where the PHP escapes it (:95-98). This render flows
		// back through execute_all_tags, so a stored "<<<MemoryList>>>" — a tool or intent string
		// that names a tag, which this log plausibly holds — must come back
		// "&lt;&lt;&lt;MemoryList&gt;&gt;&gt;" and stay inert (engine.go's header, mechanism 2). Do
		// not remove an esc() call. The two leading spaces are the PHP's indentation and are rendered
		// bytes.
		b.WriteString("  <div class='m'><div class='top'><span class='src'>" + esc(r.src) +
			"</span>" + esc(r.ts) + " &middot; session " + memListEsc(sess) +
			" &middot; <span class='tool'>" + esc(r.tool) + "</span></div>" +
			"<div class='intent'>" + esc(r.intent) + "</div></div>\n")
	}

	b.WriteString("</div>\n" + pager) // :100
	return b.String()                 // :101
}

// memListSlice is array_slice($rows, $offset, $length) for the non-negative offsets :76 can produce
// ($pg is clamped to >= 1, so the offset is >= 0). An offset at or past the end yields the empty set
// rather than an error — which is how the LAST page renders its partial remainder, and what a
// 0-row log relies on.
func memListSlice(rows []memListRow, offset, length int) []memListRow {
	if offset >= len(rows) {
		return nil
	}
	end := offset + length
	if end > len(rows) {
		end = len(rows)
	}
	return rows[offset:end]
}
