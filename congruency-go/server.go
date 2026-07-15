// server.go — congruency-go HTTP FRONT DOOR (ticket #225).
//
// WHAT THIS IS
//
// The net/http half of congruency's REST plane: the front controller that boot/rest.php's
// congruency_rest_dispatch() is in PHP, wrapping the proven data-driven engine in db.go
// (RunRoute == congruency_rest_route(), already byte-equivalent per #227/#236/#242). This file adds
// nothing to the route engine; it reproduces the SURROUNDING dispatch: the ?route / ?api split, the
// generic table CRUD with its sqlite_master / PRAGMA allowlist, the api-key / admin-session auth
// guard, the write authorization gate, the telemetry seam, and the router's page/path fall-through.
//
// THE CONTRACT: byte-identical HTTP. rest.php echoes JSON with a specific status, a specific
// Content-Type / CORS header pair, specific pretty-vs-compact encoder flags PER CALL SITE, and a
// specific trailing-"\n"-or-not per call site. Every one of those quirks is reproduced here against
// the PHP as spec — the pretty create reply, the COMPACT delete reply, the newline-less 400s, the
// 401 write-guard body verbatim. Where db.go already owns a shape (the {"route",...,"rows"} /
// {"route","affected","rowid"} replies and the 404/405/401 route errors) this file just forwards it.
//
// ARCHITECTURE (this builder's assigned approach): a stdlib net/http mux with ONE typed handler per
// surface — route dispatch, ?api CRUD, page paths — and authorization as a guard function
// (restAuthorized) that each handler calls. No framework, no middleware stack beyond a thin logging
// wrapper. The mux mirrors boot/router.php: any request carrying ?api or ?route is a REST request
// (congruency_rest_dispatch); everything else is the CMS page surface (Controller::control()).
//
// PER-REQUEST DB HANDLE. rest.php runs `new PDO('sqlite:'.CONGRUENCY_SQLITE)` per request, and db.go
// documents that PDO::lastInsertId() is a property of that one connection — a pooled/shared handle
// would let one request's write route report another request's rowid. So this server opens a FRESH
// db.go handle per request and closes it at the end, which is the faithful mirror (and the reason a
// write route's rowid is isolated exactly as PHP isolates it). Reads pay a cheap open; correctness
// wins over a connection-pool micro-optimization on the equivalence path.
//
// BORN INSTRUMENTED. Config is explicit and control-config-driven (ServerConfig, defaults in
// DefaultServerConfig): the table denylist, the CONGRUENCY_AUTH_OVERRIDE flag (true live, per
// boot/constants.default.json), the admin-session probe, and a real logging hook that fires on every
// request and on every telemetry.record beacon. The hook is a seam, not ornament — it carries the
// method/surface/route/status/bytes/duration of each request and defaults to a one-line stderr log
// that can be pointed at io.Discard or any sink.
//
// WHAT IS AND IS NOT BYTE-EQUIVALENT. The ?route and ?api surfaces are reproduced to the byte against
// the live rest.php. The page/path surface (Controller::control()) is a full PHP CMS and is NOT
// reproducible in Go; the CATALOG branch of handlePage — which answers every page key except one —
// mirrors what it honestly can (status and Content-Type) over a structurally-honest table list,
// explicitly marked as a seam rather than a forgery of the CMS HTML.
//
// ?page=tags IS THE ONE EXCEPTION: it is not a seam, it runs the real tag engine (ticket #280).
// #226 built that engine (congruency-go/tags, engine.go: execute_all_tags + both recursion guards +
// the tag registry) and exported Render/RenderTag/Handler specifically so this file could point the
// page seam at it — but #226's single-deliverable scope forbade it from editing server.go, so the
// engine sat unreachable and ?page=tags answered with a fixed placeholder that never called it.
// #280 is exactly that one wiring edit and nothing else: handleTagsPage below calls tags.RenderTag,
// so a ?page=tags&tag=<T> request now runs the real tag. Status (200) and Content-Type
// (text/html; charset=UTF-8) are unchanged from the placeholder it replaces.
//
// WHAT WAS MEASURED, AND WHAT IS NOT CLAIMED. #280's gate is "?page=tags&tag=<T> reaches the engine
// for every registered tag", and that was checked over real HTTP for all ten of tags.PortedTags()
// against the real 46-table state db: every one answers 200 and carries the engine's own render for
// that tag (TicketList alone renders ~537 KB out of the 270 real tickets). "Preserving
// status+content-type" was checked the same way rather than assumed — against the LIVE PHP this repo
// serves, PHP and this server answer ?page=tags&tag=<T> with the SAME status (200) and the SAME
// Content-Type (text/html; charset=UTF-8) for all ten registered tags AND for an unknown tag name.
//
// NOT claimed: that the page's BYTES match PHP. engine.go's header is explicit that its tags were
// never byte-diffed against a live PHP render, and #280 does not upgrade that claim — it forwards
// the engine's bytes unchanged. The PHP page is also larger by a constant ~6.2 KB of CMS chrome
// (nav/head/style from Controller::control()), which the frame here deliberately does not forge. The
// bodies were not diffed; that gate is #226's, not this ticket's.
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"congruency-go/tags"
)

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Config — the control-config surface. Every knob rest.php reads from a constant or a table is a
// field here, with the live defaults baked into DefaultServerConfig.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// ServerConfig is the server's control config. It is deliberately data, not code: the same shape the
// PHP reads from boot/constants.default.json + the api_keys table, made explicit and overridable.
type ServerConfig struct {
	// DBPath is CONGRUENCY_SQLITE — the one sqlite file both engines read.
	DBPath string

	// Denylist is the set of tables kept off the public ?api surface (rest.php's inline unset list:
	// the self-hosting archive, the auth tables, and the api_keys table).
	Denylist []string

	// AuthOverride is CONGRUENCY_AUTH_OVERRIDE. Live it is true (boot/constants.default.json:52), so
	// congruency_rest_authorized() short-circuits to true for every request. Flip to false to re-arm
	// the api-key / admin-session checks.
	AuthOverride bool

	// AdminSession models UserPrivilegeSet::logged_in() — the admin session probe the engine uses for
	// auth='admin' routes and the write guard. The override does NOT touch it, so it stays a real
	// input. nil == no session == not logged in (the safe default).
	AdminSession func(*http.Request) bool

	// TagsAppRoot is the tag engine's ABS_PATH (boot/configure.php:41) — the app root under which
	// the engine finds invocators/tags/ (TAGS_DIR, configure.php:43). TagList::scan walks that tree
	// to build the ?page=tags gallery list, and it is the ONLY thing the engine reads from the app
	// root (engine.go uses cfg.TagsDir in exactly one place: TagListTag.GetDocument).
	//
	// "" is filled in by NewServer from DBPath (see srvTagsAppRoot). Set it explicitly when the app
	// root is not the sibling of the state directory.
	//
	// NB: this knob CANNOT route a registered tag around the engine. ?page=tags&tag=<T> for a
	// registered T is answered by tags.RenderTag, which is a registry lookup and never reads
	// TagsDir; a wrong app root shortens the gallery's LIST, it does not break the render.
	TagsAppRoot string

	// EnableTelemetryIngest wires db.DB.TelemetryIngest to the logging hook so telemetry.record
	// beacons are recorded (mirrors boot/monitor.php's congruency_telemetry_ingest being defined).
	// The telemetry.record ACK body is identical whether or not this is set; only the side-log differs.
	EnableTelemetryIngest bool

	// Log is the request/telemetry logging hook. nil is replaced in NewServer by a default that
	// writes one line per event to LogWriter.
	Log func(LogEvent)

	// LogWriter is where the default logger writes. nil defaults to os.Stderr; set io.Discard to mute.
	LogWriter io.Writer
}

// DefaultDenylist is rest.php's inline admin-only unset list, verbatim and in the same order.
var DefaultDenylist = []string{
	"code_blobs", "code_refs", "doc_blobs", "doc_refs",
	"Login_Password", "User_Group_Mappings", "Group_Privileges", "api_keys",
}

// DefaultServerConfig returns the live-deployment configuration for the given db path.
func DefaultServerConfig(dbPath string) ServerConfig {
	return ServerConfig{
		DBPath:       dbPath,
		Denylist:     append([]string(nil), DefaultDenylist...),
		AuthOverride: true, // CONGRUENCY_AUTH_OVERRIDE, per boot/constants.default.json
		TagsAppRoot:  srvTagsAppRoot(dbPath),
		LogWriter:    os.Stderr,
	}
}

// srvTagsAppRoot derives the tag engine's app root from the sqlite path by INVERTING
// boot/configure.php:42:
//
//	define('CONGRUENCY_SQLITE', dirname(rtrim(ABS_PATH, SLASH)) . SLASH . 'state' . SLASH . 'congruency.sqlite');
//
// i.e. the state directory is a SIBLING of the app root, not a child. So from
// <checkout>/state/congruency.sqlite the app root is <checkout>/congruency — which is the layout
// this repo ships (checkouts/current/ holds congruency/, state/ and docs/ side by side, and
// checkouts/current/congruency/invocators/tags/ is the tree TagList::scan walks).
//
// The app directory's NAME is the one thing configure.php cannot supply here: it derives the sqlite
// path FROM the app root, and that direction does not invert (dirname loses the basename). This
// hardcodes the name the checkout actually uses; ServerConfig.TagsAppRoot overrides it for a
// checkout laid out differently. A wrong guess costs the gallery its list, never a tag's render —
// see TagsAppRoot.
func srvTagsAppRoot(dbPath string) string {
	if dbPath == "" {
		return ""
	}
	stateDir := filepath.Dir(dbPath) // <checkout>/state
	return filepath.Join(filepath.Dir(stateDir), "congruency")
}

// LogEvent is one instrumentation record. Real fields, populated on every request and beacon.
type LogEvent struct {
	Time    time.Time
	Kind    string // "request" | "telemetry"
	Method  string
	Path    string
	Surface string // "route" | "api" | "page" | "telemetry"
	Route   string
	API     string
	Status  int
	Bytes   int
	Dur     time.Duration
	Detail  string
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Server.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// Server is the congruency REST/page front door. It holds only config and a routing mux; each request
// gets its own db.go handle (see the per-request-handle note in the file header).
type Server struct {
	cfg      ServerConfig
	mux      *http.ServeMux
	reserved map[string]bool // the ?api filter reserved keys, rest.php's $reserved
}

// srvReserved is rest.php's $reserved map for ?api filtering: these query keys never become column
// filters (they are the pagination / control keys).
var srvReserved = map[string]bool{
	"api": true, "route": true, "key": true, "p": true,
	"per": true, "id": true, "order": true, "limit": true,
}

// NewServer builds a Server, filling defaults for any unset config field.
func NewServer(cfg ServerConfig) *Server {
	if cfg.Denylist == nil {
		cfg.Denylist = append([]string(nil), DefaultDenylist...)
	}
	if cfg.LogWriter == nil {
		cfg.LogWriter = os.Stderr
	}
	if cfg.Log == nil {
		cfg.Log = defaultLogger(cfg.LogWriter)
	}
	if cfg.TagsAppRoot == "" {
		cfg.TagsAppRoot = srvTagsAppRoot(cfg.DBPath)
	}
	s := &Server{cfg: cfg, mux: http.NewServeMux(), reserved: srvReserved}
	// One catch-all handler. "/" matches every path, including the "/rest.php" the live server exposes;
	// the handler mirrors router.php's decision: ?api or ?route -> REST dispatch, else the page surface.
	s.mux.HandleFunc("/", s.root)
	return s
}

// defaultLogger returns a one-line-per-event logger over w.
func defaultLogger(w io.Writer) func(LogEvent) {
	return func(e LogEvent) {
		if e.Kind == "telemetry" {
			fmt.Fprintf(w, "congruency-go telemetry route=%q %s\n", e.Route, e.Detail)
			return
		}
		fmt.Fprintf(w, "congruency-go %s %s surface=%s route=%q api=%q -> %d %dB %s\n",
			e.Method, e.Path, e.Surface, e.Route, e.API, e.Status, e.Bytes, e.Dur.Round(time.Microsecond))
	}
}

func (s *Server) log(e LogEvent) {
	if s.cfg.Log != nil {
		s.cfg.Log(e)
	}
}

// Handler returns the http.Handler for this server (the Server itself: it wraps the mux with the
// request-logging seam).
func (s *Server) Handler() http.Handler { return s }

// Listen serves HTTP on addr until the process exits (the real front-door entry point; there is no
// main() here because db.go owns package main's main — a caller wires this behind a -serve flag).
func (s *Server) Listen(addr string) error { return http.ListenAndServe(addr, s) }

// ServeHTTP is the instrumentation wrapper: it captures status/bytes and emits one LogEvent per
// request, then delegates to the mux.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	sw := &statusWriter{ResponseWriter: w, status: 200}
	s.mux.ServeHTTP(sw, r)
	q := r.URL.Query()
	surface := "page"
	if q.Has("route") {
		surface = "route"
	} else if q.Has("api") {
		surface = "api"
	}
	s.log(LogEvent{
		Time: start, Kind: "request", Method: r.Method, Path: r.URL.Path, Surface: surface,
		Route: q.Get("route"), API: q.Get("api"), Status: sw.status, Bytes: sw.n, Dur: time.Since(start),
	})
}

// statusWriter captures the status code and byte count for the logging seam.
type statusWriter struct {
	http.ResponseWriter
	status int
	n      int
	wrote  bool
}

func (w *statusWriter) WriteHeader(code int) {
	if !w.wrote {
		w.status = code
		w.wrote = true
	}
	w.ResponseWriter.WriteHeader(code)
}

func (w *statusWriter) Write(b []byte) (int, error) {
	w.wrote = true
	n, err := w.ResponseWriter.Write(b)
	w.n += n
	return n, err
}

// root mirrors boot/router.php: a request carrying ?api or ?route is REST; otherwise it is the page
// surface (the CMS front controller in PHP).
func (s *Server) root(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	if q.Has("api") || q.Has("route") {
		s.restDispatch(w, r)
		return
	}
	s.handlePage(w, r)
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// REST dispatch — congruency_rest_dispatch().
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// restDispatch sets the two headers rest.php sets up front (Content-Type + CORS) and writes the reply
// buildRest computes. Headers first, then status, then body — the PHP order.
func (s *Server) restDispatch(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	reply := s.buildRest(r)
	w.WriteHeader(reply.Status)
	w.Write(reply.Body)
}

// buildRest is the body of congruency_rest_dispatch()'s try block. Any Go error it hits is the
// PHP catch: a 500 with a pretty {"error": msg} body + "\n" (the message is Go's, not PDO's — db.go's
// header documents this as the one unreproducible byte).
func (s *Server) buildRest(r *http.Request) Reply {
	db, err := Open(s.cfg.DBPath)
	if err != nil {
		return srv500(err)
	}
	defer db.Close()
	if s.cfg.EnableTelemetryIngest {
		db.TelemetryIngest = s.telemetryHook
	}

	tableList, tableSet, err := s.tables(db)
	if err != nil {
		return srv500(err)
	}

	api := srvQueryOr(r, "api", "")
	route := srvQueryOr(r, "route", "")
	method := strings.ToUpper(r.Method)

	// (2) Data-driven named route: ?route=<name> runs an api_routes row via the db.go engine.
	if route != "" {
		return s.handleRoute(db, r, route, method)
	}

	// (3) Writes require authorization (admin session OR api key). Reads are public.
	if srvIsWrite(method) && !s.restAuthorized(r, db) {
		return srvJSON(401, Obj{
			{"error", "authorization required for writes"},
			{"method", method},
			{"hint", "send X-Api-Key: <key> (or ?key=), or log in via the Login form"},
		}, 0, true) // compact, trailing "\n"
	}

	// (1) Generic table CRUD (write verbs).
	if reply, handled := s.handleAPIWrite(db, r, api, method, tableSet); handled {
		return reply
	}

	// GET-ish surface: tables list / single row / paginated list / unknown table.
	return s.handleAPIRead(db, r, api, tableList, tableSet)
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Named-route surface.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// srvAuthorizer is the db.go Authorizer the engine consults, wired to this server's checks.
type srvAuthorizer struct {
	loggedIn   bool
	authorized bool
}

func (a srvAuthorizer) LoggedIn() bool   { return a.loggedIn }
func (a srvAuthorizer) Authorized() bool { return a.authorized }

// handleRoute assembles the engine input the way rest.php does ($_GET, merged with the JSON body for
// write methods) and runs the route. A RunRoute error is the PDOException path -> 500 (see buildRest).
func (s *Server) handleRoute(db *DB, r *http.Request, route, method string) Reply {
	input := s.routeInput(r, method)
	az := srvAuthorizer{loggedIn: s.adminSession(r), authorized: s.restAuthorized(r, db)}
	reply, err := db.RunRoute(route, method, input, az)
	if err != nil {
		return srv500(err)
	}
	return reply
}

// routeInput builds rest.php's $input: $_GET (query params, last value wins as in PHP), merged with
// the decoded JSON body for POST/PUT/PATCH/DELETE (array_merge -> body keys override query keys).
func (s *Server) routeInput(r *http.Request, method string) map[string]any {
	in := map[string]any{}
	for k, vs := range r.URL.Query() {
		in[k] = vs[len(vs)-1] // PHP $_GET keeps the LAST value of a repeated key
	}
	if srvIsWrite(method) {
		body, _ := io.ReadAll(r.Body)
		if v, err := decodeJSONOrdered(body); err == nil {
			if o, ok := v.(Obj); ok {
				for _, f := range o {
					in[f.K] = f.V // array_merge($input, $body): body wins
				}
			}
		}
	}
	return in
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Authorization guard — congruency_rest_authorized() / congruency_rest_apikey().
// ─────────────────────────────────────────────────────────────────────────────────────────────────

func (s *Server) adminSession(r *http.Request) bool {
	if s.cfg.AdminSession != nil {
		return s.cfg.AdminSession(r)
	}
	return false
}

// restAuthorized is congruency_rest_authorized(): the override flag, then the admin session, then a
// valid api key. (The Vault branch is skipped, exactly as PHP skips it when Vault is unconfigured.)
func (s *Server) restAuthorized(r *http.Request, db *DB) bool {
	if s.cfg.AuthOverride {
		return true
	}
	if s.adminSession(r) {
		return true
	}
	if s.apiKeyValid(r, db) {
		return true
	}
	return false
}

// apiKeyValid is congruency_rest_apikey(): read X-Api-Key (or ?key=), require the api_keys table to
// exist, and look the key up. A hit (any row) authorizes.
func (s *Server) apiKeyValid(r *http.Request, db *DB) bool {
	key := r.Header.Get("X-Api-Key")
	if key == "" {
		key = srvQueryOr(r, "key", "")
	}
	if key == "" {
		return false
	}
	var name string
	err := db.conn.QueryRowContext(context.Background(),
		"SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys'").Scan(&name)
	if err != nil {
		return false // no api_keys table (ErrNoRows) or a query error -> not authorized
	}
	var label, scope sql.NullString
	err = db.conn.QueryRowContext(context.Background(),
		"SELECT label, scope FROM api_keys WHERE key = ?", key).Scan(&label, &scope)
	if err != nil {
		return false // no such key (ErrNoRows) -> not authorized
	}
	return true
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Generic CRUD — the ?api surface.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// handleAPIWrite runs the write verbs (POST create / PUT|PATCH update / DELETE) when ?api names an
// allowed table. It returns handled=false when no write branch applies, so buildRest falls through to
// the read surface — exactly as the PHP `if (... isset($tables[$api])) { ... return; }` blocks fall
// through to the GET section when their condition is not met.
func (s *Server) handleAPIWrite(db *DB, r *http.Request, api, method string, tableSet map[string]bool) (Reply, bool) {
	switch {
	case method == "POST" && tableSet[api]:
		return s.apiCreate(db, r, api), true
	case (method == "PUT" || method == "PATCH") && tableSet[api]:
		return s.apiUpdate(db, r, api), true
	case method == "DELETE" && tableSet[api]:
		return s.apiDelete(db, r, api), true
	}
	return Reply{}, false
}

// apiCreate: INSERT a row from the JSON body; only real columns are used (rest ignored). 201 + pretty.
func (s *Server) apiCreate(db *DB, r *http.Request, api string) Reply {
	body, _ := io.ReadAll(r.Body)
	data, ok := srvWriteBody(body)
	if !ok {
		return srvJSON(400, Obj{{"error", "body must be a JSON object"}}, 0, false) // compact, NO newline
	}
	cols, colset, _, _, err := s.tableInfo(db, api)
	if err != nil {
		return srv500(err)
	}
	used := Obj{}
	for _, f := range data {
		if colset[f.K] {
			used = used.Set(f.K, f.V)
		}
	}
	if len(used) == 0 {
		return srvJSON(400, Obj{{"error", "no valid columns for " + api}, {"columns", cols}}, 0, false)
	}
	colFrag := make([]string, len(used))
	valFrag := make([]string, len(used))
	args := make([]any, len(used))
	for i, f := range used {
		colFrag[i] = `"` + f.K + `"`
		valFrag[i] = ":" + f.K
		args[i] = sql.Named(f.K, bindText(f.V)) // PDO PARAM_STR: every bound value is TEXT (null -> NULL)
	}
	insert := `INSERT INTO "` + api + `" (` + strings.Join(colFrag, ",") + `) VALUES (` + strings.Join(valFrag, ",") + `)`
	if _, err := db.conn.ExecContext(context.Background(), insert, args...); err != nil {
		return srv500(err)
	}
	rowid, err := db.lastInsertID()
	if err != nil {
		return srv500(err)
	}
	return srvJSON(201, Obj{
		{"created", true}, {"table", api}, {"rowid", rowid}, {"used", used},
	}, jsonPretty|jsonUnescapedSlashes, true)
}

// apiUpdate: UPDATE by single-column primary key (?id=), body of column=>value (real cols, not pk).
func (s *Server) apiUpdate(db *DB, r *http.Request, api string) Reply {
	_, colset, _, pk, err := s.tableInfo(db, api)
	if err != nil {
		return srv500(err)
	}
	id, idOK := srvQueryVal(r, "id")
	if pk == "" || !idOK {
		return srvJSON(400, Obj{{"error", "update needs a single-column pk and ?id="}}, 0, false)
	}
	body, _ := io.ReadAll(r.Body)
	data, ok := srvWriteBody(body)
	if !ok {
		return srvJSON(400, Obj{{"error", "body must be a JSON object"}}, 0, false)
	}
	used := Obj{}
	for _, f := range data {
		if colset[f.K] && f.K != pk {
			used = used.Set(f.K, f.V)
		}
	}
	if len(used) == 0 {
		return srvJSON(400, Obj{{"error", "no valid columns to update"}}, 0, false)
	}
	setFrag := make([]string, len(used))
	args := make([]any, 0, len(used)+1)
	for i, f := range used {
		setFrag[i] = `"` + f.K + `" = :` + f.K
		args = append(args, sql.Named(f.K, bindText(f.V)))
	}
	args = append(args, sql.Named("__id", bindText(id)))
	upd := `UPDATE "` + api + `" SET ` + strings.Join(setFrag, ", ") + ` WHERE "` + pk + `" = :__id`
	res, err := db.conn.ExecContext(context.Background(), upd, args...)
	if err != nil {
		return srv500(err)
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return srv500(err)
	}
	return srvJSON(200, Obj{
		{"updated", affected}, {"table", api}, {"pk", pk}, {"id", id}, {"set", used},
	}, jsonPretty|jsonUnescapedSlashes, true)
}

// apiDelete: DELETE a single row by primary key (?id=). Reply is COMPACT (rest.php passes no flags
// here) with a trailing "\n" — the one write reply that is not pretty-printed.
func (s *Server) apiDelete(db *DB, r *http.Request, api string) Reply {
	_, _, _, pk, err := s.tableInfo(db, api)
	if err != nil {
		return srv500(err)
	}
	id, idOK := srvQueryVal(r, "id")
	if pk == "" || !idOK {
		return srvJSON(400, Obj{{"error", "delete needs a single-column pk and ?id="}}, 0, false)
	}
	del := `DELETE FROM "` + api + `" WHERE "` + pk + `" = ?`
	res, err := db.conn.ExecContext(context.Background(), del, bindText(id))
	if err != nil {
		return srv500(err)
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return srv500(err)
	}
	return srvJSON(200, Obj{
		{"deleted", affected}, {"table", api}, {"pk", pk}, {"id", id},
	}, 0, true) // compact, trailing "\n"
}

// handleAPIRead is the GET-ish tail of dispatch: the tables list, a single row by id, a paginated
// list, or the unknown-table 404. All of these end in the final pretty echo.
func (s *Server) handleAPIRead(db *DB, r *http.Request, api string, tableList []string, tableSet map[string]bool) Reply {
	if api == "" || api == "tables" {
		return srvJSON(200, Obj{{"tables", tableList}}, jsonPretty|jsonUnescapedSlashes, true)
	}
	if !tableSet[api] {
		return srvJSON(404, Obj{
			{"error", "unknown table"}, {"table", api}, {"tables", tableList},
		}, jsonPretty|jsonUnescapedSlashes, true)
	}

	_, colset, firstPK, _, err := s.tableInfo(db, api)
	if err != nil {
		return srv500(err)
	}

	// Single row by primary key.
	if id, ok := srvQueryVal(r, "id"); ok && firstPK != "" {
		rows, err := srvQueryRows(db, `SELECT * FROM "`+api+`" WHERE "`+firstPK+`" = ?`, bindText(id))
		if err != nil {
			return srv500(err)
		}
		if len(rows) == 0 {
			return srvJSON(404, Obj{{"error", "not found"}, {"table", api}, {"id", id}}, jsonPretty|jsonUnescapedSlashes, true)
		}
		return srvJSON(200, Obj{{"table", api}, {"pk", firstPK}, {"row", rows[0]}}, jsonPretty|jsonUnescapedSlashes, true)
	}

	// Filtered / paginated list.
	where := []string{}
	filterKeys := []string{}
	args := []any{}
	for _, kv := range srvOrderedQuery(r.URL.RawQuery) {
		k, v := kv[0], kv[1]
		if colset[k] && !s.reserved[k] {
			where = append(where, `"`+k+`" = :f_`+k)
			args = append(args, sql.Named("f_"+k, bindText(v)))
			filterKeys = append(filterKeys, ":f_"+k)
		}
	}
	wsql := ""
	if len(where) > 0 {
		wsql = " WHERE " + strings.Join(where, " AND ")
	}
	order := ""
	if o, ok := srvQueryVal(r, "order"); ok {
		parts := strings.Split(o, ".")
		ocol := parts[0]
		dir := "ASC"
		if len(parts) > 1 && strings.ToLower(parts[1]) == "desc" {
			dir = "DESC"
		}
		if colset[ocol] {
			order = ` ORDER BY "` + ocol + `" ` + dir
		}
	}
	per := int64(50)
	if v, ok := srvQueryVal(r, "per"); ok {
		per = srvClamp(phpIntval(v), 1, 500)
	} else if v, ok := srvQueryVal(r, "limit"); ok {
		per = srvClamp(phpIntval(v), 1, 500)
	}
	pg := int64(1)
	if v, ok := srvQueryVal(r, "p"); ok {
		if iv := phpIntval(v); iv > 1 {
			pg = iv
		}
	}
	off := (pg - 1) * per

	total, err := srvScalarInt(db, `SELECT COUNT(*) FROM "`+api+`"`+wsql, args...)
	if err != nil {
		return srv500(err)
	}
	list := `SELECT * FROM "` + api + `"` + wsql + order +
		` LIMIT ` + strconv.FormatInt(per, 10) + ` OFFSET ` + strconv.FormatInt(off, 10)
	rows, err := srvQueryRows(db, list, args...)
	if err != nil {
		return srv500(err)
	}

	pages := int64(0)
	if total > 0 {
		pages = (total + per - 1) / per // (int)ceil($total / max(1,$per)), per >= 1
	}
	var pkVal any = firstPK
	if firstPK == "" {
		pkVal = nil // rest.php leaves $pk null when the table has no pk
	}
	return srvJSON(200, Obj{
		{"table", api}, {"pk", pkVal}, {"total", total}, {"page", pg}, {"per", per},
		{"pages", pages}, {"filter", filterKeys}, {"rows", rows},
	}, jsonPretty|jsonUnescapedSlashes, true)
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Page surface — ?page=tags is the ENGINE; every other key is still a seam.
//
// boot/router.php falls through to Controller::control(), the full PHP CMS front controller. Most of
// that is not reproducible in Go, and pretending otherwise would fabricate output — so the catalog
// branch below mirrors what it honestly can (HTTP status and Content-Type) over a structurally-honest
// table list, clearly marked.
//
// ?page=tags is the exception, and the whole of ticket #280: the tags package (#226) is a real port
// of the PHP tag engine, so that key is answered by RUNNING it rather than by describing it.
//
// The two branches deliberately open DIFFERENT things, and neither opens what it does not use:
//
//   - the catalog needs a db.go handle (s.tables), so handleCatalogPage opens one;
//   - the tags branch needs NONE. The engine opens its own sqlite handle per render, read-only
//     (engine.go's openDB), and this file hands it a path, not a connection.
//
// So the shared Open() the placeholder sat under moved DOWN into the catalog branch that actually
// reads it. That is not cosmetic: db.go's Open() is READ-WRITE (Open -> open(path, path), not
// OpenImmutable), and sqlite CREATES the file when it is missing — measured in this worktree, a
// fresh empty directory + Open("<dir>/missing.sqlite") returns a nil error and leaves
// missing.sqlite behind. Under the old shape, GET /?page=tags against a server whose DBPath did not
// exist CREATED an empty database on a page that never touched the handle. Now it creates nothing:
// probed in isolation this session, an empty directory listed before and after
// GET /?page=tags&tag=TicketList is still empty, and the request is a 200 carrying the engine's
// render. The catalog branch keeps the old behavior exactly, creation included.
//
// Catalog statuses are unchanged: Open() error -> 500, s.tables() error -> 500, else 200 + the same
// bytes. (In practice the 500 comes from tables(), because Open() is lazy — pointed at a file of
// garbage it still returns a nil error, and "file is not a database (26)" surfaces on the first
// query. Both branches were already there and both still are.)
// ─────────────────────────────────────────────────────────────────────────────────────────────────

func (s *Server) handlePage(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=UTF-8")

	switch srvQueryOr(r, "page", "") {
	case "tags":
		s.handleTagsPage(w, r)
	default:
		s.handleCatalogPage(w, r)
	}
}

// tagsConfig builds the engine's Config for this server: the engine's own derivation from the app
// root (tags.DefaultConfig — TAGS_DIR, and the forge/mem/omni reflection dbs from the environment,
// exactly as boot/configure.php derives them), with ONE field pinned.
//
// SQLite is overridden to DBPath because DBPath is CONGRUENCY_SQLITE — "the one sqlite file both
// engines read" (see DBPath). tags.DefaultConfig would otherwise re-derive it from TagsAppRoot via
// configure.php:42 and land on the same file in the live layout; pinning it means a caller who
// points this server at a different db (a test fixture, a replica) gets the tag engine reading that
// db too, instead of the two halves silently reading different files.
//
// Immutable is deliberately left false, i.e. the engine opens `mode=ro`. The trade engine.go's
// openDB documents is that `immutable=1` creates no -wal/-shm sidecars but reads STALE data under
// concurrent writers — which the state db has (engine.go's queryAll comment says so) — while
// `mode=ro` reads what PHP reads and can spawn sidecars on a WAL database. Fresh reads win: a
// long-lived server that serves stale pages is a correctness bug, whereas the sidecars are not a
// side effect this ticket forbids (buildRest already opens this very db READ-WRITE via Open() on
// every REST request, so mode=ro is the lighter of the two opens this server performs).
//
// In this deployment the trade does not even arise: the real state db is journal_mode=delete, not
// WAL, so mode=ro spawns nothing. Probed in isolation this session — the db's directory listed
// before and after a ?page=tags&tag=TicketList render was byte-for-byte the same entries, and so was
// the empty-directory case above.
func (s *Server) tagsConfig() tags.Config {
	cfg := tags.DefaultConfig(s.cfg.TagsAppRoot)
	cfg.SQLite = s.cfg.DBPath
	return cfg
}

// handleTagsPage is ticket #280: ?page=tags&tag=<T> -> the #226 tag engine.
//
// THE GATE — "?page=tags&tag=<T> reaches the engine for EVERY REGISTERED TAG" — rests on one
// property: tags.RenderTag is the registry lookup itself. tags.IsPorted and tags.RenderTag read the
// same map (engine.go's `registry`, whose keys are tags.PortedTags()), and RenderTag renders the tag
// standalone — `new $sel(null)`, the shape TagList.php:63-72 uses — reading NEITHER the Documents
// table NOR TAGS_DIR. So for a registered T there is no missing file, no absent state db and no
// misconfigured app root that can route the request around the engine. That is why this branch calls
// RenderTag directly rather than tags.Render:
//
//	tags.Render is the fuller mirror of the PHP router (?page=tags is a DOCUMENT lookup whose stored
//	template holds <<<TagList>>>, which the engine expands into the gallery). But it needs the
//	Documents row to exist, and the gallery it reaches then whitelists ?tag= against a TAGS_DIR
//	filesystem scan. Either input being absent turns a registered tag into a 404 or an "Unknown tag"
//	notice with the tag never rendered — the gate failing on an input the gate does not mention.
//	RenderTag has neither dependency, so the gate holds on its own terms.
//
// Everything that is NOT a registered tag — no ?tag= at all, a tag the scan lists but #226 has no
// port for, an unknown name — is answered by rendering the gallery (TagList), which is itself a
// registered tag. That is not a fallback invented here: TagList::get_document is the PHP's own
// ?page=tags surface, and it already reports each of those cases in the engine's own words (the tag
// list; notPortedHTML's marked divergence notice; "Unknown tag: <name>"). Reporting them here would
// duplicate the engine and risk contradicting it.
//
// Status and Content-Type are the placeholder's: 200 and text/html; charset=UTF-8 (set by
// handlePage, before this runs, for every page key).
func (s *Server) handleTagsPage(w http.ResponseWriter, r *http.Request) {
	tag, hasTag := srvQueryVal(r, "tag")

	// Which tag the engine runs: the requested one when it is REGISTERED, else the gallery.
	sel := "TagList"
	if hasTag && tags.IsPorted(tag) {
		sel = tag
	}

	body, ok := tags.RenderTag(s.tagsConfig(), sel, r.URL.Query())
	if !ok {
		// Unreachable by construction: sel is either IsPorted-checked above or "TagList", which is
		// in tags.PortedTags(). Kept as a real branch rather than a discarded bool so that an engine
		// that ever drops a name from its registry says so here instead of serving a blank 200.
		w.WriteHeader(http.StatusNotFound)
		fmt.Fprintf(w, "<!-- congruency-go tags wiring (#280) -->\n<!doctype html>\n"+
			"<title>no Go port: %s</title>\n<h1>no Go port: %s</h1>\n"+
			"<p>The tag engine has no registered port for this tag.</p>\n",
			htmlEscape(sel), htmlEscape(sel))
		return
	}

	title := "tags"
	if tag != "" {
		title = "tag: " + tag
	}
	w.WriteHeader(http.StatusOK)
	var b strings.Builder
	b.WriteString("<!-- congruency-go (#280): the body below is the TAG ENGINE's render (congruency-go/tags,\n")
	b.WriteString("     engine.go), not this file's. The doctype/title/h1 frame around it is this server's own:\n")
	b.WriteString("     the CMS Controller::control() page chrome is still not reproduced here. -->\n")
	b.WriteString("<!doctype html>\n<title>" + htmlEscape(title) + "</title>\n<h1>" + htmlEscape(title) + "</h1>\n")
	b.WriteString(body)
	if !strings.HasSuffix(body, "\n") {
		b.WriteString("\n")
	}
	io.WriteString(w, b.String())
}

// handleCatalogPage is every page key that is not "tags": the structurally-honest table list. This
// is unchanged from the pre-#280 default branch — same opens, same statuses, same bytes.
func (s *Server) handleCatalogPage(w http.ResponseWriter, r *http.Request) {
	db, err := Open(s.cfg.DBPath)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		fmt.Fprintf(w, "<!-- congruency-go page seam -->\n<h1>error</h1><p>%s</p>\n", htmlEscape(err.Error()))
		return
	}
	defer db.Close()

	tableList, _, err := s.tables(db)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		fmt.Fprintf(w, "<!-- congruency-go page seam -->\n<h1>error</h1><p>%s</p>\n", htmlEscape(err.Error()))
		return
	}
	w.WriteHeader(http.StatusOK)
	var b strings.Builder
	b.WriteString("<!-- congruency-go page seam: the CMS Controller::control() surface is not byte-reproduced here -->\n")
	b.WriteString("<!doctype html>\n<title>congruency</title>\n<h1>congruency</h1>\n<ul>\n")
	for _, t := range tableList {
		b.WriteString("  <li>" + htmlEscape(t) + "</li>\n")
	}
	b.WriteString("</ul>\n")
	io.WriteString(w, b.String())
}

func htmlEscape(s string) string {
	r := strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;", `"`, "&quot;")
	return r.Replace(s)
}

// telemetryHook is the db.DB.TelemetryIngest seam — records a telemetry.record beacon via the log hook.
func (s *Server) telemetryHook(kind, route, message, detail string) {
	s.log(LogEvent{
		Time: time.Now(), Kind: "telemetry", Surface: "telemetry", Route: route,
		Detail: fmt.Sprintf("kind=%s message=%q detail=%q", kind, message, detail),
	})
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// DB helpers (this file's queries against the shared handle).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// tables builds the public ?api allowlist: every non-sqlite_ table, ordered by name, minus the
// denylist — rest.php's $tables. Returns both the ordered slice (for array_keys output) and a set.
func (s *Server) tables(db *DB) ([]string, map[string]bool, error) {
	rows, err := db.conn.QueryContext(context.Background(),
		"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
	if err != nil {
		return nil, nil, err
	}
	defer rows.Close()
	deny := map[string]bool{}
	for _, d := range s.cfg.Denylist {
		deny[d] = true
	}
	var list []string
	set := map[string]bool{}
	for rows.Next() {
		var n string
		if err := rows.Scan(&n); err != nil {
			return nil, nil, err
		}
		if deny[n] {
			continue
		}
		list = append(list, n)
		set[n] = true
	}
	if err := rows.Err(); err != nil {
		return nil, nil, err
	}
	if list == nil {
		list = []string{} // encode as [], never null
	}
	return list, set, nil
}

// tableInfo runs PRAGMA table_info and returns the columns (in cid order), the column set, the FIRST
// pk column name (rest.php's GET path, which breaks at the first pk) and the LAST pk column name (the
// update/delete path, which loops without breaking). "" means no pk.
func (s *Server) tableInfo(db *DB, table string) (cols []string, colset map[string]bool, firstPK, lastPK string, err error) {
	rows, err := srvQueryRows(db, `PRAGMA table_info("`+table+`")`)
	if err != nil {
		return nil, nil, "", "", err
	}
	colset = map[string]bool{}
	firstSet := false
	for _, ro := range rows {
		o, ok := ro.(Obj)
		if !ok {
			continue
		}
		nameV, _ := o.Get("name")
		name := phpStrval(nameV)
		cols = append(cols, name)
		colset[name] = true
		pkV, _ := o.Get("pk")
		if phpIntval(pkV) > 0 {
			if !firstSet {
				firstPK = name
				firstSet = true
			}
			lastPK = name
		}
	}
	return cols, colset, firstPK, lastPK, nil
}

// srvQueryRows runs a query and returns its rows in PHP fetchAll(PDO::FETCH_ASSOC) shape via db.go's
// scanRows (ordered Obj rows, duplicate-column collapse, driver-value typing).
func srvQueryRows(db *DB, query string, args ...any) (Arr, error) {
	rows, err := db.conn.QueryContext(context.Background(), query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanRows(rows)
}

// srvScalarInt runs a single-value query and returns it as int64 (rest.php's (int)$st->fetchColumn()).
func srvScalarInt(db *DB, query string, args ...any) (int64, error) {
	var n int64
	err := db.conn.QueryRowContext(context.Background(), query, args...).Scan(&n)
	if errors.Is(err, sql.ErrNoRows) {
		return 0, nil
	}
	return n, err
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Small helpers.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// srv500 is the dispatch catch: 500 with a pretty {"error": msg} body + "\n".
func srv500(err error) Reply {
	b, e := phpJSONEncode(Obj{{"error", err.Error()}}, jsonPretty|jsonUnescapedSlashes)
	if e != nil {
		b = nil
	}
	return Reply{Status: 500, Body: append(b, '\n')}
}

// srvJSON encodes an envelope the way a rest.php echo site does: the given json_encode flags, and a
// trailing "\n" iff the PHP site appended one. When json_encode would fail (invalid UTF-8, INF/NAN),
// PHP echoes false -> the empty string, so the body is just the "\n" (or nothing) — reproduced here.
func srvJSON(status int, v any, flags int, nl bool) Reply {
	b, err := phpJSONEncode(v, flags)
	if err != nil {
		b = nil
	}
	if nl {
		b = append(b, '\n')
	}
	return Reply{Status: status, Body: b}
}

func srvIsWrite(method string) bool {
	switch method {
	case "POST", "PUT", "PATCH", "DELETE":
		return true
	}
	return false
}

func srvClamp(v, lo, hi int64) int64 {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

// srvQueryVal returns the LAST value of a query key (PHP $_GET semantics) and whether it was present.
func srvQueryVal(r *http.Request, key string) (string, bool) {
	vs, ok := r.URL.Query()[key]
	if !ok || len(vs) == 0 {
		return "", false
	}
	return vs[len(vs)-1], true
}

func srvQueryOr(r *http.Request, key, def string) string {
	if v, ok := srvQueryVal(r, key); ok {
		return v
	}
	return def
}

// srvOrderedQuery parses a raw query string preserving FIRST-occurrence key order with LAST value —
// PHP's $_GET population order, which the ?api `filter` output and WHERE clause order depend on.
func srvOrderedQuery(raw string) [][2]string {
	seen := map[string]int{}
	var out [][2]string
	for _, pair := range strings.Split(raw, "&") {
		if pair == "" {
			continue
		}
		k, v, _ := strings.Cut(pair, "=")
		dk, err := url.QueryUnescape(k)
		if err != nil {
			dk = k
		}
		dv, err := url.QueryUnescape(v)
		if err != nil {
			dv = v
		}
		if i, ok := seen[dk]; ok {
			out[i][1] = dv
		} else {
			seen[dk] = len(out)
			out = append(out, [2]string{dk, dv})
		}
	}
	return out
}

// srvWriteBody decodes a request body the way rest.php's `$data = json_decode(...); if (!is_array($data))`
// gate treats it: a JSON object -> ordered Obj (ok); a JSON array -> is_array true but yields no
// matching columns, modelled as an empty Obj (ok); anything else / malformed -> not an array (!ok,
// the "body must be a JSON object" 400).
func srvWriteBody(b []byte) (Obj, bool) {
	v, err := decodeJSONOrdered(b)
	if err != nil {
		return nil, false
	}
	switch x := v.(type) {
	case Obj:
		return x, true
	case Arr:
		return Obj{}, true
	default:
		return nil, false
	}
}

// decodeJSONOrdered decodes JSON preserving object key order (into Obj) with PHP json_decode number
// semantics (integral -> int64, else float64), so write replies that echo the body ('used'/'set')
// keep the body's field order. A JSON object -> Obj, array -> Arr, scalars -> Go primitives.
func decodeJSONOrdered(b []byte) (any, error) {
	dec := json.NewDecoder(strings.NewReader(string(b)))
	dec.UseNumber()
	v, err := srvParseJSON(dec)
	if err != nil {
		return nil, err
	}
	return v, nil
}

func srvParseJSON(dec *json.Decoder) (any, error) {
	t, err := dec.Token()
	if err != nil {
		return nil, err
	}
	switch tok := t.(type) {
	case json.Delim:
		switch tok {
		case '{':
			o := Obj{}
			for dec.More() {
				kt, err := dec.Token()
				if err != nil {
					return nil, err
				}
				key, ok := kt.(string)
				if !ok {
					return nil, fmt.Errorf("object key not a string")
				}
				val, err := srvParseJSON(dec)
				if err != nil {
					return nil, err
				}
				o = o.Set(key, val)
			}
			if _, err := dec.Token(); err != nil { // consume '}'
				return nil, err
			}
			return o, nil
		case '[':
			a := Arr{}
			for dec.More() {
				val, err := srvParseJSON(dec)
				if err != nil {
					return nil, err
				}
				a = append(a, val)
			}
			if _, err := dec.Token(); err != nil { // consume ']'
				return nil, err
			}
			return a, nil
		}
		return nil, fmt.Errorf("unexpected delimiter %v", tok)
	case json.Number:
		return phpDecodeValue(tok), nil // integral -> int64, else float64
	case string:
		return tok, nil
	case bool:
		return tok, nil
	case nil:
		return nil, nil
	}
	return nil, fmt.Errorf("unexpected JSON token %T", t)
}
