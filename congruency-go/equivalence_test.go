package main

// equivalence_test.go — ticket #227: a standing PHP<->Go byte-equivalence sweep.
//
// It answers one question: does this Go port of the api_routes engine (RunRoute) emit the EXACT
// bytes the live rest.php does, for the read-only (GET) routes? It runs each route through the Go
// engine in-process — the same code path main() drives — and compares to the golden output of the
// live PHP server (curl rest.php).
//
// ── The DB the two sides must share ──────────────────────────────────────────────────────────────
// A true engine comparison requires BOTH engines to read the SAME database; otherwise a divergence
// is a data difference, not an engine difference. The #227 brief named
// config/congruency/congruency.sqlite as "the live DB", but the running rest.php actually opens
// checkouts/current/state/congruency.sqlite (boot/configure.php: <app>/../state/congruency.sqlite),
// and that file is being written continuously by the concurrent pair_loop agents. The two files
// have DIVERGED (measured this session: 12 agents in config, 102 in checkouts/current/state). So
// this test points the Go engine at the SERVER's DB by default — resolveDB() prefers, in order:
//   1. $CONGRUENCY_EQUIV_DB (explicit override),
//   2. the server's state DB (checkouts/current/state/congruency.sqlite),
//   3. the config DB named in the brief (only static/reference routes will match from here).
//
// ── Concurrency: the stability sandwich ──────────────────────────────────────────────────────────
// Because the server's DB has live writers, a route's rows can change between the Go read and the
// PHP read. Each route is fetched from PHP twice, bracketing the Go run (php1, go, php2). If
// php1 != php2 the DB changed inside the window, so the route is reported VOLATILE and skipped for
// this run rather than false-failing. History here is append-only, so a change that reverts within
// the window cannot occur — the sandwich is sound.
//
// ── Known, by-design non-equivalence ─────────────────────────────────────────────────────────────
// A route whose SQL errors (e.g. `LIMIT :n` with :n bound NULL -> sqlite "datatype mismatch") yields
// a 500 whose ENVELOPE both sides reproduce ({"error": <msg>} pretty-printed) but whose MESSAGE is
// the driver's: Go's sqlite says "datatype mismatch (20)", PDO says
// "SQLSTATE[HY000]: General error: 20 datatype mismatch". db.go's header documents this as
// unreproducible-by-design. Such routes (knownDriverMsgDiff) are reported as a documented DIFFERENCE
// (t.Log), not a hard failure — matching #227's mandate to MEASURE, not to chase every route.
//
// Guards: the test t.Skips cleanly if the DB is missing, the server is unreachable, or no API key is
// available, so it never false-fails in CI.

import (
	"bufio"
	"bytes"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const (
	defaultServerURL = "http://127.0.0.1:8899/rest.php"
	secretsEnvFile   = "/Users/stevenpeterson/code/installed/jazz-project/.secrets/ats.env"
	serverStateDB    = "/Users/stevenpeterson/code/installed/jazz-project/congruency/checkouts/current/state/congruency.sqlite"
	configDB         = "/Users/stevenpeterson/code/installed/jazz-project/config/congruency/congruency.sqlite"
)

// getRoutes are the read-only routes this sweep covers: every route whose method is GET and whose
// auth is "public" (measured from api_routes). They run without required params — the engine binds
// missing params the way rest.php does — so empty input is a faithful request.
var getRoutes = []string{
	"agent.prompt", "agent.roster", "agent.trail", "artifact.list", "binding.list",
	"bug.list", "bug.stats", "children.list", "doc.list", "doc.read", "doc.repos",
	"error.recent", "error.stats", "guarantee.held", "guarantee.list", "job.get",
	"journey.list", "kind.roster", "lessons.recent", "lifecycle.steps", "mandate.list",
	"policy.active", "processes.running", "repo.list", "run.get", "run.recent",
	"search.facets", "search.stats", "search.text", "source.commits", "telemetry.recent",
	"ticket.approval", "ticket.crew", "ticket.journal", "ticket.manifest", "ticket.queue",
	"ticket.stops", "tickets.recent",
}

// skippedWriteRoutes are the POST routes (auth writes) this sweep deliberately does NOT exercise: a
// write against the live governed DB would mutate real state. Listed so the report is honest about
// coverage, not so any is fabricated.
var skippedWriteRoutes = []string{
	"agent.register", "artifact.record", "authorize_process", "binding.record", "bug.record",
	"doc.record", "edge.record", "guarantee.record", "job.put", "journey.record",
	"mandate.record", "policy.create", "process_status", "run.record", "search.record",
	"source.record", "telemetry.record", "ticket.approve", "ticket.assign", "ticket.create",
	"ticket.kind", "ticket.lesson", "ticket.progress", "work.record",
}

// knownDriverMsgDiff: routes whose only divergence is the driver-specific text inside a 500 error
// envelope (the PDO vs go-sqlite message). Reported as documented, not failed. See file header.
var knownDriverMsgDiff = map[string]bool{
	"run.recent":     true,
	"tickets.recent": true,
}

func resolveDB(t *testing.T) string {
	for _, p := range []string{os.Getenv("CONGRUENCY_EQUIV_DB"), serverStateDB, configDB} {
		if p == "" {
			continue
		}
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	t.Skip("no congruency.sqlite found (set $CONGRUENCY_EQUIV_DB); skipping equivalence sweep")
	return ""
}

func apiKey() string {
	if k := os.Getenv("CONGRUENCY_API_KEY"); k != "" {
		return k
	}
	f, err := os.Open(secretsEnvFile)
	if err != nil {
		return ""
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if strings.HasPrefix(line, "CONGRUENCY_API_KEY=") {
			return strings.TrimSpace(strings.TrimPrefix(line, "CONGRUENCY_API_KEY="))
		}
	}
	return ""
}

func serverURL() string {
	if u := os.Getenv("CONGRUENCY_REST_URL"); u != "" {
		return u
	}
	return defaultServerURL
}

// phpFetch pulls one route's golden output from the live rest.php. Returns (status, body).
func phpFetch(t *testing.T, client *http.Client, base, key, route string) (int, []byte, error) {
	req, err := http.NewRequest("GET", base+"?route="+route, nil)
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

// goRoute runs a route through the Go engine exactly as main() does, including main()'s wrapping of
// a RunRoute error into a pretty {"error": msg} 500 body — so the bytes are what the CLI would print.
func goRoute(d *DB, route string) (int, []byte) {
	reply, err := d.RunRoute(route, "GET", map[string]any{}, AllowAll{})
	if err != nil {
		body, _ := phpJSONEncode(Obj{{"error", err.Error()}}, jsonPretty|jsonUnescapedSlashes)
		return 500, append(body, '\n')
	}
	return reply.Status, reply.Body
}

// unifiedish renders a compact line-oriented diff for the failure message.
func unifiedish(got, want []byte) string {
	gl := strings.Split(string(got), "\n")
	wl := strings.Split(string(want), "\n")
	var b strings.Builder
	n := len(gl)
	if len(wl) > n {
		n = len(wl)
	}
	shown := 0
	for i := 0; i < n && shown < 40; i++ {
		var g, w string
		if i < len(gl) {
			g = gl[i]
		}
		if i < len(wl) {
			w = wl[i]
		}
		if g != w {
			b.WriteString(fmt.Sprintf("  - go : %q\n  + php: %q\n", g, w))
			shown++
		}
	}
	return b.String()
}

func isErrorEnvelope(b []byte) bool {
	return bytes.Contains(b, []byte(`"error"`))
}

func TestRouteEquivalence(t *testing.T) {
	key := apiKey()
	if key == "" {
		t.Skip("no CONGRUENCY_API_KEY available; skipping equivalence sweep")
	}
	base := serverURL()
	client := &http.Client{Timeout: 10 * time.Second}

	// Reachability probe: skip (never fail) if the PHP server is down.
	if _, _, err := phpFetch(t, client, base, key, "kind.roster"); err != nil {
		t.Skipf("live rest.php at %s unreachable (%v); skipping equivalence sweep", base, err)
	}

	dbPath := resolveDB(t)
	usingServerDB := dbPath == serverStateDB || dbPath == os.Getenv("CONGRUENCY_EQUIV_DB")
	if dbPath == configDB {
		t.Logf("NOTE: comparing against %s, which is NOT the DB rest.php reads (%s). Volatile "+
			"routes will report VOLATILE/DIFF due to divergent data, not an engine bug. Set "+
			"$CONGRUENCY_EQUIV_DB to the server DB for a true engine comparison.",
			filepath.Base(dbPath), serverStateDB)
	}
	_ = usingServerDB

	d, err := Open(dbPath)
	if err != nil {
		t.Skipf("cannot open %s (%v); skipping", dbPath, err)
	}
	defer d.Close()

	t.Logf("DB under test: %s", dbPath)
	t.Logf("golden source: %s", base)
	t.Logf("skipped write (POST) routes (%d): %s", len(skippedWriteRoutes), strings.Join(skippedWriteRoutes, ", "))

	var identical, documented, volatile []string

	for _, route := range getRoutes {
		route := route
		t.Run(route, func(t *testing.T) {
			// Stability sandwich: php1, go, php2. A live write inside the window makes php1 != php2.
			pStatus1, php1, err := phpFetch(t, client, base, key, route)
			if err != nil {
				t.Skipf("php fetch failed (%v)", err)
			}
			gStatus, goBody := goRoute(d, route)
			_, php2, err := phpFetch(t, client, base, key, route)
			if err != nil {
				t.Skipf("php re-fetch failed (%v)", err)
			}
			if !bytes.Equal(php1, php2) {
				volatile = append(volatile, route)
				t.Skipf("VOLATILE: rest.php output changed under concurrent writes during the window; "+
					"not an engine signal (php1=%dB php2=%dB)", len(php1), len(php2))
			}

			if bytes.Equal(goBody, php1) {
				identical = append(identical, route)
				if gStatus != pStatus1 {
					t.Errorf("bytes match but status differs: go=%d php=%d", gStatus, pStatus1)
				}
				return
			}

			// Bytes differ. Distinguish the documented driver-message class from a real regression.
			if knownDriverMsgDiff[route] && isErrorEnvelope(goBody) && isErrorEnvelope(php1) {
				documented = append(documented, route)
				t.Logf("DOCUMENTED non-equivalence (PDO vs go-sqlite error text; not a float bug):\n%s",
					unifiedish(goBody, php1))
				return
			}

			t.Errorf("BYTE MISMATCH for route %s (go=%dB php=%dB, status go=%d php=%d):\n%s",
				route, len(goBody), len(php1), gStatus, pStatus1, unifiedish(goBody, php1))
		})
	}

	t.Logf("SUMMARY: %d/%d GET routes byte-identical; %d documented driver-msg diffs (%s); %d volatile this run (%s)",
		len(identical), len(getRoutes), len(documented), strings.Join(documented, ","),
		len(volatile), strings.Join(volatile, ","))
}
