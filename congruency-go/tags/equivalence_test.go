package tags

// equivalence_test.go — ticket #282: the TAG-equivalence harness.
//
// It is the tag analogue of congruency-go/equivalence_test.go (#227, the route sweep), and it
// answers one question, per tag: does this package's Go port of tag T emit the EXACT bytes the
// live PHP emits for `?page=tags&tag=T`?
//
// #226 landed 10 tags "ported-not-measured" — the port was written against the PHP source, but no
// byte-diff was ever run, because this worktree has no php binary and no state db (both
// gitignored). Every tag unit from #246 on otherwise re-hits that same wall. This file is the way
// through it: it does NOT port a tag, it MEASURES one, against the real PHP process that is
// already running and the real database that PHP is already reading.
//
// Run it:
//
//	cd congruency-go && go test ./tags/ -run TestTagEquivalence -v
//
// It skips cleanly — never fails — when the server, the db, the app root or the API key is
// absent, so it is safe in CI where none of them exist. See "The four guards" below.
//
// ── THE TWO SIDES ────────────────────────────────────────────────────────────────────────────────
//
// GO side: tags.RenderTag(cfg, T, $_GET) — the same entry server.go's handleTagsPage calls to
// answer ?page=tags&tag=T (#280, server.go:801). It renders the tag standalone (`new $sel(null)`,
// the shape TagList.php:67-68 uses) and returns THE TAG'S OWN BYTES — no gallery, no page chrome.
//
// PHP side: an HTTP GET of http://127.0.0.1:8899/?page=tags&tag=T. This returns a FULL PAGE:
// chrome and the gallery first, then the tag's bytes, then a fixed close-and-tail. Measured this
// session, BugCatalog's own 626 bytes arrived inside a 7,167-byte page — so the tag is under 9% of
// what the URL returns, and comparing RenderTag's output to the whole page would differ for every
// tag, always, for a reason that has nothing to do with the port. The tag's bytes are a SLICE of
// that page, and the slice has to be cut exactly. That is what this harness is.
//
// ── CUTTING THE SLICE: the anchors are TagList.php's own bytes ───────────────────────────────────
//
// The page is assembled as CHROME + gallery + <the tag> + TAIL. The two cuts are not guesses;
// each is a string literal read off the live PHP that emits it — invocators/tags/dev/TagList.php:
//
//	if ($sel !== '' && in_array($sel, $names, true)) {                                        // :61
//	    $out .= "<div class='tagout'><h3>&lt;&lt;&lt;" . self::esc($sel) . "&gt;&gt;&gt;</h3>\n";  // :62
//	        ... $out .= (string)$obj->get_document();                                         // :68
//	    $out .= "</div>\n";                                                                   // :76
//
// So the tag's bytes begin immediately after the :62 heading and end immediately before the :76
// close. tagOutOpen below builds the :62 anchor with esc() — THIS package's esc, the port of
// htmlspecialchars($s, ENT_QUOTES) — because that is the identical call TagList.php:62 makes on
// the identical value, so the two strings cannot drift apart. Verified this session: the anchor
// occurs EXACTLY ONCE in each of the 10 registered tags' pages.
//
// The trailing cut cannot count "</div>" tokens: a tag's own body emits divs (TicketList's
// expansion rows do), so a nesting scan would need an HTML parser and would be wrong the first
// time a div appeared inside a <script> or a CSS string. Instead the cut is anchored to the END of
// the page, where the byte count is exact: everything after the :76 close is the document
// template's TAIL, which is the same bytes for every T (the template is the one Documents row
// keyed 'tags'; only TagList's output varies). So:
//
//	body = page[end-of-:62-anchor : len(page) - len("</div>\n"+TAIL)]
//
// ── DERIVING THE TAIL INSTEAD OF HARDCODING IT ──────────────────────────────────────────────────
//
// TAIL is measured at run time, from the live server, by pageTail() — never hardcoded, so a change
// to the page template cannot silently corrupt every slice. The probe uses TagList.php's OTHER
// branch, :77-78:
//
//	} elseif ($sel !== '') {                                                              // :77
//	    $out .= "<p style='color:#b00020'>Unknown tag: " . self::esc($sel) . "</p>";      // :78
//
// Fetching ?page=tags&tag=<a name no tag file has> takes that branch, and it emits NO trailing
// newline and NOTHING after it — so every byte following that marker is exactly TAIL. The probe
// name is asserted absent from Scan() first, so the branch is guaranteed. (Measured this session:
// TAIL = "\n</body>\n</html>\n", 17 bytes.) Each fetched page is then REQUIRED to end with
// "</div>\n"+TAIL before any slice is cut — a page that does not is reported, not silently
// mis-sliced.
//
// ── TagList IS COMPARED ON A DIFFERENT PATH, AND WHY ─────────────────────────────────────────────
//
// One tag cannot be compared through RenderTag, and pretending otherwise would report a DIFFER
// that is an artifact of the harness rather than a fact about the port.
//
// TagList is the gallery ITSELF. It carries a re-entrancy guard — `private static $rendering`
// (TagList.php:18, 40-43), ported as Engine.tagListRendering (engine.go:876, 1512-1516) — so that
// selecting the gallery inside the gallery does not recurse forever. On the PHP page, TagList is
// ALREADY rendering when it reaches :67-68 and constructs the selected tag; so when the selected
// tag IS TagList, the nested get_document() sees $rendering === true and returns just the notice
// "<em>(the tag gallery is rendered by TagList; it is not re-rendered inside itself)</em>"
// (TagList.php:40-41). That notice is what the page's slice contains — measured this session, it
// is exactly the 86 bytes ?page=tags&tag=TagList carries between the two anchors.
//
// tags.RenderTag(cfg, "TagList", ...) builds a FRESH engine, so tagListRendering is false and the
// gallery renders in full (engine.go:1509-1550). Both behaviors are correct; they are simply not
// the same call. So for TagList — and ONLY TagList — the Go side renders the gallery and this
// harness cuts the nested slice out of it with the SAME anchors it uses on the PHP page, which
// reproduces PHP's call path exactly (same guard state, same whitelist, same framing). goTagBody
// does this and returns a note saying so; the report prints the note. For all 44 other tags the
// guard is untouched and RenderTag is the direct, unmediated comparison.
//
// ── CONCURRENCY: the stability sandwich (reused from #227) ───────────────────────────────────────
//
// The state db has live writers — the concurrent pair_loop agents — so a tag's rows can change
// between the Go read and the PHP read, and a naive diff would report a data change as an engine
// bug. Each tag is fetched from PHP TWICE, bracketing the Go render (php1, go, php2). If the two
// PHP slices differ, the db moved inside the window: the tag is reported VOLATILE and skipped for
// this run rather than false-failed. This is #227's pattern (equivalence_test.go:226-240) applied
// to the tag slice instead of the route body.
//
// ── COVERAGE: 45 scanned, 10 registered, 35 skipped-not-failed ───────────────────────────────────
//
// The sweep iterates Scan(TagsDir) — the same filesystem walk the PHP gallery does
// (TagList.php:22-37), which lists 45 tags in this checkout. A tag with no Go port is t.Skip'd,
// never failed: the ticket is explicit that not-yet-ported is "skipped, not failed", and those 35
// skips are precisely the queue #246+ works through. As each unit registers its tag, that tag
// stops skipping and starts being measured here, with no edit to this file.
//
// ── THE FOUR GUARDS (why this never false-fails in CI) ───────────────────────────────────────────
//
//	no API key      -> skip   (no ../.secrets/ats.env and no $CONGRUENCY_API_KEY)
//	server down     -> skip   (the reachability probe fails)
//	no state db     -> skip   (the file the two engines must SHARE is absent)
//	no app root     -> skip   (TAGS_DIR is absent, so there is nothing to scan)
//
// ── SIDE EFFECTS ────────────────────────────────────────────────────────────────────────────────
//
// This harness only reads: the Go engine opens the db `mode=ro` (Config.Immutable left false,
// engine.go:317-320) and the PHP side is plain HTTP GETs. mode=ro is the deliberate choice over
// immutable=1: immutable=1 reads STALE data under concurrent writers, which would manufacture the
// very false diffs the sandwich exists to remove, whereas mode=ro reads what PHP reads. The usual
// cost of mode=ro on a WAL database is -wal/-shm sidecars; it does not arise here, because the
// live state db is journal_mode=delete, not WAL (probed this session; server.go:756-759 records
// the same measurement). No file is written, and no ?page= request mutates state.

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"testing"
	"time"
)

const (
	// defaultPageURL is the PAGE surface of the live PHP app. #227 points at the same origin's
	// rest.php for routes; tags are a page, not a route (?page=tags is a DOCUMENT lookup whose
	// stored template holds <<<TagList>>> — engine.go:4113-4122), so this is the app root itself.
	defaultPageURL = "http://127.0.0.1:8899/"

	// secretsEnvFile holds CONGRUENCY_API_KEY=... — the same file #227 reads
	// (equivalence_test.go:55).
	secretsEnvFile = "/Users/stevenpeterson/code/installed/jazz-project/.secrets/ats.env"

	// serverStateDB is CONGRUENCY_SQLITE as the RUNNING server resolves it
	// (boot/configure.php:42, <app>/../state/congruency.sqlite). Both engines must read this one
	// file or a diff measures data, not code.
	serverStateDB = "/Users/stevenpeterson/code/installed/jazz-project/congruency/checkouts/current/state/congruency.sqlite"

	// serverAppRoot is ABS_PATH (boot/configure.php:41) for that same server — the tree whose
	// invocators/tags/ is TAGS_DIR, which Scan walks.
	serverAppRoot = "/Users/stevenpeterson/code/installed/jazz-project/congruency/checkouts/current/congruency"

	// probeTagName takes TagList.php:77-78's "Unknown tag" branch so pageTail can measure the
	// document template's tail. Asserted absent from Scan() before it is trusted.
	probeTagName = "ZZNoSuchTagProbe282"
)

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Environment resolution. Every input is overridable, and every absence is a skip.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// apiKey is $CONGRUENCY_API_KEY, else the CONGRUENCY_API_KEY= line of ../.secrets/ats.env.
// Mirrors #227's apiKey (equivalence_test.go:105-122).
func apiKey() string {
	if k := os.Getenv("CONGRUENCY_API_KEY"); k != "" {
		return k
	}
	b, err := os.ReadFile(secretsEnvFile)
	if err != nil {
		return ""
	}
	for _, line := range strings.Split(string(b), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "CONGRUENCY_API_KEY=") {
			return strings.TrimSpace(strings.TrimPrefix(line, "CONGRUENCY_API_KEY="))
		}
	}
	return ""
}

// pageURL is the live app's page surface; $CONGRUENCY_TAGS_URL overrides it.
func pageURL() string {
	if u := os.Getenv("CONGRUENCY_TAGS_URL"); u != "" {
		return u
	}
	return defaultPageURL
}

// equivDBPath is the db BOTH engines must read; $CONGRUENCY_EQUIV_DB overrides it (the same knob
// #227 uses, equivalence_test.go:93).
func equivDBPath() string {
	if p := os.Getenv("CONGRUENCY_EQUIV_DB"); p != "" {
		return p
	}
	return serverStateDB
}

// equivAppRoot is ABS_PATH; $CONGRUENCY_APP_ROOT overrides it.
func equivAppRoot() string {
	if p := os.Getenv("CONGRUENCY_APP_ROOT"); p != "" {
		return p
	}
	return serverAppRoot
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The PHP side.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// phpPage GETs ?page=tags[&tag=<tag>] from the live server. An empty tag omits the parameter
// entirely, which is NOT the same as tag= (TagList.php:46 reads isset($_GET['tag'])).
func phpPage(client *http.Client, base, key, tag string) (int, []byte, error) {
	q := url.Values{"page": {"tags"}}
	if tag != "" {
		q.Set("tag", tag)
	}
	req, err := http.NewRequest("GET", strings.TrimSuffix(base, "/")+"/?"+q.Encode(), nil)
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("X-Api-Key", key)
	resp, err := client.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	return resp.StatusCode, body, err
}

// tagOutOpen is TagList.php:62 verbatim — the heading that immediately precedes the tag's bytes:
//
//	"<div class='tagout'><h3>&lt;&lt;&lt;" . self::esc($sel) . "&gt;&gt;&gt;</h3>\n"
//
// It is built with esc(), this package's port of that exact htmlspecialchars call, so the anchor
// this harness looks for is generated by the same rule that generated the bytes it looks in.
func tagOutOpen(tag string) string {
	return "<div class='tagout'><h3>&lt;&lt;&lt;" + esc(tag) + "&gt;&gt;&gt;</h3>\n"
}

// tagOutClose is TagList.php:76 verbatim — the close that immediately follows the tag's bytes.
const tagOutClose = "</div>\n"

// unknownTagMarker is TagList.php:78 verbatim.
func unknownTagMarker(tag string) string {
	return "<p style='color:#b00020'>Unknown tag: " + esc(tag) + "</p>"
}

// pageTail measures the document template's trailing bytes — everything the page emits AFTER
// TagList's output — by driving TagList.php:77-78's "Unknown tag" branch, which emits its marker
// with nothing after it. See the file header. The tail is constant across ?page=tags requests
// because the template is one Documents row and only TagList's output varies.
func pageTail(client *http.Client, base, key string) ([]byte, error) {
	_, page, err := phpPage(client, base, key, probeTagName)
	if err != nil {
		return nil, err
	}
	marker := []byte(unknownTagMarker(probeTagName))
	i := bytes.Index(page, marker)
	if i < 0 {
		return nil, fmt.Errorf("probe page (%dB) has no %q marker: the live TagList did not take "+
			"its Unknown-tag branch (TagList.php:77-78), so the page tail cannot be measured",
			len(page), string(marker))
	}
	return page[i+len(marker):], nil
}

// tagSlice cuts tag T's own bytes out of a rendered ?page=tags&tag=T page, using the two
// TagList.php anchors and the measured tail. It is deliberately strict: every failure returns an
// error naming what did not hold, so a mis-slice is reported rather than diffed.
//
// The same function cuts the GO gallery (whose tail is empty) — see goTagBody — so both sides of
// the TagList comparison are sliced by identical code.
func tagSlice(page []byte, tag string, tail []byte) ([]byte, error) {
	open := []byte(tagOutOpen(tag))
	i := bytes.Index(page, open)
	if i < 0 {
		return nil, fmt.Errorf("no tagout heading for %q in the %dB render: the gallery did not "+
			"select this tag (TagList.php:61-62 needs it in the scanned whitelist)", tag, len(page))
	}
	if n := bytes.Count(page, open); n != 1 {
		return nil, fmt.Errorf("tagout heading for %q occurs %d times; the slice would be ambiguous", tag, n)
	}
	suffix := append([]byte(tagOutClose), tail...)
	if !bytes.HasSuffix(page, suffix) {
		return nil, fmt.Errorf("the %dB render does not end with %q+tail(%dB); the page template "+
			"changed shape and this harness's cut is no longer valid",
			len(page), tagOutClose, len(tail))
	}
	start, end := i+len(open), len(page)-len(suffix)
	if end < start {
		return nil, fmt.Errorf("the tagout heading for %q sits past the closing %q; the render is "+
			"not the shape TagList.php:61-76 emits", tag, tagOutClose)
	}
	return page[start:end], nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The Go side.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// equivConfig builds the engine Config for this sweep the way server.go's tagsConfig does
// (server.go:760-764): DefaultConfig from the app root, with SQLite PINNED to the db the live PHP
// reads, so the two engines cannot silently read different files. Immutable stays false (mode=ro)
// — see the file header's side-effects note.
func equivConfig() Config {
	cfg := DefaultConfig(equivAppRoot())
	cfg.SQLite = equivDBPath()
	return cfg
}

// goTagBody renders tag T through the Go engine and returns the bytes that correspond to the PHP
// page's tagout slice, plus a note naming the path taken (empty for the direct path).
//
// For every tag but TagList this is tags.RenderTag itself — the ticket's named entry, and the very
// call server.go:801 serves ?page=tags&tag=T with.
//
// TagList is the gallery, and its re-entrancy guard means the PHP page's slice holds the NESTED
// render, not a top-level one; RenderTag would produce the top-level gallery. So for TagList the Go
// side renders the gallery (which is still RenderTag) and this cuts the nested slice out with the
// same anchors used on the PHP page — reproducing PHP's call path exactly. See the file header.
func goTagBody(cfg Config, tag string) (body string, note string, ok bool) {
	get := url.Values{"page": {"tags"}, "tag": {tag}}
	if tag != "TagList" {
		out, found := RenderTag(cfg, tag, get)
		return out, "", found
	}
	gallery, found := RenderTag(cfg, "TagList", get)
	if !found {
		return "", "", false
	}
	// The Go gallery is TagList's return value alone: no page template, hence no tail.
	slice, err := tagSlice([]byte(gallery), tag, nil)
	if err != nil {
		return "", "", false
	}
	return string(slice), "compared on the gallery-nested path (TagList's own re-entrancy guard; " +
		"see the file header), not the top-level RenderTag render", true
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The report.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// tagDiff renders a compact line-oriented diff, capped so a 550KB tag cannot flood the log.
// Mirrors #227's unifiedish (equivalence_test.go:159-182).
func tagDiff(got, want []byte) string {
	gl := strings.Split(string(got), "\n")
	wl := strings.Split(string(want), "\n")
	n := len(gl)
	if len(wl) > n {
		n = len(wl)
	}
	var b strings.Builder
	shown := 0
	for i := 0; i < n && shown < 20; i++ {
		var g, w string
		if i < len(gl) {
			g = gl[i]
		}
		if i < len(wl) {
			w = wl[i]
		}
		if g != w {
			b.WriteString(fmt.Sprintf("  line %d:\n    - go : %s\n    + php: %s\n", i+1, clip(g), clip(w)))
			shown++
		}
	}
	if shown == 0 {
		b.WriteString("  (no differing line; the bytes differ only in trailing content or length)\n")
	}
	return b.String()
}

func clip(s string) string {
	const max = 220
	if len(s) > max {
		return fmt.Sprintf("%q… (%dB total)", s[:max], len(s))
	}
	return fmt.Sprintf("%q", s)
}

// TestTagEquivalence is the sweep: for every tag the PHP gallery lists, compare the Go engine's
// render against the live PHP's, byte for byte.
func TestTagEquivalence(t *testing.T) {
	// ── Guard 1: the API key ──
	key := apiKey()
	if key == "" {
		t.Skipf("no API key ($CONGRUENCY_API_KEY, or a CONGRUENCY_API_KEY= line in %s); "+
			"skipping the tag-equivalence sweep", secretsEnvFile)
	}

	// ── Guard 2: the state db both engines must share ──
	dbPath := equivDBPath()
	if _, err := os.Stat(dbPath); err != nil {
		t.Skipf("state db %s is absent (%v); the Go engine has nothing to read that the live PHP "+
			"also reads, so there is no equivalence to measure. Set $CONGRUENCY_EQUIV_DB.", dbPath, err)
	}

	// ── Guard 3: the app root, whose invocators/tags is TAGS_DIR ──
	appRoot := equivAppRoot()
	cfg := equivConfig()
	names := Scan(cfg.TagsDir)
	if len(names) == 0 {
		t.Skipf("TAGS_DIR %s lists no tags (app root %s absent or empty); nothing to sweep. "+
			"Set $CONGRUENCY_APP_ROOT.", cfg.TagsDir, appRoot)
	}

	// ── Guard 4: the live server ──
	base := pageURL()
	client := &http.Client{Timeout: 90 * time.Second}
	status, probe, err := phpPage(client, base, key, "")
	if err != nil {
		t.Skipf("live server at %s is unreachable (%v); skipping the tag-equivalence sweep", base, err)
	}
	if status != http.StatusOK {
		t.Skipf("live server at %s answered ?page=tags with HTTP %d (%dB); it is not serving the "+
			"tag gallery, so there is no golden render to compare against", base, status, len(probe))
	}

	// The tail cut, measured — never hardcoded. See the file header.
	if inStrings(probeTagName, names) {
		t.Skipf("the tail probe name %q is a real tag in %s; it would take the gallery's SELECTED "+
			"branch instead of the Unknown-tag branch, so the page tail cannot be measured",
			probeTagName, cfg.TagsDir)
	}
	tail, err := pageTail(client, base, key)
	if err != nil {
		t.Skipf("cannot measure the page tail (%v); without it no slice can be cut safely", err)
	}

	ported := PortedTags()
	t.Logf("db under test : %s (shared by both engines)", dbPath)
	t.Logf("app root      : %s", appRoot)
	t.Logf("golden source : %s?page=tags&tag=<T>", strings.TrimSuffix(base, "/")+"/")
	t.Logf("page tail     : %dB %q (measured via the Unknown-tag probe)", len(tail), string(tail))
	t.Logf("coverage      : %d tags scanned, %d registered in the Go engine, %d not yet ported "+
		"(reported as SKIP, never FAIL)", len(names), len(ported), len(names)-len(ported))

	var identical, differ, volatile, notPorted []string

	for _, name := range names {
		name := name
		t.Run(name, func(t *testing.T) {
			// Not yet ported is a SKIP, not a failure: it is the #246+ queue, not a defect.
			if !IsPorted(name) {
				notPorted = append(notPorted, name)
				t.Skip("no Go port yet — the PHP renders this tag, this package has no registered " +
					"factory for it. A tag unit (#246+) registers it; this harness then measures it " +
					"with no edit here.")
			}

			// ── The stability sandwich (#227): php1, go, php2 ──
			_, page1, err := phpPage(client, base, key, name)
			if err != nil {
				t.Skipf("php fetch failed (%v)", err)
			}
			php1, err := tagSlice(page1, name, tail)
			if err != nil {
				t.Fatalf("cannot cut the PHP render for %s: %v", name, err)
			}

			goBody, note, ok := goTagBody(cfg, name)
			if !ok {
				t.Fatalf("the Go engine reports %s registered (IsPorted) but rendered nothing for "+
					"it; the registry and the render path disagree", name)
			}

			_, page2, err := phpPage(client, base, key, name)
			if err != nil {
				t.Skipf("php re-fetch failed (%v)", err)
			}
			php2, err := tagSlice(page2, name, tail)
			if err != nil {
				t.Fatalf("cannot cut the PHP re-render for %s: %v", name, err)
			}

			if !bytes.Equal(php1, php2) {
				volatile = append(volatile, name)
				t.Skipf("VOLATILE: the live PHP render changed under concurrent writers inside the "+
					"measurement window (php1=%dB php2=%dB); that is a data signal, not an engine "+
					"signal, so this tag is not judged this run", len(php1), len(php2))
			}

			if note != "" {
				t.Logf("NOTE: %s", note)
			}

			if bytes.Equal([]byte(goBody), php1) {
				identical = append(identical, name)
				t.Logf("IDENTICAL: %dB byte-for-byte", len(php1))
				return
			}

			differ = append(differ, name)
			t.Errorf("BYTE MISMATCH for tag %s (go=%dB php=%dB):\n%s",
				name, len(goBody), len(php1), tagDiff([]byte(goBody), php1))
		})
	}

	t.Logf("SUMMARY: %d/%d registered tags byte-identical to the live PHP; %d differ (%s); "+
		"%d volatile this run (%s); %d not yet ported, skipped (%s)",
		len(identical), len(ported), len(differ), joinOr(differ, "none"),
		len(volatile), joinOr(volatile, "none"),
		len(notPorted), joinOr(notPorted, "none"))
}

func joinOr(xs []string, empty string) string {
	if len(xs) == 0 {
		return empty
	}
	return strings.Join(xs, ",")
}
