// engine.go — congruency-go SCRIPTING LAYER (ticket #226).
//
// # WHAT THIS IS
//
// The pure-Go half of congruency's tag/scripting plane: the TAG ENGINE
// (Tag_Wrapper::execute_all_tags and the parser beneath it) plus ports of the dev tags
// (invocators), reading the SAME congruency.sqlite and the SAME tag directory the PHP reads.
//
// THE CONTRACT: byte-identical HTML. The PHP echoes its render; this file reproduces those bytes.
// Everything below that looks quirky is quirky because the PHP is: THE PHP IS THE SPEC, and where
// they disagree the Go is wrong.
//
// ── The layer this file mirrors, file by file ───────────────────────────────────────────────────
//
//	lib/TagLoader/Tag/Tag_Wrapper.php          execute_all_tags / identify_tag / replace_tag
//	lib/TagLoader/Parser/Tag_Parser.php        extract_tag_name / get_tag_identifier
//	lib/TagLoader/Arguments/TagArguments.php   argumentFactory / top / pop / removeParenthesis
//	boot/constants.default.json                the tag regex + KEY_PREFIX/KEY_SUFFIX (lines 29-36)
//	boot/configure.php                         CONGRUENCY_SQLITE / TAGS_DIR (lines 42-43)
//	lib/Controller/Controller.php              control() -> validatePageKey -> display()
//	lib/Modules/.../Document/Document.php      get_document() / __toString() -> execute_all_tags
//	lib/Modules/.../DAO/DocumentDAO.php        the Documents INNER JOIN Document_Templates SELECT
//	invocators/tags/dev/*.php                  the tags themselves
//
// All paths above are relative to the app root, which in this checkout is
// checkouts/current/congruency/ (see Config.AppRoot).
//
// ── THE TWO RECURSION GUARDS (the ticket names both) ────────────────────────────────────────────
//
// The ticket asks for "execute_all_tags recursion with the htmlspecialchars recursion guard".
// Those are TWO distinct, cooperating mechanisms, and this file reproduces both:
//
//  1. THE DEPTH CAP — a hard bound inside the engine. execute_all_tags recurses into a tag's
//     RENDERED OUTPUT looking for more tags. With no bound, a document whose stored Title is
//     itself "<<<TitleTag>>>" makes the tag emit its own trigger and the engine recurses until
//     memory is exhausted — that is BUG-06 (dev/bugs/BUGS.md:25, repro at
//     dev/bugs/repro/bug06_tag_recursion.php). The live Tag_Wrapper fixes it with a depth cap:
//
//     if ($depth >= 64) { return $result_string; }   // Tag_Wrapper.php:65
//
//     ...which leaves any deeper nested tag as LITERAL text. MaxTagDepth below is that 64, and
//     ExecuteAllTags checks it at exactly the same point — AFTER get_document(), BEFORE scanning
//     the output — so the boundary render matches byte for byte.
//
//     NB: the OTHER Tag_Wrapper copy in this repo (tooling/congruencey/lib/TagLoader/Tag/
//     Tag_Wrapper.php:63) is the UNFIXED pre-BUG-06 original with no depth parameter at all. The
//     copy under checkouts/current/congruency/ — the app boot/router.php actually serves — is the
//     fixed one, and is what this file mirrors.
//
//  2. THE htmlspecialchars GUARD — the escape-first discipline in the tags. The depth cap bounds
//     a runaway, but the reason a runaway is rare is that every tag escapes DB/-derived text
//     before returning it, so a stored "<<<Tag>>>" comes back as "&lt;&lt;&lt;Tag&gt;&gt;&gt;",
//     which identify_tag can no longer match — the stored tag stays inert. The tags state this as
//     a standing rule; e.g. TicketList.php:101-107 ("ticket titles may themselves contain <<<Tag>>>
//     syntax ... EVERY value is passed through htmlspecialchars() before it is emitted — otherwise
//     execute_all_tags would re-parse the output and recurse the tag engine. Do not remove an
//     esc() call."), and the same rule in TreeView.php:20-22, BugCatalog.php:20-22,
//     ForgeView.php:20-22, MemGraph.php:25-29, OmniExplorer.php:22-24, SemanticSearch.php:24-27.
//     Every esc() in this file is that guard; phpHTMLSpecialChars is byte-exact with PHP's
//     htmlspecialchars($s, ENT_QUOTES) so the guard escapes the identical set.
//
// ── WHY package tags, and why nothing here imports congruency-go ────────────────────────────────
//
// congruency-go's root is `package main` (db.go:137, server.go:43). A Go main package cannot be
// imported, and #226's deliverable is this file alone ("touch nothing else") — so this package
// cannot reuse db.go's *DB or server.go's helpers, and server.go cannot be edited to call in.
// This file is therefore a SELF-CONTAINED LEAF: it re-derives the small amount of sqlite plumbing
// it needs (openDB/queryRows below), and exports Handler/Render/RenderTag so the page seam in
// server.go:636-670 can be pointed at it by whoever owns that file, in one line, with no change
// here. Nothing in this package writes to the DB or to disk.
//
// "THIS FILE ALONE" IS A PER-TICKET DELIVERABLE RULE, NOT A PACKAGE RULE — and the distinction
// matters now, so read it before you think two parts of this header disagree. Each of #226 and
// #281 was scoped to engine.go and could add no second file, which is why the sqlite plumbing is
// re-derived here and why the invariants live in SelfCheck instead of a _test.go. The PACKAGE has
// never been limited to one file, and #281 exists precisely to make more files the normal way to
// grow it: from #246 on, every newly ported tag is its OWN congruency-go/tags/<Tag>.go that
// self-registers from init() and changes nothing in here. See "The registry" section below.
//
// ── RE2 HAS NO LOOKAROUND: three hand-ports, not regex translations ─────────────────────────────
//
// Go's regexp is RE2, which by design has no lookahead or lookbehind. Three PHP patterns use them,
// so they are implemented directly rather than transliterated. Each is proved by SelfCheck:
//
//	GET_TAG_IDENTIFIER  /([a-zA-Z0-9]+\s?(?=\(\s?[a-zA-Z0-9]*\s?\)))|(\s?[a-zA-Z0-9]+\s?)/
//	                    -> getTagIdentifier()  (lookAHEAD)
//	TicketList::sigKey  /(?<![#\d])\d+/ -> '#'  -> foldDigitRuns(s, "#")   (lookBEHIND)
//	TicketList::sigLabel/(?<![#\d])\d+/ -> '…'  -> foldDigitRuns(s, "…")   (lookBEHIND)
//
// The remaining patterns are RE2-clean and are compiled from the SAME constant text the PHP uses
// (see tagPattern / functionArgument below); only PCRE's "\>" (a literal '>') is unescaped for RE2.
//
// ── WHAT WAS AND WAS NOT VERIFIED IN THIS CHECKOUT (read this before trusting a claim) ──────────
//
// This file was NOT byte-diffed against a live PHP render, because neither side of that diff can
// be produced in this worktree:
//
//   - THERE IS NO PHP. The ticket names tooling/congruencey-harness/php/php; that path does not
//     exist here and `php` is not on PATH. It is PROVISIONED, not committed — .gitignore:10 lists
//     "/tooling/congruencey-harness/php/". (db.go's header cites the same binary at PHP 8.4.23, so
//     it existed when #224 ran; it is simply absent now.)
//   - THERE IS NO DB. The tags read CONGRUENCY_SQLITE = <app>/../state/congruency.sqlite
//     (configure.php:42) = checkouts/current/state/congruency.sqlite. That file is not in the
//     worktree either — .gitignore:11 lists it. No *.sqlite exists anywhere under the repo root.
//
// So "renders IDENTICAL HTML to the PHP" is, in this file, a claim derived by PORTING THE SOURCE
// LINE BY LINE — not a measured result, and it is not reported as one.
//
// Each block below is attributed to the ticket whose session actually ran it. Nothing here is
// carried forward as "verified" by a later ticket that did not re-run it.
//
// WHAT #226 RAN when it wrote this port (go1.26.5):
//
//   - `go build` and `go vet` clean.
//   - SelfCheck() — every parser/engine/PHP-primitive invariant below, computed against values read
//     off the PHP source, including both recursion guards and all three lookaround ports. It found
//     a real off-by-one in a draft of its own depth-cap expectation, which is why that check now
//     spells the arithmetic out.
//   - Scan() against the REAL invocators/tags tree: 45 tags, matching a `grep -rl Tag_Interface`
//     of the same directory. (That is where the "30 dev tags" intuition breaks — see COVERAGE.)
//   - RenderTag for all 10 ported tags against a synthetic sqlite db built to the real schema —
//     each runs, hits its SQL and emits HTML; no raw "<<<" survives into any render.
//   - Render(?page=tags&tag=TicketList) end to end: the 'tags' document's template expanded by the
//     engine, a ticket title containing a literal <<<TicketList>>> coming back escaped and inert,
//     and the flood-grouping folding 3 rows while leaving a one-word 'Research:' stem ungrouped.
//   - The open-mode side-effect + staleness probe quantified in openDB's comment.
//
// WHAT #281 RE-RAN for the registry refactor (go1.26.5, this session). #281 changed HOW the
// registry is filled, so what it had to prove is that the observable surface did not move:
//
//   - `go build ./...`, `go vet ./...` and `gofmt -l` clean, before and after the refactor.
//   - SelfCheck() green, now including the registry invariants at the end of SelfCheck (each of
//     the 10 present and constructible, PortedTags sorted and deduped, IsPorted's negatives, and
//     Register's three panics leaving the registry unmutated). Those invariants are deliberately
//     ADDITIVE-SAFE — subset and floor, never equality — so that #246+ adding a <Tag>.go keeps
//     SelfCheck green without editing this file; the comment on them says why that is required.
//   - THE EQUIVALENCE THAT MATTERS: the whole observable registry surface dumped from the
//     PRE-refactor file and the POST-refactor file and diffed — SelfCheck's result, PortedTags()
//     in order, IsPorted() over all 45 names Scan lists plus negatives, and newTag()'s (ok,
//     concrete Go type) for every ported name with both nil and real arguments. The two dumps are
//     IDENTICAL, which is what "preserve IsPorted/lookup behavior byte-for-byte" means here.
//   - Scan() against the REAL invocators/tags tree again: still 45, so the COVERAGE arithmetic
//     below (45 listed, 10 ported, 35 not) still holds after the refactor.
//   - `go test -race` over concurrent newTag/IsPorted/PortedTags with a Register racing them:
//     clean, which is the claim registryMu is there to earn.
//
// NOT run, and therefore NOT claimed: a byte-diff against PHP, for any tag — by #226 or by #281.
// #281 also did not re-run #226's synthetic-db RenderTag sweep or its end-to-end Render (both need
// a DB to be built up first); it proves the registry's own surface instead, which is the only thing
// it touched. php and congruency.sqlite are both still absent from this checkout, re-checked this
// session — so that gate is no more runnable now than it was for #226.
//
// To CLOSE the gate (the byte-diff #226 actually asks for) once php + the state DB are provisioned:
//
//	go run ./tags -equivalence -php http://127.0.0.1:8899 -db <state>/congruency.sqlite
//
// ...is NOT provided, because this package is a library and neither #226 nor #281 could add a
// second file to hold a main() or a _test.go (see "THIS FILE ALONE" above — a ticket whose
// deliverable covers those files may add them). Drive it instead from the repo's established
// harness pattern — the
// PHP-vs-Go byte sweep in congruency-go/equivalence_test.go (#227), which fetches each route from
// the live PHP twice around the Go run (the "stability sandwich", equivalence_test.go:22-27) so a
// concurrent write reports VOLATILE instead of false-failing. The tag analogue is:
//
//	php1 := GET <php>/?page=tags&tag=<T>
//	go   := tags.RenderTag(cfg, "<T>", url.Values{"page":{"tags"},"tag":{"<T>"}})
//	php2 := GET <php>/?page=tags&tag=<T>
//	php1 == php2 && go == php1   =>  <T> is equivalent
//
// PortedTags() below returns exactly the set of T for which that diff is meaningful today.
//
// ── COVERAGE: which tags are ported, and which are NOT ──────────────────────────────────────────
//
// #226 names nine tags explicitly and closes with "...". All nine are ported, plus TagList — the
// gallery that IS the ?page=tags surface. That is 10 of the 45 tags the gate can select.
//
// WHY 45 AND NOT 31. TAGS_DIR is invocators/tags/ and TagList::scan RECURSES it, so the gallery
// covers every subdirectory — dev/ (31 files), plus Maker/, document/, forms/, login/, store/,
// test_tags/, user/, utilities/ and MemoryList.php at the top. Measured in this checkout this
// session: 45 files contain "Tag_Interface", and Scan returns all 45 (the ticket's parenthetical
// names only tags from dev/). Scan is filesystem-driven precisely so this number tracks the tree
// instead of a hardcoded list that would rot.
//
// Only a tag with a Go port can be RENDERED. Selecting an unported tag returns an explicit, marked
// divergence notice (notPortedHTML); it does NOT fabricate a render, and it does NOT reuse PHP's
// "Tag class not loadable." message — PHP loads those classes fine, so borrowing that message
// would be a false claim about the PHP dressed up as equivalence.
//
//	PORTED (10) — the ticket's nine, plus the gallery:
//	    BugCatalog, CategoryBrowse, ForgeView, FormTag, MemGraph, OmniExplorer, SemanticSearch,
//	    TagList, TicketList, TreeView                             (== PortedTags(), which is the
//	                                                                 authority; this list is a copy)
//	NOT PORTED (35):
//	    AnnotateHandler, Annotations, ApiReference, BodyTag, BugDemo, BugReport, Catalog_Controller,
//	    CategoryPages, CategoryView, Config_Form_Invocator, ContentTag, DatabaseInfo, DocList,
//	    GraphNode, Login, Logout, MemoryList, NewCategoryHandler, PageList, PriceMakerControl,
//	    ProductView, RepoDocs, ShadowForge, ShowPost, SiteMap, SourceList, Style, TagPageHandler,
//	    TelemetryBeacon, TestTagA, TicketGraph, TicketGraphList, TicketLogger, TitleTag, ToggleLogin
//
// A curiosity the scan makes visible, and a good check on the constants above: Catalog_Controller
// and Config_Form_Invocator carry UNDERSCORES, and FUNCTION_NAME is [a-zA-Z]+ — so neither can ever
// be invoked from document content as <<<Catalog_Controller>>>; the engine will not match it and
// leaves it literal. The gallery still lists and renders them, because ?tag= selects by FILENAME
// and never goes through the tag parser at all.
//
// ── DELIBERATE, DOCUMENTED DIVERGENCES (all three are safety, not sloppiness) ───────────────────
//
//  1. UNKNOWN TAG CLASS. PHP's get_tag_wrapper does `new $tag_class(...)` on a class the loader
//     could not find, which throws Error and — since execute_all_tags has NO error boundary
//     (FormTag.php:53-55 says so) — takes the whole page down with a fatal. Go returns a marked
//     literal (unknownTagHTML) instead of panicking: a crash is a #226 finding by definition, and
//     an engine that dies on bad stored content is not a better port than one that says so.
//  2. DB OPEN. PHP does `new PDO('sqlite:'.$path)` READ-WRITE, which CREATES an empty db when the
//     path is missing. openDB opens read-only and never creates. See openDB's comment for why the
//     WAL forces a choice between `mode=ro` (correct reads, spawns -wal/-shm) and `immutable=1`
//     (zero side effects, but stale under the concurrent writers this DB has) — and why the
//     default is the one that reads what PHP reads. Config.Immutable selects the other.
//  3. NO SESSION / POM. FORM_MANAGER lives in the PHP session's PersistentObjectManager. FormTag's
//     FORM_MANAGER branch is therefore reachable only via Config.FormManager; with none set,
//     FormTag renders its no-manager note, which is itself a faithful PHP branch (FormTag.php:139-141).
//
// Every claim above was read off the cited file in THIS checkout this session.
package tags

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	_ "modernc.org/sqlite"
)

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Constants — boot/constants.default.json:29-36, verbatim.
//
// The PHP builds its scanner by CONCATENATING four constants:
//
//	TAG_KEY_PREFIX . FUNCTION_NAME . FUNCTION_ARGUMENTS . TAG_KEY_SUFFIX      (Tag_Wrapper.php:57)
//	  "/<<<"  +  "[a-zA-Z]+"  +  "(\([A-Za-z0-9]*\))*"  +  "\>>>/"
//	= /<<<[a-zA-Z]+(\([A-Za-z0-9]*\))*\>>>/
//
// The leading "/" and trailing "/" are PCRE delimiters, not pattern. PCRE's "\>" is a literal '>'
// (escaping a non-special char is a no-op), so the RE2 form is the same language with "\>" -> ">".
//
// TWO THINGS THAT LOOK LIKE TYPOS AND ARE NOT:
//   - FUNCTION_NAME is "[a-zA-Z]+" — NO digits and NO underscore. A tag named Foo2 or Foo_Bar can
//     never be invoked from document content; the engine will not see it and leaves it literal.
//   - FUNCTION_ARGUMENTS is "[A-Za-z0-9]*" — no underscore, no hyphen. FormTag.php:44-51 documents
//     the consequence: the stored form "ConfigForm-6" is a valid form key that CANNOT be written as
//     <<<FormTag(ConfigForm-6)>>>, because the parser will not match it.
//
// (A second constants copy — tooling/congruencey/etc/Constants.php:209-212 — widens both to include
// '_'. That copy belongs to the OTHER tree, tooling/congruencey/, and is NOT what the live app
// boots: boot/configure.php loads boot/constants.default.json. These are the live values.)
const (
	KeyPrefix = "<<<" // KEY_PREFIX
	KeySuffix = ">>>" // KEY_SUFFIX

	// The raw PHP constant bodies, kept so a reader can match them to the JSON by eye.
	FunctionName      = "[a-zA-Z]+"
	FunctionArguments = `(\([A-Za-z0-9]*\))*`

	// MaxTagDepth is the BUG-06 depth cap: Tag_Wrapper.php:65 `if ($depth >= 64)`.
	MaxTagDepth = 64
)

var (
	// tagPattern is TAG_KEY_PREFIX.FUNCTION_NAME.FUNCTION_ARGUMENTS.TAG_KEY_SUFFIX, assembled from
	// the same constants the PHP concatenates, so the two cannot drift apart silently.
	tagPattern = regexp.MustCompile(KeyPrefix + FunctionName + FunctionArguments + KeySuffix)

	// functionArgument is FUNCTION_ARGUMENT = /\([A-Za-z0-9]*\)/ (constants.default.json:35).
	functionArgument = regexp.MustCompile(`\([A-Za-z0-9]*\)`)

	// digitRun backs the two lookbehind ports (foldDigitRuns). RE2-clean on its own; the lookbehind
	// is applied as a predicate on the match position, not as pattern syntax.
	digitRun = regexp.MustCompile(`[0-9]+`)
)

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Config — the constants boot/configure.php define()s, as data.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// Config is the ambient environment a PHP tag reads through constants, getenv() and the POM.
// The zero value is not useful; build one with DefaultConfig.
type Config struct {
	// AppRoot is ABS_PATH — the app root (configure.php:41). In this repo:
	// <repo>/checkouts/current/congruency.
	AppRoot string

	// SQLite is CONGRUENCY_SQLITE (configure.php:42): <app>/../state/congruency.sqlite.
	SQLite string

	// TagsDir is TAGS_DIR (configure.php:43): <app>/invocators/tags/. TagList::scan walks it.
	TagsDir string

	// ForgeDB, MemGraphDB, OmniDB are the SEPARATE sqlite files the reflection tags open — each
	// resolved in PHP as getenv(X) ?: $HOME/code/installed/jazz-project/config/forge/<file>
	// (ForgeView.php:31-35, MemGraph.php:38-42, OmniExplorer.php:33-37).
	ForgeDB    string
	MemGraphDB string
	OmniDB     string

	// Immutable selects the sqlite open mode; see openDB. false (default) = `mode=ro`, which reads
	// what PHP reads through the WAL. true = `immutable=1`, zero side effects but stale under
	// concurrent writers.
	Immutable bool

	// FormManager is the FORM_MANAGER seam (PersistentObjectManager::getData("FORM_MANAGER")).
	// nil means "no FORM_MANAGER in the POM", which is a real, faithful FormTag branch.
	FormManager FormManager

	// Exec runs a command and returns its stdout. It exists so TreeView's read-only git plumbing is
	// injectable. nil uses os/exec.
	Exec func(name string, args ...string) ([]byte, error)

	// Embed is SemanticSearch's embedding seam (see the Embed type). nil uses ollamaEmbed, the
	// localhost:11434 endpoint the PHP posts to.
	Embed Embed

	// Now is the clock. nil uses time.Now. Only stamp() reads it.
	Now func() time.Time
}

// FormManager is the seam for the PHP FormManager (lib/.../FormManager.php), which FormTag calls
// as $formManager->runForm($id). It is an interface because the PHP form pipeline
// (FormElementDAO -> FormElementBean -> produceElement -> StandardForm) is NOT ported by #226:
// this file's job is the tag engine, and a form pipeline is its own layer. With no FormManager,
// FormTag renders FormTag.php:139-141's note verbatim.
type FormManager interface {
	// RunForm mirrors FormManager::runForm($formKey) — the rendered form HTML, or the
	// FORM_LOAD_FAILURE sentinel when no such form is stored.
	RunForm(formKey string) string
	// LoadFailure mirrors the FORM_LOAD_FAILURE constant runForm returns on an unbuildable form.
	LoadFailure() string
}

// DefaultConfig derives a Config the way boot/configure.php derives its constants: everything from
// the app root, with the forge/mem/omni reflections from the environment when set (the PHP
// getenv() ?: $HOME/... rule).
func DefaultConfig(appRoot string) Config {
	appRoot = strings.TrimSuffix(appRoot, "/")
	home, _ := os.UserHomeDir()
	pick := func(env, def string) string {
		if v := os.Getenv(env); v != "" {
			return v
		}
		return def
	}
	forgeDir := filepath.Join(home, "code/installed/jazz-project/config/forge")
	return Config{
		AppRoot: appRoot + "/",
		// configure.php:42 — state is a SIBLING of the app root, not a child.
		SQLite:     filepath.Join(filepath.Dir(appRoot), "state", "congruency.sqlite"),
		TagsDir:    filepath.Join(appRoot, "invocators", "tags") + "/",
		ForgeDB:    pick("FORGE_DB", filepath.Join(forgeDir, "forge.db")),
		MemGraphDB: pick("MEM_GRAPH_DB", filepath.Join(forgeDir, "mem_graph.db")),
		OmniDB:     pick("OMNI_INDEX_DB", filepath.Join(forgeDir, "omni_index.db")),
	}
}

func (c Config) now() time.Time {
	if c.Now != nil {
		return c.Now()
	}
	return time.Now()
}

func (c Config) exec(name string, args ...string) ([]byte, error) {
	if c.Exec != nil {
		return c.Exec(name, args...)
	}
	return exec.Command(name, args...).Output()
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// PHP primitives — the exact semantics of the PHP functions the tags lean on.
//
// These are the highest-risk part of a byte-equivalence port: each is a place where a "reasonable"
// Go stdlib call is subtly WRONG. Every one below is deliberately NOT the stdlib call.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// phpHTMLSpecialChars is htmlspecialchars($s, ENT_QUOTES) on PHP 8 with the default UTF-8 charset.
// It is THE htmlspecialchars recursion guard (see the file header): it turns a stored "<<<Tag>>>"
// into "&lt;&lt;&lt;Tag&gt;&gt;&gt;", which tagPattern cannot match, so stored tags stay inert.
//
// NOT html.EscapeString: Go escapes ' as "&#39;" and " as "&#34;", PHP as "&#039;" and "&quot;".
// Three of those five differ, so html.EscapeString would corrupt every attribute in every tag.
//
// PHP 8.1+ folds ENT_SUBSTITUTE into the default flags, so an invalid UTF-8 byte becomes U+FFFD
// rather than emptying the whole string (the pre-8.1 behavior). DB text is normally valid UTF-8,
// so this branch is rare — but BugCatalog stores adversarial titles by design (BugCatalog.php:20),
// which is exactly where a stray byte would land.
func phpHTMLSpecialChars(s string) string {
	if utf8.ValidString(s) {
		return phpEscValid(s)
	}
	// ENT_SUBSTITUTE: replace each invalid byte with U+FFFD, then escape.
	var b strings.Builder
	for i := 0; i < len(s); {
		r, size := utf8.DecodeRuneInString(s[i:])
		if r == utf8.RuneError && size == 1 {
			b.WriteRune(0xFFFD)
			i++
			continue
		}
		b.WriteString(s[i : i+size])
		i += size
	}
	return phpEscValid(b.String())
}

// phpEscValid is the escape table itself. ENT_QUOTES = ENT_HTML_QUOTE_DOUBLE|ENT_HTML_QUOTE_SINGLE,
// so both quote forms are escaped; PHP escapes exactly these five and nothing else.
func phpEscValid(s string) string {
	if !strings.ContainsAny(s, `&"'<>`) {
		return s
	}
	var b strings.Builder
	b.Grow(len(s) + 16)
	for i := 0; i < len(s); i++ {
		switch s[i] {
		case '&':
			b.WriteString("&amp;")
		case '"':
			b.WriteString("&quot;")
		case '\'':
			b.WriteString("&#039;") // PHP: &#039; — Go's html pkg emits &#39;
		case '<':
			b.WriteString("&lt;")
		case '>':
			b.WriteString("&gt;")
		default:
			b.WriteByte(s[i])
		}
	}
	return b.String()
}

// phpURLEncode is PHP's urlencode() (RFC1738).
//
// NOT url.QueryEscape: Go leaves '~' unescaped, PHP escapes it to %7E. Everything else about the
// two agrees (including ' ' -> '+'), which is exactly what makes the difference easy to ship by
// accident. PHP leaves ONLY [A-Za-z0-9-_.] alone.
func phpURLEncode(s string) string {
	const hex = "0123456789ABCDEF"
	var b strings.Builder
	b.Grow(len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		switch {
		case c >= 'A' && c <= 'Z', c >= 'a' && c <= 'z', c >= '0' && c <= '9',
			c == '-', c == '_', c == '.':
			b.WriteByte(c)
		case c == ' ':
			b.WriteByte('+')
		default:
			b.WriteByte('%')
			b.WriteByte(hex[c>>4])
			b.WriteByte(hex[c&0x0F])
		}
	}
	return b.String()
}

// phpSubstr is substr($s, $start, $len) for the non-negative, left-anchored cases the tags use.
// PHP substr counts BYTES, not runes — s[:240] on a multibyte string can split a rune, and PHP
// does exactly that (SemanticSearch.php:90 substr($text,0,240), TreeView.php:66 substr($c,0,12)).
// Reproducing the split is the point: a "safe" rune-aware truncation would not match PHP.
func phpSubstr(s string, start, length int) string {
	if start < 0 || start > len(s) {
		return ""
	}
	s = s[start:]
	if length >= 0 && length < len(s) {
		s = s[:length]
	}
	return s
}

// phpString is PHP's (string) cast for the values a PDO FETCH_ASSOC row can hold.
// PHP 8's PDO_SQLite returns NATIVE types (int64 for INTEGER, float64 for REAL, nil for NULL), and
// every tag then does esc((string)$v) on them — so the cast, not the SQL, decides the bytes.
func phpString(v any) string {
	switch x := v.(type) {
	case nil:
		return "" // (string)NULL === ""
	case string:
		return x
	case []byte:
		return string(x)
	case bool:
		if x { // (string)true === "1"; (string)false === ""
			return "1"
		}
		return ""
	case int:
		return strconv.Itoa(x)
	case int32:
		return strconv.FormatInt(int64(x), 10)
	case int64:
		return strconv.FormatInt(x, 10)
	case float32:
		return phpFloatString(float64(x))
	case float64:
		return phpFloatString(x)
	default:
		return fmt.Sprintf("%v", v)
	}
}

// phpFloatString is PHP's (string) cast for a float, which formats with the `precision` ini —
// default 14 — as %.*G. So (string)(1/3) is "0.33333333333333", NOT Go's default
// strconv.FormatFloat(v,'g',-1,64) shortest-round-trip "0.3333333333333333".
//
// Reached through MemGraph's `round(weight,4)` and ForgeView's SUM(size) columns.
func phpFloatString(f float64) string {
	if math.IsInf(f, 1) {
		return "INF"
	}
	if math.IsInf(f, -1) {
		return "-INF"
	}
	if math.IsNaN(f) {
		return "NAN"
	}
	// PHP's %G drops the fraction for integral values in range: (string)3.0 === "3".
	s := strconv.FormatFloat(f, 'G', 14, 64)
	// Go renders exponents as "1E+20"; PHP's precision-14 %G renders "1.0E+20".
	if i := strings.IndexByte(s, 'E'); i >= 0 && !strings.Contains(s[:i], ".") {
		s = s[:i] + ".0" + s[i:]
	}
	return s
}

// phpNumberOrDash mirrors the ternaries in TicketList's journal: NULL renders as the em-dash the
// PHP writes, an int renders as (int)$v.
func phpNumberOrDash(v any) string {
	if v == nil {
		return "—"
	}
	return strconv.FormatInt(toInt(v), 10)
}

// toInt is PHP's (int) cast for DB values.
func toInt(v any) int64 {
	switch x := v.(type) {
	case nil:
		return 0
	case int64:
		return x
	case int:
		return int64(x)
	case float64:
		return int64(x)
	case []byte:
		n, _ := strconv.ParseInt(strings.TrimSpace(string(x)), 10, 64)
		return n
	case string:
		// PHP's (int)"12abc" === 12: take the leading integer, ignore the rest.
		n, _ := strconv.ParseInt(leadingInt(x), 10, 64)
		return n
	default:
		return 0
	}
}

func leadingInt(s string) string {
	s = strings.TrimSpace(s)
	i := 0
	if i < len(s) && (s[i] == '-' || s[i] == '+') {
		i++
	}
	start := i
	for i < len(s) && s[i] >= '0' && s[i] <= '9' {
		i++
	}
	if i == start {
		return "0"
	}
	return s[:i]
}

// esc is the shorthand every ported tag uses, exactly as each PHP class defines
// `private static function esc($s) { return htmlspecialchars((string)$s, ENT_QUOTES); }`.
func esc(v any) string { return phpHTMLSpecialChars(phpString(v)) }

// gmdate mirrors gmdate('Y-m-d H:i', $t) — TicketList::stamp (TicketList.php:190-193). UTC.
func gmdate(t int64) string { return time.Unix(t, 0).UTC().Format("2006-01-02 15:04") }

// collapseWS is preg_replace('/\s+/', ' ', $s). PHP's \s is [ \t\n\r\f\v] — ASCII only, and
// notably NOT Unicode spaces, which is why this is a byte loop and not strings.Fields.
func collapseWS(s string) string {
	var b strings.Builder
	b.Grow(len(s))
	inRun := false
	for i := 0; i < len(s); i++ {
		if isPHPSpace(s[i]) {
			if !inRun {
				b.WriteByte(' ')
				inRun = true
			}
			continue
		}
		inRun = false
		b.WriteByte(s[i])
	}
	return b.String()
}

func isPHPSpace(c byte) bool {
	return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v'
}

// phpTrim is trim($s) — PHP's default charlist " \t\n\r\0\x0B" (note: \0 and \x0B, NOT \f).
// strings.TrimSpace would also strip \f and Unicode spaces, which PHP's trim does not.
func phpTrim(s string) string {
	return strings.Trim(s, " \t\n\r\x00\x0B")
}

// splitWS is preg_split('/\s+/', $s, -1, PREG_SPLIT_NO_EMPTY) — TicketList::groupable.
func splitWS(s string) []string {
	var out []string
	cur := strings.Builder{}
	flush := func() {
		if cur.Len() > 0 {
			out = append(out, cur.String())
			cur.Reset()
		}
	}
	for i := 0; i < len(s); i++ {
		if isPHPSpace(s[i]) {
			flush()
			continue
		}
		cur.WriteByte(s[i])
	}
	flush()
	return out
}

// foldDigitRuns is the LOOKBEHIND port: preg_replace('/(?<![#\d])\d+/', repl, $s).
//
// TicketList.php:161-174 explains the intent: fold the VARYING index in a flood of near-identical
// titles ("crank1", "crank10" -> "crank#") while leaving a TICKET REFERENCE ("#25") intact.
//
// The reduction that makes this RE2-able: \d+ is greedy, so every match is a MAXIMAL digit run,
// so the character before a run is never itself a digit. The lookbehind (?<![#\d]) therefore
// collapses to the single test "the byte before this run is not '#'".
//
// PCRE does not then retry INSIDE a rejected run — it advances and every later position in that
// run is preceded by a digit, so it fails too. Hence a run introduced by '#' is skipped WHOLE
// ("#25" stays "#25", it does not become "#2#"). This loop reproduces that by skipping the run.
func foldDigitRuns(s, repl string) string {
	var b strings.Builder
	last := 0
	for _, m := range digitRun.FindAllStringIndex(s, -1) {
		start, end := m[0], m[1]
		if start > 0 && s[start-1] == '#' {
			continue // lookbehind rejects it; the whole run survives verbatim
		}
		b.WriteString(s[last:start])
		b.WriteString(repl)
		last = end
	}
	b.WriteString(s[last:])
	return b.String()
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// TagArguments — lib/TagLoader/Arguments/TagArguments.php
//
// The reversal at the end of setArguments (TagArguments.php:47) is load-bearing and easy to
// mis-port: arguments are stored REVERSED, so end()/array_pop() — i.e. Top()/Pop() — hand back the
// argument the AUTHOR WROTE FIRST. <<<FormTag(OrderForm)>>> must yield "OrderForm" from Pop().
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// TagArguments is the argument wrapper a tag's constructor receives.
type TagArguments struct {
	arguments []string // stored reversed, as PHP stores them
	count     int
}

// ArgumentFactory is TagArguments::argumentFactory($functionCall) — the full tag body with the
// <<< >>> already stripped, e.g. "FormTag(OrderForm)".
func ArgumentFactory(functionCall string) *TagArguments {
	a := &TagArguments{}
	a.setArguments(a.obtainArguments(functionCall))
	return a
}

// obtainArguments is preg_match_all(FUNCTION_ARGUMENT, ...) -> $result[0] ("complete matches only").
func (a *TagArguments) obtainArguments(functionCall string) []string {
	return functionArgument.FindAllString(functionCall, -1)
}

// setArguments strips each argument's parentheses, counts, then REVERSES (TagArguments.php:38-48).
func (a *TagArguments) setArguments(args []string) {
	a.arguments = nil
	a.count = 0
	for _, arg := range args {
		a.arguments = append(a.arguments, removeParenthesis(arg))
		a.count++
	}
	// array_reverse($this->arguments)
	for i, j := 0, len(a.arguments)-1; i < j; i, j = i+1, j-1 {
		a.arguments[i], a.arguments[j] = a.arguments[j], a.arguments[i]
	}
}

// removeParenthesis is substr($key, 1, strlen($key)-2): "(abc)" -> "abc", "()" -> "".
func removeParenthesis(key string) string {
	if len(key) < 2 {
		return ""
	}
	return key[1 : len(key)-1]
}

// GetArguments is getArguments().
func (a *TagArguments) GetArguments() []string { return a.arguments }

// Top is end($this->arguments) — the LAST stored element, i.e. the FIRST-written argument.
// PHP's end() on an empty array returns false, and every caller casts it: (string)false === "".
func (a *TagArguments) Top() string {
	if a == nil || len(a.arguments) == 0 {
		return ""
	}
	return a.arguments[len(a.arguments)-1]
}

// Pop is array_pop($this->arguments) — removes and returns the first-written argument.
// PHP's array_pop on an empty array returns NULL, and FormTag's is_string(NULL) is false, so the
// second result reports "there was no value" rather than an empty one.
func (a *TagArguments) Pop() (string, bool) {
	if a == nil || len(a.arguments) == 0 {
		return "", false
	}
	a.count--
	v := a.arguments[len(a.arguments)-1]
	a.arguments = a.arguments[:len(a.arguments)-1]
	return v, true
}

// Finished is finished() — PHP returns ($this->count > 0), which reads backwards for a method of
// this name. Ported as-is: the PHP is the spec, quirk included.
func (a *TagArguments) Finished() bool { return a.count > 0 }

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Tag_Parser — lib/TagLoader/Parser/Tag_Parser.php
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// TagParser is Tag_Parser: it splits one invocation string into a function name and arguments.
type TagParser struct {
	tag          string // the invocation with <<< >>> stripped: "Foo(a)(b)"
	functionName string // "Foo"
	arguments    *TagArguments
}

// GetTagParser is Tag_Parser::get_tag_parser($full_tag), $full_tag being "<<<Foo(a)>>>".
func GetTagParser(fullTag string) *TagParser {
	p := &TagParser{}
	p.initialize(fullTag)
	return p
}

// initialize mirrors Tag_Parser::initialize (Tag_Parser.php:24-31).
func (p *TagParser) initialize(tagInvocation string) {
	p.tag = extractTagName(tagInvocation)
	// PHP guards with isset($this->tag); extract_tag_name always returns a string here.
	p.functionName = getTagIdentifier(p.tag)
	p.arguments = ArgumentFactory(p.tag)
}

// extractTagName is Tag_Parser::extract_tag_name — substr($tag, strlen(KEY_PREFIX),
// strlen($tag) - strlen(KEY_PREFIX.KEY_SUFFIX)): strip the "<<<" and the ">>>".
func extractTagName(tag string) string {
	prefix := len(KeyPrefix)
	length := len(tag) - len(KeyPrefix+KeySuffix)
	return phpSubstr(tag, prefix, length)
}

// getTagIdentifier is the LOOKAHEAD port of GET_TAG_IDENTIFIER:
//
//	/([a-zA-Z0-9]+\s?(?=\(\s?[a-zA-Z0-9]*\s?\)))|(\s?[a-zA-Z0-9]+\s?)/
//
// preg_match takes the LEFTMOST match, trying alternative 1 then alternative 2 at each position:
//
//	alt 1  an alnum run (plus one optional space) that IS FOLLOWED BY a "( ... )" argument list
//	alt 2  an optional space, an alnum run, an optional space   [no lookahead]
//
// Worked, against the two shapes that actually occur:
//
//	"Foo(bar)"  pos 0, alt 1: run "Foo", lookahead sees '(' -> MATCH "Foo".
//	"TagList"   pos 0, alt 1: run "TagList", lookahead needs '(' at EOS -> fail; backtracking to
//	            shorter runs fails the same way (the next char is never '('). alt 2 -> "TagList".
//
// Both land on the leading alnum run, which is why this reduces to the scan below. The optional
// \s? either side of alt 2 can only capture a space that a tagPattern-matched invocation cannot
// contain (FUNCTION_NAME is [a-zA-Z]+), so it never fires on real input.
//
// PHP returns NULL when nothing matches (e.g. an empty or punctuation-only body); the caller then
// leaves $function_name unset and `new $tag_class` fatals. Go returns "" and the engine reports an
// unknown tag — divergence 1 in the file header.
func getTagIdentifier(tagString string) string {
	i := 0
	for i < len(tagString) && !isAlnumASCII(tagString[i]) {
		// alt 2's leading \s? can absorb ONE space; anything else means no match starts here.
		if !isPHPSpace(tagString[i]) {
			return ""
		}
		i++
	}
	start := i
	for i < len(tagString) && isAlnumASCII(tagString[i]) {
		i++
	}
	return tagString[start:i]
}

func isAlnumASCII(c byte) bool {
	return c >= 'A' && c <= 'Z' || c >= 'a' && c <= 'z' || c >= '0' && c <= '9'
}

// GetFullTag is get_full_tag().
func (p *TagParser) GetFullTag() string { return p.tag }

// GetFunctionName is get_function_name().
func (p *TagParser) GetFunctionName() string { return p.functionName }

// GetTagArguments is get_tag_arguments().
func (p *TagParser) GetTagArguments() *TagArguments { return p.arguments }

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Tag_Wrapper — lib/TagLoader/Tag/Tag_Wrapper.php — THE ENGINE.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// Tag is Tag_Interface: `interface Tag_Interface { public function get_document(); }`.
// Document implements it too, which is what lets execute_all_tags start at a document.
type Tag interface {
	GetDocument() string
}

// TagWrapper is Tag_Wrapper: a node in the render tree — one tag plus the children discovered in
// its output.
type TagWrapper struct {
	parser   *TagParser
	children []*TagWrapper
	tag      Tag
	engine   *Engine
}

// Engine carries the per-request ambient state through the recursion. PHP reaches the equivalent
// state through global constants, the $_GET superglobal and the POM singleton; Go passes it
// explicitly. An Engine is ONE REQUEST's worth of state and is not safe for concurrent use — which
// matches its PHP counterpart, where all of it is per-request global.
type Engine struct {
	cfg Config
	get url.Values // $_GET

	// tagListRendering is TagList::$rendering (TagList.php:18) — the static re-entrancy guard that
	// stops the gallery rendering itself inside itself. Static in PHP means per-request in
	// practice (a PHP process serves one request); here it lives on the Engine for the same span.
	tagListRendering bool

	// Lookup overrides the package registry for this engine — the seam that stands in for swapping
	// TAG_LOADER in the POM. nil uses the registry. SelfCheck drives the engine through it with
	// synthetic tags (a self-referential one, an escaping one) that must NOT appear in PortedTags.
	Lookup func(e *Engine, name string, args *TagArguments) (Tag, bool)
}

// lookupTag is `$tag_loader->loadClassByName($n); new $n($args);` with the Lookup override applied.
func (e *Engine) lookupTag(name string, args *TagArguments) (Tag, bool) {
	if e.Lookup != nil {
		return e.Lookup(e, name, args)
	}
	return newTag(e, name, args)
}

// NewEngine builds an Engine over cfg with an empty $_GET.
func NewEngine(cfg Config) *Engine { return &Engine{cfg: cfg, get: url.Values{}} }

// NewEngineWithQuery builds an Engine over cfg whose tags see get as their $_GET.
func NewEngineWithQuery(cfg Config, get url.Values) *Engine {
	if get == nil {
		get = url.Values{}
	}
	return &Engine{cfg: cfg, get: get}
}

// Config returns the engine's configuration.
func (e *Engine) Config() Config { return e.cfg }

// getStr is the tags' standard read: the value when the key is set, the empty string when it is
// not — PHP's `isset($_GET[k]) ? (string)$_GET[k] : <empty>` ternary.
//
// PHP takes the LAST value for a repeated scalar key (?a=1&a=2 makes $_GET['a'] the string "2",
// since each assignment overwrites), so this returns the last value, as PHP does.
func (e *Engine) getStr(k string) string {
	v, ok := e.getIsset(k)
	if !ok {
		return ""
	}
	return v
}

// getIsset is `isset($_GET[k])` plus the value. A key present with an EMPTY value IS still set in
// PHP (?tag= makes isset($_GET['tag']) true, with the value being the empty string), and several
// tags branch on exactly that distinction — MemGraph.php:114 tests isset($_GET['node']) AND that
// the node is non-empty, and takes different branches for the two.
func (e *Engine) getIsset(k string) (string, bool) {
	if e.get == nil {
		return "", false
	}
	vs, ok := e.get[k]
	if !ok || len(vs) == 0 {
		return "", false
	}
	return vs[len(vs)-1], true
}

// CreateDocumentTag is Tag_Wrapper::create_document_tag($document) — the root of the render tree.
// Note it sets ONLY ->tag: the document has no parser and no invocation string, because nothing
// invoked it.
func (e *Engine) CreateDocumentTag(d Tag) *TagWrapper {
	return &TagWrapper{tag: d, engine: e}
}

// getTagWrapper is Tag_Wrapper::get_tag_wrapper($invocation_string): parse the invocation, load the
// class by name, construct it with the parsed arguments.
//
// PHP: `$tag_loader->loadClassByName($tag_class); $tag_wrapper->tag = new $tag_class(args);`
// Go: newTag is the registry lookup. An unknown name is divergence 1 (header) — PHP fatals, we
// return ok=false and the caller emits a marked literal.
func (e *Engine) getTagWrapper(invocationString string) (*TagWrapper, bool) {
	w := &TagWrapper{engine: e}
	w.parser = GetTagParser(invocationString)
	tag, ok := e.lookupTag(w.parser.GetFunctionName(), w.parser.GetTagArguments())
	if !ok {
		return nil, false
	}
	w.tag = tag
	return w, true
}

// AddChild is Tag_Wrapper::add_child($invocation_string).
func (w *TagWrapper) AddChild(invocationString string) (*TagWrapper, bool) {
	child, ok := w.engine.getTagWrapper(invocationString)
	if !ok {
		return nil, false
	}
	w.children = append(w.children, child)
	return child, true
}

// identifyTag is Tag_Wrapper::identify_tag($document_string):
//
//	$matchPattern = TAG_KEY_PREFIX . FUNCTION_NAME . FUNCTION_ARGUMENTS . TAG_KEY_SUFFIX;
//	preg_match_all($matchPattern, $document_string, $tags);
//	return $tags[0];
//
// $tags[0] is the full-match group, in order of occurrence, WITH DUPLICATES KEPT — which matters;
// see ExecuteAllTags.
func identifyTag(documentString string) []string {
	return tagPattern.FindAllString(documentString, -1)
}

// replaceTag is Tag_Wrapper::replace_tag — str_replace($invocation, $replacement, $document).
// str_replace replaces EVERY occurrence, not the first. Kept as a named function because that
// "every" is the whole reason the duplicate handling in ExecuteAllTags works out.
func replaceTag(documentString, replacementString, invocationString string) string {
	return strings.ReplaceAll(documentString, invocationString, replacementString)
}

// unknownTagHTML is divergence 1 (see the file header): PHP fatals the page on an unloadable tag
// class; we mark it and carry on. Deliberately NOT valid tag syntax, so it cannot re-trigger the
// scanner on a later pass.
func unknownTagHTML(invocation string) string {
	return "<!-- congruency-go tags: no Go port for " + phpHTMLSpecialChars(invocation) +
		" (PHP would render it; see PortedTags) -->"
}

// ExecuteAllTags is Tag_Wrapper::execute_all_tags($tag_wrapper, $depth = 0) — THE RECURSION.
//
//	public static function execute_all_tags($tag_wrapper, $depth = 0){
//	    $result_string = $tag_wrapper->tag->get_document();
//	    if ($depth >= 64) { return $result_string; }
//	    $document_string = $result_string;
//	    $tIA = $tag_wrapper->identify_tag($document_string);
//	    foreach($tIA as $tag_invocation){
//	        $child_tag = $tag_wrapper->add_child($tag_invocation);
//	        $result_substring = self::execute_all_tags($child_tag, $depth + 1);
//	        $result_string = self::replace_tag($result_string,$result_substring,$tag_invocation);
//	    }
//	    return $result_string;
//	}
//
// Four details that must survive the port, because each changes the bytes:
//
//  1. THE CAP IS CHECKED AFTER get_document(). The tag at depth 64 still RENDERS; only its
//     children are left literal. Checking before would drop its output entirely.
//  2. identify_tag SCANS $document_string — the ORIGINAL output — while the replacements
//     accumulate in $result_string. The scan list is fixed before the first substitution, so a
//     tag that a CHILD's output introduces is not picked up by this frame (the child's own frame
//     already expanded its own output).
//  3. DUPLICATES ARE KEPT in $tIA, and str_replace already replaced every copy on the first pass.
//     The second visit re-renders the tag (side effects and all) and then replaces nothing,
//     because the needle is gone. Both facts are preserved: we iterate the duplicate too.
//  4. Recursion is DEPTH-FIRST, in match order.
func ExecuteAllTags(w *TagWrapper, depth int) string {
	resultString := w.tag.GetDocument() // the tag is processed
	if depth >= MaxTagDepth {
		return resultString // BUG-06 cap: leave nested tags literal (Tag_Wrapper.php:65)
	}
	documentString := resultString
	for _, tagInvocation := range identifyTag(documentString) {
		var resultSubstring string
		child, ok := w.AddChild(tagInvocation)
		if !ok {
			resultSubstring = unknownTagHTML(tagInvocation)
		} else {
			resultSubstring = ExecuteAllTags(child, depth+1)
		}
		resultString = replaceTag(resultString, resultSubstring, tagInvocation)
	}
	return resultString
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// Document / DocumentManager — the root of a page render.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// Document is lib/Modules/Constructs/Document/Document/Document.php. Its get_document() returns the
// TEMPLATE (the Content column), which is the string the engine scans for tags.
type Document struct {
	Title       string
	Template    string
	Description string
	Key         string
	ContentID   string
}

// GetDocument is Document::get_document() — `return $this->template;` (Document.php:70-72).
// This is why a Document is a Tag: execute_all_tags starts by calling it.
func (d *Document) GetDocument() string { return d.Template }

// String is Document::__toString() — `return Tag_Wrapper::execute_all_tags($this->document_tag);`
// (Document.php:78-80). Note the engine is needed, so this is a method on Engine in Go.
func (e *Engine) RenderDocument(d *Document) string {
	return ExecuteAllTags(e.CreateDocumentTag(d), 0)
}

// validatePageKey is ValidateFields::validatePageKey (ValidateFields.php:13-22):
//
//	preg_match("/[A-Za-z]{2,}/", $pageKey, $result);
//	if ($pageKey == $result[0]) { return $result[0]; } else { return NULL; }
//
// i.e. the key is accepted only if it is ENTIRELY a run of 2+ ASCII letters. "tags" passes;
// "tags2", "a", "" and "../x" do not. ok=false is the PHP's NULL.
var pageKeyRe = regexp.MustCompile(`[A-Za-z]{2,}`)

func validatePageKey(pageKey string) (string, bool) {
	m := pageKeyRe.FindString(pageKey)
	if m == "" {
		// PHP reads $result[0] on an empty array here: "Warning: Undefined array key 0", then
		// compares $pageKey == NULL. For "" that is TRUE, so PHP returns NULL either way.
		return "", false
	}
	if pageKey == m {
		return m, true
	}
	return "", false
}

// GetDocumentByKey is DocumentManager::get_document($key) reduced to its DAO SELECT
// (DocumentDAO::getDocumentData, DocumentDAO.php:37-56):
//
//	SELECT * FROM Documents
//	  INNER JOIN Document_Templates ON Documents.TemplateID = Document_Templates.TemplateID
//	  WHERE Documents.DocumentID = '$key'
//
// and Document::sql_assoc_array's field mapping (Document.php:16-27): Content -> template,
// Title -> title, Description -> description, DocumentID -> key, ContentID -> content_outline.
// The join is what supplies Content: it lives in Document_Templates, not in Documents.
//
// The PHP INTERPOLATES $key into the SQL (a real injection, still live in the checkout) — but only
// AFTER validatePageKey has restricted it to [A-Za-z]{2,}, so no injectable key survives. We bind
// the parameter instead: for every key that reaches this line the two are identical, and binding
// cannot be the thing that makes the Go diverge.
func (e *Engine) GetDocumentByKey(key string) (*Document, error) {
	validated, ok := validatePageKey(key)
	if !ok {
		return nil, fmt.Errorf("invalid page key: %q", key)
	}
	db, err := openDB(e.cfg, e.cfg.SQLite)
	if err != nil {
		return nil, err
	}
	defer db.Close()

	rows, err := queryRows(db, "SELECT * FROM Documents"+
		" INNER JOIN Document_Templates ON Documents.TemplateID = Document_Templates.TemplateID"+
		" WHERE Documents.DocumentID = ?", validated)
	if err != nil {
		return nil, err
	}
	// DocumentDAO returns a row ONLY when the result set holds exactly one ($rows == 1).
	if len(rows) != 1 {
		return nil, fmt.Errorf("no such document: %q", validated)
	}
	r := rows[0]
	return &Document{
		Template:    phpString(r["Content"]),
		Title:       phpString(r["Title"]),
		Description: phpString(r["Description"]),
		Key:         phpString(r["DocumentID"]),
		ContentID:   phpString(r["ContentID"]),
	}, nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// sqlite plumbing — the small part of db.go this leaf package must re-derive (see the header).
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// openDB opens a congruency sqlite file for READING ONLY.
//
// WHY NOT MIRROR PDO EXACTLY. The PHP does `new PDO('sqlite:'.$path)` — read-write — and TicketList
// then pins it with `PRAGMA query_only = TRUE` (TicketList.php:133-138). A read-write open CREATES
// AN EMPTY DB when the path is missing, which is a side effect this port refuses to inherit.
//
// WHY mode=ro AND NOT immutable=1. This is a real trade-off, the repo has hit it before, and both
// halves of it were MEASURED this session rather than assumed. Against a WAL-mode copy of this
// schema, directory listed before and after one TicketList render with nothing else touching it:
//
//	                   new files created        sees a committed-but-uncheckpointed WAL row
//	mode=ro            2  (-wal, -shm)          YES   (10677B render)
//	immutable=1        0                        NO    (10048B render — STALE)
//
// ...with the db's own content hash UNCHANGED in both cases. So:
//
//   - `immutable=1` promises sqlite the file cannot change, so it reads with no locking and
//     creates ZERO sidecar files. db.go's OpenImmutable (db.go:714-723) uses it, and #153's lesson
//     (docs/PLAYBOOK.md, Theme 3) is exactly the first column above.
//   - BUT that promise is FALSE here: the state db is WAL-mode with LIVE CONCURRENT WRITERS (the
//     pair_loop agents — equivalence_test.go:22-27 is built entirely around that fact). immutable=1
//     makes sqlite IGNORE THE WAL, so it reads the main file only and returns data the PHP would
//     never return. That is the second column: a row the PHP's handle sees and this one does not.
//
// For an EQUIVALENCE gate the second column decides it. A stale read makes the Go differ from the
// PHP on DATA, and the byte-diff would blame the engine for a difference the engine never made —
// the exact failure #227's header warns about ("a divergence is a data difference, not an engine
// difference"). #153's constraint was "never create files"; #226's is equivalence, and they pull
// opposite ways. So the default is `mode=ro`: it reads through the WAL exactly as PHP's handle
// does. It writes no byte of the db; the -wal/-shm are sqlite's own bookkeeping, materialized
// alongside a db whose live writers already maintain them.
//
// Set Config.Immutable for the zero-sidecar read when nothing is writing (or when side-effect
// freedom matters more than freshness) — knowing it can be stale.
//
// Missing file -> error, never creation.
func openDB(cfg Config, path string) (*sql.DB, error) {
	if path == "" {
		return nil, fmt.Errorf("no database path configured")
	}
	if _, err := os.Stat(path); err != nil {
		return nil, fmt.Errorf("database not found: %s", path)
	}
	dsn := "file:" + path + "?mode=ro"
	if cfg.Immutable {
		dsn = "file:" + path + "?immutable=1"
	}
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, err
	}
	return db, nil
}

// queryAll is PDO::query(...)->fetchAll(PDO::FETCH_ASSOC), returning the COLUMN ORDER alongside the
// rows.
//
// The order is returned because a PHP FETCH_ASSOC row is an ordered array and a Go map is not, and
// two callers genuinely need it: FETCH_COLUMN takes column 0 POSITIONALLY, and MemGraph::high_drift
// renders `SELECT *` with array_keys($rows[0]) as its header. Returning it from the SAME statement
// is also what keeps this to ONE execution — reading the order from a second identical query would
// both double the work and, against a db with live concurrent writers (which the state db has),
// risk the two reads disagreeing.
func queryAll(db *sql.DB, query string, args ...any) ([]string, []map[string]any, error) {
	rows, err := db.Query(query, args...)
	if err != nil {
		return nil, nil, err
	}
	defer rows.Close()
	cols, err := rows.Columns()
	if err != nil {
		return nil, nil, err
	}
	var out []map[string]any
	for rows.Next() {
		cells := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range cells {
			ptrs[i] = &cells[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			return nil, nil, err
		}
		m := make(map[string]any, len(cols))
		for i, c := range cols {
			v := cells[i]
			// PDO hands back strings for TEXT; the driver may hand back []byte.
			if b, ok := v.([]byte); ok {
				v = string(b)
			}
			m[c] = v
		}
		out = append(out, m)
	}
	return cols, out, rows.Err()
}

// queryRows is queryAll without the column order — the common case.
func queryRows(db *sql.DB, query string, args ...any) ([]map[string]any, error) {
	_, rows, err := queryAll(db, query, args...)
	return rows, err
}

// queryColumn is fetchAll(PDO::FETCH_COLUMN, 0) — the first column of every row, BY POSITION.
func queryColumn(db *sql.DB, query string, args ...any) ([]any, error) {
	cols, rows, err := queryAll(db, query, args...)
	if err != nil || len(rows) == 0 || len(cols) == 0 {
		return nil, err
	}
	out := make([]any, 0, len(rows))
	for _, r := range rows {
		out = append(out, r[cols[0]])
	}
	return out, nil
}

// scalar is PDO::query($sql)->fetchColumn() — the first column of the first row, or nil.
func scalar(db *sql.DB, query string, args ...any) (any, error) {
	cols, rows, err := queryAll(db, query, args...)
	if err != nil || len(rows) == 0 || len(cols) == 0 {
		return nil, err
	}
	return rows[0][cols[0]], nil
}

// scalarOrZero is the `($v === false || $v === null) ? 0 : $v` idiom shared by ForgeView::scalar
// (ForgeView.php:56-59), MemGraph::scalar and OmniExplorer::scalar. The 0 is an INT, so it renders
// as "0" — not "" — which is why this cannot just return the nil.
func scalarOrZero(db *sql.DB, query string) any {
	v, err := scalar(db, query)
	if err != nil || v == nil {
		return int64(0)
	}
	return v
}

// safeRows is TicketList::safe($db,$sql) (TicketList.php:142-148): run a SELECT, and on ANY error
// (typically "no such table" in a checkout where migration 0029+ never ran) degrade to an empty
// set rather than a fatal.
func safeRows(db *sql.DB, query string, args ...any) []map[string]any {
	rows, err := queryRows(db, query, args...)
	if err != nil {
		return nil
	}
	return rows
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The registry — the Go stand-in for TAG_LOADER->loadClassByName($n) + `new $n($args)`.
//
// ── HOW A TAG GETS IN HERE (#281): ADD A FILE; CHANGE NOTHING CENTRAL ───────────────────────────
//
// The registry is a MUTABLE map, populated at process start by Register, which each tag calls from
// an init() in ITS OWN FILE. To port a tag, add congruency-go/tags/<Tag>.go holding that tag's
// type, its GetDocument, and its self-registration:
//
//	func init() {
//	    Register("Foo", func(e *Engine, a *TagArguments) Tag { return &FooTag{e: e, args: a} })
//	}
//
// ...and NOTHING in engine.go changes. That is the whole point of #281. This file previously held
// a hardcoded map literal naming every tag inline, so adding a tag meant EDITING that literal —
// which would have made the 45 remaining per-tag ports (#246+) all collide on this one file and
// forced them to serialize. With self-registration they are add-a-file-only, and therefore run
// fully in parallel.
//
// WHY init() IS ENOUGH. Go initializes a package — every init() in it, in every file — before any
// other code in that package runs (Go spec, "Package initialization"). So the registry is complete
// before the first newTag/IsPorted/PortedTags call can happen, with no explicit wiring step to
// forget. Order across files is irrelevant: Register is order-independent (it only inserts) and
// PortedTags sorts its own output, so the observable surface does not depend on which file's
// init() ran first.
//
// WHY THE 10 EXISTING TAGS ARE STILL REGISTERED HERE. #281's deliverable is engine.go alone
// ("touch nothing else"), so the tags #226 ported self-register from the single init() below
// rather than from 10 new files. That init() is the PROOF the mechanism carries the real set —
// it is not a special case: its Register calls are ordinary ones, and moving any of the 10 into
// its own <Tag>.go later is a cut-and-paste of that tag's Register line into that file's init(),
// with no edit to anything here.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// tagFactory constructs one tag. args mirrors the PHP constructor's $arguments and is NIL when the
// tag is rendered standalone — TagList.php:67 does exactly `new $sel(null)`, which is the shape the
// ?page=tags&tag=<T> gate always takes. Every ported constructor below handles a nil *TagArguments
// the way its PHP handles NULL.
type tagFactory func(e *Engine, args *TagArguments) Tag

// registry maps tag name -> factory. NEVER assign to it directly: Register is its only writer, and
// direct assignment would bypass the duplicate check that stands in for what the compiler used to
// do (see Register).
var registry = map[string]tagFactory{}

// registryMu guards registry. The map literal this replaced was fixed at compile time and so was
// race-free by construction; a map that is written at run time is not, and Register is exported —
// so the lock KEEPS that property rather than leaving it to callers' discipline. In the intended
// use (Register from init(), which runs single-threaded before main) it is uncontended, and the
// read path takes only RLock, which costs nothing beside the SQL every real tag runs.
var registryMu sync.RWMutex

// Register adds name's factory to the registry, and is the ONLY supported way in. Call it from an
// init() in the tag's own file (see the section header above); calling it later is allowed and
// safe, but a tag registered after a render has begun will not appear in a page already served.
//
// It PANICS on an empty name, a nil factory, or a name already registered. This is deliberate, and
// it is NOT in tension with divergence 1 ("a crash is a #226 finding") in the file header: that
// divergence is about CONTENT — an unknown tag name in a stored document must never take the page
// down, and it still does not (newTag returns ok=false and the caller emits a marked literal).
// These three panics are programmer errors in registration code, they are independent of any input
// or DB state, and they fire during package init — before any request exists to break. A duplicate
// name in the old map literal was a COMPILE error ("duplicate key in map literal"); two files
// claiming the same tag is the same mistake, so it stays loud and immediate instead of silently
// letting one file's factory shadow another's.
func Register(name string, f func(e *Engine, args *TagArguments) Tag) {
	if name == "" {
		panic("tags.Register: empty tag name")
	}
	if f == nil {
		panic("tags.Register: nil factory for tag " + name)
	}
	registryMu.Lock()
	defer registryMu.Unlock()
	if _, dup := registry[name]; dup {
		panic("tags.Register: duplicate registration for tag " + name)
	}
	registry[name] = f
}

// init self-registers the 10 tags #226 ported. These lines are the former map literal, one
// Register call per entry and byte-identical factories — PortedTags/IsPorted/newTag therefore
// answer exactly as they did before #281. See the section header for why these 10 live here
// instead of in 10 files, and how to move them out.
func init() {
	Register("TagList", func(e *Engine, a *TagArguments) Tag { return &TagListTag{e: e, args: a} })
	Register("TicketList", func(e *Engine, a *TagArguments) Tag { return &TicketListTag{e: e, args: a} })
	Register("TreeView", func(e *Engine, a *TagArguments) Tag { return &TreeViewTag{e: e, args: a} })
	Register("OmniExplorer", func(e *Engine, a *TagArguments) Tag { return &OmniExplorerTag{e: e, args: a} })
	Register("ForgeView", func(e *Engine, a *TagArguments) Tag { return &ForgeViewTag{e: e, args: a} })
	Register("MemGraph", func(e *Engine, a *TagArguments) Tag { return &MemGraphTag{e: e, args: a} })
	Register("BugCatalog", func(e *Engine, a *TagArguments) Tag { return &BugCatalogTag{e: e, args: a} })
	Register("SemanticSearch", func(e *Engine, a *TagArguments) Tag { return &SemanticSearchTag{e: e, args: a} })
	Register("CategoryBrowse", func(e *Engine, a *TagArguments) Tag { return newCategoryBrowseTag(e, a) })
	Register("FormTag", func(e *Engine, a *TagArguments) Tag { return newFormTag(e, a) })
}

// newTag is `$tag_loader->loadClassByName($n); new $n($args);`. ok=false is "no Go port" — see
// divergence 1 in the file header for why that is not a panic.
//
// The factory is called AFTER the lock is dropped: constructing a tag is the caller's work, it can
// run arbitrarily long (newFormTag/newCategoryBrowseTag read arguments), and holding the registry
// lock across it would serialize concurrent renders for no reason.
func newTag(e *Engine, name string, args *TagArguments) (Tag, bool) {
	registryMu.RLock()
	f, ok := registry[name]
	registryMu.RUnlock()
	if !ok {
		return nil, false
	}
	return f(e, args), true
}

// PortedTags returns the sorted names of every tag this package can render. It is the exact set of
// T for which `?page=tags&tag=<T>` is a meaningful Go-vs-PHP byte diff today; every other name that
// Scan lists renders as a marked divergence notice instead. See COVERAGE in the file header.
func PortedTags() []string {
	registryMu.RLock()
	out := make([]string, 0, len(registry))
	for n := range registry {
		out = append(out, n)
	}
	registryMu.RUnlock()
	sort.Strings(out)
	return out
}

// IsPorted reports whether name has a Go port.
func IsPorted(name string) bool {
	registryMu.RLock()
	_, ok := registry[name]
	registryMu.RUnlock()
	return ok
}

// Scan is TagList::scan() (TagList.php:22-37) — the gallery's tag list.
//
//	$it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator(TAGS_DIR, SKIP_DOTS));
//	foreach ($it as $f)
//	    if ($f->isFile() && strtolower($f->getExtension()) === 'php') {
//	        $src = @file_get_contents($f->getPathname());
//	        if ($src !== false && strpos($src, 'Tag_Interface') !== false)
//	            $names[substr($f->getFilename(), 0, -4)] = 1;
//	    }
//	$names = array_keys($names); sort($names); return $names;
//
// It is a FILESYSTEM scan of the real PHP tag tree, and porting it as one is what makes the Go
// gallery list the same 30 names as the PHP gallery: same directory, same Tag_Interface filter,
// same basename rule, same sort. A hardcoded Go list would drift the moment a tag file is added.
//
// Details that matter: the recursion covers TAGS_DIR's subdirectories (dev/, forms/, ...); the
// extension test is case-insensitive but the name is cut as substr(...,0,-4), so "Foo.PHP" lists as
// "Foo"; the map keys dedupe a name that appears in two subdirectories; an unreadable file is
// skipped (@file_get_contents === false), not fatal; a missing TAGS_DIR yields an empty list
// (TagList.php:24), not an error.
func Scan(tagsDir string) []string {
	names := map[string]bool{}
	if tagsDir == "" {
		return []string{}
	}
	if st, err := os.Stat(tagsDir); err != nil || !st.IsDir() {
		return []string{} // !defined('TAGS_DIR') || !is_dir(TAGS_DIR)
	}
	_ = filepath.WalkDir(tagsDir, func(p string, d os.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil //lint:ignore nilerr an unreadable entry is skipped, as @file_get_contents does
		}
		base := filepath.Base(p)
		if len(base) < 5 || !strings.EqualFold(filepath.Ext(base), ".php") {
			return nil
		}
		src, err := os.ReadFile(p)
		if err != nil {
			return nil // @file_get_contents(...) === false -> skip
		}
		if strings.Contains(string(src), "Tag_Interface") {
			names[base[:len(base)-4]] = true // substr($f->getFilename(), 0, -4)
		}
		return nil
	})
	out := make([]string, 0, len(names))
	for n := range names {
		out = append(out, n)
	}
	sort.Strings(out) // sort($names) — plain ASCII names, so PHP's SORT_REGULAR is a string sort
	return out
}

func inStrings(needle string, hay []string) bool {
	for _, h := range hay {
		if h == needle {
			return true
		}
	}
	return false
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// TagList — invocators/tags/dev/TagList.php — the ?page=tags gallery. THE GATE'S FRAME.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// TagListTag is TagList: every tag under TAGS_DIR as a link; the selected one rendered below.
type TagListTag struct {
	e    *Engine
	args *TagArguments
}

// notPortedHTML is what renderSelected emits for a tag Scan lists but this package cannot render.
//
// It deliberately does NOT reuse TagList.php:74's "Tag class not loadable." — the PHP loads those
// classes perfectly well, so borrowing its message would be a false claim about the PHP's behavior
// dressed up as equivalence. This says what is true instead. See COVERAGE in the file header.
func notPortedHTML(sel string) string {
	return "<p style='color:#b00020'>congruency-go: no Go port of <code>" + esc(sel) +
		"</code> yet &mdash; the PHP renders this tag; this port does not. " +
		"This notice is a DIVERGENCE from the PHP render, not a reproduction of it.</p>"
}

// GetDocument is TagList::get_document() (TagList.php:39-86).
func (t *TagListTag) GetDocument() string {
	// The re-entrancy guard: selecting TagList would otherwise render the gallery inside itself
	// forever (TagList.php:18, 40-43).
	if t.e.tagListRendering {
		return "<em>(the tag gallery is rendered by TagList; it is not re-rendered inside itself)</em>"
	}
	t.e.tagListRendering = true
	defer func() { t.e.tagListRendering = false }() // PHP's finally (TagList.php:83-85)

	names := Scan(t.e.cfg.TagsDir)
	sel := t.e.getStr("tag")

	var out strings.Builder
	out.WriteString("<style>.taglist{display:flex;flex-wrap:wrap;gap:.4rem;list-style:none;padding:0}" +
		".taglist a{display:inline-block;border:1px solid #d8d2c4;border-radius:4px;padding:.15rem .5rem;background:#fffdf8;font:.85rem/1.4 monospace}" +
		".taglist a.sel{background:#8a5a1a;color:#fff;border-color:#8a5a1a}" +
		".tagout{margin-top:1.2rem;border:1px solid #d8d2c4;border-left:5px solid #8a5a1a;border-radius:6px;padding:.8rem 1rem;background:#fffdf8}" +
		".tagout h3{margin:0 0 .5rem;font-weight:normal}</style>\n")
	out.WriteString("<p style='font-size:.85rem;color:#555'><strong>" + strconv.Itoa(len(names)) +
		"</strong> tags &mdash; click one to render it.</p>\n")
	out.WriteString("<ul class='taglist'>\n")
	for _, n := range names {
		cls := ""
		if n == sel {
			cls = " class='sel'"
		}
		out.WriteString("  <li><a" + cls + " href='?page=tags&tag=" + esc(n) + "'>" + esc(n) + "</a></li>\n")
	}
	out.WriteString("</ul>\n")

	// in_array($sel, $names, true) — the whitelist that stops ?tag= loading an arbitrary class
	// (TagList.php:10-12). Only a name the scan already found is ever instantiated.
	switch {
	case sel != "" && inStrings(sel, names):
		out.WriteString("<div class='tagout'><h3>&lt;&lt;&lt;" + esc(sel) + "&gt;&gt;&gt;</h3>\n")
		out.WriteString(t.renderSelected(sel))
		out.WriteString("</div>\n")
	case sel != "":
		out.WriteString("<p style='color:#b00020'>Unknown tag: " + esc(sel) + "</p>")
	}
	return out.String()
}

// renderSelected is TagList.php:63-75: load the class, construct it with NULL, render it, and
// catch anything it throws.
//
//	$obj = new $sel(null);
//	$out .= (string)$obj->get_document();
//	catch (\Throwable $e) -> "This tag needs context to render standalone: <class>: <msg>"
//
// The recover() below is that catch. Each ported tag already catches its own errors internally
// (mirroring its PHP class's own try/catch), so this is the outer net for a Go panic — e.g. a nil
// map deref — which has no PHP counterpart and therefore no faithful message. It reports itself as
// a Go panic rather than impersonating a PHP exception string; a crash is a #226 finding, a marked
// panic notice is not.
func (t *TagListTag) renderSelected(sel string) (out string) {
	defer func() {
		if r := recover(); r != nil {
			out = "<p style='color:#b00020'>congruency-go: panic rendering <code>" + esc(sel) +
				"</code>: " + esc(fmt.Sprint(r)) + "</p>"
		}
	}()
	obj, ok := t.e.lookupTag(sel, nil) // new $sel(null)
	if !ok {
		return notPortedHTML(sel)
	}
	return obj.GetDocument()
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// CategoryBrowse — invocators/tags/dev/CategoryBrowse.php
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// CategoryBrowseTag is CategoryBrowse: every category and its tagged pages in one expanded pass.
type CategoryBrowseTag struct {
	e        *Engine
	category string
}

// newCategoryBrowseTag is CategoryBrowse::__construct (CategoryBrowse.php:29-32):
//
//	$this->category = (isset($arguments) && method_exists($arguments,'top')) ? $arguments->top() : '';
//
// A nil *TagArguments is the PHP's NULL, which is the standalone/gallery case.
func newCategoryBrowseTag(e *Engine, args *TagArguments) *CategoryBrowseTag {
	c := &CategoryBrowseTag{e: e}
	if args != nil {
		c.category = args.Top()
	}
	return c
}

// GetDocument is CategoryBrowse::get_document() (CategoryBrowse.php:69-107).
func (t *CategoryBrowseTag) GetDocument() (out string) {
	defer catchThrowable(&out, "CategoryBrowse")
	if t.e.cfg.SQLite == "" {
		return "<p>CategoryBrowse: no DB.</p>" // !defined('CONGRUENCY_SQLITE')
	}
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return throwableHTML("CategoryBrowse", err)
	}
	defer db.Close()

	// focus comes from the tag argument, else the ?category= URL param
	cat := phpTrim(t.category)
	if cat == "" {
		if v, ok := t.e.getIsset("category"); ok {
			cat = phpTrim(v)
		}
	}

	if cat != "" { // focus a single category
		rows, err := queryRows(db, "SELECT name, description,\n"+
			"                        (SELECT COUNT(*) FROM annotations a WHERE a.tag=Categories.name AND a.target LIKE 'page:%') AS n\n"+
			"                        FROM Categories WHERE name=?", cat)
		if err != nil {
			return throwableHTML("CategoryBrowse", err)
		}
		if len(rows) == 0 {
			return "<p>No such category: <code>" + esc(cat) + "</code>. <a href='?page=tags&tag=CategoryBrowse'>&larr; browse all</a></p>"
		}
		c := rows[0]
		return "<div class='category-browse'>" + t.section(db, phpString(c["name"]), c["description"], c["n"]) +
			"<p style='margin-top:.8rem'><a href='?page=tags&tag=CategoryBrowse'>&larr; browse all categories</a></p></div>"
	}

	// full browse: every category, with page counts, ordered by name
	cats, err := queryRows(db, "SELECT name, description,\n"+
		"                    (SELECT COUNT(*) FROM annotations a WHERE a.tag=Categories.name AND a.target LIKE 'page:%') AS n\n"+
		"                    FROM Categories ORDER BY name")
	if err != nil {
		return throwableHTML("CategoryBrowse", err)
	}
	if len(cats) == 0 {
		return "<p>No categories yet. Create one at <a href='?page=forms'>the admin forms</a>.</p>"
	}

	pages := int64(0)
	for _, c := range cats {
		pages += toInt(c["n"])
	}
	// PHP: count($cats)===1 ? "y" : "ies"  /  $pages===1 ? "" : "s"
	out = "<div class='category-browse'><p style='color:#555;font-size:.9rem'><strong>" +
		strconv.Itoa(len(cats)) + "</strong> categor" + plural(len(cats) == 1, "y", "ies") +
		" &middot; <strong>" + strconv.FormatInt(pages, 10) + "</strong> page tag" + plural(pages == 1, "", "s") + "</p>"
	for _, c := range cats {
		out += t.section(db, phpString(c["name"]), c["description"], c["n"])
	}
	return out + "</div>"
}

func plural(cond bool, a, b string) string {
	if cond {
		return a
	}
	return b
}

// section is CategoryBrowse::section (CategoryBrowse.php:59-67): heading + description + pages.
// $n is cast (int) in the PHP, so a NULL count renders "0".
func (t *CategoryBrowseTag) section(db *sql.DB, name string, description, n any) string {
	head := "<h3 style='margin:.8rem 0 .2rem;font-weight:normal'>" +
		"<a href='?page=pages&category=" + esc(name) + "'>" + esc(name) + "</a>" +
		" <span style='color:#888;font-size:.85rem'>(" + strconv.FormatInt(toInt(n), 10) + ")</span></h3>"
	// PHP: if ($description !== null && $description !== '')
	if d := phpString(description); description != nil && d != "" {
		head += "<p style='margin:.1rem 0 .3rem;color:#666;font-size:.9rem'>" + esc(d) + "</p>"
	}
	return head + t.pagesFor(db, name)
}

// pagesFor is CategoryBrowse::pagesFor (CategoryBrowse.php:43-56). The join reproduces the
// comment's rule exactly: 'page:' is 5 chars and sqlite's substr is 1-indexed, so substr(target,6)
// is the DocumentID.
func (t *CategoryBrowseTag) pagesFor(db *sql.DB, name string) string {
	rows, err := queryRows(db, "SELECT d.DocumentID, d.Title FROM annotations a\n"+
		"                JOIN Documents d ON d.DocumentID=substr(a.target, 6)\n"+
		"                WHERE a.tag=? AND a.target LIKE 'page:%' ORDER BY d.DocumentID", name)
	if err != nil || len(rows) == 0 {
		return "<p style='margin:.2rem 0 .2rem 1rem;color:#888'><em>no pages tagged yet</em></p>"
	}
	out := "<ul style='margin:.2rem 0 .6rem'>"
	for _, r := range rows {
		// PHP: ($r['Title'] !== null && $r['Title'] !== '') ? $r['Title'] : $r['DocumentID']
		title := phpString(r["Title"])
		if r["Title"] == nil || title == "" {
			title = phpString(r["DocumentID"])
		}
		out += "<li><a href='?page=" + esc(r["DocumentID"]) + "'>" + esc(title) + "</a></li>"
	}
	return out + "</ul>"
}

// catchThrowable / throwableHTML model each tag's own `catch (\Throwable $e)` arm, which every
// ported class below has because the engine has NO error boundary of its own (FormTag.php:53-55:
// "Tag_Wrapper::execute_all_tags calls get_document() uncaught — so a form problem would otherwise
// take the whole page down").
//
// PHP renders get_class($e).': '.$e->getMessage(); a Go error has no class, so the message alone is
// used. That text is inside a marked cy-form-error div in both, and only appears when something is
// already broken.
func throwableHTML(tag string, err error) string {
	return "<div class='cy-form-error'>" + tag + " error: " + esc(err.Error()) + "</div>"
}

func catchThrowable(out *string, tag string) {
	if r := recover(); r != nil {
		*out = "<div class='cy-form-error'>" + tag + " error: " + esc(fmt.Sprint(r)) + "</div>"
	}
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// TreeView — invocators/tags/dev/TreeView.php — browse a registered repo's tree from forge's remote.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// TreeViewTag is TreeView. Its data plane is `git --git-dir=<remote> ls-tree|show`, read-only.
//
// The PHP builds a SHELL string and escapeshellarg()s every argument (TreeView.php:92-96,132-133).
// Go runs git directly with an argv — no shell, so nothing needs escaping and nothing can be
// injected. That is the same command with the same arguments; escapeshellarg exists precisely to
// turn a string into one argv entry, which is what an argv already is. The repo NAME is still
// whitelist-checked against the DB first (TreeView.php:37,45-47), exactly as the PHP does.
type TreeViewTag struct {
	e    *Engine
	args *TagArguments
}

type treeRepo struct{ name, forgeRemote, headCommit string }

// GetDocument is TreeView::get_document() (TreeView.php:31-59).
func (t *TreeViewTag) GetDocument() (out string) {
	defer catchThrowable(&out, "TreeView")
	if t.e.cfg.SQLite == "" {
		return "<p>TreeView: no DB.</p>"
	}
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		// TreeView's catch prints only getMessage(), not get_class().': '.getMessage().
		return "<div class='cy-form-error'>TreeView error: " + esc(err.Error()) + "</div>"
	}
	defer db.Close()

	// whitelist: ONLY repos actually registered in the DB may be browsed
	rows, err := queryRows(db, "SELECT name, forge_remote, head_commit FROM repos ORDER BY name")
	if err != nil {
		return "<div class='cy-form-error'>TreeView error: " + esc(err.Error()) + "</div>"
	}
	repos := map[string]treeRepo{}
	order := make([]string, 0, len(rows))
	for _, r := range rows {
		n := phpString(r["name"])
		repos[n] = treeRepo{n, phpString(r["forge_remote"]), phpString(r["head_commit"])}
		order = append(order, n)
	}

	repo := t.e.getStr("repo")
	if repo == "" {
		return t.index(repos, order)
	}
	r, ok := repos[repo]
	if !ok {
		return "<p><strong>No such registered repo.</strong> <a href='?page=tree'>&larr; repos</a></p>"
	}
	if blob := t.e.getStr("blob"); blob != "" {
		return t.viewBlob(repo, r.forgeRemote, r.headCommit, blob)
	}
	return t.viewTree(repo, r.forgeRemote, r.headCommit, t.e.getStr("path"))
}

// index is TreeView::index (TreeView.php:61-69). PHP iterates $repos in INSERTION order (the SQL's
// ORDER BY name), which `order` preserves — a Go map range would not.
func (t *TreeViewTag) index(repos map[string]treeRepo, order []string) string {
	if len(order) == 0 {
		return "<p>No repos registered.</p>"
	}
	out := "<p>Registered repos &mdash; browse each one's real source tree, read straight from its forge remote.</p>\n<ul class='srclist'>\n"
	for _, name := range order {
		r := repos[name]
		out += "<li>&#128193; <a href='?page=tree&repo=" + esc(phpURLEncode(name)) + "'>" + esc(name) + "</a> " +
			"<span style='color:#888;font-size:.85em'>@ " + esc(phpSubstr(r.headCommit, 0, 12)) + "</span></li>\n"
	}
	return out + "</ul>\n"
}

// crumbs is TreeView::crumbs (TreeView.php:72-89) — "repos › <repo> › seg › seg", last seg plain.
func (t *TreeViewTag) crumbs(repo, path string) string {
	out := "<p style='font-size:.9rem'><a href='?page=tree'>repos</a> &rsaquo; " +
		"<a href='?page=tree&repo=" + esc(phpURLEncode(repo)) + "'>" + esc(repo) + "</a>"
	var segs []string
	if path != "" {
		segs = strings.Split(strings.Trim(path, "/"), "/")
	}
	last := len(segs) - 1
	acc := ""
	for i, s := range segs {
		if s == "" {
			continue
		}
		if acc == "" {
			acc = s
		} else {
			acc = acc + "/" + s
		}
		out += " &rsaquo; "
		if i == last {
			out += esc(s)
		} else {
			out += "<a href='?page=tree&repo=" + esc(phpURLEncode(repo)) + "&path=" + esc(phpURLEncode(acc)) + "'>" + esc(s) + "</a>"
		}
	}
	return out + "</p>\n"
}

// viewTree is TreeView::viewTree (TreeView.php:91-129): `git --git-dir=<d> ls-tree <commit> [path/]`.
func (t *TreeViewTag) viewTree(repo, gitdir, commit, path string) string {
	spec := ""
	if path != "" {
		spec = strings.TrimRight(path, "/") + "/"
	}
	argv := []string{"--git-dir=" + gitdir, "ls-tree", commit}
	if spec != "" {
		argv = append(argv, spec)
	}
	stdout, err := t.e.cfg.exec("git", argv...)

	out := t.crumbs(repo, path)
	if err != nil { // $rc !== 0 (the PHP's `2>/dev/null` is Output()'s dropped stderr)
		return out + "<p>Could not read the tree at <code>" + esc(path) + "</code>.</p>"
	}
	type ent struct{ name, full string }
	var dirs, files []ent
	for _, ln := range execLines(string(stdout)) {
		// <mode> SP <type> SP <object> TAB <name>
		tab := strings.IndexByte(ln, '\t')
		if tab < 0 {
			continue
		}
		meta, name := ln[:tab], ln[tab+1:]
		parts := splitWS(meta) // preg_split('/\s+/', $meta)
		typ := ""
		if len(parts) > 1 {
			typ = parts[1]
		}
		base := filepath.Base(name)
		switch typ {
		case "tree":
			dirs = append(dirs, ent{base, name})
		case "blob":
			files = append(files, ent{base, name})
		}
	}
	if len(dirs) == 0 && len(files) == 0 {
		return out + "<p>(empty tree)</p>"
	}
	out += "<ul class='srclist'>\n"
	for _, d := range dirs {
		out += "<li>&#128193; <a href='?page=tree&repo=" + esc(phpURLEncode(repo)) + "&path=" + esc(phpURLEncode(d.full)) + "'>" + esc(d.name) + "/</a></li>\n"
	}
	for _, f := range files {
		out += "<li>&#128196; <a href='?page=tree&repo=" + esc(phpURLEncode(repo)) + "&blob=" + esc(phpURLEncode(f.full)) + "'>" + esc(f.name) + "</a></li>\n"
	}
	return out + "</ul>\n"
}

// execLines mirrors PHP exec()'s $output array: one entry per line, no trailing newline, and no
// final empty element for the trailing newline the command emits.
func execLines(s string) []string {
	s = strings.TrimSuffix(s, "\n")
	if s == "" {
		return nil
	}
	return strings.Split(s, "\n")
}

// viewBlob is TreeView::viewBlob (TreeView.php:131-149): `git --git-dir=<d> show <commit>:<path>`
// into a line-numbered <pre>, every line htmlspecialchars()'d BEFORE it is emitted (the guard).
//
// NB shell_exec() returns NULL "if an error occurred or the command produces no output" — so an
// EMPTY blob takes the same branch as a missing one. That is reproduced: empty stdout is null.
func (t *TreeViewTag) viewBlob(repo, gitdir, commit, blob string) string {
	stdout, err := t.e.cfg.exec("git", "--git-dir="+gitdir, "show", commit+":"+blob)
	out := t.crumbs(repo, blob)
	if err != nil || len(stdout) == 0 { // $body === null
		return out + "<p>Could not read <code>" + esc(blob) + "</code>. <a href='?page=tree&repo=" + esc(phpURLEncode(repo)) + "'>&larr; tree</a></p>"
	}
	head := "<p><strong>" + esc(blob) + "</strong> <span style='color:#888'>@ " + esc(phpSubstr(commit, 0, 12)) + "</span></p>\n"
	// esc FIRST, then split — the PHP escapes the whole body and explodes the escaped string, so a
	// literal <<<Tag>>> in source is inert before it is ever emitted (TreeView.php:20-22).
	lines := strings.Split(esc(string(stdout)), "\n")
	code := "<pre style='background:#f4f1e8;border:1px solid #d8d2c4;padding:.6rem;overflow:auto;font-size:.82rem;line-height:1.4'>"
	n := 1
	for _, ln := range lines {
		code += "<span style='color:#b0a890;user-select:none'>" + fmt.Sprintf("%4d", n) + "</span>  " + ln + "\n"
		n++
	}
	code += "</pre>\n"
	return out + head + code
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// BugCatalog — invocators/tags/dev/BugCatalog.php — the unified bug catalog on ?page=bugs.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// BugCatalogTag is BugCatalog. Its stored titles CONTAIN literal <<<Tag>>> and <script> by design
// (BugCatalog.php:20-22), which makes it the sharpest test of the htmlspecialchars guard: every
// value below is esc()'d before it can flow back into execute_all_tags.
type BugCatalogTag struct {
	e    *Engine
	args *TagArguments
}

func bugSeverityColor(s string) string {
	switch s {
	case "critical":
		return "#c62828"
	case "high":
		return "#e65100"
	case "medium":
		return "#b5a300"
	case "low":
		return "#777"
	default:
		return "#555"
	}
}

// GetDocument is BugCatalog::get_document() (BugCatalog.php:42-71).
func (t *BugCatalogTag) GetDocument() (out string) {
	defer catchThrowable(&out, "BugCatalog")
	source := t.e.getStr("source")
	severity := t.e.getStr("severity")
	if !inStrings(source, []string{"", "congruency", "corpus"}) {
		source = ""
	}
	if !inStrings(severity, []string{"", "critical", "high", "medium", "low"}) {
		severity = ""
	}

	form := t.form(source, severity)
	if t.e.cfg.SQLite == "" {
		return form + "<p class='cy-form-error'>BugCatalog: no DB.</p>"
	}
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return form + "<div class='cy-form-error'>BugCatalog error: " + esc(err.Error()) + "</div>"
	}
	defer db.Close()

	// A missing `bugs` table is its own message, distinct from an empty one (BugCatalog.php:58-65).
	total, err := scalar(db, "SELECT COUNT(*) FROM bugs")
	if err != nil {
		return form + "<p class='cy-form-error'>no bugs table yet &mdash; ingest with <code>bug.record</code></p>"
	}
	if toInt(total) == 0 {
		return form + "<p>no bugs recorded yet &mdash; ingest with <code>bug.record</code> (source=congruency|corpus).</p>\n"
	}
	summary, err := t.summary(db)
	if err != nil {
		return form + "<div class='cy-form-error'>BugCatalog error: " + esc(err.Error()) + "</div>"
	}
	table, err := t.table(db, source, severity)
	if err != nil {
		return form + "<div class='cy-form-error'>BugCatalog error: " + esc(err.Error()) + "</div>"
	}
	return form + summary + table
}

// form is BugCatalog::form (BugCatalog.php:73-90). The option lists are PHP ARRAY LITERALS, so
// their order is fixed by the source, not by any sort.
func (t *BugCatalogTag) form(source, severity string) string {
	out := "<form method='get' action=''>\n"
	out += "<input type='hidden' name='page' value='bugs'>\n"
	out += "<select name='source'>\n"
	for _, kv := range [][2]string{{"", "(all sources)"}, {"congruency", "congruency"}, {"corpus", "corpus"}} {
		sel := ""
		if source == kv[0] {
			sel = " selected"
		}
		out += "<option value='" + esc(kv[0]) + "'" + sel + ">" + esc(kv[1]) + "</option>\n"
	}
	out += "</select>\n"
	out += "<select name='severity'>\n"
	for _, kv := range [][2]string{{"", "(any severity)"}, {"critical", "critical"}, {"high", "high"}, {"medium", "medium"}, {"low", "low"}} {
		sel := ""
		if severity == kv[0] {
			sel = " selected"
		}
		out += "<option value='" + esc(kv[0]) + "'" + sel + ">" + esc(kv[1]) + "</option>\n"
	}
	out += "</select>\n"
	out += "<button type='submit'>Filter</button>\n</form>\n"
	return out
}

// summary is BugCatalog::summary (BugCatalog.php:92-109).
func (t *BugCatalogTag) summary(db *sql.DB) (string, error) {
	total, err := scalar(db, "SELECT COUNT(*) FROM bugs")
	if err != nil {
		return "", err
	}
	bysev, err := queryRows(db, "SELECT severity, COUNT(*) AS n FROM bugs GROUP BY severity")
	if err != nil {
		return "", err
	}
	bysrc, err := queryRows(db, "SELECT source, COUNT(*) AS n FROM bugs GROUP BY source")
	if err != nil {
		return "", err
	}
	var sevparts, srcparts []string
	for _, r := range bysev {
		sevparts = append(sevparts, "<span style='color:"+bugSeverityColor(phpString(r["severity"]))+"'>"+
			esc(r["severity"])+"</span>&nbsp;"+esc(r["n"]))
	}
	for _, r := range bysrc {
		srcparts = append(srcparts, esc(r["source"])+"&nbsp;"+esc(r["n"]))
	}
	out := "<p class='bug-summary'><strong>" + esc(total) + "</strong> bugs"
	if len(sevparts) > 0 {
		out += " &mdash; by severity: " + strings.Join(sevparts, " &middot; ")
	}
	if len(srcparts) > 0 {
		out += " &mdash; by source: " + strings.Join(srcparts, " &middot; ")
	}
	return out + "</p>\n", nil
}

// table is BugCatalog::table (BugCatalog.php:111-147). The facets are BOUND, never interpolated —
// the PHP's own rule (BugCatalog.php:22). Its WHERE makes an unset facet match everything by
// comparing the bound value to the empty string:
//
//	WHERE (:source='' OR source=:source) AND (:severity='' OR severity=:severity)
//
// Each named param therefore appears TWICE, which database/sql supports through sql.Named.
func (t *BugCatalogTag) table(db *sql.DB, source, severity string) (string, error) {
	rows, err := queryRows(db,
		"SELECT bug_id, source, title, severity, location, repro, success, fanout, repos, status, pattern\n"+
			"                    FROM bugs WHERE (:source='' OR source=:source) AND (:severity='' OR severity=:severity)\n"+
			"                    ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, source, bug_id LIMIT 300",
		sql.Named("source", source), sql.Named("severity", severity))
	if err != nil {
		return "", err
	}
	out := "<h2>Bugs"
	if source != "" {
		out += " &middot; " + esc(source)
	}
	if severity != "" {
		out += " &middot; " + esc(severity)
	}
	if source != "" || severity != "" {
		out += " <a href='?page=bugs'>&times;</a>"
	}
	out += "</h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no bugs match this filter)</p>\n", nil
	}

	out += "<table class='bug-catalog' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += "<tr><th style='text-align:left'>id</th><th style='text-align:left'>severity</th><th style='text-align:left'>title</th><th style='text-align:left'>location</th><th style='text-align:left'>source</th><th style='text-align:left'>detail</th><th style='text-align:left'>status</th></tr>\n"
	for _, r := range rows {
		c := bugSeverityColor(phpString(r["severity"]))
		var detail string
		if phpString(r["source"]) == "corpus" {
			detail = "fanout " + esc(r["fanout"]) + " / " + esc(r["repos"]) + " repos"
			if r["pattern"] != nil && phpString(r["pattern"]) != "" {
				detail += " <code>" + esc(r["pattern"]) + "</code>"
			}
		} else if r["repro"] != nil && phpString(r["repro"]) != "" {
			detail = "<code>" + esc(r["repro"]) + "</code>"
		} else {
			detail = esc(r["success"])
		}
		out += "<tr>" +
			"<td><code>" + esc(r["bug_id"]) + "</code></td>" +
			"<td class='bug-sev bug-sev-" + esc(r["severity"]) + "' style='color:" + c + ";font-weight:600'>" + esc(r["severity"]) + "</td>" +
			"<td>" + esc(r["title"]) + "</td>" +
			"<td>" + esc(r["location"]) + "</td>" +
			"<td>" + esc(r["source"]) + "</td>" +
			"<td>" + detail + "</td>" +
			"<td>" + esc(r["status"]) + "</td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// FormTag — invocators/tags/dev/FormTag.php — render a stored form by id.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// formKeyRe is FormTag::FORM_KEY_RE = '/^[A-Za-z0-9_-]+\z/' (FormTag.php:62). \z (not $) so a
// trailing newline cannot slip past — Go's $ is already \z-like under default (non-multiline)
// flags, but `\z` is written out so the intent survives a reader's glance.
var formKeyRe = regexp.MustCompile(`^[A-Za-z0-9_-]+\z`)

// tagArgRe is FormTag::TAG_ARG_RE = '/^[A-Za-z0-9]+\z/' (FormTag.php:65) — the tag parser's
// FUNCTION_ARGUMENT charset, used only to label the stored-form list.
var tagArgRe = regexp.MustCompile(`^[A-Za-z0-9]+\z`)

// FormTagTag is FormTag.
//
// #226's gate renders it as `new FormTag(null)` (TagList.php:67), which lands on the empty-id
// branch — the usage panel. That is deliberate on the PHP's side: FormTag.php:17-42 exists because
// the empty id used to hit ValidateFields::validateFormKey's unguarded $result[0] read and print
// two PHP warnings into the page (bug #160). FormTag answers the empty id ITSELF, before the
// pipeline ever sees it, which is why this branch is pure string-building and ports exactly.
type FormTagTag struct {
	e      *Engine
	formID string
}

// newFormTag is FormTag::__construct (FormTag.php:69-77):
//
//	if (is_object($arguments) && method_exists($arguments,'pop')) $id = $arguments->pop();
//	elseif (is_string($arguments)) $id = $arguments;
//	$this->formId = is_string($id) ? trim($id) : '';
//
// pop() returns NULL once the list is empty, and is_string(NULL) is false — hence formID "".
func newFormTag(e *Engine, args *TagArguments) *FormTagTag {
	f := &FormTagTag{e: e}
	if args != nil {
		if v, ok := args.Pop(); ok {
			f.formID = phpTrim(v)
		}
	}
	return f
}

// formNote is FormTag::note (FormTag.php:81-84).
func formNote(html string) string {
	return "<div class='cy-form-note' style='border:1px solid #d8d2c4;border-left:5px solid #8a5a1a;" +
		"border-radius:6px;padding:.7rem .9rem;background:#fffdf8'>" + html + "</div>"
}

// GetDocument is FormTag::get_document() (FormTag.php:127-155).
func (t *FormTagTag) GetDocument() (out string) {
	defer catchThrowable(&out, "FormTag")
	if t.formID == "" {
		return formNote("<strong>FormTag</strong> renders a stored form by id. Give it one, e.g." +
			" <code>&lt;&lt;&lt;FormTag(OrderForm)&gt;&gt;&gt;</code>." + t.formsLine())
	}
	if !formKeyRe.MatchString(t.formID) {
		return formNote("<strong>FormTag:</strong> <code>" + esc(t.formID) + "</code> is not a usable" +
			" form id — an id is one or more letters, digits, <code>-</code> or <code>_</code>," +
			" and nothing else." + t.formsLine())
	}
	fm := t.e.cfg.FormManager
	if fm == nil { // !isset($formManager) — no FORM_MANAGER in the POM (divergence 3 in the header)
		return formNote("<strong>FormTag:</strong> no FORM_MANAGER in the POM — the form system is not" +
			" initialized, so no form can be built.")
	}
	html := fm.RunForm(t.formID)
	// runForm() reports an unbuildable form by returning FORM_LOAD_FAILURE, an HTML comment —
	// invisible on the page. Say it out loud instead (FormTag.php:144-149).
	if lf := fm.LoadFailure(); lf != "" && html == lf {
		return formNote("<strong>FormTag:</strong> no form named <code>" + esc(t.formID) +
			"</code> is stored." + t.formsLine())
	}
	return "<div class='cy-form'>" + html + "</div>"
}

// knownForms is FormTag::knownForms (FormTag.php:89-100) — the distinct formName values in `forms`.
func (t *FormTagTag) knownForms() ([]string, error) {
	var names []string
	if t.e.cfg.SQLite == "" {
		return names, nil
	}
	if _, err := os.Stat(t.e.cfg.SQLite); err != nil {
		return names, nil // !is_file(CONGRUENCY_SQLITE)
	}
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	col, err := queryColumn(db, "SELECT DISTINCT formName FROM forms ORDER BY formName")
	if err != nil {
		return nil, err
	}
	for _, v := range col {
		if n := phpTrim(phpString(v)); n != "" {
			names = append(names, n)
		}
	}
	return names, nil
}

// formsLine is FormTag::formsLine (FormTag.php:105-125): "Stored forms: a, b, c", plus a sentence
// naming any id that cannot be written as a document tag. Returns "" if the list cannot be read —
// "the caller is already explaining something, and a database problem must not replace that
// explanation".
func (t *FormTagTag) formsLine() string {
	names, err := t.knownForms()
	if err != nil {
		return ""
	}
	if len(names) == 0 {
		return ""
	}
	var shown, literal []string
	for _, n := range names {
		shown = append(shown, "<code>"+esc(n)+"</code>")
		if !tagArgRe.MatchString(n) {
			literal = append(literal, "<code>"+esc(n)+"</code>")
		}
	}
	out := "<p style='margin:.5rem 0 0'>Stored forms: " + strings.Join(shown, ", ") + "</p>"
	if len(literal) > 0 {
		out += "<p style='margin:.35rem 0 0;font-size:.85rem;color:#555'>" +
			strings.Join(literal, ", ") + " cannot be written as a document tag: the tag parser accepts" +
			" only letters and digits between the parentheses, so such an invocation stays literal text.</p>"
	}
	return out
}

// thRow is the `private static function th($cols)` shared verbatim by MemGraph (MemGraph.php:78-82)
// and OmniExplorer (OmniExplorer.php:147-151).
func thRow(cols ...string) string {
	out := "<tr>"
	for _, c := range cols {
		out += "<th style='text-align:left'>" + esc(c) + "</th>"
	}
	return out + "</tr>\n"
}

// openReflection is the shared shape of the three reflection tags' open:
//
//	if (!is_file($path) || !is_readable($path)) return <missing>;
//	$db = new PDO('sqlite:'.$path); $db->exec('PRAGMA query_only=1');
//
// The PRAGMA is redundant against openDB's read-only handle (the connection cannot write either
// way), but it is issued anyway so the Go states the same guarantee the PHP does at the same point.
func openReflection(cfg Config, path string) (*sql.DB, bool) {
	st, err := os.Stat(path)
	if err != nil || st.IsDir() {
		return nil, false
	}
	db, err := openDB(cfg, path)
	if err != nil {
		return nil, false
	}
	if _, err := db.Exec("PRAGMA query_only=1"); err != nil {
		db.Close()
		return nil, false
	}
	return db, true
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// ForgeView — invocators/tags/dev/ForgeView.php — a read-only reflection of the LOCAL forge store.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// ForgeViewTag is ForgeView. It reads forge.db — a SEPARATE sqlite file from CONGRUENCY_SQLITE
// (ForgeView.php:8-13) — through a second handle, and degrades gracefully when it is absent.
type ForgeViewTag struct {
	e    *Engine
	args *TagArguments
}

func forgeStatusColor(s string) string {
	switch s {
	case "ok":
		return "#2e7d32"
	case "started":
		return "#1565c0"
	case "fail":
		return "#c62828"
	case "skipped":
		return "#8d6e00"
	default:
		return "#555"
	}
}

// GetDocument is ForgeView::get_document() (ForgeView.php:37-54).
func (t *ForgeViewTag) GetDocument() (out string) {
	defer catchThrowable(&out, "ForgeView")
	path := t.e.cfg.ForgeDB
	db, ok := openReflection(t.e.cfg, path)
	if !ok {
		return "<p class='cy-form-error'>forge db not found at <code>" + esc(path) + "</code></p>"
	}
	defer db.Close()

	summary, err := t.summary(db)
	if err != nil {
		return "<div class='cy-form-error'>ForgeView error: " + esc(err.Error()) + "</div>"
	}
	actions, err := t.actions(db)
	if err != nil {
		return "<div class='cy-form-error'>ForgeView error: " + esc(err.Error()) + "</div>"
	}
	artifacts, err := t.artifacts(db)
	if err != nil {
		return "<div class='cy-form-error'>ForgeView error: " + esc(err.Error()) + "</div>"
	}
	return summary + actions + artifacts
}

// summary is ForgeView::summary (ForgeView.php:71-110).
func (t *ForgeViewTag) summary(db *sql.DB) (string, error) {
	acts := scalarOrZero(db, "SELECT COUNT(*) FROM actions")
	runs := scalarOrZero(db, "SELECT COUNT(DISTINCT run_id) FROM actions")
	arts := scalarOrZero(db, "SELECT COUNT(*) FROM artifacts")
	names := scalarOrZero(db, "SELECT COUNT(DISTINCT name) FROM artifacts")
	size := scalarOrZero(db, "SELECT COALESCE(SUM(size),0) FROM artifacts")

	out := "<h2>Summary</h2>\n<ul class='srclist'>\n"
	out += "<li><strong>" + esc(acts) + "</strong> actions across <strong>" + esc(runs) + "</strong> runs</li>\n"
	out += "<li><strong>" + esc(arts) + "</strong> artifacts (<strong>" + esc(names) + "</strong> distinct names), <strong>" + esc(size) + "</strong> bytes total</li>\n"

	byst, err := queryRows(db, "SELECT status, COUNT(*) AS n FROM actions GROUP BY status ORDER BY status")
	if err != nil {
		return "", err
	}
	if len(byst) > 0 {
		var parts []string
		for _, r := range byst {
			parts = append(parts, "<a href='?page=forge&status="+esc(phpURLEncode(phpString(r["status"])))+"'><span style='color:"+
				forgeStatusColor(phpString(r["status"]))+"'>"+esc(r["status"])+"</span></a>&nbsp;"+esc(r["n"]))
		}
		out += "<li>status: " + strings.Join(parts, " &middot; ") + "</li>\n"
	}
	topact, err := queryRows(db, "SELECT action, COUNT(*) AS n FROM actions GROUP BY action ORDER BY n DESC, action LIMIT 12")
	if err != nil {
		return "", err
	}
	if len(topact) > 0 {
		var aparts []string
		for _, r := range topact {
			aparts = append(aparts, "<a href='?page=forge&action="+esc(phpURLEncode(phpString(r["action"])))+"'>"+
				esc(r["action"])+"</a>&nbsp;"+esc(r["n"]))
		}
		out += "<li>top actions: " + strings.Join(aparts, " &middot; ") + "</li>\n"
	}
	out += "</ul>\n"

	// the omni corpus / bare archives: archive.register row(s) if present
	ar, err := queryRows(db, "SELECT id, target, status, substr(detail,1,120) AS detail FROM actions WHERE action='archive.register' ORDER BY id DESC LIMIT 5")
	if err != nil {
		return "", err
	}
	if len(ar) > 0 {
		out += "<p><strong>Archives (archive.register):</strong></p>\n<ul class='srclist'>\n"
		for _, r := range ar {
			out += "<li>&#128230; " + esc(r["target"]) + " <span style='color:#888;font-size:.85em'>" +
				esc(r["status"]) + " &middot; " + esc(r["detail"]) + "</span></li>\n"
		}
		out += "</ul>\n"
	}
	return out, nil
}

// actions is ForgeView::actions (ForgeView.php:112-144). The WHERE is assembled from whichever
// facets are set, each BOUND.
func (t *ForgeViewTag) actions(db *sql.DB) (string, error) {
	action := t.e.getStr("action")
	run := t.e.getStr("run")
	status := t.e.getStr("status")

	q := "SELECT id, ts, run_id, action, target, status, substr(detail,1,80) AS detail FROM actions"
	var where []string
	var params []any
	if action != "" {
		where = append(where, "action = :action")
		params = append(params, sql.Named("action", action))
	}
	if run != "" {
		where = append(where, "run_id = :run")
		params = append(params, sql.Named("run", run))
	}
	if status != "" {
		where = append(where, "status = :status")
		params = append(params, sql.Named("status", status))
	}
	if len(where) > 0 {
		q += " WHERE " + strings.Join(where, " AND ")
	}
	q += " ORDER BY id DESC LIMIT 40"
	rows, err := queryRows(db, q, params...)
	if err != nil {
		return "", err
	}

	out := "<h2>Recent actions"
	if action != "" || run != "" || status != "" {
		out += " &middot;"
		if action != "" {
			out += " action " + esc(action)
		}
		if run != "" {
			out += " run " + esc(run)
		}
		if status != "" {
			out += " status " + esc(status)
		}
		out += " <a href='?page=forge'>&times;</a>"
	}
	out += "</h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no actions)</p>\n", nil
	}
	out += "<table class='forge-actions' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += "<tr><th style='text-align:left'>id</th><th style='text-align:left'>ts</th><th style='text-align:left'>run</th><th style='text-align:left'>action</th><th style='text-align:left'>target</th><th style='text-align:left'>status</th><th style='text-align:left'>detail</th></tr>\n"
	for _, r := range rows {
		out += "<tr>" +
			"<td>" + esc(r["id"]) + "</td>" +
			"<td>" + esc(r["ts"]) + "</td>" +
			"<td><a href='?page=forge&run=" + esc(phpURLEncode(phpString(r["run_id"]))) + "'>" + esc(r["run_id"]) + "</a></td>" +
			"<td><a href='?page=forge&action=" + esc(phpURLEncode(phpString(r["action"]))) + "'>" + esc(r["action"]) + "</a></td>" +
			"<td>" + esc(r["target"]) + "</td>" +
			"<td style='color:" + forgeStatusColor(phpString(r["status"])) + "'>" + esc(r["status"]) + "</td>" +
			"<td>" + esc(r["detail"]) + "</td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// artifacts is ForgeView::artifacts (ForgeView.php:146-181).
func (t *ForgeViewTag) artifacts(db *sql.DB) (string, error) {
	name := t.e.getStr("name")
	artkind := t.e.getStr("artkind")
	srcrepo := t.e.getStr("srcrepo")

	q := "SELECT id, name, version, kind, size, substr(sha256,1,12) AS sha, source_repo, source_commit FROM artifacts"
	var where []string
	var params []any
	if name != "" {
		where = append(where, "name = :name")
		params = append(params, sql.Named("name", name))
	}
	if artkind != "" {
		where = append(where, "kind = :artkind")
		params = append(params, sql.Named("artkind", artkind))
	}
	if srcrepo != "" {
		where = append(where, "source_repo = :srcrepo")
		params = append(params, sql.Named("srcrepo", srcrepo))
	}
	if len(where) > 0 {
		q += " WHERE " + strings.Join(where, " AND ")
	}
	q += " ORDER BY id DESC LIMIT 40"
	rows, err := queryRows(db, q, params...)
	if err != nil {
		return "", err
	}

	out := "<h2>Artifacts"
	if name != "" || artkind != "" || srcrepo != "" {
		out += " &middot;"
		if name != "" {
			out += " name " + esc(name)
		}
		if artkind != "" {
			out += " kind " + esc(artkind)
		}
		if srcrepo != "" {
			out += " srcrepo " + esc(srcrepo)
		}
		out += " <a href='?page=forge'>&times;</a>"
	}
	out += "</h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no artifacts)</p>\n", nil
	}
	out += "<table class='forge-artifacts' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += "<tr><th style='text-align:left'>name</th><th style='text-align:left'>version</th><th style='text-align:left'>kind</th><th style='text-align:left'>size</th><th style='text-align:left'>sha256</th><th style='text-align:left'>source</th></tr>\n"
	for _, r := range rows {
		src := "<a href='?page=forge&srcrepo=" + esc(phpURLEncode(phpString(r["source_repo"]))) + "'>" + esc(r["source_repo"]) + "</a>"
		if r["source_commit"] != nil && phpString(r["source_commit"]) != "" {
			src += " <span style='color:#888'>@ " + esc(phpSubstr(phpString(r["source_commit"]), 0, 12)) + "</span>"
		}
		out += "<tr>" +
			"<td><a href='?page=forge&name=" + esc(phpURLEncode(phpString(r["name"]))) + "'>" + esc(r["name"]) + "</a></td>" +
			"<td>" + esc(r["version"]) + "</td>" +
			"<td><a href='?page=forge&artkind=" + esc(phpURLEncode(phpString(r["kind"]))) + "'>" + esc(r["kind"]) + "</a></td>" +
			"<td>" + esc(r["size"]) + "</td>" +
			"<td><code>" + esc(r["sha"]) + "</code></td>" +
			"<td>" + src + "</td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// MemGraph — invocators/tags/dev/MemGraph.php — the RFC-0031 memory-and-spec graph reflection.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// MemGraphTag is MemGraph, reading mem_graph.db (a SEPARATE file; MemGraph.php:8-21).
type MemGraphTag struct {
	e    *Engine
	args *TagArguments
}

// GetDocument is MemGraph::get_document() (MemGraph.php:44-62). Note the lookup form is rendered
// FIRST and prefixed to every branch, including the failures.
func (t *MemGraphTag) GetDocument() (out string) {
	defer catchThrowable(&out, "MemGraph")
	form := t.lookupForm()
	path := t.e.cfg.MemGraphDB
	db, ok := openReflection(t.e.cfg, path)
	if !ok {
		return form + "<p class='cy-form-error'>memory graph not built yet at <code>" + esc(path) +
			"</code> &mdash; run forge/mem_graph.py</p>"
	}
	defer db.Close()

	summary, err := t.summary(db)
	if err != nil {
		return form + "<div class='cy-form-error'>MemGraph error: " + esc(err.Error()) + "</div>"
	}
	body, err := t.body(db)
	if err != nil {
		return form + "<div class='cy-form-error'>MemGraph error: " + esc(err.Error()) + "</div>"
	}
	return form + summary + body
}

// lookupForm is MemGraph::lookup_form (MemGraph.php:64-71).
func (t *MemGraphTag) lookupForm() string {
	return "<form method='get' class='memgraph-lookup' style='margin:.5rem 0'>" +
		"<input type='hidden' name='page' value='memgraph'>" +
		"<input type='text' name='node' value='" + esc(t.e.getStr("node")) + "' placeholder='node id' size='40'>" +
		" <button type='submit'>look up node</button>" +
		"</form>\n"
}

// summary is MemGraph::summary (MemGraph.php:84-111).
func (t *MemGraphTag) summary(db *sql.DB) (string, error) {
	nodes := scalarOrZero(db, "SELECT COUNT(*) FROM node")
	edges := scalarOrZero(db, "SELECT COUNT(*) FROM edge")
	out := "<h2>Summary</h2>\n<ul class='srclist'>\n"
	// The meta table may be absent; its own try/catch degrades to no line (MemGraph.php:88-90).
	if m := safeRows(db, "SELECT built_at, n_nodes, n_edges FROM meta LIMIT 1"); len(m) > 0 {
		out += "<li>built <strong>" + esc(m[0]["built_at"]) + "</strong> &middot; meta says <strong>" +
			esc(m[0]["n_nodes"]) + "</strong> nodes / <strong>" + esc(m[0]["n_edges"]) + "</strong> edges</li>\n"
	}
	out += "<li><strong>" + esc(nodes) + "</strong> nodes &middot; <strong>" + esc(edges) + "</strong> edges (live count)</li>\n"
	out += "</ul>\n"

	nk, err := queryRows(db, "SELECT kind, COUNT(*) AS n FROM node GROUP BY kind ORDER BY 2 DESC")
	if err != nil {
		return "", err
	}
	if len(nk) > 0 {
		var parts []string
		for _, r := range nk {
			parts = append(parts, "<strong>"+esc(r["n"])+"</strong>&nbsp;<a href='?page=memgraph&nodekind="+
				esc(phpURLEncode(phpString(r["kind"])))+"'>"+esc(r["kind"])+"</a>")
		}
		out += "<p><strong>nodes by kind:</strong> " + strings.Join(parts, " &middot; ") + "</p>\n"
	}
	ek, err := queryRows(db, "SELECT kind, COUNT(*) AS n FROM edge GROUP BY kind ORDER BY 2 DESC")
	if err != nil {
		return "", err
	}
	if len(ek) > 0 {
		var parts []string
		for _, r := range ek {
			parts = append(parts, "<strong>"+esc(r["n"])+"</strong>&nbsp;<a href='?page=memgraph&edge="+
				esc(phpURLEncode(phpString(r["kind"])))+"'>"+esc(r["kind"])+"</a>")
		}
		out += "<p><strong>edges by kind:</strong> " + strings.Join(parts, " &middot; ") + "</p>\n"
	}
	return out, nil
}

// body is MemGraph::body (MemGraph.php:113-118) — the facet router. Each test asks that the key is
// set AND non-empty, and the ORDER below is the PHP's: node, then edge, then nodekind, then the
// default. A set-but-empty facet falls through to the next, which is why getIsset is used here.
func (t *MemGraphTag) body(db *sql.DB) (string, error) {
	if v, ok := t.e.getIsset("node"); ok && v != "" {
		return t.byNode(db, v)
	}
	if v, ok := t.e.getIsset("edge"); ok && v != "" {
		return t.byEdge(db, v)
	}
	if v, ok := t.e.getIsset("nodekind"); ok && v != "" {
		return t.byNodeKind(db, v)
	}
	hd, err := t.highDrift(db)
	if err != nil {
		return "", err
	}
	nd, err := t.nearDupes(db)
	if err != nil {
		return "", err
	}
	mc, err := t.mostConnected(db)
	if err != nil {
		return "", err
	}
	return hd + nd + mc, nil
}

// byNodeKind is MemGraph::by_nodekind (MemGraph.php:121-136).
func (t *MemGraphTag) byNodeKind(db *sql.DB, kind string) (string, error) {
	out := "<h2>nodes of kind <code>" + esc(kind) + "</code> <a href='?page=memgraph'>&times;</a></h2>\n"
	rows, err := queryRows(db, "SELECT id, label FROM node WHERE kind=:nodekind ORDER BY id LIMIT 200",
		sql.Named("nodekind", kind))
	if err != nil {
		return "", err
	}
	if len(rows) == 0 {
		return out + "<p>(no nodes of this kind)</p>\n", nil
	}
	out += "<table class='memgraph-nodekind' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += thRow("id", "label")
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=memgraph&node=" + esc(phpURLEncode(phpString(r["id"]))) + "'>" + esc(r["id"]) + "</a></td>" +
			"<td>" + esc(r["label"]) + "</td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// byEdge is MemGraph::by_edge (MemGraph.php:139-155).
func (t *MemGraphTag) byEdge(db *sql.DB, kind string) (string, error) {
	out := "<h2>edges of kind <code>" + esc(kind) + "</code> <a href='?page=memgraph'>&times;</a></h2>\n"
	rows, err := queryRows(db, "SELECT src, dst, round(weight,4) AS w FROM edge WHERE kind=:edge ORDER BY weight DESC, src LIMIT 200",
		sql.Named("edge", kind))
	if err != nil {
		return "", err
	}
	if len(rows) == 0 {
		return out + "<p>(no edges of this kind)</p>\n", nil
	}
	out += "<table class='memgraph-edge' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += thRow("src", "dst", "weight")
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=memgraph&node=" + esc(phpURLEncode(phpString(r["src"]))) + "'>" + esc(r["src"]) + "</a></td>" +
			"<td><a href='?page=memgraph&node=" + esc(phpURLEncode(phpString(r["dst"]))) + "'>" + esc(r["dst"]) + "</a></td>" +
			"<td>" + esc(r["w"]) + "</td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// byNode is MemGraph::by_node (MemGraph.php:158-200) — the node row plus its edges both ways.
func (t *MemGraphTag) byNode(db *sql.DB, node string) (string, error) {
	out := "<h2>node <code>" + esc(node) + "</code> <a href='?page=memgraph'>&times;</a></h2>\n"
	n, err := queryRows(db, "SELECT kind, label, attrs FROM node WHERE id=:node", sql.Named("node", node))
	if err != nil {
		return "", err
	}
	if len(n) > 0 {
		out += "<p>kind <strong>" + esc(n[0]["kind"]) + "</strong> &middot; label <strong>" + esc(n[0]["label"]) +
			"</strong></p>\n<pre style='white-space:pre-wrap;font-size:.8rem'>" + esc(n[0]["attrs"]) + "</pre>\n"
	} else {
		out += "<p>(no such node)</p>\n"
	}

	og, err := queryRows(db, "SELECT kind, dst FROM edge WHERE src=:node ORDER BY kind LIMIT 100", sql.Named("node", node))
	if err != nil {
		return "", err
	}
	out += "<h3>outgoing (" + strconv.Itoa(len(og)) + ")</h3>\n"
	if len(og) == 0 {
		out += "<p>(none)</p>\n"
	} else {
		out += "<table class='memgraph-out' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
		out += thRow("kind", "dst")
		for _, r := range og {
			out += "<tr><td>" + esc(r["kind"]) + "</td>" +
				"<td><a href='?page=memgraph&node=" + esc(phpURLEncode(phpString(r["dst"]))) + "'>" + esc(r["dst"]) + "</a></td></tr>\n"
		}
		out += "</table>\n"
	}

	ic, err := queryRows(db, "SELECT kind, src FROM edge WHERE dst=:node ORDER BY kind LIMIT 100", sql.Named("node", node))
	if err != nil {
		return "", err
	}
	out += "<h3>incoming (" + strconv.Itoa(len(ic)) + ")</h3>\n"
	if len(ic) == 0 {
		out += "<p>(none)</p>\n"
	} else {
		out += "<table class='memgraph-in' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
		out += thRow("kind", "src")
		for _, r := range ic {
			out += "<tr><td>" + esc(r["kind"]) + "</td>" +
				"<td><a href='?page=memgraph&node=" + esc(phpURLEncode(phpString(r["src"]))) + "'>" + esc(r["src"]) + "</a></td></tr>\n"
		}
		out += "</table>\n"
	}
	return out, nil
}

// highDrift is MemGraph::high_drift (MemGraph.php:204-228).
//
// `SELECT *` with DYNAMIC columns: the header is array_keys($rows[0]), so the column ORDER is the
// table's, discovered at runtime. queryRows returns a map, which has no order — so the order is
// re-read from the statement with columnOrder. Getting this wrong would silently shuffle columns.
func (t *MemGraphTag) highDrift(db *sql.DB) (string, error) {
	out := "<h2>High-drift paths <span style='color:#888;font-size:.8em'>(pingpong_raw: raw / branch-interleaved &mdash; not settled truth)</span></h2>\n"
	cols, rows, err := queryAll(db, "SELECT * FROM drift ORDER BY COALESCE(pingpong_raw,0) DESC LIMIT 30")
	if err != nil {
		return out + "<p>(no drift table)</p>\n", nil // catch -> "(no drift table)"
	}
	if len(rows) == 0 {
		return out + "<p>(no drift rows)</p>\n", nil
	}
	out += "<table class='memgraph-drift' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n<tr>"
	for _, c := range cols {
		lbl := c
		if c == "pingpong_raw" {
			lbl = "pingpong_raw (raw / branch-interleaved)"
		}
		out += "<th style='text-align:left'>" + esc(lbl) + "</th>"
	}
	out += "</tr>\n"
	for _, r := range rows {
		out += "<tr>"
		for _, c := range cols {
			// PHP: esc($v === null ? '' : $v)
			out += "<td>" + esc(r[c]) + "</td>"
		}
		out += "</tr>\n"
	}
	return out + "</table>\n", nil
}

// nearDupes is MemGraph::near_dupes (MemGraph.php:231-245).
func (t *MemGraphTag) nearDupes(db *sql.DB) (string, error) {
	rows, err := queryRows(db, "SELECT src, dst, round(weight,4) AS w FROM edge WHERE kind='similar_to' ORDER BY weight DESC LIMIT 30")
	if err != nil {
		return "", err
	}
	out := "<h2>Near-duplicates <span style='color:#888;font-size:.8em'>(similar_to)</span></h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no similar_to edges)</p>\n", nil
	}
	out += "<table class='memgraph-sim' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += thRow("src", "dst", "weight")
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=memgraph&node=" + esc(phpURLEncode(phpString(r["src"]))) + "'>" + esc(r["src"]) + "</a></td>" +
			"<td><a href='?page=memgraph&node=" + esc(phpURLEncode(phpString(r["dst"]))) + "'>" + esc(r["dst"]) + "</a></td>" +
			"<td>" + esc(r["w"]) + "</td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// mostConnected is MemGraph::most_connected (MemGraph.php:248-261).
func (t *MemGraphTag) mostConnected(db *sql.DB) (string, error) {
	rows, err := queryRows(db, "SELECT src, COUNT(*) AS c FROM edge GROUP BY src ORDER BY c DESC LIMIT 20")
	if err != nil {
		return "", err
	}
	out := "<h2>Most-connected nodes</h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no edges)</p>\n", nil
	}
	out += "<table class='memgraph-conn' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += thRow("node", "out-edges")
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=memgraph&node=" + esc(phpURLEncode(phpString(r["src"]))) + "'>" + esc(r["src"]) + "</a></td>" +
			"<td>" + esc(r["c"]) + "</td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// OmniExplorer — invocators/tags/dev/OmniExplorer.php — the omni-git INDEX reflection.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// OmniExplorerTag is OmniExplorer, reading omni_index.db (a SEPARATE file; OmniExplorer.php:8-16).
// occ holds one row per (blob,path) OCCURRENCE across every snapshot, so a path fans out to many
// (repo,ts) pairs.
type OmniExplorerTag struct {
	e    *Engine
	args *TagArguments
}

// GetDocument is OmniExplorer::get_document() (OmniExplorer.php:39-57).
func (t *OmniExplorerTag) GetDocument() (out string) {
	defer catchThrowable(&out, "OmniExplorer")
	form := t.lookupForm()
	path := t.e.cfg.OmniDB
	db, ok := openReflection(t.e.cfg, path)
	if !ok {
		return form + "<p class='cy-form-error'>omni index not found at <code>" + esc(path) + "</code></p>"
	}
	defer db.Close()

	summary, err := t.summary(db)
	if err != nil {
		return form + "<div class='cy-form-error'>OmniExplorer error: " + esc(err.Error()) + "</div>"
	}
	body, err := t.body(db)
	if err != nil {
		return form + "<div class='cy-form-error'>OmniExplorer error: " + esc(err.Error()) + "</div>"
	}
	return form + summary + body
}

// lookupForm is OmniExplorer::lookup_form (OmniExplorer.php:59-66).
func (t *OmniExplorerTag) lookupForm() string {
	return "<form method='get' class='omni-lookup' style='margin:.5rem 0'>" +
		"<input type='hidden' name='page' value='omni'>" +
		"<input type='text' name='path' value='" + esc(t.e.getStr("path")) + "' placeholder='src/app.py' size='40'>" +
		" <button type='submit'>look up file</button>" +
		"</form>\n"
}

// summary is OmniExplorer::summary (OmniExplorer.php:73-81).
func (t *OmniExplorerTag) summary(db *sql.DB) (string, error) {
	occ := scalarOrZero(db, "SELECT COUNT(*) FROM occ")
	paths := scalarOrZero(db, "SELECT COUNT(DISTINCT path) FROM occ")
	repos := scalarOrZero(db, "SELECT COUNT(DISTINCT repo) FROM occ")
	blobs := scalarOrZero(db, "SELECT COUNT(*) FROM blob")
	return "<p class='omni-summary'><strong>" + esc(occ) + "</strong> occurrences &middot; <strong>" +
		esc(paths) + "</strong> distinct paths &middot; <strong>" + esc(repos) +
		"</strong> repos &middot; <strong>" + esc(blobs) + "</strong> blobs</p>\n", nil
}

// body is OmniExplorer::body (OmniExplorer.php:83-91) — the facet router, in the PHP's order.
func (t *OmniExplorerTag) body(db *sql.DB) (string, error) {
	if v, ok := t.e.getIsset("path"); ok && v != "" {
		return t.byPath(db, v)
	}
	if v, ok := t.e.getIsset("repo"); ok && v != "" {
		return t.byRepo(db, v)
	}
	if v, ok := t.e.getIsset("sha"); ok && v != "" {
		return t.bySha(db, v)
	}
	if v, ok := t.e.getIsset("ext"); ok && v != "" {
		return t.byExt(db, v)
	}
	if v, ok := t.e.getIsset("ts"); ok && v != "" {
		return t.byTS(db, v)
	}
	if v, ok := t.e.getIsset("ref"); ok && v != "" {
		return t.byRef(db, v)
	}
	return t.overview(db)
}

// byRef is OmniExplorer::by_ref (OmniExplorer.php:94-109).
func (t *OmniExplorerTag) byRef(db *sql.DB, ref string) (string, error) {
	rows, err := queryRows(db, "SELECT DISTINCT path, repo FROM occ WHERE ref=:ref ORDER BY repo, path LIMIT 200",
		sql.Named("ref", ref))
	if err != nil {
		return "", err
	}
	out := "<h2>files on ref <code>" + esc(ref) + "</code> <a href='?page=omni'>&times;</a></h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no files)</p>\n", nil
	}
	out += "<table class='omni-ref' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += thRow("path", "repo")
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=omni&path=" + esc(phpURLEncode(phpString(r["path"]))) + "'>" + esc(r["path"]) + "</a></td>" +
			"<td><a href='?page=omni&repo=" + esc(phpURLEncode(phpString(r["repo"]))) + "'>" + esc(r["repo"]) + "</a></td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// byTS is OmniExplorer::by_ts (OmniExplorer.php:112-127).
func (t *OmniExplorerTag) byTS(db *sql.DB, ts string) (string, error) {
	rows, err := queryRows(db, "SELECT DISTINCT path, repo FROM occ WHERE ts=:ts ORDER BY repo, path LIMIT 200",
		sql.Named("ts", ts))
	if err != nil {
		return "", err
	}
	out := "<h2>files at snapshot <code>" + esc(ts) + "</code> <a href='?page=omni'>&times;</a></h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no files)</p>\n", nil
	}
	out += "<table class='omni-ts' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += thRow("path", "repo")
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=omni&path=" + esc(phpURLEncode(phpString(r["path"]))) + "'>" + esc(r["path"]) + "</a></td>" +
			"<td><a href='?page=omni&repo=" + esc(phpURLEncode(phpString(r["repo"]))) + "'>" + esc(r["repo"]) + "</a></td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// byExt is OmniExplorer::by_ext (OmniExplorer.php:130-145).
func (t *OmniExplorerTag) byExt(db *sql.DB, ext string) (string, error) {
	rows, err := queryRows(db, "SELECT path, COUNT(DISTINCT repo) AS nr FROM occ WHERE ext=:ext GROUP BY path ORDER BY nr DESC, path LIMIT 200",
		sql.Named("ext", ext))
	if err != nil {
		return "", err
	}
	out := "<h2>files with extension <code>" + esc(ext) + "</code> <a href='?page=omni'>&times;</a></h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no files)</p>\n", nil
	}
	out += "<table class='omni-ext' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += thRow("path", "repos")
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=omni&path=" + esc(phpURLEncode(phpString(r["path"]))) + "'>" + esc(r["path"]) + "</a></td>" +
			"<td>" + esc(r["nr"]) + "</td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// byPath is OmniExplorer::by_path (OmniExplorer.php:154-183) — file -> repos@times, with a LIKE
// candidate fallback when there is no exact hit.
func (t *OmniExplorerTag) byPath(db *sql.DB, p string) (string, error) {
	rows, err := queryRows(db, "SELECT repo, ts, substr(sha,1,10) AS sha, size FROM occ WHERE path=:path ORDER BY ts DESC, repo LIMIT 200",
		sql.Named("path", p))
	if err != nil {
		return "", err
	}
	if len(rows) > 0 {
		out := "<h2>" + esc(p) + " appears in " + strconv.Itoa(len(rows)) + " repos/snapshots</h2>\n"
		out += "<table class='omni-occ' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
		out += thRow("repo", "ts", "sha", "size")
		for _, r := range rows {
			out += "<tr>" +
				"<td><a href='?page=omni&repo=" + esc(phpURLEncode(phpString(r["repo"]))) + "'>" + esc(r["repo"]) + "</a></td>" +
				"<td>" + esc(r["ts"]) + "</td>" +
				"<td><code>" + esc(r["sha"]) + "</code></td>" +
				"<td>" + esc(r["size"]) + "</td>" +
				"</tr>\n"
		}
		return out + "</table>\n", nil
	}
	// no exact hit -> candidate paths (LIKE), each links back to an exact lookup
	cands, err := queryColumn(db, "SELECT DISTINCT path FROM occ WHERE path LIKE :like ORDER BY path LIMIT 60",
		sql.Named("like", "%"+p+"%"))
	if err != nil {
		return "", err
	}
	out := "<h2>No exact match for <code>" + esc(p) + "</code></h2>\n"
	if len(cands) == 0 {
		return out + "<p>(no candidate paths)</p>\n", nil
	}
	out += "<p>candidate paths:</p>\n<ul class='srclist'>\n"
	for _, c := range cands {
		out += "<li><a href='?page=omni&path=" + esc(phpURLEncode(phpString(c))) + "'>" + esc(c) + "</a></li>\n"
	}
	return out + "</ul>\n", nil
}

// byRepo is OmniExplorer::by_repo (OmniExplorer.php:186-202).
func (t *OmniExplorerTag) byRepo(db *sql.DB, repo string) (string, error) {
	rows, err := queryRows(db, "SELECT DISTINCT path, substr(sha,1,10) AS sha, size FROM occ WHERE repo=:repo ORDER BY path LIMIT 200",
		sql.Named("repo", repo))
	if err != nil {
		return "", err
	}
	out := "<h2>files in <code>" + esc(repo) + "</code> <a href='?page=omni'>&times;</a></h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no files)</p>\n", nil
	}
	out += "<table class='omni-repo' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += thRow("path", "sha", "size")
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=omni&path=" + esc(phpURLEncode(phpString(r["path"]))) + "'>" + esc(r["path"]) + "</a></td>" +
			"<td><code>" + esc(r["sha"]) + "</code></td>" +
			"<td>" + esc(r["size"]) + "</td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// bySha is OmniExplorer::by_sha (OmniExplorer.php:205-221) — every place that exact blob lives.
func (t *OmniExplorerTag) bySha(db *sql.DB, sha string) (string, error) {
	rows, err := queryRows(db, "SELECT DISTINCT path, repo, ts FROM occ WHERE sha=:sha ORDER BY repo LIMIT 200",
		sql.Named("sha", sha))
	if err != nil {
		return "", err
	}
	out := "<h2>blob <code>" + esc(sha) + "</code> <a href='?page=omni'>&times;</a></h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no occurrences)</p>\n", nil
	}
	out += "<table class='omni-sha' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += thRow("path", "repo", "ts")
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=omni&path=" + esc(phpURLEncode(phpString(r["path"]))) + "'>" + esc(r["path"]) + "</a></td>" +
			"<td><a href='?page=omni&repo=" + esc(phpURLEncode(phpString(r["repo"]))) + "'>" + esc(r["repo"]) + "</a></td>" +
			"<td>" + esc(r["ts"]) + "</td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// overview is OmniExplorer::overview (OmniExplorer.php:224-273) — the default view.
func (t *OmniExplorerTag) overview(db *sql.DB) (string, error) {
	wide, err := queryRows(db, "SELECT path, COUNT(DISTINCT repo) AS nr FROM occ GROUP BY path ORDER BY nr DESC LIMIT 30")
	if err != nil {
		return "", err
	}
	out := "<h2>Most widely-copied files</h2>\n"
	if len(wide) == 0 {
		out += "<p>(empty index)</p>\n"
	} else {
		out += "<table class='omni-wide' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
		out += thRow("path", "repos")
		for _, r := range wide {
			out += "<tr>" +
				"<td><a href='?page=omni&path=" + esc(phpURLEncode(phpString(r["path"]))) + "'>" + esc(r["path"]) + "</a></td>" +
				"<td>" + esc(r["nr"]) + "</td>" +
				"</tr>\n"
		}
		out += "</table>\n"
	}
	repos, err := queryColumn(db, "SELECT DISTINCT repo FROM occ ORDER BY repo LIMIT 60")
	if err != nil {
		return "", err
	}
	out += "<h2>Repos</h2>\n"
	if len(repos) == 0 {
		return out + "<p>(no repos)</p>\n", nil
	}
	out += "<ul class='srclist'>\n"
	for _, rp := range repos {
		out += "<li><a href='?page=omni&repo=" + esc(phpURLEncode(phpString(rp))) + "'>" + esc(rp) + "</a></li>\n"
	}
	out += "</ul>\n"

	exts, err := queryRows(db, "SELECT ext, COUNT(*) AS n FROM occ WHERE ext IS NOT NULL AND ext<>'' GROUP BY ext ORDER BY n DESC LIMIT 40")
	if err != nil {
		return "", err
	}
	if len(exts) > 0 {
		out += "<h2>By extension</h2>\n<ul class='srclist'>\n"
		for _, e := range exts {
			out += "<li><a href='?page=omni&ext=" + esc(phpURLEncode(phpString(e["ext"]))) + "'>" + esc(e["ext"]) +
				"</a> <span style='color:#888'>" + esc(e["n"]) + "</span></li>\n"
		}
		out += "</ul>\n"
	}
	snaps, err := queryRows(db, "SELECT ts, COUNT(DISTINCT repo) AS nr FROM occ WHERE ts IS NOT NULL AND ts<>'' GROUP BY ts ORDER BY ts DESC LIMIT 40")
	if err != nil {
		return "", err
	}
	if len(snaps) > 0 {
		out += "<h2>Recent snapshots</h2>\n<ul class='srclist'>\n"
		for _, s := range snaps {
			out += "<li><a href='?page=omni&ts=" + esc(phpURLEncode(phpString(s["ts"]))) + "'>" + esc(s["ts"]) +
				"</a> <span style='color:#888'>" + esc(s["nr"]) + " repos</span></li>\n"
		}
		out += "</ul>\n"
	}
	refs, err := queryRows(db, "SELECT ref, COUNT(DISTINCT path) AS nf FROM occ WHERE ref IS NOT NULL AND ref<>'' GROUP BY ref ORDER BY nf DESC LIMIT 40")
	if err != nil {
		return "", err
	}
	if len(refs) > 0 {
		out += "<h2>By ref</h2>\n<ul class='srclist'>\n"
		for _, rf := range refs {
			out += "<li><a href='?page=omni&ref=" + esc(phpURLEncode(phpString(rf["ref"]))) + "'>" + esc(rf["ref"]) +
				"</a> <span style='color:#888'>" + esc(rf["nf"]) + " files</span></li>\n"
		}
		out += "</ul>\n"
	}
	return out, nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// SemanticSearch — invocators/tags/dev/SemanticSearch.php — multi-axis search over the doc corpus.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// Hit is one search result — the PHP's associative array, typed.
type Hit struct {
	Repo, Path, Section, Text string
	Score                     float64
	Axis                      string

	// Vector is the row's stored embedding. Rank reads it; the PHP reads $row['vector'] and
	// treats a non-array as the empty vector (SemanticSearch.php:310), which a nil slice is.
	Vector []float64

	// merge()-only bookkeeping (SemanticSearch.php:224-259).
	semantic, keyword         float64
	fromSemantic, fromKeyword bool
	both                      bool
}

// SemanticSearchTag is SemanticSearch.
//
// PHP's get_document opens by nudging memory_limit up (SemanticSearch.php:42-47). That has NO
// effect on the emitted bytes — it is defense-in-depth for the embedding path — and Go has no
// memory_limit, so it is deliberately not ported. It is the only statement in this class with no
// Go counterpart.
type SemanticSearchTag struct {
	e    *Engine
	args *TagArguments
}

// Embed is the seam for SemanticSearch::embed (SemanticSearch.php:263-293): the query embedded via
// Ollama's OpenAI-compatible endpoint, L2-normalized, or ok=false on ANY failure (the page then
// degrades to the "offline" notice and never crashes). Config.Embed overrides it; nil uses
// ollamaEmbed.
type Embed func(q string) ([]float64, bool)

// ollamaEmbed is the default embedder — POST http://localhost:11434/v1/embeddings.
func ollamaEmbed(q string) ([]float64, bool) {
	payload, err := json.Marshal(map[string]any{"model": "nomic-embed-text", "input": "search_query: " + q})
	if err != nil {
		return nil, false
	}
	client := &http.Client{Timeout: 10 * time.Second} // CURLOPT_TIMEOUT, 10
	resp, err := client.Post("http://localhost:11434/v1/embeddings", "application/json", strings.NewReader(string(payload)))
	if err != nil {
		return nil, false
	}
	defer resp.Body.Close()
	var data struct {
		Data []struct {
			Embedding []float64 `json:"embedding"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return nil, false
	}
	if len(data.Data) == 0 || len(data.Data[0].Embedding) == 0 {
		return nil, false
	}
	return l2normalize(data.Data[0].Embedding), true
}

func (t *SemanticSearchTag) embed(q string) ([]float64, bool) {
	if t.e.cfg.Embed != nil {
		return t.e.cfg.Embed(q)
	}
	return ollamaEmbed(q)
}

// l2normalize is SemanticSearch::l2normalize (SemanticSearch.php:295-303).
func l2normalize(v []float64) []float64 {
	n := 0.0
	for _, x := range v {
		n += x * x
	}
	n = math.Sqrt(n)
	if n == 0.0 {
		return v
	}
	out := make([]float64, 0, len(v))
	for _, x := range v {
		out = append(out, x/n)
	}
	return out
}

// Cosine is SemanticSearch::cosine (SemanticSearch.php:323-334) — dot(a,b)/(|a||b|), over the
// SHORTER of the two vectors, normalizing defensively even when both are already L2-normed.
// Exported because the PHP exports it and drives it from a CLI self-test.
func Cosine(a, b []float64) float64 {
	n := len(a)
	if len(b) < n {
		n = len(b)
	}
	dot := 0.0
	for i := 0; i < n; i++ {
		dot += a[i] * b[i]
	}
	na, nb := 0.0, 0.0
	for _, x := range a {
		na += x * x
	}
	for _, y := range b {
		nb += y * y
	}
	na, nb = math.Sqrt(na), math.Sqrt(nb)
	if na == 0.0 || nb == 0.0 {
		return 0.0
	}
	return dot / (na * nb)
}

// KeywordScore is SemanticSearch::keywordScore (SemanticSearch.php:209-219) — PURE: term frequency
// (dominant) plus earliness of the first match, both from a case-folded body.
//
// strtolower() is BYTE-wise ASCII-only in PHP (locale-independent since PHP 8.2), so
// strings.ToLower — which lowercases Unicode — would score differently on non-ASCII text.
// asciiLower reproduces PHP's fold exactly.
func KeywordScore(body, q string) float64 {
	bl := asciiLower(body)
	ql := asciiLower(q)
	if ql == "" {
		return 0.0
	}
	count := strings.Count(bl, ql) // substr_count
	if count == 0 {
		return 0.0
	}
	pos := strings.Index(bl, ql) // strpos
	length := len(bl)            // strlen — BYTES
	earliness := 1.0
	if length > 0 {
		earliness = 1.0 - (float64(pos) / float64(length))
	}
	return float64(count) + earliness
}

// asciiLower is PHP 8's strtolower: A-Z only, every other byte untouched.
func asciiLower(s string) string {
	b := []byte(s)
	for i := range b {
		if b[i] >= 'A' && b[i] <= 'Z' {
			b[i] += 'a' - 'A'
		}
	}
	return string(b)
}

// Rank is SemanticSearch::rank (SemanticSearch.php:307-320) — the top-k rows by cosine DESC.
//
// PHP's usort has been STABLE since PHP 8.0, and the comparator returns 0 for equal scores, so
// equal-scoring rows keep their input order. sort.SliceStable is the match; sort.Slice is not.
func Rank(queryVec []float64, rows []Hit, k int) []Hit {
	scored := make([]Hit, len(rows))
	copy(scored, rows)
	for i := range scored {
		scored[i].Score = Cosine(queryVec, scored[i].Vector)
	}
	sort.SliceStable(scored, func(i, j int) bool { return scored[i].Score > scored[j].Score })
	if k >= 0 && len(scored) > k {
		scored = scored[:k]
	}
	return scored
}

// Merge is SemanticSearch::merge (SemanticSearch.php:224-259) — PURE: dedupe by (repo,path),
// COMBINE scores, and order so a doc found by BOTH axes always outranks one found by only one.
//
// Two things the PHP's shape forces:
//   - $acc is a PHP array keyed by "repo\0path", and PHP arrays preserve INSERTION order. A Go map
//     does not, so `order` tracks it — otherwise ties (which the comparator returns 0 for, and a
//     stable sort therefore leaves alone) would come out in a random order.
//   - section/text are filled from the FIRST hit that carries them (the PHP only assigns while the
//     accumulated value is still empty), so a later hit cannot overwrite them.
func Merge(semanticHits, keywordHits []Hit, k int) []Hit {
	acc := map[string]*Hit{}
	var order []string
	ingest := func(h Hit, axis string) {
		key := h.Repo + "\x00" + h.Path
		e, ok := acc[key]
		if !ok {
			e = &Hit{Repo: h.Repo, Path: h.Path}
			acc[key] = e
			order = append(order, key)
		}
		if h.Section != "" && e.Section == "" {
			e.Section = h.Section
		}
		if h.Text != "" && e.Text == "" {
			e.Text = h.Text
		}
		switch axis {
		case "semantic":
			if h.Score > e.semantic {
				e.semantic = h.Score
			}
			e.fromSemantic = true
		case "keyword":
			if h.Score > e.keyword {
				e.keyword = h.Score
			}
			e.fromKeyword = true
		}
	}
	for _, h := range semanticHits {
		ingest(h, "semantic")
	}
	for _, h := range keywordHits {
		ingest(h, "keyword")
	}

	merged := make([]Hit, 0, len(order))
	for _, key := range order {
		e := acc[key]
		e.both = e.fromSemantic && e.fromKeyword
		switch {
		case e.both:
			e.Axis = "both"
		case e.fromSemantic:
			e.Axis = "meaning"
		default:
			e.Axis = "keyword"
		}
		e.Score = e.semantic + e.keyword
		merged = append(merged, *e)
	}
	sort.SliceStable(merged, func(i, j int) bool {
		if merged[i].both != merged[j].both {
			return merged[i].both // $a['both'] ? -1 : 1
		}
		return merged[i].Score > merged[j].Score
	})
	if k >= 0 && len(merged) > k {
		merged = merged[:k]
	}
	return merged
}

// GetDocument is SemanticSearch::get_document() (SemanticSearch.php:40-104).
func (t *SemanticSearchTag) GetDocument() (out string) {
	defer catchThrowable(&out, "SemanticSearch")
	q := t.e.getStr("q")
	axis := "meaning"
	if v, ok := t.e.getIsset("axis"); ok {
		axis = v
	}
	if !inStrings(axis, []string{"meaning", "keyword", "both"}) {
		axis = "meaning"
	}
	repo := t.e.getStr("repo")
	kind := t.e.getStr("kind")

	if t.e.cfg.SQLite == "" {
		return t.form(nil, q, axis, repo, kind) + "<p>SemanticSearch: no DB.</p>"
	}
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return "<div class='cy-form-error'>SemanticSearch error: " + esc(err.Error()) + "</div>"
	}
	defer db.Close()

	out = t.form(t.repos(db), q, axis, repo, kind)
	out += t.stats(db)
	if q == "" {
		return out
	}

	var semantic, keyword []Hit
	var notes []string

	if axis == "meaning" || axis == "both" {
		qv, ok := t.embed(q)
		if !ok {
			notes = append(notes, "embedding service offline (start Ollama + <code>ollama pull nomic-embed-text</code>)")
		} else {
			semantic, err = t.semanticHits(db, qv, repo)
			if err != nil {
				return "<div class='cy-form-error'>SemanticSearch error: " + esc(err.Error()) + "</div>"
			}
		}
	}
	if axis == "keyword" || axis == "both" {
		keyword, err = t.keywordHits(db, q, repo, kind)
		if err != nil {
			return "<div class='cy-form-error'>SemanticSearch error: " + esc(err.Error()) + "</div>"
		}
	}

	var hits []Hit
	switch axis {
	case "meaning":
		hits = semantic
	case "keyword":
		hits = keyword
	default:
		hits = Merge(semantic, keyword, 12)
	}

	// NB the note is NOT esc()'d in the PHP — it is a literal built above, containing <code> markup
	// on purpose (SemanticSearch.php:84).
	for _, n := range notes {
		out += "<p class='cy-form-error'>" + n + "</p>\n"
	}
	if len(hits) == 0 {
		return out + "<p>No matches &mdash; try another axis or a broader query.</p>\n"
	}
	out += "<ol class='srclist'>\n"
	for _, h := range hits {
		snippet := phpSubstr(h.Text, 0, 240)
		ax := h.Axis
		if ax == "" {
			ax = axis
		}
		out += "<li><span class='cy-axis'>[" + esc(ax) + "]</span> " +
			"<code>" + esc(fmt.Sprintf("%.3f", h.Score)) + "</code> " +
			"<a href='?page=repodocs&repo=" + esc(phpURLEncode(h.Repo)) +
			"&doc=" + esc(phpURLEncode(h.Path)) + "'>" +
			esc(h.Repo) + " / " + esc(h.Path) + "</a> " +
			"<span style='color:#888'>" + esc(h.Section) + "</span>" +
			"<br><span>" + esc(snippet) + "</span></li>\n"
	}
	return out + "</ol>\n"
}

// repos is SemanticSearch::repos (SemanticSearch.php:106-111) — degrades to empty on any error.
func (t *SemanticSearchTag) repos(db *sql.DB) []string {
	col, err := queryColumn(db, "SELECT DISTINCT repo FROM repo_docs ORDER BY repo")
	if err != nil {
		return nil
	}
	out := make([]string, 0, len(col))
	for _, v := range col {
		out = append(out, phpString(v))
	}
	return out
}

// form is SemanticSearch::form (SemanticSearch.php:113-137).
func (t *SemanticSearchTag) form(repos []string, q, axis, repo, kind string) string {
	out := "<form method='get' action=''>\n"
	out += "<input type='hidden' name='page' value='search'>\n"
	out += "<input type='text' name='q' value='" + esc(q) + "' size='40' placeholder='search the docs...'>\n"
	out += "<select name='axis'>\n"
	for _, v := range []string{"meaning", "keyword", "both"} {
		sel := ""
		if axis == v {
			sel = " selected"
		}
		out += "<option value='" + esc(v) + "'" + sel + ">" + esc(v) + "</option>\n"
	}
	out += "</select>\n"
	out += "<select name='repo'>\n<option value=''>(all repos)</option>\n"
	for _, r := range repos {
		sel := ""
		if repo == r {
			sel = " selected"
		}
		out += "<option value='" + esc(r) + "'" + sel + ">" + esc(r) + "</option>\n"
	}
	out += "</select>\n"
	out += "<select name='kind'>\n"
	for _, kv := range [][2]string{{"", "(any type)"}, {"md", "md"}, {"text", "text"}} {
		sel := ""
		if kind == kv[0] {
			sel = " selected"
		}
		out += "<option value='" + esc(kv[0]) + "'" + sel + ">" + esc(kv[1]) + "</option>\n"
	}
	out += "</select>\n"
	out += "<button type='submit'>Search</button>\n</form>\n"
	return out
}

// stats is SemanticSearch::stats (SemanticSearch.php:139-149) — the vector-store coverage line.
// A missing `embeddings` table returns "" (its own catch); an empty one says so.
func (t *SemanticSearchTag) stats(db *sql.DB) string {
	rows, err := queryRows(db, "SELECT model, COUNT(*) AS chunks, COUNT(DISTINCT repo||'/'||path) AS docs FROM embeddings GROUP BY model")
	if err != nil {
		return ""
	}
	if len(rows) == 0 {
		return "<p style='color:#888'>Vector store empty &mdash; no embeddings ingested yet.</p>\n"
	}
	var parts []string
	for _, r := range rows {
		parts = append(parts, esc(r["model"])+": "+esc(r["chunks"])+" chunks / "+esc(r["docs"])+" docs")
	}
	return "<p style='color:#888'>Vector store &mdash; " + strings.Join(parts, "; ") + "</p>\n"
}

// semanticHits is SemanticSearch::semanticHits (SemanticSearch.php:155-179).
//
// It STREAMS the stored vectors and keeps a bounded top-12 — O(k) memory, never materializing the
// full set (that bound is the real fix behind the memory_limit nudge). The insertion is a linear
// scan from the back, and a row is skipped early only when the buffer is full AND its score is
// <= the current worst; both conditions are reproduced, because they decide which of several
// equal-scoring rows survives.
func (t *SemanticSearchTag) semanticHits(db *sql.DB, qv []float64, repo string) ([]Hit, error) {
	var rows *sql.Rows
	var err error
	if repo != "" {
		rows, err = db.Query("SELECT repo, path, section, text, vector FROM embeddings WHERE repo=?", repo)
	} else {
		rows, err = db.Query("SELECT repo, path, section, text, vector FROM embeddings")
	}
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	const k = 12
	var top []Hit
	for rows.Next() {
		var r, p, sec, txt, vec any
		if err := rows.Scan(&r, &p, &sec, &txt, &vec); err != nil {
			return nil, err
		}
		var v []float64
		// json_decode((string)$r['vector'], true); !is_array($vec) -> continue
		if err := json.Unmarshal([]byte(phpString(vec)), &v); err != nil {
			continue
		}
		score := Cosine(qv, v)
		n := len(top)
		if n >= k && score <= top[n-1].Score {
			continue
		}
		hit := Hit{Repo: phpString(r), Path: phpString(p), Section: phpString(sec),
			Text: phpString(txt), Score: score, Axis: "meaning"}
		i := n
		for i > 0 && top[i-1].Score < score {
			i--
		}
		top = append(top, Hit{})
		copy(top[i+1:], top[i:])
		top[i] = hit
		if len(top) > k {
			top = top[:k] // array_pop
		}
	}
	return top, rows.Err()
}

// keywordHits is SemanticSearch::keywordHits (SemanticSearch.php:183-205) — a LIKE full-text scan
// over repo_docs, scored by KeywordScore and ordered by it DESC (a stable usort).
func (t *SemanticSearchTag) keywordHits(db *sql.DB, q, repo, kind string) ([]Hit, error) {
	if q == "" {
		return nil, nil
	}
	sqlStr := "SELECT repo, path, kind, body FROM repo_docs WHERE body LIKE :like"
	args := []any{sql.Named("like", "%"+q+"%")}
	if repo != "" {
		sqlStr += " AND repo=:repo"
		args = append(args, sql.Named("repo", repo))
	}
	if kind != "" {
		sqlStr += " AND kind=:kind"
		args = append(args, sql.Named("kind", kind))
	}
	sqlStr += " ORDER BY repo, path LIMIT 40"
	raw, err := queryRows(db, sqlStr, args...)
	if err != nil {
		return nil, err
	}
	hits := make([]Hit, 0, len(raw))
	for _, r := range raw {
		body := phpString(r["body"])
		hits = append(hits, Hit{
			Repo: phpString(r["repo"]), Path: phpString(r["path"]), Section: phpString(r["kind"]),
			Text: phpSubstr(body, 0, 240), Score: KeywordScore(body, q), Axis: "keyword",
		})
	}
	sort.SliceStable(hits, func(i, j int) bool { return hits[i].Score > hits[j].Score })
	return hits, nil
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// TicketList — invocators/tags/dev/TicketList.php — the project ticket table.
//
// The biggest tag, and the one whose header (TicketList.php:7-107) is worth reading before this
// code. Three of its rules drive almost all of the logic below:
//
//   - PROGRESS COUNTS DOWN. ticket_events.steps_remaining is steps LEFT, so a DONE ticket reports
//     0. The column shows FORWARD progress D = Y - R, clamped to 0..Y, so a finished ticket reads
//     "Y of Y" and never a backwards-looking "0 of Y".
//   - FLOODS COLLAPSE. Machine-filed tickets arrive in near-identical floods; three or more rows
//     sharing a SIGNATURE fold into one group header at the position of the first member. Two
//     guards keep that from hiding real work: GROUP_MIN (3) and MIN_SIG_WORDS (2) — a one-word
//     stem like "Build" is a category, not a description, and is never grouped.
//   - THE EDGES ARE A DAG, NOT A TREE. Shared subtrees would re-render exponentially and a cycle
//     would never terminate, so treeHtml carries a `seen` set across the WHOLE walk of one ticket
//     and marks a repeat "shown above". MAX_TREE_DEPTH is a second, independent stop.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

const (
	ticketGroupMin     = 3 // TicketList::GROUP_MIN
	ticketMinSigWords  = 2 // TicketList::MIN_SIG_WORDS
	ticketMaxTreeDepth = 8 // TicketList::MAX_TREE_DEPTH
)

// TicketListTag is TicketList.
type TicketListTag struct {
	e    *Engine
	args *TagArguments
}

type ticketEdge struct {
	other int64 // child (in kids) or parent (in parents)
	kind  string
}

type ticketMeta struct{ status, title string }

type ticketView struct {
	r       map[string]any
	id      int64
	stopped bool
	st      string
	key     string
	sig     string
}

// sigStem is TicketList::sigStem (TicketList.php:154-159) — the part before the FIRST ':' (or the
// whole title), whitespace-collapsed. `$i > 0` means a title STARTING with ':' keeps its whole self.
func sigStem(title string) string {
	s := phpTrim(title)
	if i := strings.IndexByte(s, ':'); i > 0 {
		s = s[:i]
	}
	return phpTrim(collapseWS(s))
}

// sigKey is TicketList::sigKey (TicketList.php:165-167) — the stem, lowercased, digit-runs folded.
func sigKey(title string) string { return foldDigitRuns(asciiLower(sigStem(title)), "#") }

// sigLabel is TicketList::sigLabel (TicketList.php:172-174) — the stem in its ORIGINAL case (not
// lowercased, unlike sigKey), with the varying digit-runs shown as '…'.
func sigLabel(title string) string { return foldDigitRuns(sigStem(title), "…") }

// groupable is TicketList::groupable (TicketList.php:177-179).
func groupable(sig string) bool { return len(splitWS(sig)) >= ticketMinSigWords }

// band is TicketList::band (TicketList.php:183-187) — mirrors the ORDER BY CASE in the SELECT.
func band(st string) int {
	switch st {
	case "ACTIVE":
		return 0
	case "OPEN", "REQUESTED":
		return 1
	}
	return 2
}

// stamp is TicketList::stamp (TicketList.php:190-193).
func stamp(ts any) string {
	t := toInt(ts)
	if t > 0 {
		return gmdate(t)
	}
	return "—"
}

// nodeHtml is TicketList::nodeHtml (TicketList.php:198-206) — '#id title [STATUS]'. An edge may
// name a ticket that no longer resolves; say so plainly rather than render a bare number.
func nodeHtml(id int64, meta map[int64]ticketMeta) string {
	out := "<span class='tid'>#" + esc(id) + "</span> "
	m, ok := meta[id]
	if !ok {
		return out + "<span class='tnote'>(no such ticket row)</span>"
	}
	return out + esc(m.title) + " <span class='tst'>" + esc(m.status) + "</span>"
}

// treeHtml is TicketList::treeHtml (TicketList.php:213-233). `seen` is the PHP's by-reference
// $seen, carried across the whole walk — a Go map is already a reference, so passing it is the
// same semantics.
func treeHtml(id int64, depth int, seen map[int64]bool, kids map[int64][]ticketEdge, meta map[int64]ticketMeta) string {
	if _, ok := kids[id]; !ok {
		return ""
	}
	if depth >= ticketMaxTreeDepth {
		return "<ul class='tree'><li><span class='tnote'>… depth cap (" +
			esc(ticketMaxTreeDepth) + ") reached; open this ticket's own row to go deeper</span></li></ul>"
	}
	out := "<ul class='tree'>"
	for _, e := range kids[id] {
		cid := e.other
		out += "<li><span class='ek ek-" + esc(e.kind) + "'>" + esc(e.kind) + "</span> " + nodeHtml(cid, meta)
		if seen[cid] {
			out += " <span class='tnote'>↑ shown above</span>"
		} else {
			seen[cid] = true
			out += treeHtml(cid, depth+1, seen, kids, meta)
		}
		out += "</li>"
	}
	return out + "</ul>"
}

// expansionHtml is TicketList::expansionHtml (TicketList.php:237-286) — PROVENANCE, TREE, JOURNAL.
func expansionHtml(id int64, kids, parents map[int64][]ticketEdge, journal map[int64][]map[string]any, meta map[int64]ticketMeta) string {
	out := "<div class='exp'>"

	// PROVENANCE — the incoming edges.
	out += "<div class='exph'>PROVENANCE</div>"
	if ps, ok := parents[id]; ok {
		out += "<ul class='tree'>"
		for _, e := range ps {
			out += "<li><span class='ek ek-" + esc(e.kind) + "'>" + esc(e.kind) + "</span> " +
				nodeHtml(e.other, meta) + " <span class='tnote'>→ this ticket</span></li>"
		}
		out += "</ul>"
	} else {
		out += "<p class='tnote'>no incoming edges — this ticket is a root.</p>"
	}

	// TREE — the outgoing edges below it.
	out += "<div class='exph'>TREE</div>"
	if _, ok := kids[id]; ok {
		seen := map[int64]bool{id: true}
		out += treeHtml(id, 0, seen, kids, meta)
	} else {
		out += "<p class='tnote'>no outgoing edges — this ticket spawned nothing.</p>"
	}

	// JOURNAL — every appended event, oldest first (the ticket.journal order).
	out += "<div class='exph'>JOURNAL</div>"
	if js, ok := journal[id]; ok {
		out += "<table class='jr'><thead><tr><th>WHEN</th><th>AGENT</th><th>EVENT</th>" +
			"<th>STATUS</th><th class='num'>STEPS LEFT</th><th>NOTE</th></tr></thead><tbody>"
		for _, j := range js {
			agent := phpString(j["agent_id"])
			if j["agent_id"] == nil || agent == "" {
				agent = "(mechanical)"
			}
			steps := phpNumberOrDash(j["steps_remaining"])
			note := phpString(j["note"])
			if j["note"] == nil || note == "" {
				note = "—"
			}
			status := phpString(j["status"])
			if j["status"] == nil || status == "" {
				status = "—"
			}
			out += "<tr><td class='jts'>" + esc(stamp(j["ts"])) + "</td>" +
				"<td class='jag'>" + esc(agent) + "</td>" +
				"<td class='jev'>" + esc(j["event"]) + "</td>" +
				"<td>" + esc(status) + "</td>" +
				"<td class='num'>" + esc(steps) + "</td>" +
				"<td class='jnote'>" + esc(note) + "</td></tr>"
		}
		out += "</tbody></table>"
	} else {
		out += "<p class='tnote'>no journal entries — nothing has been appended to this ticket.</p>"
	}

	return out + "</div>"
}

// GetDocument is TicketList::get_document() (TicketList.php:288-588).
func (t *TicketListTag) GetDocument() (out string) {
	defer catchThrowable(&out, "TicketList")
	if t.e.cfg.SQLite == "" {
		return "<p style='color:#b00020'>TicketList: CONGRUENCY_SQLITE is not defined.</p>"
	}
	db, err := openDB(t.e.cfg, t.e.cfg.SQLite)
	if err != nil {
		return "<p style='color:#b00020'>TicketList: could not open the database (" + esc(err.Error()) + ").</p>"
	}
	defer db.Close()
	// PRAGMA query_only = TRUE (TicketList.php:136) — redundant on a read-only handle, issued so
	// the Go states the same guarantee at the same point.
	if _, err := db.Exec("PRAGMA query_only = TRUE"); err != nil {
		return "<p style='color:#b00020'>TicketList: could not open the database (" + esc(err.Error()) + ").</p>"
	}

	// The base ticket rows — ACTIVE (band 0) first, then OPEN/REQUESTED (1), then the rest (2),
	// newest id first within each band. The `tickets` table pre-dates 0029, so it is always
	// expected; if even it is unreadable that is fatal to this view.
	rows, err := queryRows(db, "SELECT id, kind, status, title FROM tickets "+
		"ORDER BY CASE WHEN upper(status)='ACTIVE' THEN 0 "+
		"WHEN upper(status) IN ('OPEN','REQUESTED') THEN 1 ELSE 2 END, id DESC")
	if err != nil {
		return "<p style='color:#b00020'>TicketList: could not read tickets (" + esc(err.Error()) + ").</p>"
	}
	if len(rows) == 0 {
		return "<p style='color:#555'>TicketList: no tickets yet.</p>"
	}

	// ── the authorization overlays (each degrades to empty if its table is absent) ──

	// CREW: distinct roles per ticket, in assignment order, deduped so the first wins.
	crew := map[int64][]string{}
	for _, a := range safeRows(db, "SELECT ticket_id, role FROM ticket_agents ORDER BY ticket_id, ts, role") {
		tid := toInt(a["ticket_id"])
		role := phpString(a["role"])
		if !inStrings(role, crew[tid]) {
			crew[tid] = append(crew[tid], role)
		}
	}
	// WORKS: size of the UID'd manifest per ticket.
	works := map[int64]int64{}
	for _, w := range safeRows(db, "SELECT ticket_id, COUNT(*) AS n FROM ticket_works GROUP BY ticket_id") {
		works[toInt(w["ticket_id"])] = toInt(w["n"])
	}
	// LESSONS: harvested 'lesson' events per ticket.
	lessons := map[int64]int64{}
	for _, l := range safeRows(db, "SELECT ticket_id, COUNT(*) AS n FROM ticket_events WHERE event='lesson' GROUP BY ticket_id") {
		lessons[toInt(l["ticket_id"])] = toInt(l["n"])
	}
	// PROGRESS (remaining): the LATEST reported steps_remaining per ticket. Rows arrive oldest
	// first, so the last write per ticket wins — which is why this is an overwrite, not a first-set.
	stepsRemaining := map[int64]int64{}
	for _, s := range safeRows(db, "SELECT ticket_id, steps_remaining FROM ticket_events "+
		"WHERE steps_remaining IS NOT NULL ORDER BY ticket_id, ts, id") {
		stepsRemaining[toInt(s["ticket_id"])] = toInt(s["steps_remaining"])
	}
	// PROGRESS Y: the enumerable lifecycle length per kind (version 1).
	stepsY := map[string]int64{}
	for _, y := range safeRows(db, "SELECT kind, COUNT(*) AS n FROM ticket_lifecycles WHERE version=1 GROUP BY kind") {
		stepsY[phpString(y["kind"])] = toInt(y["n"])
	}

	// ── the drill-down overlays: one bulk SELECT each, bucketed here — never a query per row ──
	kids := map[int64][]ticketEdge{}
	parents := map[int64][]ticketEdge{}
	for _, e := range safeRows(db, "SELECT parent_id, child_id, kind FROM ticket_edges ORDER BY parent_id, kind, child_id") {
		p, c := toInt(e["parent_id"]), toInt(e["child_id"])
		k := phpString(e["kind"])
		kids[p] = append(kids[p], ticketEdge{other: c, kind: k})
		parents[c] = append(parents[c], ticketEdge{other: p, kind: k})
	}
	journal := map[int64][]map[string]any{}
	for _, j := range safeRows(db, "SELECT ticket_id, ts, agent_id, event, status, note, steps_remaining "+
		"FROM ticket_events ORDER BY ticket_id, ts, id") {
		tid := toInt(j["ticket_id"])
		journal[tid] = append(journal[tid], j)
	}

	// STOPPED: mirror the ticket.stops route. A ticket is halted when a 'stops' edge is aimed at IT
	// or any ancestor (walking 'spawned' edges upward), UNLESS the stop ticket has itself been
	// released by a 'starts' edge aimed back at it.
	stopTargets := map[int64]bool{}
	for _, e := range safeRows(db, "SELECT DISTINCT st.child_id FROM ticket_edges st WHERE st.kind='stops' "+
		"AND NOT EXISTS (SELECT 1 FROM ticket_edges rel "+
		"WHERE rel.kind='starts' AND rel.child_id = st.parent_id)") {
		stopTargets[toInt(e["child_id"])] = true
	}
	spawnParent := map[int64][]int64{}
	for _, e := range safeRows(db, "SELECT parent_id, child_id FROM ticket_edges WHERE kind='spawned'") {
		c := toInt(e["child_id"])
		spawnParent[c] = append(spawnParent[c], toInt(e["parent_id"]))
	}

	var b strings.Builder
	b.WriteString("<style>")
	b.WriteString(".tkl{width:100%;border-collapse:collapse;font-size:.82rem}")
	b.WriteString(".tkl th{text-align:left;border-bottom:2px solid #d8d2c4;padding:.35rem .5rem;color:#555;font-weight:600;white-space:nowrap}")
	b.WriteString(".tkl td{border-bottom:1px solid #eee4d0;padding:.35rem .5rem;vertical-align:top}")
	b.WriteString(".tkl .id{font:600 .78rem/1 monospace;color:#555;white-space:nowrap}")
	b.WriteString(".tkl .kind{font:.72rem/1 monospace;color:#8a5a1a;white-space:nowrap}")
	b.WriteString(".tkl .st{font:600 .62rem/1.6 sans-serif;text-transform:uppercase;color:#fff;padding:.05rem .4rem;border-radius:3px}")
	b.WriteString(".tkl .crew{font:.72rem/1.3 monospace;color:#3a5a3a}")
	b.WriteString(".tkl .num{text-align:right;font-variant-numeric:tabular-nums;color:#555;white-space:nowrap}")
	b.WriteString(".tkl .stopped{font:700 .6rem/1.6 sans-serif;text-transform:uppercase;color:#fff;background:#b00020;padding:.05rem .4rem;border-radius:3px;margin-left:.4rem}")
	b.WriteString(".tkl tr.muted td{color:#aaa;background:#faf8f2}")
	b.WriteString(".tkl tr.muted .kind,.tkl tr.muted .crew,.tkl tr.muted .num{color:#aaa}")
	b.WriteString(".tkl summary{cursor:pointer;list-style:none}")
	b.WriteString(".tkl summary::-webkit-details-marker{display:none}")
	b.WriteString(".tkl summary::before{content:'▸ ';color:#8a5a1a;font-size:.7rem}")
	b.WriteString(".tkl details[open]>summary::before{content:'▾ '}")
	b.WriteString(".tkl summary:hover{background:#fdf8ec}")
	b.WriteString(".exp{margin:.5rem 0 .3rem;padding:.5rem .6rem;background:#fbf9f3;border-left:3px solid #d8d2c4}")
	b.WriteString(".exph{font:700 .6rem/1.8 sans-serif;letter-spacing:.08em;color:#8a5a1a;text-transform:uppercase}")
	b.WriteString(".tree{margin:.1rem 0 .4rem;padding-left:1rem;list-style:none}")
	b.WriteString(".tree li{padding:.1rem 0;border-left:1px dotted #d8d2c4;padding-left:.5rem}")
	b.WriteString(".tid{font:600 .74rem/1 monospace;color:#555}")
	b.WriteString(".tst{font:.62rem/1 sans-serif;color:#888;text-transform:uppercase}")
	b.WriteString(".tnote{font:italic .7rem/1.4 sans-serif;color:#999}")
	b.WriteString(".ek{font:600 .58rem/1.6 sans-serif;text-transform:uppercase;color:#fff;background:#888;padding:.02rem .3rem;border-radius:3px}")
	b.WriteString(".ek-spawned{background:#3a6a8a}.ek-supersedes{background:#8a5a1a}.ek-stops{background:#b00020}.ek-starts{background:#1a7a3a}")
	b.WriteString(".jr{width:100%;border-collapse:collapse;font-size:.7rem;margin:.1rem 0 .2rem}")
	b.WriteString(".jr th{text-align:left;border-bottom:1px solid #d8d2c4;padding:.15rem .35rem;color:#777;font-weight:600;white-space:nowrap}")
	b.WriteString(".jr td{border-bottom:1px solid #f0ead8;padding:.15rem .35rem;vertical-align:top}")
	b.WriteString(".jr .jts,.jr .jag,.jr .jev{font:.68rem/1.3 monospace;color:#555;white-space:nowrap}")
	b.WriteString(".jr .jnote{color:#444}")
	b.WriteString(".jr .num{text-align:right;font-variant-numeric:tabular-nums;color:#555}")
	b.WriteString(".tkl tr.grp>td{background:#f6f2e6;border-bottom:1px solid #d8d2c4}")
	b.WriteString(".gsig{font:600 .8rem/1.4 sans-serif;color:#3a3a3a}")
	b.WriteString(".gcount{font:700 .62rem/1.6 sans-serif;text-transform:uppercase;color:#fff;background:#8a5a1a;padding:.05rem .4rem;border-radius:3px;margin-left:.4rem}")
	b.WriteString(".gmeta{font:.7rem/1.4 sans-serif;color:#777;margin-left:.4rem}")
	b.WriteString(".tkl table.sub{margin:.4rem 0 .2rem;background:#fff}")
	b.WriteString("</style>\n")

	total := len(rows)
	active, openish, doneish, stoppedCount := 0, 0, 0, 0

	view := make([]ticketView, 0, len(rows))
	meta := map[int64]ticketMeta{}
	sigCount := map[string]int{}
	for _, r := range rows {
		id := toInt(r["id"])

		// STOPPED: this id or any spawned-ancestor is an unreleased stop target. array_pop makes
		// the PHP's $stack LIFO; the visited set makes the walk terminate on a cyclic edge.
		stopped := false
		seen := map[int64]bool{}
		stack := []int64{id}
		for len(stack) > 0 {
			cur := stack[len(stack)-1]
			stack = stack[:len(stack)-1]
			if seen[cur] {
				continue
			}
			seen[cur] = true
			if stopTargets[cur] {
				stopped = true
				break
			}
			stack = append(stack, spawnParent[cur]...)
		}

		st := strings.ToUpper(phpString(r["status"]))
		switch {
		case st == "ACTIVE":
			active++
		case st == "OPEN" || st == "REQUESTED":
			openish++
		default:
			doneish++
		}
		if stopped {
			stoppedCount++
		}

		meta[id] = ticketMeta{status: phpString(r["status"]), title: phpString(r["title"])}

		// The grouping key is scoped to the status band, so a flood of CLOSED rows can never
		// swallow an ACTIVE ticket that shares its wording.
		sig := sigKey(phpString(r["title"]))
		key := strconv.Itoa(band(st)) + "\x00" + sig
		if groupable(sig) {
			sigCount[key]++
		}
		view = append(view, ticketView{r: r, id: id, stopped: stopped, st: st, key: key, sig: sig})
	}

	// Fold each flood into ONE slot at the position of its FIRST (newest-id) member. Walking view
	// in order preserves the established ACTIVE-first / newest-first order exactly.
	type slot struct {
		isGroup bool
		v       ticketView
		label   string
		members []ticketView
	}
	var slots []*slot
	slotOfKey := map[string]int{}
	var slotKeyOrder []string
	for _, v := range view {
		if sigCount[v.key] < ticketGroupMin {
			slots = append(slots, &slot{v: v})
			continue
		}
		i, ok := slotOfKey[v.key]
		if !ok {
			i = len(slots)
			slotOfKey[v.key] = i
			slotKeyOrder = append(slotKeyOrder, v.key)
			slots = append(slots, &slot{isGroup: true, label: sigLabel(phpString(v.r["title"]))})
		}
		slots[i].members = append(slots[i].members, v)
	}

	groupCount := len(slotOfKey)
	groupedRows := 0
	for _, k := range slotKeyOrder {
		groupedRows += len(slots[slotOfKey[k]].members)
	}

	b.WriteString("<p style='font-size:.85rem;color:#555'><strong>" + esc(total) +
		"</strong> tickets &middot; <strong>" + esc(active) +
		"</strong> active &middot; <strong>" + esc(openish) +
		"</strong> open/requested &middot; <strong>" + esc(doneish) +
		"</strong> done/other &middot; <strong>" + esc(stoppedCount) +
		"</strong> stopped</p>\n")
	b.WriteString("<p style='font-size:.75rem;color:#777'>" +
		esc(groupedRows) + " near-identical tickets are folded into " +
		esc(groupCount) + " group" + plural(groupCount == 1, "", "s") +
		" &middot; click a group to list its members, or any ticket's title to expand" +
		" its provenance tree and journal.</p>\n")

	head := "<thead><tr>" +
		"<th>#</th><th>KIND</th><th>STATUS</th><th>TITLE</th>" +
		"<th>CREW</th><th>PROGRESS</th><th class='num'>WORKS</th><th class='num'>LESSONS</th>" +
		"</tr></thead>\n"
	b.WriteString("<table class='tkl'>\n" + head + "<tbody>\n")

	for _, s := range slots {
		if !s.isGroup {
			b.WriteString(t.rowHTML(s.v, crew, stepsRemaining, stepsY, works, lessons, kids, parents, journal, meta))
			continue
		}

		// ── a group header: one row for the whole flood, members one click away ──
		members := s.members
		n := len(members)

		var ids []int64
		byStatus := map[string]int{}
		var statusOrder []string
		muteAll := true
		for _, m := range members {
			ids = append(ids, m.id)
			st := phpString(m.r["status"])
			if _, ok := byStatus[st]; !ok {
				statusOrder = append(statusOrder, st) // PHP array insertion order
			}
			byStatus[st]++
			if m.st != "DONE" && m.st != "CLOSED" {
				muteAll = false
			}
		}
		var mix []string
		for _, st := range statusOrder {
			mix = append(mix, st+"×"+strconv.Itoa(byStatus[st])) // "\u{00d7}" is '×'
		}
		minID, maxID := ids[0], ids[0]
		for _, i := range ids {
			if i < minID {
				minID = i
			}
			if i > maxID {
				maxID = i
			}
		}
		rng := "#" + strconv.FormatInt(ids[0], 10)
		if n > 1 {
			// NB an EN DASH (–), not a hyphen (TicketList.php:568).
			rng = "#" + strconv.FormatInt(minID, 10) + "–#" + strconv.FormatInt(maxID, 10)
		}

		b.WriteString("<tr class='grp" + plural(muteAll, " muted", "") + "'><td colspan='8'>")
		b.WriteString("<details><summary>")
		b.WriteString("<span class='gsig'>" + esc(s.label) + "</span>")
		b.WriteString("<span class='gcount'>" + esc(n) + " similar</span>")
		b.WriteString("<span class='gmeta'>" + esc(rng) + " &middot; " + esc(strings.Join(mix, ", ")) + "</span>")
		b.WriteString("</summary>")
		b.WriteString("<table class='tkl sub'>\n" + head + "<tbody>\n")
		for _, m := range members {
			b.WriteString(t.rowHTML(m, crew, stepsRemaining, stepsY, works, lessons, kids, parents, journal, meta))
		}
		b.WriteString("</tbody>\n</table>")
		b.WriteString("</details></td></tr>\n")
	}

	b.WriteString("</tbody>\n</table>\n")
	return b.String()
}

// rowHTML is TicketList::rowHtml (TicketList.php:593-649) — one ticket row, used for both an
// ungrouped row and a group member, so a folded ticket loses nothing but its top-level slot.
func (t *TicketListTag) rowHTML(v ticketView, crew map[int64][]string, stepsRemaining map[int64]int64,
	stepsY map[string]int64, works, lessons map[int64]int64, kids, parents map[int64][]ticketEdge,
	journal map[int64][]map[string]any, meta map[int64]ticketMeta) string {

	r, id, st := v.r, v.id, v.st

	// kind -> '(unkinded)' when NULL/empty on a legacy row.
	kindRaw := phpString(r["kind"])
	kind := kindRaw
	if kind == "" {
		kind = "(unkinded)"
	}

	// CREW -> 'role,role,...' or '—'.
	crewStr := "—"
	if cl := crew[id]; len(cl) > 0 {
		crewStr = strings.Join(cl, ",")
	}

	// PROGRESS -> 'D of Y' only when BOTH are known. steps_remaining counts DOWN, so DONE = Y - R,
	// clamped to 0..Y so an over/under-reported remaining cannot print a nonsensical 'D of Y'.
	_, hasR := stepsRemaining[id]
	totalSteps, hasY := int64(0), false
	if kindRaw != "" {
		if y, ok := stepsY[kindRaw]; ok && y > 0 {
			totalSteps, hasY = y, true
		}
	}
	progress := "—"
	if hasR && hasY {
		done := totalSteps - stepsRemaining[id]
		if done < 0 {
			done = 0
		}
		if done > totalSteps {
			done = totalSteps
		}
		progress = esc(done) + " of " + esc(totalSteps)
	}

	// DONE/CLOSED render muted.
	muted := ""
	if st == "DONE" || st == "CLOSED" {
		muted = " class='muted'"
	}
	stColour := "#888"
	switch {
	case st == "ACTIVE":
		stColour = "#1a7a3a"
	case st == "OPEN" || st == "REQUESTED":
		stColour = "#b5651d"
	}

	// Every dynamic value below is passed through esc() — the recursion guard (TicketList.php:101-107).
	out := "<tr" + muted + ">"
	out += "<td class='id'>#" + esc(id) + "</td>"
	out += "<td class='kind'>" + esc(kind) + "</td>"
	out += "<td><span class='st' style='background:" + stColour + "'>" + esc(r["status"]) + "</span>" +
		plural(v.stopped, "<span class='stopped'>Stopped</span>", "") + "</td>"
	out += "<td><details><summary>" + esc(r["title"]) + "</summary>" +
		expansionHtml(id, kids, parents, journal, meta) + "</details></td>"
	out += "<td class='crew'>" + esc(crewStr) + "</td>"
	out += "<td class='num'>" + progress + "</td>"
	out += "<td class='num'>" + esc(works[id]) + "</td>"
	out += "<td class='num'>" + esc(lessons[id]) + "</td>"
	out += "</tr>\n"
	return out
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// The page surface — Controller::control() / display(), and #226's gate.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// Render is Controller::control() (Controller.php:15-22) plus display() (Controller.php:30-39):
//
//	if (isset($_GET['page'])) $post_validated = ValidateFields::validatePageKey($_GET['page']);
//	else                      $post_validated = "catalog";
//	$document = DocumentManager::get_document($post_validated);
//	print $document->__toString();          // -> Tag_Wrapper::execute_all_tags
//
// So ?page=tags is a DOCUMENT lookup, not a route: the Documents row keyed 'tags' carries a
// template holding <<<TagList>>>, and the ENGINE — not the router — turns that into the gallery.
// That indirection is why this function is the whole page surface in six lines.
//
// PHP's PersistentObjectManager::setData('WORKING_PAGE', $document) and ::executeCommands() have no
// counterpart here (there is no POM; see divergence 3) and neither emits bytes.
func Render(cfg Config, get url.Values) (string, error) {
	page := "catalog" // the PHP's default when ?page= is absent
	if v, ok := get["page"]; ok && len(v) > 0 {
		page = v[len(v)-1]
	}
	e := NewEngineWithQuery(cfg, get)
	doc, err := e.GetDocumentByKey(page)
	if err != nil {
		return "", err
	}
	return e.RenderDocument(doc), nil
}

// RenderTag renders ONE tag standalone, exactly as the gallery does it — `new $sel(null)` with the
// ambient $_GET (TagList.php:63-72). It is the Go side of #226's per-tag equivalence gate:
//
//	go := tags.RenderTag(cfg, "TicketList", url.Values{"page":{"tags"},"tag":{"TicketList"}})
//
// ok=false means the name has no Go port (see PortedTags), which is the honest answer rather than
// an invented render. Note this returns the TAG's own bytes, not the surrounding gallery frame —
// for the full ?page=tags&tag=T page, use Render.
func RenderTag(cfg Config, name string, get url.Values) (out string, ok bool) {
	e := NewEngineWithQuery(cfg, get)
	defer func() {
		if r := recover(); r != nil {
			out, ok = "<p style='color:#b00020'>congruency-go: panic rendering <code>"+esc(name)+
				"</code>: "+esc(fmt.Sprint(r))+"</p>", true
		}
	}()
	tag, found := e.lookupTag(name, nil)
	if !found {
		return "", false
	}
	return tag.GetDocument(), true
}

// Handler serves the page surface: GET /?page=<key>[&...]. It is the seam server.go's handlePage
// (server.go:636-670) can be pointed at — that file currently answers ?page=tags with a marked
// placeholder ("a seam, not a forgery"), which this package exists to replace. Wiring it is one
// line THERE; #226 forbids this file from making that edit.
//
// The status/Content-Type mirror what the PHP router emits for a rendered page. A page key the
// DAO cannot resolve is a 404 rather than a PHP fatal (Controller::display would call
// __toString() on NULL); the PHP's own comment at Controller.php:31-35 admits that branch was
// never thought through ("under what conditions does DocumentManager not return a document?").
func Handler(cfg Config) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=UTF-8")
		body, err := Render(cfg, r.URL.Query())
		if err != nil {
			w.WriteHeader(http.StatusNotFound)
			fmt.Fprintf(w, "<!-- congruency-go tags -->\n<h1>not found</h1><p>%s</p>\n", esc(err.Error()))
			return
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, body)
	})
}

// ─────────────────────────────────────────────────────────────────────────────────────────────────
// SelfCheck — the invariants this port stands on, checkable with no PHP, no DB and no network.
//
// It exists because #226's real gate (a byte-diff against a live PHP render) CANNOT be run in this
// checkout — there is no php binary and no congruency.sqlite (see the header). What CAN be proved
// here is that every rule this port was written to obey actually holds in the code: the tag regex
// admits exactly what the PHP's admits, the parser lands on the same names/arguments, both
// recursion guards bite, and each PHP primitive matches PHP's output byte for byte.
//
// Every expectation below is a value read off the PHP source or PHP's documented semantics, named
// in the check's message. SelfCheck returns nil when they all hold.
// ─────────────────────────────────────────────────────────────────────────────────────────────────

// selfRefTag emits its own trigger forever — the BUG-06 shape (a document whose Title is
// "<<<TitleTag>>>"; dev/bugs/repro/bug06_tag_recursion.php). Unguarded, this is the infinite
// recursion. It is registered ONLY through Engine.Lookup, never in the package registry.
type selfRefTag struct{ depth *int }

func (s *selfRefTag) GetDocument() string { *s.depth++; return "<<<SelfRef>>>" }

// escapingTag models the htmlspecialchars guard: a tag whose DB-derived text CONTAINS a tag
// invocation, escaped on the way out — so the engine cannot re-parse it.
type escapingTag struct{}

func (escapingTag) GetDocument() string { return esc("<<<SelfRef>>> stored in a ticket title") }

// literalTag returns fixed text, for the substitution checks.
type literalTag struct{ s string }

func (l literalTag) GetDocument() string { return l.s }

// SelfCheck runs every invariant. It performs no I/O.
func SelfCheck() error {
	var fails []string
	check := func(name string, got, want any) {
		if fmt.Sprint(got) != fmt.Sprint(want) {
			fails = append(fails, fmt.Sprintf("%s:\n  got  %q\n  want %q", name, fmt.Sprint(got), fmt.Sprint(want)))
		}
	}

	// ── the scanner: TAG_KEY_PREFIX.FUNCTION_NAME.FUNCTION_ARGUMENTS.TAG_KEY_SUFFIX ──
	check("tagPattern source", tagPattern.String(), `<<<[a-zA-Z]+(\([A-Za-z0-9]*\))*>>>`)
	check("identifyTag: plain", identifyTag("a <<<TagList>>> b"), []string{"<<<TagList>>>"})
	check("identifyTag: with args", identifyTag("<<<FormTag(OrderForm)>>>"), []string{"<<<FormTag(OrderForm)>>>"})
	check("identifyTag: multi-arg", identifyTag("<<<Foo(a)(b)>>>"), []string{"<<<Foo(a)(b)>>>"})
	check("identifyTag: empty args", identifyTag("<<<FormTag()>>>"), []string{"<<<FormTag()>>>"})
	// FUNCTION_NAME is [a-zA-Z]+ — no digits, no underscore. Both of these are NOT tags.
	check("identifyTag: digit in name is not a tag", len(identifyTag("<<<Foo2>>>")), 0)
	check("identifyTag: underscore in name is not a tag", len(identifyTag("<<<Foo_Bar>>>")), 0)
	// FUNCTION_ARGUMENT is [A-Za-z0-9]* — a hyphen cannot appear (FormTag.php:44-51).
	check("identifyTag: hyphen in arg is not a tag", len(identifyTag("<<<FormTag(ConfigForm-6)>>>")), 0)
	// The escaped form must NOT match — this IS the htmlspecialchars guard.
	check("identifyTag: escaped tag is inert", len(identifyTag(esc("<<<TagList>>>"))), 0)

	// ── Tag_Parser ──
	check("extractTagName", extractTagName("<<<Foo(a)>>>"), "Foo(a)")
	check("getTagIdentifier: with args (lookahead alt 1)", getTagIdentifier("Foo(bar)"), "Foo")
	check("getTagIdentifier: bare (alt 2)", getTagIdentifier("TagList"), "TagList")
	check("getTagIdentifier: multi-arg", getTagIdentifier("Foo(a)(b)"), "Foo")
	check("GetTagParser: function name", GetTagParser("<<<FormTag(OrderForm)>>>").GetFunctionName(), "FormTag")

	// ── TagArguments: the reversal means Top/Pop hand back the FIRST-written argument ──
	check("ArgumentFactory: Pop is the first argument",
		mustPop(ArgumentFactory("FormTag(OrderForm)")), "OrderForm")
	check("ArgumentFactory: Top is the first argument", ArgumentFactory("Foo(a)(b)").Top(), "a")
	check("ArgumentFactory: () yields one empty argument", mustPop(ArgumentFactory("FormTag()")), "")
	check("ArgumentFactory: no parens yields no arguments", len(ArgumentFactory("TagList").GetArguments()), 0)
	// `new FormTag(null)` — the gallery's shape — must leave formId "" (FormTag.php:69-77).
	check("FormTag(nil): empty id", newFormTag(NewEngine(Config{}), nil).formID, "")
	check("CategoryBrowse(nil): empty category", newCategoryBrowseTag(NewEngine(Config{}), nil).category, "")

	// ── PHP primitives ──
	check("htmlspecialchars ENT_QUOTES", phpHTMLSpecialChars(`<a href="x">&'</a>`),
		`&lt;a href=&quot;x&quot;&gt;&amp;&#039;&lt;/a&gt;`)
	check("htmlspecialchars: single quote is &#039; not &#39;", phpHTMLSpecialChars("'"), "&#039;")
	check("urlencode: space is +, ~ is %7E", phpURLEncode("a b~c/d"), "a+b%7Ec%2Fd")
	check("urlencode: keeps -_.", phpURLEncode("a-b_c.d"), "a-b_c.d")
	check("(string)null", phpString(nil), "")
	check("(string)int", phpString(int64(42)), "42")
	check("(string)float integral", phpString(3.0), "3")
	check("(string)float precision=14", phpString(1.0/3.0), "0.33333333333333")
	check("(int)\"12abc\"", toInt("12abc"), 12)
	check("substr counts bytes", phpSubstr("abcdef", 0, 3), "abc")
	check("collapseWS", collapseWS("a  \t b"), "a b")
	check("gmdate", gmdate(0), "1970-01-01 00:00")

	// ── the lookbehind ports (TicketList::sigKey / sigLabel) ──
	check("foldDigitRuns: bare index folds", foldDigitRuns("crank1", "#"), "crank#")
	check("foldDigitRuns: multi-digit index folds", foldDigitRuns("crank10", "#"), "crank#")
	check("foldDigitRuns: #25 is a ticket ref and survives WHOLE", foldDigitRuns("#25", "#"), "#25")
	check("sigKey: crank1 and crank10 share a signature",
		sigKey("PREDICTION #25 crank1"), sigKey("PREDICTION #25 crank10"))
	check("sigKey: the shared signature", sigKey("PREDICTION #25 crank1"), "prediction #25 crank#")
	check("sigKey: #44 and #45 stay distinct families",
		sigKey("PREDICTION #44 crank1") != sigKey("PREDICTION #45 crank1"), true)
	check("sigKey: stem is the part before the first ':'",
		sigKey("Docs may be stale: a/b/c.md"), "docs may be stale")
	check("sigLabel: original case, varying run shown as …",
		sigLabel("PREDICTION #25 crank1"), "PREDICTION #25 crank…")
	// MIN_SIG_WORDS: a one-word stem is a category, never grouped (TicketList.php:62-67).
	check("groupable: one word is not groupable", groupable("build"), false)
	check("groupable: two words are groupable", groupable("docs may"), true)
	check("band", []int{band("ACTIVE"), band("OPEN"), band("REQUESTED"), band("DONE")}, []int{0, 1, 1, 2})

	// ── the engine: substitution ──
	e := NewEngine(Config{})
	e.Lookup = func(_ *Engine, name string, _ *TagArguments) (Tag, bool) {
		switch name {
		case "Leaf":
			return literalTag{"LEAF"}, true
		case "Esc":
			return escapingTag{}, true
		}
		return nil, false
	}
	check("engine: a tag is replaced by its render",
		ExecuteAllTags(e.CreateDocumentTag(&Document{Template: "[<<<Leaf>>>]"}), 0), "[LEAF]")
	// str_replace replaces EVERY occurrence (Tag_Wrapper::replace_tag).
	check("engine: str_replace replaces every occurrence",
		ExecuteAllTags(e.CreateDocumentTag(&Document{Template: "<<<Leaf>>>/<<<Leaf>>>"}), 0), "LEAF/LEAF")
	check("engine: an unknown tag is marked, never a panic",
		strings.Contains(ExecuteAllTags(e.CreateDocumentTag(&Document{Template: "<<<Nope>>>"}), 0), "no Go port"), true)

	// ── GUARD 2: the htmlspecialchars guard — an escaped stored tag does NOT recurse ──
	check("guard: escaped output stays literal",
		ExecuteAllTags(e.CreateDocumentTag(&Document{Template: "<<<Esc>>>"}), 0),
		"&lt;&lt;&lt;SelfRef&gt;&gt;&gt; stored in a ticket title")

	// ── GUARD 1: the BUG-06 depth cap — a self-referential tag terminates ──
	//
	// Unguarded this is the infinite recursion of dev/bugs/repro/bug06_tag_recursion.php: the tag
	// emits its own trigger, so the engine re-parses its output forever.
	//
	// The render COUNT pins down exactly where the cap bites, and the arithmetic is worth stating
	// because it is easy to get off by one. ExecuteAllTags starts at the DOCUMENT (depth 0), whose
	// get_document() returns the template and is not the recursive tag. So the tag first renders at
	// depth 1, and the frame at depth 64 renders (the cap is checked AFTER get_document()) and then
	// returns without scanning. The tag therefore renders at depths 1..64 => exactly MaxTagDepth
	// renders, and the text that survives is the child's un-expanded, literal trigger.
	renders := 0
	g := NewEngine(Config{})
	g.Lookup = func(_ *Engine, name string, _ *TagArguments) (Tag, bool) {
		if name == "SelfRef" {
			return &selfRefTag{depth: &renders}, true
		}
		return nil, false
	}
	got := ExecuteAllTags(g.CreateDocumentTag(&Document{Template: "<<<SelfRef>>>"}), 0)
	check("guard: BUG-06 depth cap terminates the recursion", got, "<<<SelfRef>>>")
	check("guard: the tag renders at depths 1..64 (see the arithmetic above)", renders, MaxTagDepth)

	// ── validatePageKey (ValidateFields.php:13-22): entirely 2+ ASCII letters ──
	check("validatePageKey: tags", mustKey("tags"), "tags")
	check("validatePageKey: rejects a digit", mustKey("tags2"), "")
	check("validatePageKey: rejects one letter", mustKey("a"), "")
	check("validatePageKey: rejects a path", mustKey("../x"), "")

	// ── SemanticSearch's pure math (the PHP exports these for its own self-tests) ──
	check("cosine: identical vectors", fmt.Sprintf("%.4f", Cosine([]float64{1, 0}, []float64{1, 0})), "1.0000")
	check("cosine: orthogonal", fmt.Sprintf("%.4f", Cosine([]float64{1, 0}, []float64{0, 1})), "0.0000")
	check("cosine: a zero vector scores 0", Cosine([]float64{0, 0}, []float64{1, 0}), 0.0)
	check("keywordScore: absent term scores 0", KeywordScore("hello world", "zzz"), 0.0)
	check("keywordScore: tf + earliness", fmt.Sprintf("%.2f", KeywordScore("ab ab", "ab")), "3.00")
	// merge(): a doc found by BOTH axes outranks one found by only one, whatever the scores.
	both := Merge(
		[]Hit{{Repo: "r", Path: "both.md", Score: 0.1}, {Repo: "r", Path: "solo.md", Score: 9.0}},
		[]Hit{{Repo: "r", Path: "both.md", Score: 0.1}}, 12)
	if len(both) != 2 || both[0].Path != "both.md" || both[0].Axis != "both" {
		fails = append(fails, fmt.Sprintf("merge: a both-axis hit must outrank a higher-scoring single-axis hit; got %#v", both))
	}

	// ── the registry (#281): init()-based self-registration ──
	//
	// These pin the property #281 exists to create — the registry is filled by Register from
	// init(), not by a literal — and the property #281 must NOT change: the tags #226 ported are
	// still there, still looked up the same way. If a per-tag <Tag>.go is added later and its
	// init() does not run, these are what say so.
	//
	// EVERY CHECK HERE IS ADDITIVE-SAFE, AND THAT IS A HARD REQUIREMENT, NOT A STYLE CHOICE.
	// #281 exists so that #246+ can each add a <Tag>.go and change NOTHING central. An invariant
	// that asserts the registry holds EXACTLY these 10 names, or that some specific unported name
	// is absent, would break the moment the first of those tickets lands — and "fixing" it would
	// mean editing engine.go, which is the very collision #281 removes. So: the 10 are asserted as
	// a SUBSET (each present), never as the whole set; the count is a floor, never an equality;
	// and the negatives below are names that can NEVER be legitimately registered, never merely
	// names that are unported today. Do not tighten these into equalities.
	ported := []string{"BugCatalog", "CategoryBrowse", "ForgeView", "FormTag", "MemGraph",
		"OmniExplorer", "SemanticSearch", "TagList", "TicketList", "TreeView"}
	check("registry: init() populated it (a literal no longer does)", len(PortedTags()) > 0, true)
	check("registry: at least the 10 tags #226 ported are registered", len(PortedTags()) >= len(ported), true)
	for _, n := range ported {
		check("registry: IsPorted("+n+") — #226's port survives #281", IsPorted(n), true)
		tg, ok := newTag(NewEngine(Config{}), n, nil)
		check("registry: newTag("+n+", nil) constructs", ok && tg != nil, true)
	}
	// PortedTags must stay sorted and duplicate-free however many files register into it.
	check("registry: PortedTags is sorted and deduped", sort.StringsAreSorted(PortedTags()) &&
		len(uniq(PortedTags())) == len(PortedTags()), true)
	// The negative half of the lookup. Both names are permanently unregisterable: Register panics
	// on the empty name, and FUNCTION_NAME is [a-zA-Z]+ so a name with a digit can never be
	// invoked from content — no <Tag>.go will ever claim either, so neither check can rot.
	for _, n := range []string{"", "ZzzNotARealTag0"} {
		check("registry: IsPorted("+n+") is false", IsPorted(n), false)
	}
	check("registry: newTag of an unregistered name is (nil,false), never a panic",
		fmt.Sprint(func() (Tag, bool) { return newTag(NewEngine(Config{}), "ZzzNotARealTag0", nil) }()),
		"<nil> false")

	// Register's three programmer-error panics (see Register). Each must fire BEFORE the write, so
	// none of them may leave the registry mutated — SelfCheck performs no I/O and no side effects,
	// and that includes not registering anything itself. The comparison is relative (before vs
	// after), so it too holds no matter how many tags are registered.
	before := PortedTags()
	check("Register: a duplicate name panics (the map literal made it a compile error)",
		panics(func() { Register("TagList", func(*Engine, *TagArguments) Tag { return literalTag{"x"} }) }), true)
	check("Register: an empty name panics",
		panics(func() { Register("", func(*Engine, *TagArguments) Tag { return literalTag{"x"} }) }), true)
	check("Register: a nil factory panics", panics(func() { Register("NeverRegistered", nil) }), true)
	check("Register: a rejected registration does not mutate the registry", PortedTags(), before)

	if len(fails) > 0 {
		return fmt.Errorf("SelfCheck: %d invariant(s) failed:\n%s", len(fails), strings.Join(fails, "\n"))
	}
	return nil
}

func mustPop(a *TagArguments) string { v, _ := a.Pop(); return v }
func mustKey(k string) string        { v, _ := validatePageKey(k); return v }

// uniq returns s with adjacent duplicates dropped. SelfCheck uses it on the already-sorted
// PortedTags, where adjacent-only is the same as global.
func uniq(s []string) []string {
	out := s[:0:0]
	for i, v := range s {
		if i == 0 || v != s[i-1] {
			out = append(out, v)
		}
	}
	return out
}

// panics reports whether f panicked. It is SelfCheck's way of asserting Register's guard rails
// without a testing package — #281's deliverable is engine.go alone, so there is no _test.go to
// put them in (see "THIS FILE ALONE" in the header).
func panics(f func()) (did bool) {
	defer func() {
		if recover() != nil {
			did = true
		}
	}()
	f()
	return false
}
