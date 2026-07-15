// db.go — congruency-go DATABASE LAYER (ticket #224).
//
// WHAT THIS IS
//
// The pure-Go half of congruency's data plane: a sqlite handle over the SAME congruency.sqlite,
// the SAME schema, UNCHANGED (this file issues no DDL and no migration — it only opens what is
// already there), plus a reimplementation of the data-driven `api_routes` engine that boot/rest.php
// implements in PHP as congruency_rest_route().
//
// The engine is data-driven: an endpoint is a ROW of the `api_routes` table
// (name, method, sql, auth, params, meta), not code. Given such a row, the engine gates the request
// on the row's method/auth, binds the declared :params the row's sql actually mentions, executes,
// and shapes the reply. Adding an endpoint is adding a row — in Go exactly as in PHP.
//
// THE CONTRACT: byte-identical JSON. rest.php ECHOES its replies; this file reproduces those bytes
// exactly — same key order, same number formatting, same escaping, same 4-space pretty indent, same
// trailing "\n", and the same COMPACT (non-pretty) encoding for the engine's own error replies.
// Everything below that looks quirky is quirky because the PHP is: the PHP is the spec, and where
// they disagree the Go is wrong. Every claim in this file was verified against the repo's own PHP
// (tooling/congruencey-harness/php/php, PHP 8.4.23) and the live state db this session; the notes
// record what was measured, not what was assumed.
//
// TERMS (defined here because this artifact stands alone):
//
//	route     — one row of `api_routes`, keyed by `name`. Its `sql` is admin-authored and trusted;
//	            consumer-supplied values are only ever BOUND, never concatenated (no injection).
//	params    — the route row's `params` column: a JSON object {"<name>":"<type>"} declaring the
//	            :placeholders the sql may use and each one's type (int | float/real | anything else
//	            = string). It is a DECLARATION, not a schema: nothing is rejected, values are cast.
//	engine    — congruency_rest_route()'s job, and this file's: row -> gate -> bind -> execute -> shape.
//	PDO       — PHP's database abstraction. rest.php drives sqlite through it; its defaults (below)
//	            are load-bearing for equivalence.
//
// HOW TO BUILD AND RUN IT
//
// Ticket #224's deliverable is this one file, so this file does not carry a go.mod (creating one
// would be a side effect the ticket forbids: "touch nothing else"). The one-time module bootstrap
// is therefore the caller's, and it is exactly this — from the directory holding db.go:
//
//	go mod init congruency-go
//	go get modernc.org/sqlite@v1.53.0     # pure Go, no cgo -> a single static binary
//	go build .                            # or: go run . -selftest
//
// modernc.org/sqlite is the ticket's preferred driver: it is a pure-Go translation of sqlite, so
// CGO_ENABLED=0 still yields one self-contained static binary. Then, against the live state db:
//
//	go run . -db ../congruency/checkouts/current/state/congruency.sqlite -routes
//	go run . -db ../congruency/checkouts/current/state/congruency.sqlite -route kind.roster
//	go run . -db ../congruency/checkouts/current/state/congruency.sqlite -route agent.roster -input '{"n":2}'
//	go run . -selftest                    # the built-in checks; needs no db
//
// -selftest asserts this file's PHP-mirroring conversions against values measured from the repo's
// PHP this session. It creates nothing and opens no db.
//
// SIDE EFFECTS. Read routes touch nothing. Open() mirrors PHP's `new PDO('sqlite:'.$path)`:
// read/write, and (like PDO) it CREATES the file if it does not exist — so a typo'd -db path makes
// an empty db rather than an error, exactly as the PHP does. Pass -immutable (OpenImmutable) to
// probe read routes with a guarantee of zero writes and zero sidecar files. The live state db is
// journal_mode=delete (measured), not WAL, so a plain read opens no -wal/-shm; -immutable holds
// regardless of journal mode. A WRITE route obviously writes: probe those against a COPY of the db,
// never the live state db.
//
// THE PHP BEHAVIOURS THIS FILE MIRRORS (each measured against the repo's php this session; the
// non-obvious ones are what an "obvious" port gets wrong):
//
//  1. EVERY BOUND VALUE IS SQLITE **TEXT**. rest.php calls $st->bindValue(':'.$p, $val) with no
//     third argument, so the type defaults to PDO::PARAM_STR — and PDO_SQLite stringifies the zval
//     and calls sqlite3_bind_text for it. The engine's (int)/(float) casts therefore only NORMALISE
//     the value; they do not make it an integer to sqlite. Measured: bind PHP int 5 -> typeof() is
//     'text'; `SELECT :n AS n` with (int)7 returns the STRING "7"; and `WHERE (id+0) = :id` with
//     (int)2 matches NOTHING, because TEXT '2' never equals INTEGER 2 where no column affinity
//     coerces it. A port that binds int64 would silently return rows PHP does not. Hence bindText().
//     NULL is the sole exception: a null value binds SQL NULL (typeof 'null').
//
//  2. ONLY DECLARED PARAMS THE SQL MENTIONS ARE BOUND, and the test PHP uses is the naive substring
//     `strpos($sql, ':'.$name) === false`. A param the sql does not mention is skipped; a param the
//     sql mentions but `params` does not declare is never bound and sqlite leaves it NULL. Routes
//     lean on this: `agent.roster` is `... LIMIT COALESCE(:n,-1)`, so an absent n binds NULL,
//     COALESCE yields -1, and LIMIT -1 means "all rows". Absent and explicitly-null are the same
//     input (PHP tests array_key_exists then binds null either way).
//
//  3. THE READ/WRITE SPLIT IS A PREFIX TEST, NOT A PARSE: stripos(ltrim($sql),'select') === 0. So
//     `WITH x AS (...) SELECT ...` is shaped as a WRITE, and a sql starting "selection" as a read.
//     ltrim strips PHP's set " \t\n\r\0\x0B" (vertical tab, NOT form feed). Faithfully reproduced.
//
//  4. THE REPLY SHAPES. A read: {"route":..,"rows":[..]} pretty-printed. A write:
//     {"route":..,"affected":<int>,"rowid":<STRING>}. `rowid` is a JSON **string** because
//     PDO::lastInsertId() returns a string — measured "2" after an insert, and "0" on a connection
//     that has inserted nothing (so an UPDATE/DELETE route reports "0"). PHP opens a fresh PDO per
//     request, so this file pins ONE sqlite connection per Open() to reproduce that per-handle
//     lastInsertId; a pooled handle would leak another request's rowid.
//
//  5. THE ENGINE'S ERROR REPLIES ARE **COMPACT**, not pretty: rest.php passes no flags to
//     json_encode for the 404/405/401 bodies, while success bodies get
//     JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES. Compact also means slashes ARE escaped there ("\/"),
//     since JSON_UNESCAPED_SLASHES is absent. Both encoders live below; the flags pick the shape.
//
//  6. PHP'S NUMBER FORMATTING IS NOT GO'S. json_encode of a double uses serialize_precision=-1
//     (shortest round-trip digits) with zend_gcvt's threshold 17 and a lowercase 'e': PHP prints
//     1.0e+100 where Go's encoding/json prints 1e+100, and 1.0e-5 where Go prints 0.00001. The
//     (string) cast of a double is a DIFFERENT formatter again — precision=14, uppercase 'E'
//     (measured: (string)(0.1+0.2) is "0.3", (string)1e15 is "1.0E+15"). This matters on the
//     critical path: ticket_events.ts is a REAL column, so ticket.journal and lessons.recent return
//     doubles. phpGcvt() below implements both; encoding/json is deliberately NOT used to emit.
//
//  7. json_encode FAILS (returns false) on invalid UTF-8 and on INF/NAN. rest.php does not check:
//     `echo json_encode(...) . "\n"` then echoes false . "\n" — i.e. a lone "\n" with a 200 status.
//     Reproduced exactly; the db does hold non-UTF-8 blobs, so this path is real.
//
//  8. PDO::FETCH_ASSOC COLLAPSES DUPLICATE COLUMN NAMES with PHP array semantics: the key keeps its
//     FIRST position and takes the LAST value (measured: `SELECT 10 AS id, 20 AS id, 30 AS other`
//     -> {"id":20,"other":30}). Row order is column order, so this file never uses a Go map to hold
//     a row (Go maps have no order and would sort the keys).
//
//  9. method/auth normalisation: method is strtoupper(...) ?: 'GET' then split on ',' and trimmed,
//     so an empty/NULL method means GET; auth is strtolower(trim(...)) with a NULL (not empty)
//     default of 'public' — only the exact strings "admin" and "token" gate anything.
//
// 10. telemetry.record SHORT-CIRCUITS. rest.php checks `function_exists('congruency_telemetry_record')`
//     and that function is defined in rest.php itself, so the branch is ALWAYS taken: the route's
//     INSERT sql never runs from the engine, and the reply is {"route","ok","kind"} (pretty). The
//     actual row is written by boot/monitor.php's congruency_telemetry_ingest, which the engine
//     calls only `if (function_exists(...))` — a hook, modelled here as DB.TelemetryIngest (nil =
//     the function is not defined). The short-circuit happens AFTER the method/auth gates and after
//     the input is assembled, but BEFORE any param binding. Same order here.
//
// WHAT THIS FILE DELIBERATELY LEAVES TO #225 (the server layer). The engine is the unit here; the
// ?api CRUD verbs, the table allowlist/denylist, the HTTP front door, the API-key/session/Vault
// checks, and turning a thrown error into a 500 {"error": msg} are congruency_rest_dispatch's job.
// Their seams are present and named: RunRoute takes the already-assembled input map (rest.php builds
// it from $_GET plus, for write methods, the JSON body) and an Authorizer (the two callbacks the
// engine consults); a route whose sql fails to prepare/execute is returned as a Go error, which is
// precisely the PDOException rest.php lets propagate to dispatch's catch. That error's TEXT is the
// one thing that cannot match: PDO says `SQLSTATE[HY000]: General error: 1 no such table: x` and
// sqlite/Go do not. It is off the equivalence gate's path (all 62 live routes prepare cleanly) and
// is called out here rather than faked.
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"math"
	"os"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"

	_ "modernc.org/sqlite"
)

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PHP json_encode flags. The literal values PHP uses, so a reader can match them to the rest.php
// call sites: success bodies use jsonPretty|jsonUnescapedSlashes, error bodies use 0.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

const (
	jsonUnescapedSlashes = 64  // JSON_UNESCAPED_SLASHES
	jsonPretty           = 128 // JSON_PRETTY_PRINT
)

// phpPrecision is PHP's `precision` ini (measured: 14). It drives the (string) cast of a double.
// phpSerializePrecision is `serialize_precision` (measured: -1 = shortest round-trip digits), which
// drives json_encode of a double; its gcvt threshold is 17.
const (
	phpPrecision          = 14
	phpSerializeThreshold = 17
)

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The PHP value model.
//
// A PHP associative array is ORDERED, and json_encode emits it in insertion order. Go maps are not
// ordered, so a row is a slice of fields. Obj is a JSON object, Arr a JSON list — the same
// distinction PHP draws between an assoc array and a packed list.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// Field is one key/value pair of an Obj.
type Field struct {
	K string
	V any
}

// Obj is an ordered string-keyed PHP array (encodes as a JSON object).
type Obj []Field

// Arr is a packed PHP list (encodes as a JSON array).
type Arr []any

// Set assigns k, with PHP array semantics: a repeated key keeps its ORIGINAL position and takes the
// NEW value. This is what makes PDO::FETCH_ASSOC collapse duplicate column names the way it does
// (measured: SELECT 10 AS id, 20 AS id, 30 AS other -> {"id":20,"other":30}).
func (o Obj) Set(k string, v any) Obj {
	for i := range o {
		if o[i].K == k {
			o[i].V = v
			return o
		}
	}
	return append(o, Field{k, v})
}

// Get returns the value for k and whether it was present.
func (o Obj) Get(k string) (any, bool) {
	for i := range o {
		if o[i].K == k {
			return o[i].V, true
		}
	}
	return nil, false
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PHP number formatting — phpGcvt.
//
// zend_gcvt(value, ndigit, dec_point, exp_char, buf) is the formatter behind BOTH of PHP's
// double-to-text conversions, and they differ in every argument that matters:
//
//	json_encode(double)   ndigit=17 (serialize_precision=-1 -> shortest round-trip digits), 'e'
//	(string)$double       ndigit=14 (the `precision` ini -> 14 significant digits),         'E'
//
// The shared shape rules, measured across 34 values this session:
//   - exponential form iff decExp < -4 || decExp >= ndigit, where value = d.ddd x 10^decExp;
//   - in exponential form the mantissa ALWAYS carries a fraction: 1e100 prints "1.0e+100", never
//     "1e+100" (this is exactly where Go's encoding/json diverges);
//   - the exponent always carries a sign and is NEVER zero-padded: "1.5e-7", not "1.5e-07"
//     (this is where C's printf %e diverges);
//   - fixed form never gains a trailing ".0": json_encode(1.0) is "1";
//   - trailing zeros are stripped from the digit string before shaping;
//   - -0.0 prints "-0".
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// phpGcvt renders f the way zend_gcvt does. shortest selects the digit source: true = the shortest
// round-trip digits (json_encode's serialize_precision=-1), false = exactly ndigit significant
// digits (the (string) cast's `precision`). ndigit is also the exponential-form threshold.
func phpGcvt(f float64, ndigit int, expChar byte, shortest bool) string {
	if math.IsNaN(f) {
		return "NAN"
	}
	if math.IsInf(f, 1) {
		return "INF"
	}
	if math.IsInf(f, -1) {
		return "-INF"
	}
	if f == 0 {
		if math.Signbit(f) {
			return "-0"
		}
		return "0"
	}

	// Take the digits and the decimal exponent from Go's 'e' form, which is defined as d.dddde±XX,
	// i.e. exactly the d.ddd x 10^decExp that gcvt's rules are written against.
	prec := -1
	if !shortest {
		prec = ndigit - 1
	}
	e := strconv.FormatFloat(f, 'e', prec, 64)

	neg := false
	if e[0] == '-' {
		neg = true
		e = e[1:]
	}
	ePos := strings.IndexByte(e, 'e')
	mant, expPart := e[:ePos], e[ePos+1:]
	decExp, err := strconv.Atoi(expPart)
	if err != nil { // unreachable for a finite float; never guess silently
		return e
	}
	digits := strings.Replace(mant, ".", "", 1)
	digits = strings.TrimRight(digits, "0")
	if digits == "" {
		digits = "0" // the value rounded to zero at this precision
	}

	var out string
	if decExp < -4 || decExp >= ndigit {
		// exponential: one leading digit, a forced fraction, a signed unpadded exponent.
		frac := digits[1:]
		if frac == "" {
			frac = "0"
		}
		sign := "+"
		if decExp < 0 {
			sign = "-"
			decExp = -decExp
		}
		out = digits[:1] + "." + frac + string(expChar) + sign + strconv.Itoa(decExp)
	} else {
		out = fixedFromDigits(digits, decExp)
	}
	if neg {
		out = "-" + out
	}
	return out
}

// fixedFromDigits renders digits x 10^decExp in plain notation, given -4 <= decExp < ndigit.
func fixedFromDigits(digits string, decExp int) string {
	n := len(digits)
	switch {
	case decExp >= n-1: // integral, pad with zeros: "1" e2 -> "100"
		return digits + strings.Repeat("0", decExp-(n-1))
	case decExp >= 0: // point falls inside the digits: "12345" e2 -> "123.45"
		return digits[:decExp+1] + "." + digits[decExp+1:]
	default: // leading zeros: "1" e-4 -> "0.0001"
		return "0." + strings.Repeat("0", -decExp-1) + digits
	}
}

// phpJSONDouble formats a double the way json_encode does (serialize_precision=-1).
func phpJSONDouble(f float64) string { return phpGcvt(f, phpSerializeThreshold, 'e', true) }

// phpStringDouble formats a double the way PHP's (string) cast does (`precision`=14, uppercase E).
func phpStringDouble(f float64) string {
	if math.IsNaN(f) {
		return "NAN"
	}
	if math.IsInf(f, 1) {
		return "INF"
	}
	if math.IsInf(f, -1) {
		return "-INF"
	}
	return phpGcvt(f, phpPrecision, 'E', false)
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PHP scalar casts — what the engine does to a value before binding it.
//
// rest.php:  if ($t === 'int') { $val = (int) $val; }
//            elseif ($t === 'float' || $t === 'real') { $val = (float) $val; }
//            else { $val = (string) $val; }
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// numericPrefix implements PHP's is_numeric_string_ex(allow_errors=true): it reads the LONGEST
// leading numeric run of s — optional whitespace, optional sign, digits, optional fraction,
// optional exponent — and reports whether that run is integral. Trailing junk is tolerated and
// ignored, which is why (int)"12abc" is 12 and (int)"abc" is 0.
func numericPrefix(s string) (isInt bool, i int64, f float64, ok bool) {
	j := 0
	for j < len(s) && (s[j] == ' ' || s[j] == '\t' || s[j] == '\n' || s[j] == '\r' || s[j] == '\v' || s[j] == '\f') {
		j++
	}
	start := j
	if j < len(s) && (s[j] == '+' || s[j] == '-') {
		j++
	}
	intDigits := 0
	for j < len(s) && s[j] >= '0' && s[j] <= '9' {
		j++
		intDigits++
	}
	fracDigits, isFloat := 0, false
	if j < len(s) && s[j] == '.' {
		k := j + 1
		for k < len(s) && s[k] >= '0' && s[k] <= '9' {
			k++
			fracDigits++
		}
		if intDigits > 0 || fracDigits > 0 {
			isFloat = true
			j = k
		}
	}
	if intDigits == 0 && fracDigits == 0 {
		return false, 0, 0, false // no number here at all
	}
	// An exponent only counts when it is well-formed; "1e" is the number 1 with junk after it.
	if j < len(s) && (s[j] == 'e' || s[j] == 'E') {
		k := j + 1
		if k < len(s) && (s[k] == '+' || s[k] == '-') {
			k++
		}
		expDigits := 0
		for k < len(s) && s[k] >= '0' && s[k] <= '9' {
			k++
			expDigits++
		}
		if expDigits > 0 {
			isFloat = true
			j = k
		}
	}
	lit := s[start:j]
	f, ferr := strconv.ParseFloat(lit, 64)
	if ferr != nil {
		return false, 0, 0, false
	}
	if !isFloat {
		if v, ierr := strconv.ParseInt(lit, 10, 64); ierr == nil {
			return true, v, f, true
		}
		return false, 0, f, true // integral but overflows int64 -> PHP treats it as a double
	}
	return false, 0, f, true
}

// dvalToLvalCap is zend_dval_to_lval_cap: truncate toward zero, saturating at the int64 bounds
// (measured: (int)"9999999999999999999" is 9223372036854775807), NaN to 0.
func dvalToLvalCap(f float64) int64 {
	switch {
	case math.IsNaN(f):
		return 0
	case f >= math.MaxInt64:
		return math.MaxInt64
	case f <= math.MinInt64:
		return math.MinInt64
	}
	return int64(f)
}

// phpIntval is PHP's (int) cast.
func phpIntval(v any) int64 {
	switch x := v.(type) {
	case nil:
		return 0
	case bool:
		if x {
			return 1
		}
		return 0
	case int:
		return int64(x)
	case int64:
		return x
	case float64:
		return dvalToLvalCap(x)
	case string:
		isInt, i, f, ok := numericPrefix(x)
		if !ok {
			return 0
		}
		if isInt {
			return i
		}
		return dvalToLvalCap(f)
	case []any, map[string]any, Obj, Arr:
		return 1 // PHP: (int) of a non-empty array is 1
	}
	return 0
}

// phpFloatval is PHP's (float) cast.
func phpFloatval(v any) float64 {
	switch x := v.(type) {
	case nil:
		return 0
	case bool:
		if x {
			return 1
		}
		return 0
	case int:
		return float64(x)
	case int64:
		return float64(x)
	case float64:
		return x
	case string:
		isInt, i, f, ok := numericPrefix(x)
		if !ok {
			return 0
		}
		if isInt {
			return float64(i)
		}
		return f
	case []any, map[string]any, Obj, Arr:
		return 1
	}
	return 0
}

// phpStrval is PHP's (string) cast. Note the double branch uses the `precision`=14 formatter, NOT
// json_encode's — (string)(0.1+0.2) is "0.3" while json_encode(0.1+0.2) is 0.30000000000000004.
func phpStrval(v any) string {
	switch x := v.(type) {
	case nil:
		return ""
	case bool:
		if x {
			return "1"
		}
		return ""
	case int:
		return strconv.Itoa(x)
	case int64:
		return strconv.FormatInt(x, 10)
	case float64:
		return phpStringDouble(x)
	case string:
		return x
	case []byte:
		return string(x)
	case []any, map[string]any, Obj, Arr:
		return "Array" // PHP emits a notice and the literal string "Array"
	}
	return fmt.Sprint(v)
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The PHP JSON encoder.
//
// Deliberately not encoding/json: Go escapes <, > and & by default and PHP does not; Go's float
// format differs (see phpGcvt); Go maps sort keys and PHP arrays keep insertion order; and Go
// silently replaces invalid UTF-8 where PHP fails the whole encode.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// errJSONMalformedUTF8 / errJSONInfNan are the two failures json_encode can hit here. Both make
// json_encode return false, which rest.php echoes as the empty string.
var (
	errJSONMalformedUTF8 = errors.New("Malformed UTF-8 characters, possibly incorrectly encoded")
	errJSONInfNan        = errors.New("Inf and NaN cannot be JSON encoded")
)

// phpJSONEncode mirrors json_encode($v, $flags). It returns an error exactly where json_encode
// would return false. Supported inputs are the ones the engine can produce: nil, bool, int64, int,
// float64, string, []byte (a BLOB, which PDO hands back as a PHP string), Obj, Arr, []string.
func phpJSONEncode(v any, flags int) ([]byte, error) {
	var b strings.Builder
	if err := encodeValue(&b, v, flags, 0); err != nil {
		return nil, err
	}
	return []byte(b.String()), nil
}

func encodeValue(b *strings.Builder, v any, flags, depth int) error {
	switch x := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		if x {
			b.WriteString("true")
		} else {
			b.WriteString("false")
		}
	case int:
		b.WriteString(strconv.Itoa(x))
	case int64:
		b.WriteString(strconv.FormatInt(x, 10))
	case float64:
		if math.IsNaN(x) || math.IsInf(x, 0) {
			return errJSONInfNan
		}
		b.WriteString(phpJSONDouble(x))
	case string:
		return encodeString(b, x, flags)
	case []byte:
		return encodeString(b, string(x), flags)
	case Obj:
		return encodeObj(b, x, flags, depth)
	case Arr:
		return encodeArr(b, x, flags, depth)
	case []string:
		a := make(Arr, len(x))
		for i := range x {
			a[i] = x[i]
		}
		return encodeArr(b, a, flags, depth)
	default:
		return fmt.Errorf("phpJSONEncode: unsupported type %T", v)
	}
	return nil
}

// indent writes JSON_PRETTY_PRINT's 4 spaces per level (measured against the repo's php).
func indent(b *strings.Builder, flags, depth int) {
	if flags&jsonPretty != 0 {
		b.WriteString(strings.Repeat("    ", depth))
	}
}

func encodeObj(b *strings.Builder, o Obj, flags, depth int) error {
	if len(o) == 0 {
		b.WriteString("{}") // an empty PHP array would be [], but the engine builds no empty Obj
		return nil
	}
	b.WriteByte('{')
	for i, f := range o {
		if i > 0 {
			b.WriteByte(',')
		}
		if flags&jsonPretty != 0 {
			b.WriteByte('\n')
		}
		indent(b, flags, depth+1)
		if err := encodeString(b, f.K, flags); err != nil {
			return err
		}
		b.WriteByte(':')
		if flags&jsonPretty != 0 {
			b.WriteByte(' ')
		}
		if err := encodeValue(b, f.V, flags, depth+1); err != nil {
			return err
		}
	}
	if flags&jsonPretty != 0 {
		b.WriteByte('\n')
		indent(b, flags, depth)
	}
	b.WriteByte('}')
	return nil
}

func encodeArr(b *strings.Builder, a Arr, flags, depth int) error {
	if len(a) == 0 {
		b.WriteString("[]")
		return nil
	}
	b.WriteByte('[')
	for i, v := range a {
		if i > 0 {
			b.WriteByte(',')
		}
		if flags&jsonPretty != 0 {
			b.WriteByte('\n')
		}
		indent(b, flags, depth+1)
		if err := encodeValue(b, v, flags, depth+1); err != nil {
			return err
		}
	}
	if flags&jsonPretty != 0 {
		b.WriteByte('\n')
		indent(b, flags, depth)
	}
	b.WriteByte(']')
	return nil
}

// encodeString mirrors PHP's json escaper for the flags rest.php uses. Measured behaviour it
// reproduces: \b \f \n \r \t use short forms; every other byte < 0x20 becomes \u00xx (lowercase
// hex); 0x7f (DEL) is NOT escaped; <, >, &, ' are NOT escaped (PHP only escapes those under
// JSON_HEX_*); every non-ASCII rune becomes \uXXXX, with a surrogate pair above the BMP; and '/'
// is escaped as "\/" UNLESS JSON_UNESCAPED_SLASHES is set.
func encodeString(b *strings.Builder, s string, flags int) error {
	if !utf8.ValidString(s) {
		return errJSONMalformedUTF8
	}
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString("\\\"")
		case '\\':
			b.WriteString("\\\\")
		case '/':
			if flags&jsonUnescapedSlashes != 0 {
				b.WriteByte('/')
			} else {
				b.WriteString("\\/")
			}
		case '\b':
			b.WriteString("\\b")
		case '\f':
			b.WriteString("\\f")
		case '\n':
			b.WriteString("\\n")
		case '\r':
			b.WriteString("\\r")
		case '\t':
			b.WriteString("\\t")
		default:
			switch {
			case r < 0x20:
				fmt.Fprintf(b, "\\u%04x", r)
			case r < 0x80:
				b.WriteByte(byte(r))
			case r > 0xFFFF:
				// outside the BMP: PHP emits a UTF-16 surrogate pair.
				r -= 0x10000
				fmt.Fprintf(b, "\\u%04x\\u%04x", 0xD800+(r>>10), 0xDC00+(r&0x3FF))
			default:
				fmt.Fprintf(b, "\\u%04x", r)
			}
		}
	}
	b.WriteByte('"')
	return nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The sqlite handle.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// DB is one congruency sqlite handle. It wraps exactly ONE sqlite connection, because rest.php runs
// `new PDO('sqlite:'.CONGRUENCY_SQLITE)` per request and PDO::lastInsertId() is a property of that
// one connection: pooling would let a write route report a rowid another request inserted.
type DB struct {
	db   *sql.DB
	conn *sql.Conn
	path string

	// TelemetryIngest models boot/monitor.php's congruency_telemetry_ingest, which rest.php calls
	// only `if (function_exists(...))`. nil means the function is not defined — the engine then
	// only emits telemetry.record's ack, exactly as PHP does with monitor.php absent. It never
	// returns an error because the PHP ingest swallows its own failures so a beacon cannot fatal a
	// page.
	TelemetryIngest func(kind, route, message, detail string)
}

// Open opens the db read/write, mirroring `new PDO('sqlite:'.$path)` — including PDO's habit of
// CREATING an empty db when $path does not exist.
func Open(path string) (*DB, error) { return open(path, path) }

// OpenImmutable opens the db read-only via sqlite's `immutable=1` URI flag: it promises the file
// will not change, so sqlite reads the committed data with no locking and creates NO sidecar files
// (a plain read-only open of a WAL db would spin up -wal/-shm). Use it to probe read routes with a
// guarantee of zero side effects. A write route against an immutable handle fails, by design.
func OpenImmutable(path string) (*DB, error) {
	if _, err := os.Stat(path); err != nil {
		return nil, fmt.Errorf("database not found: %s", path)
	}
	return open("file:"+path+"?immutable=1", path)
}

func open(dsn, path string) (*DB, error) {
	d, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	// One connection, for the lastInsertId reason above. MaxIdleConns matches so the pool never
	// closes and silently reopens it (which would reset last_insert_rowid mid-handle).
	d.SetMaxOpenConns(1)
	d.SetMaxIdleConns(1)
	d.SetConnMaxLifetime(0)
	conn, err := d.Conn(context.Background())
	if err != nil {
		d.Close()
		return nil, err
	}
	return &DB{db: d, conn: conn, path: path}, nil
}

// Close releases the handle.
func (d *DB) Close() error {
	if d.conn != nil {
		d.conn.Close()
	}
	return d.db.Close()
}

// Path is the file this handle opened.
func (d *DB) Path() string { return d.path }

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Routes.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// RouteDef is one `api_routes` row, as the engine needs it. Method/SQL/Auth/Params are TEXT columns
// and every one of them is nullable, hence the sql.NullString-free "" convention: a NULL column
// reads as "", which is exactly how PHP's (string) cast of NULL behaves at each of these sites.
type RouteDef struct {
	Name   string
	Method string
	SQL    string
	Auth   string
	Params string
}

// Authorizer is the pair of checks congruency_rest_route consults. Both live in the server layer
// (#225): LoggedIn is UserPrivilegeSet::logged_in(); Authorized is congruency_rest_authorized(),
// which today short-circuits to true on the CONGRUENCY_AUTH_OVERRIDE constant.
type Authorizer interface {
	LoggedIn() bool
	Authorized() bool
}

// DenyAll is the zero-trust Authorizer: no session, no key. It is the safe default for RunRoute's
// nil argument, so a caller that forgets to pass one gets 401s, not an open door.
type DenyAll struct{}

func (DenyAll) LoggedIn() bool   { return false }
func (DenyAll) Authorized() bool { return false }

// AllowAll mirrors the live deployment, where CONGRUENCY_AUTH_OVERRIDE makes
// congruency_rest_authorized() return true for everything. LoggedIn stays false because the
// override does NOT touch the admin-session check the engine uses for auth='admin' routes.
type AllowAll struct{}

func (AllowAll) LoggedIn() bool   { return false }
func (AllowAll) Authorized() bool { return true }

// HasRoutesTable mirrors the engine's first guard: a db with no `api_routes` table 404s.
func (d *DB) HasRoutesTable() (bool, error) {
	var name string
	err := d.conn.QueryRowContext(context.Background(),
		"SELECT name FROM sqlite_master WHERE type='table' AND name='api_routes'").Scan(&name)
	if errors.Is(err, sql.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

// LookupRoute reads one route row by name. It returns (nil, nil) when the route does not exist —
// the engine's "unknown route" 404.
func (d *DB) LookupRoute(name string) (*RouteDef, error) {
	var method, sqlText, auth, params sql.NullString
	err := d.conn.QueryRowContext(context.Background(),
		"SELECT method, sql, auth, params FROM api_routes WHERE name = ?", name).
		Scan(&method, &sqlText, &auth, &params)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &RouteDef{
		Name: name, Method: method.String, SQL: sqlText.String,
		Auth: auth.String, Params: params.String,
	}, nil
}

// RouteNames lists every route, ordered by name.
func (d *DB) RouteNames() ([]string, error) {
	rows, err := d.conn.QueryContext(context.Background(), "SELECT name FROM api_routes ORDER BY name")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var n string
		if err := rows.Scan(&n); err != nil {
			return nil, err
		}
		out = append(out, n)
	}
	return out, rows.Err()
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The engine.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// Reply is what rest.php would send: the HTTP status it sets, and the exact bytes it echoes
// (already including the trailing "\n").
type Reply struct {
	Status int
	Body   []byte
}

// phpLtrimSet is PHP's default ltrim character set. Note it contains \v (0x0B) but NOT \f (0x0C) —
// the engine's read/write test is stripos(ltrim($sql),'select')===0, so this set is load-bearing.
const phpLtrimSet = " \t\n\r\x00\x0B"

// isSelectSQL reproduces stripos(ltrim($sql), 'select') === 0. It is a case-insensitive PREFIX test,
// not a parse: "WITH x AS (SELECT 1) SELECT *" is NOT a select by this rule (and so is shaped as a
// write), while "selection" is. Faithful on purpose.
func isSelectSQL(s string) bool {
	t := strings.TrimLeft(s, phpLtrimSet)
	return len(t) >= 6 && strings.EqualFold(t[:6], "select")
}

// declaredParams parses a route's `params` column the way the engine does:
// json_decode(((string)$params) ?: '{}', true), then `if (!is_array($decl)) $decl = array();`.
// So an empty/NULL params, and any params that is not a JSON object/array, both yield no params.
// The declared TYPE is read through PHP's (string) cast, so a non-string type value still works.
func declaredParams(params string) map[string]string {
	out := map[string]string{}
	s := params
	if s == "" {
		s = "{}"
	}
	var raw map[string]any
	if err := jsonUnmarshalObject(s, &raw); err != nil {
		return out
	}
	for k, v := range raw {
		out[k] = phpStrval(v)
	}
	return out
}

// sqlParamNames returns the :placeholders the sql really has, lexing it once, left to right, so a
// ':name' inside a string literal, an identifier quote, or a comment is NOT mistaken for a
// parameter. (A regex over sql would find one; sqlite would not, and then the bind counts disagree.)
func sqlParamNames(s string) []string {
	var out []string
	seen := map[string]bool{}
	for i := 0; i < len(s); {
		c := s[i]
		switch {
		case c == '\'' || c == '"' || c == '`': // string literal / quoted identifier ('' escapes)
			q := c
			i++
			for i < len(s) {
				if s[i] == q {
					if i+1 < len(s) && s[i+1] == q {
						i += 2
						continue
					}
					i++
					break
				}
				i++
			}
		case c == '[': // sqlite's bracket-quoted identifier
			for i < len(s) && s[i] != ']' {
				i++
			}
			i++
		case c == '-' && i+1 < len(s) && s[i+1] == '-': // line comment
			for i < len(s) && s[i] != '\n' {
				i++
			}
		case c == '/' && i+1 < len(s) && s[i+1] == '*': // block comment
			i += 2
			for i+1 < len(s) && !(s[i] == '*' && s[i+1] == '/') {
				i++
			}
			i += 2
		case c == ':':
			j := i + 1
			for j < len(s) && (s[j] == '_' || (s[j] >= 'a' && s[j] <= 'z') ||
				(s[j] >= 'A' && s[j] <= 'Z') || (s[j] >= '0' && s[j] <= '9')) {
				j++
			}
			if j > i+1 {
				n := s[i+1 : j]
				if !seen[n] {
					seen[n] = true
					out = append(out, n)
				}
			}
			i = j
		default:
			i++
		}
	}
	return out
}

// bindText is the heart of the equivalence. rest.php binds with PDO's default PARAM_STR, so PDO
// stringifies the value and calls sqlite3_bind_text: EVERY non-null parameter reaches sqlite as
// TEXT, whatever the params declaration said (measured — see note 1 in the file header). nil stays
// SQL NULL. Returning `any` keeps the two cases in one place: a Go string binds text, a nil binds
// null, and nothing else is ever produced.
func bindText(v any) any {
	if v == nil {
		return nil
	}
	return phpStrval(v)
}

// castParam applies the engine's declared-type cast, then PDO's stringification.
//
//	if ($val !== null) { int -> (int); float|real -> (float); else -> (string) }
//	$st->bindValue(':'.$p, $val);          // PARAM_STR
//
// A null value skips the cast entirely and binds SQL NULL — which is how `LIMIT COALESCE(:n,-1)`
// turns an absent n into "no limit".
func castParam(v any, declType string) any {
	if v == nil {
		return nil
	}
	switch strings.ToLower(declType) {
	case "int":
		return bindText(phpIntval(v))
	case "float", "real":
		return bindText(phpFloatval(v))
	default:
		return bindText(phpStrval(v))
	}
}

// buildArgs decides what to bind, reproducing the engine's rule and staying compatible with
// database/sql's insistence that len(args) == the statement's parameter count.
//
// PHP:  foreach ($decl as $p => $t) { if (strpos($sql, ':'.$p) === false) continue; ... bind }
//
// Three cases fall out, and all three are PHP's:
//   - declared AND the sql mentions it  -> bind the cast value;
//   - the sql has a :placeholder that `params` does not declare -> PHP never binds it, so sqlite
//     leaves it NULL. Binding an explicit NULL here is the identical result and keeps the arg count
//     right (database/sql would otherwise refuse to run the statement at all);
//   - declared but the sql does not mention it -> skipped, never bound (e.g. telemetry.record
//     declares "message", whose sql has no :message).
//
// The leftover case is PHP's own bug surface: because `strpos` is a naive substring test, a param
// named "n" is considered "used" by a sql that only mentions ":note". PHP then binds a parameter
// sqlite does not have and PDO throws ("column index out of range"). No live route does this, and
// rather than invent a behaviour, this returns an error — the same outcome PHP has (a thrown
// error that dispatch turns into a 500), differing only in the message.
func buildArgs(sqlText string, decl map[string]string, input map[string]any) ([]any, error) {
	inSQL := sqlParamNames(sqlText)
	known := map[string]bool{}
	for _, n := range inSQL {
		known[n] = true
	}

	// PHP's naive test, over declared params in a stable order (Go map order is random; a
	// deterministic error message is worth the sort).
	declNames := make([]string, 0, len(decl))
	for k := range decl {
		declNames = append(declNames, k)
	}
	sort.Strings(declNames)

	bound := map[string]any{}
	for _, p := range declNames {
		if !strings.Contains(sqlText, ":"+p) {
			continue // the sql never mentions it
		}
		if !known[p] {
			return nil, fmt.Errorf("route sql has no parameter :%s, but params declares it and the "+
				"sql contains the substring \":%s\" (PDO raises \"column index out of range\" here)", p, p)
		}
		v := input[p] // a missing key yields nil, which is what array_key_exists() + null binding does
		bound[p] = castParam(v, decl[p])
	}

	args := make([]any, 0, len(inSQL))
	for _, n := range inSQL {
		args = append(args, sql.Named(n, bound[n])) // unbound -> nil -> SQL NULL, as PHP leaves it
	}
	return args, nil
}

// scanRows turns a result set into PHP's fetchAll(PDO::FETCH_ASSOC) shape: a list of ordered rows,
// column order preserved, duplicate column names collapsed with PHP array semantics.
func scanRows(rows *sql.Rows) (Arr, error) {
	cols, err := rows.Columns()
	if err != nil {
		return nil, err
	}
	out := Arr{}
	for rows.Next() {
		cells := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range cells {
			ptrs[i] = &cells[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			return nil, err
		}
		row := make(Obj, 0, len(cols))
		for i, c := range cols {
			v, err := phpValue(cells[i])
			if err != nil {
				return nil, err
			}
			row = row.Set(c, v)
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

// phpValue maps a driver value to the PHP value PDO would have produced. PDO_SQLite with
// ATTR_STRINGIFY_FETCHES=false (the PHP >= 8.1 default, measured false on this build) types each
// cell by its RUNTIME sqlite3_column_type: INTEGER -> int, FLOAT -> float, NULL -> null, TEXT and
// BLOB -> string. modernc's driver reports the same runtime types, so the mapping is 1:1. An
// unexpected type is an error rather than a guess — a silent coercion is how a port drifts.
func phpValue(v any) (any, error) {
	switch x := v.(type) {
	case nil:
		return nil, nil
	case int64:
		return x, nil
	case float64:
		return x, nil
	case string:
		return x, nil
	case []byte:
		return string(x), nil // a BLOB; PDO hands these back as PHP strings
	}
	return nil, fmt.Errorf("unexpected driver value %T (%v): PDO would not produce this; refusing to "+
		"guess a conversion", v, v)
}

// RunRoute is congruency_rest_route(). It returns the Reply rest.php would send, or an error for the
// case PHP throws (a sql that will not prepare or execute) — which dispatch (#225) renders as a 500.
//
// input is the map rest.php assembles before this point: $_GET, merged with the JSON body for
// POST/PUT/PATCH/DELETE. Values arrive as they do in PHP — strings from the query string, decoded
// JSON types from a body. az is nil-safe and denies by default.
//
// The order of operations below is the PHP's, exactly: routes-table guard, route lookup, method
// gate, auth gate, telemetry short-circuit, param binding, execute, shape.
func (d *DB) RunRoute(route, method string, input map[string]any, az Authorizer) (Reply, error) {
	if az == nil {
		az = DenyAll{}
	}
	if input == nil {
		input = map[string]any{}
	}

	ok, err := d.HasRoutesTable()
	if err != nil {
		return Reply{}, err
	}
	if !ok {
		return errReply(404, Obj{{"error", "no api_routes table"}}), nil
	}

	def, err := d.LookupRoute(route)
	if err != nil {
		return Reply{}, err
	}
	if def == nil {
		return errReply(404, Obj{{"error", "unknown route"}, {"route", route}}), nil
	}

	// method: strtoupper((string)$def['method'] ?: 'GET'), split on ',', each trimmed.
	m := strings.ToUpper(def.Method)
	if m == "" {
		m = "GET"
	}
	allowed := strings.Split(m, ",")
	for i := range allowed {
		allowed[i] = strings.Trim(allowed[i], phpTrimSet)
	}
	if !contains(allowed, method) {
		return errReply(405, Obj{{"error", "method not allowed"}, {"route", route}, {"allowed", allowed}}), nil
	}

	// auth: strtolower(trim((string)($def['auth'] ?? 'public'))). Only "admin" and "token" gate.
	auth := strings.ToLower(strings.Trim(def.Auth, phpTrimSet))
	if auth == "admin" && !az.LoggedIn() {
		return errReply(401, Obj{{"error", "admin login required"}, {"route", route}}), nil
	}
	if auth == "token" && !az.Authorized() {
		return errReply(401, Obj{{"error", "API key or admin login required"}, {"route", route}}), nil
	}

	// telemetry.record short-circuits BEFORE any binding: its kind (error|pageview|event) needs a
	// branch a single sql row cannot make. See note 10 in the file header.
	if route == "telemetry.record" {
		return d.telemetryRecord(input), nil
	}

	decl := declaredParams(def.Params)
	args, err := buildArgs(def.SQL, decl, input)
	if err != nil {
		return Reply{}, err
	}

	ctx := context.Background()
	if isSelectSQL(def.SQL) {
		rows, err := d.conn.QueryContext(ctx, def.SQL, args...)
		if err != nil {
			return Reply{}, err
		}
		defer rows.Close()
		data, err := scanRows(rows)
		if err != nil {
			return Reply{}, err
		}
		return okReply(Obj{{"route", route}, {"rows", data}}), nil
	}

	res, err := d.conn.ExecContext(ctx, def.SQL, args...)
	if err != nil {
		return Reply{}, err
	}
	affected, err := res.RowsAffected() // PDOStatement::rowCount() == sqlite3_changes()
	if err != nil {
		return Reply{}, err
	}
	// PDO::lastInsertId() is the CONNECTION's last insert rowid, as a STRING — "0" when this
	// connection has inserted nothing, which is what an UPDATE/DELETE route reports.
	rowid, err := d.lastInsertID()
	if err != nil {
		return Reply{}, err
	}
	return okReply(Obj{{"route", route}, {"affected", affected}, {"rowid", rowid}}), nil
}

// lastInsertID reads sqlite3_last_insert_rowid() for THIS handle's one connection and renders it as
// PDO does: a decimal string.
func (d *DB) lastInsertID() (string, error) {
	var id int64
	if err := d.conn.QueryRowContext(context.Background(), "SELECT last_insert_rowid()").Scan(&id); err != nil {
		return "", err
	}
	return strconv.FormatInt(id, 10), nil
}

// telemetryRecord is congruency_telemetry_record(): read the four fields the engine already merged
// into the input, hand them to the ingest hook if it exists, and ack. It never fails.
func (d *DB) telemetryRecord(input map[string]any) Reply {
	get := func(k, dflt string) string {
		if v, ok := input[k]; ok {
			return phpStrval(v) // PHP: isset($input[k]) ? (string)$input[k] : $dflt
		}
		return dflt
	}
	kind := get("kind", "pageview")
	if d.TelemetryIngest != nil {
		d.TelemetryIngest(kind, get("route", ""), get("message", ""), get("detail", ""))
	}
	return okReply(Obj{{"route", "telemetry.record"}, {"ok", true}, {"kind", kind}})
}

// phpTrimSet is PHP's default trim set (used for the method/auth normalisation, where PHP calls
// trim()). It is ltrim's set — \v included, \f not.
const phpTrimSet = phpLtrimSet

func contains(hay []string, needle string) bool {
	for _, h := range hay {
		if h == needle { // PHP's in_array(..., true): strict, so case matters
			return true
		}
	}
	return false
}

// okReply encodes a success body: JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES, status 200.
// When json_encode fails (invalid UTF-8 in a row, or an INF/NAN), PHP echoes false — the empty
// string — and still sends 200, so the body is a lone "\n". Reproduced, not "fixed".
func okReply(o Obj) Reply {
	b, err := phpJSONEncode(o, jsonPretty|jsonUnescapedSlashes)
	if err != nil {
		return Reply{Status: 200, Body: []byte("\n")}
	}
	return Reply{Status: 200, Body: append(b, '\n')}
}

// errReply encodes one of the engine's own error bodies. These are COMPACT — rest.php passes no
// flags at those call sites — so slashes are escaped here and there is no pretty indent.
func errReply(status int, o Obj) Reply {
	b, err := phpJSONEncode(o, 0)
	if err != nil {
		return Reply{Status: status, Body: []byte("\n")}
	}
	return Reply{Status: status, Body: append(b, '\n')}
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Reading JSON — the `params` column, and the CLI's -input.
//
// encoding/json is fine for READING (only its ENCODER had to be replaced — see the encoder section).
// The one thing it gets wrong for our purposes is numbers: encoding/json makes every JSON number a
// float64, while PHP's json_decode makes an INTEGRAL number an int and only a fractional/exponent
// one a float. That difference is visible downstream — (string) of PHP int 100000000000000000000
// is "100000000000000000000", but of the float64 it is "1.0E+20" — so numbers are converted here
// the way PHP does, via json.Number.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// jsonUnmarshalObject decodes a JSON object into PHP-equivalent Go values, as
// json_decode($s, true) would. A non-object (a list, a scalar, malformed input) is an error; the
// engine's own call site treats that as "no params", which is `if (!is_array($decl))` in the PHP.
func jsonUnmarshalObject(s string, out *map[string]any) error {
	dec := json.NewDecoder(strings.NewReader(s))
	dec.UseNumber()
	var v any
	if err := dec.Decode(&v); err != nil {
		return err
	}
	m, ok := v.(map[string]any)
	if !ok {
		return fmt.Errorf("expected a JSON object, got %T", v)
	}
	*out = phpDecodeValue(m).(map[string]any)
	return nil
}

// phpDecodeValue walks a decoded tree and converts json.Number the way PHP's json_decode does:
// integral -> int64, anything else -> float64.
func phpDecodeValue(v any) any {
	switch x := v.(type) {
	case map[string]any:
		for k, e := range x {
			x[k] = phpDecodeValue(e)
		}
		return x
	case []any:
		for i, e := range x {
			x[i] = phpDecodeValue(e)
		}
		return x
	case json.Number:
		s := x.String()
		if !strings.ContainsAny(s, ".eE") {
			if i, err := strconv.ParseInt(s, 10, 64); err == nil {
				return i
			}
		}
		f, err := strconv.ParseFloat(s, 64)
		if err != nil {
			return s
		}
		return f
	}
	return v
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The CLI: the layer's own harness, so this file can be run and diffed on its own.
//
// It prints to STDOUT exactly the bytes rest.php echoes, and the HTTP status to STDERR, so that a
// diff of stdout against the PHP is a diff of the contract:
//
//	diff <(go run . -db DB -route agent.roster -input '{"n":2}') <(php <the php side> ...)
// ─────────────────────────────────────────────────────────────────────────────────────────────────

func main() {
	var (
		dbPath    = flag.String("db", os.Getenv("CONGRUENCY_SQLITE"), "path to congruency.sqlite (default $CONGRUENCY_SQLITE)")
		route     = flag.String("route", "", "the api_routes name to run")
		method    = flag.String("method", "GET", "the HTTP method to present")
		inputJSON = flag.String("input", "", "the request input as a JSON object (rest.php's $_GET merged with the body)")
		list      = flag.Bool("routes", false, "list every route name and exit")
		selftest  = flag.Bool("selftest", false, "run the built-in PHP-equivalence checks and exit (needs no db)")
		immutable = flag.Bool("immutable", false, "open the db read-only with immutable=1: no writes, no sidecar files (read routes only)")
		authed    = flag.Bool("authorized", false, "present an authorized caller, as CONGRUENCY_AUTH_OVERRIDE does live (default: deny)")
	)
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "db.go — the congruency-go database layer (#224): pure-Go sqlite + the api_routes engine.\n\n"+
			"Prints the exact bytes rest.php would echo to stdout; the HTTP status to stderr.\n\n"+
			"usage:\n  %s -db <congruency.sqlite> -route <name> [-method GET] [-input '<json>']\n"+
			"  %s -db <congruency.sqlite> -routes\n  %s -selftest\n\nflags:\n", os.Args[0], os.Args[0], os.Args[0])
		flag.PrintDefaults()
	}
	flag.Parse()

	if *selftest {
		os.Exit(runSelftest())
	}
	if *dbPath == "" {
		die("no database: pass -db <path to congruency.sqlite> or set $CONGRUENCY_SQLITE")
	}
	if !*list && *route == "" {
		die("nothing to do: pass -route <name>, or -routes to list them, or -selftest")
	}

	opener := Open
	if *immutable {
		opener = OpenImmutable
	}
	d, err := opener(*dbPath)
	if err != nil {
		die(fmt.Sprintf("cannot open %s: %v", *dbPath, err))
	}
	defer d.Close()

	if *list {
		names, err := d.RouteNames()
		if err != nil {
			die(fmt.Sprintf("cannot list routes: %v", err))
		}
		for _, n := range names {
			fmt.Println(n)
		}
		return
	}

	input := map[string]any{}
	if *inputJSON != "" {
		if err := jsonUnmarshalObject(*inputJSON, &input); err != nil {
			die(fmt.Sprintf("-input must be a JSON object: %v", err))
		}
	}

	var az Authorizer = DenyAll{}
	if *authed {
		az = AllowAll{}
	}
	reply, err := d.RunRoute(*route, strings.ToUpper(*method), input, az)
	if err != nil {
		// The PDOException path: rest.php lets it reach dispatch, which answers 500 {"error": msg}.
		// The shape is reproduced; the message is Go's, and cannot be PDO's (see the file header).
		body, _ := phpJSONEncode(Obj{{"error", err.Error()}}, jsonPretty|jsonUnescapedSlashes)
		fmt.Fprintln(os.Stderr, "HTTP 500")
		os.Stdout.Write(append(body, '\n'))
		os.Exit(1)
	}
	fmt.Fprintf(os.Stderr, "HTTP %d\n", reply.Status)
	os.Stdout.Write(reply.Body)
}

func die(msg string) {
	fmt.Fprintf(os.Stderr, "db: %s\n", msg) // a one-line message, never a panic trace
	os.Exit(2)
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// -selftest — the PHP-equivalence checks that need no db.
//
// Every EXPECTATION below is a value MEASURED from the repo's own php this session
// (tooling/congruencey-harness/php/php, PHP 8.4.23), not a value inferred from documentation. They
// pin the conversions that a Go port gets wrong by default: float formatting, string escaping, the
// (int)/(string) casts, and the pretty/compact encoder shapes. Reproduce any line with:
//
//	tooling/congruencey-harness/php/php -r 'echo json_encode(1e100);'                  # => 1.0e+100
//	tooling/congruencey-harness/php/php -r 'echo json_encode(1.0e-5);'                 # => 1.0e-5
//	tooling/congruencey-harness/php/php -r 'var_dump((string)(0.1+0.2));'              # => "0.3"
//	tooling/congruencey-harness/php/php -r 'echo json_encode("a/b\u{e9}");'            # => "a\/bé"
// ─────────────────────────────────────────────────────────────────────────────────────────────────

func runSelftest() int {
	fails := 0
	check := func(what, got, want string) {
		if got != want {
			fails++
			fmt.Printf("FAIL %-34s got %-28q want %q\n", what, got, want)
		}
	}

	// json_encode of a double: serialize_precision=-1, threshold 17, lowercase 'e', forced ".0"
	// mantissa in exponential form, unpadded exponent. The lines Go's encoding/json would fail are
	// marked; they are why phpGcvt exists.
	//
	// f01f02 is the runtime double 0.1+0.2 (0x3fd3333333333334, prints "0.30000000000000004"), the
	// famous value PHP's json_encode(0.1+0.2) emits. It MUST be computed from float64 VARIABLES: the
	// constant expression `0.1 + 0.2` is folded by Go at arbitrary precision to the *different* double
	// nearest 0.3 (0x3fd3333333333333, prints "0.3"), which would silently test the wrong number.
	f01, f02 := 0.1, 0.2
	f01f02 := f01 + f02
	for _, c := range []struct {
		in   float64
		want string
	}{
		{0, "0"}, {math.Copysign(0, -1), "-0"}, {1, "1"}, {-1, "-1"}, {0.5, "0.5"},
		{100, "100"}, {1e15, "1000000000000000"}, {1e16, "10000000000000000"},
		{1e17, "1.0e+17"}, // Go's encoding/json: 1e+17
		{1e18, "1.0e+18"}, {1e20, "1.0e+20"}, {1e21, "1.0e+21"}, {1e22, "1.0e+22"},
		{1e-3, "0.001"}, {1e-4, "0.0001"},
		{1e-5, "1.0e-5"}, // Go's encoding/json: 0.00001
		{1e-6, "1.0e-6"}, {1e-7, "1.0e-7"}, {1.5e-7, "1.5e-7"},
		{123.456, "123.456"},
		{1e100, "1.0e+100"}, // Go's encoding/json: 1e+100
		{1e-100, "1.0e-100"},
		{1.0 / 3.0, "0.3333333333333333"}, {2.0 / 3.0, "0.6666666666666666"},
		{0.1, "0.1"}, {0.2, "0.2"}, {f01f02, "0.30000000000000004"},
		{1e6, "1000000"}, {1e7, "10000000"},
		{12345678901234567890.0, "1.2345678901234567e+19"},
		{9007199254740993.0, "9007199254740992"},
		{1.7976931348623157e308, "1.7976931348623157e+308"},
		{5e-324, "5.0e-324"}, {1e-320, "1.0e-320"},
		{1784103352.0, "1784103352"}, // a real ticket_events.ts value: REAL, whole, prints fixed
	} {
		check(fmt.Sprintf("json_encode(%g)", c.in), phpJSONDouble(c.in), c.want)
	}

	// (string)$double: the `precision`=14 formatter, uppercase 'E' — a DIFFERENT function.
	for _, c := range []struct {
		in   float64
		want string
	}{
		{5, "5"}, {1.5, "1.5"}, {0.1, "0.1"}, {0.1 + 0.2, "0.3"}, {1.0, "1"},
		{1e100, "1.0E+100"}, {1e-7, "1.0E-7"}, {1.0 / 3.0, "0.33333333333333"},
		{math.Copysign(0, -1), "-0"}, {1e15, "1.0E+15"}, {1e16, "1.0E+16"},
		{1e17, "1.0E+17"}, {1e21, "1.0E+21"}, {100.0, "100"}, {2.5, "2.5"},
	} {
		check(fmt.Sprintf("(string)%g", c.in), phpStringDouble(c.in), c.want)
	}

	// (int) casts of strings — PHP's leading-numeric-prefix rule, with int64 saturation.
	for _, c := range []struct {
		in   string
		want int64
	}{
		{"5", 5}, {"5.9", 5}, {"abc", 0}, {"", 0}, {"0x1A", 0}, {"12abc", 12},
		{" 7 ", 7}, {"1e3", 1000}, {"-3", -3}, {"9999999999999999999", math.MaxInt64},
	} {
		check(fmt.Sprintf("(int)%q", c.in), strconv.FormatInt(phpIntval(c.in), 10), strconv.FormatInt(c.want, 10))
	}
	// (float) casts of strings.
	for _, c := range []struct {
		in   string
		want float64
	}{{"1.5", 1.5}, {"abc", 0}, {"1e3", 1000}, {" 2.5x", 2.5}} {
		check(fmt.Sprintf("(float)%q", c.in), phpJSONDouble(phpFloatval(c.in)), phpJSONDouble(c.want))
	}

	// String escaping, both flag shapes. Measured: '/' escaped without JSON_UNESCAPED_SLASHES;
	// <, >, &, ' never escaped; 0x7f never escaped; non-ASCII always \uXXXX, surrogate-paired.
	enc := func(v any, flags int) string {
		b, err := phpJSONEncode(v, flags)
		if err != nil {
			return "ERR:" + err.Error()
		}
		return string(b)
	}
	check("slashes escaped (flags 0)", enc("a/b", 0), `"a\/b"`)
	check("slashes kept (UNESCAPED)", enc("a/b", jsonUnescapedSlashes), `"a/b"`)
	// Non-ASCII is ALWAYS \uXXXX (no JSON_UNESCAPED_UNICODE), above the BMP as a surrogate
	// pair; <, >, & and ' stay literal; DEL (0x7f) stays literal. Each want below is a RAW Go
	// literal, so what you read here is the exact byte sequence the repo's php printed.
	check("unicode + specials", enc("caf\u00e9 / \U0001F600 \t\"q\" \\ <>&", jsonUnescapedSlashes),
		`"caf\u00e9 / \ud83d\ude00 \t\"q\" \\ <>&"`)
	check("ctrl chars", enc("\x00\x01\x08\x09\x0a\x0b\x0c\x0d\x1f", 0),
		`"\u0000\u0001\b\t\n\u000b\f\r\u001f"`)
	check("DEL not escaped", enc("\x7f", 0), "\"\x7f\"")
	check("u2028/u2029", enc("\u2028\u2029", 0), `"\u2028\u2029"`)

	// The two envelope shapes, exactly as rest.php emits them.
	check("pretty envelope", enc(Obj{{"route", "x"}, {"rows", Arr{}}}, jsonPretty|jsonUnescapedSlashes),
		"{\n    \"route\": \"x\",\n    \"rows\": []\n}")
	check("pretty nested row", enc(Obj{{"route", "x"}, {"rows", Arr{Obj{{"i", int64(42)}, {"n", nil}}}}},
		jsonPretty|jsonUnescapedSlashes),
		"{\n    \"route\": \"x\",\n    \"rows\": [\n        {\n            \"i\": 42,\n            \"n\": null\n        }\n    ]\n}")
	check("compact error envelope", enc(Obj{{"error", "unknown route"}, {"route", "a/b"}}, 0),
		`{"error":"unknown route","route":"a\/b"}`)
	check("compact 405 envelope", enc(Obj{{"error", "method not allowed"}, {"route", "agent.roster"},
		{"allowed", []string{"GET"}}}, 0),
		`{"error":"method not allowed","route":"agent.roster","allowed":["GET"]}`)

	// json_encode fails on invalid UTF-8 and on INF/NAN; rest.php then echoes a lone "\n".
	if _, err := phpJSONEncode("\xff\xfe", 0); err == nil {
		fails++
		fmt.Println("FAIL invalid utf-8 should fail the encode")
	}
	if _, err := phpJSONEncode(math.Inf(1), 0); err == nil {
		fails++
		fmt.Println("FAIL INF should fail the encode")
	}
	if r := okReply(Obj{{"route", "x"}, {"rows", Arr{Obj{{"b", "\xff"}}}}}); string(r.Body) != "\n" || r.Status != 200 {
		fails++
		fmt.Printf("FAIL invalid-utf8 reply: got %q/%d want \"\\n\"/200\n", r.Body, r.Status)
	}

	// PHP array semantics: a repeated key keeps its position, takes the last value.
	check("duplicate column collapse", enc(Obj{}.Set("id", int64(10)).Set("id", int64(20)).Set("other", int64(30)), 0),
		`{"id":20,"other":30}`)

	// The read/write prefix test, quirks included.
	for _, c := range []struct {
		in   string
		want bool
	}{
		{"  SELECT 1", true}, {"\n\t select 1", true}, {"WITH x AS (SELECT 1) SELECT * FROM x", false},
		{"INSERT INTO t VALUES(1,2)", false}, {"selection", true}, {"", false},
	} {
		check(fmt.Sprintf("isSelect(%q)", c.in), fmt.Sprint(isSelectSQL(c.in)), fmt.Sprint(c.want))
	}

	// Every bound value is TEXT; only NULL stays NULL.
	if got := castParam("7", "int"); got != "7" {
		fails++
		fmt.Printf("FAIL castParam int should bind TEXT \"7\", got %#v\n", got)
	}
	if got := castParam(nil, "int"); got != nil {
		fails++
		fmt.Printf("FAIL castParam nil should bind NULL, got %#v\n", got)
	}
	if got := castParam("abc", "int"); got != "0" {
		fails++
		fmt.Printf("FAIL castParam (int)\"abc\" should bind TEXT \"0\", got %#v\n", got)
	}

	// The sql lexer must not see a parameter inside a literal or a comment.
	check("sqlParamNames", fmt.Sprint(sqlParamNames(
		"SELECT ':notaparam', x /* :nope */ FROM t WHERE a=:real -- :alsonope\n AND b=:real AND c=:two")),
		"[real two]")

	if fails == 0 {
		fmt.Println("selftest: OK — all PHP-equivalence checks pass")
		return 0
	}
	fmt.Printf("selftest: %d FAILURE(S)\n", fails)
	return 1
}
