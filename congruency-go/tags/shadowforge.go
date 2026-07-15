// shadowforge.go — ticket #329, unit go-port:tags:tag:ShadowForge.
//
// The Go port of ONE tag: invocators/tags/dev/ShadowForge.php. It is a self-contained leaf in the
// sense #281 established — this file holds the tag's type, its GetDocument, its helpers and its
// self-registration, and it changes NOTHING in engine.go. That is the whole footprint.
//
// THE CONTRACT: byte-identical HTML. The PHP is the spec. Everything below that looks quirky is
// quirky because ShadowForge.php is, and where the two disagree the Go is wrong.
//
// ── WHAT THE TAG IS ─────────────────────────────────────────────────────────────────────────────
//
// A read-only reflection of the SHADOW FORGE INDEX — shadow_index.db, a sqlite database SEPARATE
// from CONGRUENCY_SQLITE, built by jazz-forge's forge/shadow_forge.py (RFC-0030). It reports
// per-file test/spec coverage over the actively-developed code plus the DEFICIT backlog (files
// lacking a test and/or a spec citation). Four views, selected from $_GET alone:
//
//	?shadow=<name>  -> summary + every file that shadow-doc covers      (by_shadow)
//	?file=<path>    -> summary + which shadow-docs cover that file      (by_file)
//	(neither)       -> summary + facet form + deficit backlog + exemplars
//
// It is the fourth REFLECTION tag in this package — ForgeView (forge.db), MemGraph (mem_graph.db)
// and OmniExplorer (omni_index.db) are the other three (engine.go:310-315). It is unlike them in
// one way that drives real code below: its two "database is not there" states are DISTINCT
// messages, so it cannot use the shared openReflection helper. See "DEGRADATION".
//
// ── IT TAKES NO TAG ARGUMENTS IT EVER READS ─────────────────────────────────────────────────────
//
// ShadowForge.php:35 is `__construct($arguments){ $this->arguments = $arguments; }` — it STORES
// $arguments and never reads them again (grep of the class this session: `arguments` appears on
// exactly two lines, the property declaration at :34 and that constructor). AnnotationsTag has the
// same shape for the same reason, so the field is kept here to mirror the class rather than
// dropped. Every input arrives through $_GET. `new ShadowForge(null)` — the standalone/gallery
// shape (TagList.php:67) — is therefore a no-op, which is what the ?page=tags&tag=ShadowForge gate
// always constructs.
//
// ── THE DB PATH IS RESOLVED AT RENDER TIME, FROM THE ENVIRONMENT, NOT FROM Config ────────────────
//
// ShadowForge.php:38-42:
//
//	$p = getenv('SHADOW_FORGE_DB');
//	if ($p !== false && $p !== '') { return $p; }
//	return getenv('HOME') . '/code/installed/jazz-project/config/forge/shadow_forge/shadow_index.db';
//
// Config has ForgeDB/MemGraphDB/OmniDB fields but NO ShadowDB (engine.go:310-315, read this
// session), and this ticket's deliverable is this file alone, so adding one is out of scope. That
// costs nothing here, and is arguably MORE faithful: DefaultConfig reads its env vars ONCE when the
// Config is built (its `pick` closure, engine.go:357-362, called at :369-371), whereas shadow_path()
// calls getenv() inside get_document() on EVERY render. shadowPath below does the same, at the same
// point.
//
// os.Getenv("HOME"), not os.UserHomeDir(): the PHP reads the HOME *variable*, and UserHomeDir falls
// back to other sources when HOME is unset. With HOME unset PHP's getenv returns false, and
// false . '/code/...' is '/code/...' — which os.Getenv("")+"/code/..." reproduces exactly.
//
// ── DEGRADATION: TWO DISTINCT MISSING-DB STATES, WHICH IS WHY openReflection IS NOT USED ─────────
//
// The ticket asks that a tag degrading against a missing dependency degrade IDENTICALLY in Go.
// ShadowForge.php:46-55 has TWO error strings, not one:
//
//	!is_file($path) || !is_readable($path)   -> "shadow forge not built yet at <code>P</code> &mdash; run forge/shadow_forge.py"
//	new PDO(...) / PRAGMA throws             -> "shadow forge not readable at <code>P</code> &mdash; run forge/shadow_forge.py"
//
// engine.go's shared openReflection (engine.go:2241-2255) collapses both into a single bool, so a
// tag built on it CANNOT tell the two messages apart. ForgeView/MemGraph/OmniExplorer can use it
// because each has only ONE missing-db message. This tag has two, so it opens the db itself, in
// openShadow below, keeping the PHP's two branches as two branches. Reusing the shared helper here
// would be tidier and would emit the wrong string for one of the two states.
//
// is_readable is modelled with os.Open, not os.Stat: os.Stat succeeds on a file the process cannot
// read (stat needs search permission on the directory, not read permission on the file), so a
// chmod-000 shadow_index.db would pass a Stat-only check and then fail the OPEN — emitting "not
// readable" where the PHP emits "not built yet". Opening the file read-only and closing it
// immediately is precisely the question is_readable asks, it creates nothing, and it is portable
// (syscall.Access is not — no Windows). The residual difference is that access(2) asks about the
// REAL uid and open(2) about the EFFECTIVE one; they differ only for a setuid process, which a
// `php -S` dev server started from a shell is not. That last point is reasoning, not a measurement —
// neither degradation branch could be provoked out of the live server (see "WHAT WAS AND WAS NOT
// RUN"), so this is the one corner of this file resting on an argument rather than on bytes.
//
// The read-only guarantee is doubled, exactly as the PHP doubles it: openDB opens `mode=ro`
// (engine.go:1180) and then `PRAGMA query_only=1` is issued anyway, so the Go states the same
// guarantee at the same point the PHP states it (ShadowForge.php:52). NEITHER can mutate the shadow
// index. openDB also refuses to CREATE a missing file, where PHP's `new PDO('sqlite:'.$path)` is
// read-write and would create one — but that path is unreachable here, because the is_file check
// above already returned the "not built yet" state before any open happens. So this tag inherits
// none of engine.go's divergence-2 exposure.
//
// AND THE SIDECAR TRAP IS CHECKED, NOT ASSUMED (docs/PLAYBOOK.md Theme 3 — #153's lesson is that
// `mode=ro` on a WAL database spawns -wal/-shm sidecars, i.e. "read-only" is NOT automatically
// side-effect-free). Probed in isolation this session against a COPY of the real shadow_index.db in
// an otherwise empty directory, listed and hashed before and after a `file:<p>?mode=ro` open plus
// this tag's PRAGMA and its five summary scalars: files created NONE, db content hash UNCHANGED.
// The trap does not fire here because this database is journal_mode=delete, not WAL (measured on
// both the original and the copy) — engine.go's openDB comment records the same trade-off, and the
// zero-sidecar `immutable=1` alternative is available via Config.Immutable for a caller who wants
// the guarantee regardless of journal mode.
//
// ── THE ERROR DIV: SAME SHAPE, AND THE MESSAGE TEXT CANNOT MATCH ────────────────────────────────
//
// ShadowForge.php:64-66 wraps the three view branches in `catch (\Throwable $e)` ->
// "<div class='cy-form-error'>ShadowForge error: " . esc($e->getMessage()) . "</div>". That is
// byte-for-byte engine.go's throwableHTML("ShadowForge", err) (engine.go:1711-1713), which is used
// below rather than re-spelled. catchThrowable (engine.go:1715-1719) covers the panic case.
//
// A caveat stated rather than hidden: on a shadow_index.db that opens but whose tables are missing,
// BOTH sides render an error div and the div's TEXT differs — PDO says "SQLSTATE[HY000]: General
// error: 1 no such table: sf_file" and sqlite/Go does not. db.go's header calls out this same
// limit ("That error's TEXT is the one thing that cannot match"). It is off the gate's path (the
// live shadow_index.db has all three tables — verified this session) and is named here rather than
// faked.
//
// THAT IS ALSO WHY THIS FILE DOES NOT USE scalarOrZero. engine.go's scalarOrZero (engine.go:1271-
// 1277) swallows the error and returns 0, which would render a plausible all-zeroes SUMMARY where
// the PHP renders an error div — a worse divergence than a differing message inside a div of the
// same shape. sfScalar below propagates the error and keeps `($v === false || $v === null) ? 0 : $v`
// (ShadowForge.php:69-72) for the non-error case only.
//
// ── SF-1 / SF-3: pct() IS PHP's round(), AND IT IS COMPUTED EXACTLY RATHER THAN GUESSED ──────────
//
// ShadowForge.php:74-76 is `return ($den > 0) ? round(100 * $num / $den, 1) : 0;` — and PHP's
// round() is NOT math.Round(v*10)/10. PHP pre-rounds to the precision FP actually guarantees before
// rounding to the requested places, specifically so that a value whose double representation sits a
// hair below a tie still rounds as the decimal it was meant to be. The classic divergence:
// round(2.35, 1) is 2.4 in PHP, while 2.35*10 is 23.499999999999996 in IEEE754, so a naive
// math.Round gives 23 -> 2.3.
//
// Porting php-src's _php_math_round from memory is exactly the "assert from memory" failure Theme 1
// of docs/PLAYBOOK.md warns about — worse, round()'s pre-rounding has itself been reworked across
// 8.x, so "the algorithm" is version-specific and this session cannot run a php to settle which one
// is live (a binary exists on the machine but is not invocable here — see "WHAT WAS AND WAS NOT
// RUN"). So pct is not a transliteration of round() — it SIDESTEPS it, and the sidestep is provable
// without knowing which round() implementation is on the other side:
//
//	$num and $den are COUNT(*) results, i.e. non-negative INTEGERS. So 100*num/den is a RATIONAL,
//	and round(100*num/den, 1) is by definition round_half_away_from_zero(1000*num/den) / 10 —
//	which integer arithmetic computes with ZERO floating-point error (sfPct below).
//
// That this equals what PHP's round() returns rests on two facts, both of which hold for every
// integer num/den:
//
//  1. NOT A TIE -> both agree, unconditionally. If 1000*num/den is not an exact half-integer, the
//     true value's distance from the nearest tie is at least 1/(2*den) — for any den under ~1e11
//     that is astronomically larger than the ~1e-14 relative error PHP's double arithmetic can
//     introduce, so PHP's float path lands on the same integer the exact path does.
//  2. AN EXACT TIE -> PHP's documented mode is HALF_UP, i.e. half away from zero, and the pre-
//     rounding exists precisely to recover the exact decimal before that rule is applied. `2*r >= b`
//     below is that same rule.
//
// The final arithmetic is the same expression PHP evaluates, not merely an equal value: PHP's
// round() finishes with `tmp_value / f1` where f1 = php_intpow10(1) = 10.0, and sfPct finishes with
// float64(k) / 10. IEEE754 division is correctly rounded, so both yield the identical double, and
// phpString then renders identical bytes.
//
// AND FOR THIS DATABASE A TIE IS UNREACHABLE, which is worth recording because it bounds fact 2 to
// theory here: the two live denominators are 53 and 76 (measured). 100*num/53 is a terminating
// decimal only when 53 | num (53 is prime and coprime to 10), and it is then an integer — never a
// .X5 tie. 100*num/76 = 25*num/19 is likewise terminating only when 19 | num, and is then a
// multiple of 25 — again never a .X5 tie. So every pct() the gate can reach falls in case 1.
//
// TWO RETURN TYPES, DELIBERATELY. round() returns a FLOAT and the `: 0` arm returns an INT. Both
// reach esc((string)$v), and PHP renders them through different formatters — (string)50.0 is "50"
// via precision=14 %G (phpFloatString, engine.go:530-547), (string)0 is "0" via the int path. sfPct
// returns `any` so esc picks the same branch PHP's cast picks. Collapsing it to float64 would be
// invisible on today's data and wrong the first time a table is empty.
//
// ── FACETS ARE BOUND, AND EACH NAME APPEARS TWICE ───────────────────────────────────────────────
//
// ShadowForge.php:143-150's WHERE is three NULL-safe optional-facet guards:
//
//	WHERE (COALESCE(:reason,'')='' OR d.reason=:reason)
//	  AND (COALESCE(:repo,'')='' OR d.repo=:repo)
//	  AND (COALESCE(:ext,'')='' OR f.ext=:ext)
//
// so each name occurs TWICE in one statement. sqlite maps repeated occurrences of a named parameter
// to a SINGLE index, and database/sql carries that through sql.Named — the identical shape
// BugCatalog::table already relies on in this package (engine.go:2036-2048). PDO binds through
// execute(array(...)), i.e. PARAM_STR, so every facet reaches sqlite as TEXT; a Go string through
// sql.Named binds text too, so `f.ext=:ext` is the same comparison on both sides.
//
// The COALESCE is defensive on the PHP's part rather than reachable: both call sites cast to
// (string) first (ShadowForge.php:140-142), so the bound value is never NULL and COALESCE(:x,'')
// always reduces to :x. Ported as written.
//
// ── SECURITY: ESCAPE-FIRST, AS THE PHP'S OWN HEADER MANDATES ────────────────────────────────────
//
// ShadowForge.php:25-29 states the rule this file keeps: EVERY value read from shadow_index.db
// (paths, repos, reasons, spec_refs) is htmlspecialchars()'d before it flows back through
// execute_all_tags, so a stored "<<<Tag>>>" or "<script>" in a path stays inert. That is the
// htmlspecialchars recursion guard engine.go's header describes, and esc() (engine.go:599) is
// byte-exact with htmlspecialchars($s, ENT_QUOTES). Every DB-derived byte below goes through it.
// Unlike Catalog_Controller (#253), there is no un-escaped path in this tag's chain at all.
//
// Note the ORDER in the href builders: the PHP is esc(urlencode($v)) — urlencode FIRST, then
// htmlspecialchars over its output. urlencode already removes every character esc would touch, so
// the esc is a no-op there; it is kept because removing it would be a silent change to a security
// rule, and because ForgeView's ported hrefs spell it the same way (engine.go:2327).
//
// ── WHAT WAS AND WAS NOT RUN (read this before trusting a claim above) ───────────────────────────
//
// THIS FILE WAS NOT COMPILED, and that is stated first because it bounds everything after it. The
// Go toolchain is not invocable in the session that wrote it: `go version` and `go build ./...` were
// both refused by the harness with "This command requires approval", and there was no one to
// approve. So there is NO build, NO vet, NO gofmt and NO SelfCheck() run behind this port, and none
// is claimed. THE FIRST THING TO DO WITH THIS FILE IS RUN:
//
//	cd congruency-go && go build ./... && go vet ./... && gofmt -l .
//	cd tags && go test -run TestTagEquivalence          # with the live PHP up on 8899
//
// THAT SECOND LINE IS THIS UNIT'S REAL GATE, and it needs NO new code: #282's TestTagEquivalence
// (tags/equivalence_test.go:395) already sweeps Scan(TagsDir) — all 45 tags — and byte-compares the
// live PHP's slice against tags.RenderTag for every name IsPorted reports (:413,:442,:452-456). So
// registering "ShadowForge" ENROLLS IT IN THAT SWEEP AUTOMATICALLY; nothing in that file needs to
// change, which is the #281 add-a-file model paying off. The python sweep recorded below is a
// stand-in for exactly that test, run by the only interpreter this session could invoke — it uses
// the same two anchors and the same live server, and it should be DISCARDED in favour of the Go test
// the moment the toolchain is available.
//
// The same gate covers php. A php binary DOES exist on this machine — the process table shows
// 127.0.0.1:8899 being served by
// ~/code/installed/jazz-project/congruency/tooling/congruencey-harness/php/php (`-S 0.0.0.0:8899
// boot/router.php`), i.e. the repo php the ticket names, living in the SIBLING checkout rather than
// in this worktree (.gitignore:10 excludes /tooling/congruencey-harness/php/, so it is provisioned,
// never committed — which is why this worktree has none). Invoking it directly was also refused
// ("This command requires approval"). Shelling out to either php or go from the python that IS
// permitted would route around a permission gate, which is not a measurement; it was not done (#253
// set that precedent and it is kept). Consequently NO php was executed by this session: every PHP
// fact below is a response fetched over HTTP from that already-running server, which is the repo's
// own established oracle (equivalence_test.go fetches the live PHP exactly this way) and needed no
// gate to reach.
//
// WHAT WAS RUN, AND WHY IT IS STRONGER THAN #253's EVIDENCE. #253 had no PHP oracle at all. This
// session does: THE LIVE PHP THIS REPO SERVES IS UP on 127.0.0.1:8899, and the real shadow_index.db
// is present and readable at the default shadow_path() (76 sf_file rows, 23 sf_shadow, 74
// sf_deficit; journal_mode=delete — read this session through a python3 `immutable=1` handle, which
// creates no sidecar files and cannot write). So the ORACLE IS THE LIVE PHP, not a reading of it:
//
//   - THE TAG'S OWN BYTES ARE CUT OUT OF THE LIVE PAGE with #282's anchors — the technique
//     documented at tags/equivalence_test.go:35-73 and implemented by its tagOutOpen (:247),
//     tagOutClose (:252) and pageTail (:263). (#253's header cites those anchors as
//     "equivalence_test.go:35-75"; re-checked this session, that range in the ROOT
//     congruency-go/equivalence_test.go is the import block — the anchors live in the tags package's
//     own equivalence_test.go. Corrected here rather than copied forward.) The page is CHROME +
//     gallery + <the tag> + TAIL; the head cut is TagList.php:62's
//     "<div class='tagout'><h3>&lt;&lt;&lt;ShadowForge&gt;&gt;&gt;</h3>\n" literal and the tail cut
//     is len(page) - len("</div>\n" + "\n</body>\n</html>\n"). Both cuts are SEARCHED for, never
//     offsets, and every page is REQUIRED to end with "</div>\n"+TAIL before a slice is taken, so a
//     page that does not is reported rather than silently mis-sliced. Unlike #253's tag, this one
//     emits NO warnings — its bare gate body is 27,288 bytes and the page preamble is the ordinary
//     2 bytes ("\n\n"), so nothing shifts the cuts.
//   - THE COMPARISON MODELS THIS FILE'S OWN CONTROL FLOW over Go's primitive CONTRACTS (the method
//     #253's adversary forced): the transliteration runs sqlite through Python's sqlite3 against the
//     SAME shadow_index.db opened `immutable=1`, and reimplements phpURLEncode, phpHTMLSpecialChars
//     (&#039; not &#39;, &quot; not &#34;), phpString's int64/float64/nil branches and
//     phpFloatString's precision-14 %G — reading each off engine.go this session rather than
//     assuming Python's equivalent matches.
//
// THE RESULT: 31 inputs, 0 mismatches, 26 of them carrying more than 1,000 bytes beyond the summary
// both branches always share (a pass on two near-identical short strings is weak evidence, so the
// thin ones are counted separately). Every byte count below was MEASURED this session:
//
//	(bare)                                     27,288B  summary + facets + 74-row backlog + exemplars
//	&reason=no-spec | no-test | no-test+no-spec  12,926B / 4,945B / 16,481B   all three real reasons
//	&repo=congruency | jazz-forge               19,822B / 11,028B             both real repos
//	&ext=.py | .sql | py | zz          18,657B / 12,185B / 3,242B / 3,242B    the LEFT JOIN facet
//	&reason=no-spec&repo=jazz-forge[&ext=py]     4,085B / 3,291B              facets combined
//	&reason=zzz | &repo=zzz             3,235B / 3,233B   the "(no deficits)" empty state
//	&file=<real> | nope | ''            1,394B / 934B / 27,288B   (empty ?file= falls through)
//	&shadow=<real> | nope | ''          1,326B / 939B / 27,288B   (empty ?shadow= falls through)
//	&file=<real>&shadow=<real>          1,326B  BOTH set: ?shadow= wins, which is the branch ORDER
//	&file=x'&<>"y | a b~c%d             957B / 937B    escape-first over hostile input
//	&shadow=<<<TitleTag>>>                967B  a stored tag invocation comes back inert
//	&ext=' OR 1=1 -- | &reason=<script>alert(1)</script>   3,270B / 3,269B   bound, never interpolated
//
// A QUIRK THE SWEEP MADE VISIBLE, ported faithfully and not fixed: sf_file.ext stores the dot
// (".py", ".sql" — measured), while the facet form's own placeholder suggests "py"
// (ShadowForge.php:132). So the value the form proposes matches NOTHING: &ext=py returns the same
// 3,242B empty backlog as the nonsense &ext=zz, while &ext=.py returns 18,657B. That is the PHP's
// defect, it deserves a bug ticket of its own, and per the ticket's instruction it is reproduced
// rather than "improved" here — this file just runs the PHP's query.
//
// PROOF THE SWEEP CAN SEE A DEFECT (the method #253's adversary forced — a harness that cannot
// reproduce a bug cannot certify against it). 11 mutations, each a defect a reasonable Go port would
// plausibly ship, were injected into the transliteration. FIVE ARE CAUGHT, and they are the ones
// that matter most: Go's html.EscapeString for esc (&#39; vs PHP's &#039;) fails 1/22; dropping the
// COALESCE optional-facet guard fails 9/22; loosening by_file's strict `!== ''` fails 1/22; swapping
// the ?shadow=/?file= branch order fails 1/22; and treating a present-but-empty ?file= as set fails
// 2/22. Baseline, unmutated: 0/22.
//
// THE OTHER SIX SURVIVE, AND THAT IS A LIMIT OF THE DATA, NOT A DEFECT — recorded here rather than
// left for the adversary to find, because it bounds exactly how much the 31-input sweep proves.
// Each was checked against the live shadow_index.db this session:
//
//	url.QueryEscape instead of phpURLEncode   no DB value contains '~' or ' ' (81 checked) — the
//	                                          only bytes on which the two differ
//	urlencode(esc(v)) vs esc(urlencode(v))    no DB value contains & < > ' " — so esc is a no-op there
//	naive math.Round(v*10)/10 for pct         neither ratio is a tie: 1000*23/53 leaves r=51 (d=53),
//	                                          1000*7/76 leaves r=8 (d=76). See "SF-1 / SF-3".
//	pct returning float64 always              both denominators are > 0 (53, 76), so the `: 0` arm
//	                                          is unreachable on this data
//	INNER JOIN instead of LEFT JOIN           0 sf_deficit rows lack an sf_file row, so the join type
//	                                          is invisible
//	ORDER BY repo instead of n DESC, repo     congruency(49) then jazz-forge(25) — the two orders
//	                                          coincide by accident of the counts
//
// In all six this file matches the PHP SOURCE (checked line by line against ShadowForge.php this
// session); what is missing is a live input that could TELL them apart, and no such input exists in
// this database. They are the places a future data change would first expose a wrong choice.
//
// THE TWO DEGRADATION BRANCHES ARE NOT MEASURED, and this is stated rather than glossed: the real
// shadow_index.db IS present and readable on the machine serving 8899, and this session cannot set
// SHADOW_FORGE_DB on an already-running server, so neither "not built yet" nor "not readable" can be
// provoked out of the live PHP from here. They were checked the only way left — each string was
// RECONSTRUCTED from the PHP's own source literal (ShadowForge.php:47, :54) and, independently, from
// this file's shadowNotBuilt/shadowNotReadable literals, then compared byte for byte with a path
// chosen to exercise every htmlspecialchars character (/tmp/x'&<>".db). Both match. That tests the
// STRINGS; it does not test which branch fires, which rests on the reading of is_file/is_readable
// recorded under "DEGRADATION".
//
// WHAT THAT DOES AND DOES NOT ESTABLISH. It establishes that the LOGIC encoded here — its branch
// selection, its SQL, its ordering, its escaping and its number formatting — reproduces the live PHP
// byte for byte on all 31 inputs, against the same database, and that the sweep detects five real
// classes of defect. It does NOT establish that this file COMPILES, that gofmt/vet are clean, that
// the six data-blind choices above are right (they are source-checked, not measured), or that either
// degradation branch fires where the PHP's does. To reduce the compile risk the toolchain would
// otherwise have caught, every external symbol this file uses was read out of engine.go this session
// and checked against its real signature (Tag, Config, Engine.cfg, Engine.getStr, Register, openDB,
// scalar, queryRows, queryColumn, esc, phpString, phpURLEncode, toInt, throwableHTML,
// catchThrowable — all 15 found), every name this file DECLARES was checked against every other file
// in package tags for a redeclaration (10 package-level names, all unique — Register panics on a
// duplicate and nothing else registers "ShadowForge"), and every import was checked as used (an
// unused import is a build error in Go).
//
// ── THIS UNIT'S GATE IS NOT EMPTY, AND THE REASON IS NOT THIS UNIT ──────────────────────────────
//
// Stated plainly because the ticket asks for exactly this ("if you cannot make a diff here run
// against THIS unit, say so on the ticket rather than settling on a diff that would be empty even
// with the unit unimplemented"). BOTH of the ticket's diffs were RUN this session and BOTH are
// non-empty, for reasons that are all upstream of this file:
//
//	diff <(curl -s 'http://127.0.0.1:8899/?page=tags&tag=ShadowForge') \
//	     <(curl -s 'http://127.0.0.1:8900/?page=tags&tag=ShadowForge')     33,830B vs 4,094B
//	for p in shadowforge; do diff <(curl -s ".../?page=$p") <(curl -s ".../?page=$p"); done
//	                                                                       30,319B vs 1,037B
//
//  1. THE DEPLOYED GO BINARY ON 8900 DOES NOT CONTAIN THIS FILE, and cannot: building it needs the
//     toolchain this session was refused. 8900 answers ?tag=ShadowForge with the gallery carrying
//     notPortedHTML's divergence notice (4,094B, no <h2>Summary</h2>), because the tag is
//     unregistered in that binary. IT IS STALE GENERALLY, not just for this ticket — measured this
//     session, 8900 returns that same "no Go port" notice for Annotations (#247), ApiReference
//     (#248), Catalog_Controller (#253), PageList (#324) and ProductView (#326), every one of which
//     is ALREADY MERGED TO MAIN. Rebuilding and redeploying 8900 is a precondition for ANY tag's
//     gate here, it is upstream of every per-tag ticket, and it is not this ticket's deliverable.
//  2. PAGE CHROME. congruency-go's server does not reproduce the PHP CMS chrome and declines to
//     forge it (server.go:64-66). The two pages differ by that ~6.2 KB whether or not this file
//     exists.
//  3. THE GALLERY FRAME. handleTagsPage (server.go:792-829) answers a REGISTERED tag by rendering
//     THAT TAG ALONE via tags.RenderTag — no tag list, no <div class='tagout'> wrapper — while the
//     PHP page carries the whole gallery around the tag. So registering this tag CHANGES the Go
//     page's shape; it does not converge it.
//  4. ?page=shadowforge IS NOT WIRED AT ALL, and this is the one specific to this unit's second
//     diff. handlePage (server.go:727-736) routes exactly ONE key — "tags" — to the tag engine;
//     every other key, shadowforge included, falls to handleCatalogPage, which renders a table list
//     and never consults Documents/Document_Templates or the engine. The PHP's ?page=shadowforge
//     (30,319B) is a real document whose stored template holds <<<ShadowForge>>>, which
//     execute_all_tags expands — verified this session: that page contains the tag's <h2>Summary</h2>
//     and no literal "<<<" survives. Nothing this file can do reaches that route; tags.Render (the
//     fuller router mirror, engine.go:4126) exists and would, but calling it is server.go's edit and
//     server.go is not this ticket's deliverable.
//
// So the honest measurement — the one that isolates THIS unit's bytes and changes exactly when this
// file changes — is the 31-input diff recorded above. With this unit unimplemented that diff is not
// empty, it is 27,288 bytes of summary/backlog against notPortedHTML's divergence notice, so it is
// not a diff that passes vacuously.
//
// WHAT WOULD MAKE THE LITERAL GATES EMPTY, for whoever picks this up: a rebuilt 8900, plus a server
// that renders the gallery frame and the CMS chrome (then diff 1 converges), plus routing non-"tags"
// page keys through tags.Render (then diff 2 converges). A server ticket and a deploy — neither of
// them this one.
package tags

import (
	"database/sql"
	"os"
	"strings"
)

// init self-registers the tag (#281's add-a-file model: engine.go is untouched). The factory KEEPS
// its *TagArguments because ShadowForge.php:35's constructor stores $arguments — even though the
// class never reads them again. See "IT TAKES NO TAG ARGUMENTS IT EVER READS" in the file header.
func init() {
	Register("ShadowForge", func(e *Engine, a *TagArguments) Tag {
		return &ShadowForgeTag{e: e, args: a}
	})
}

// ShadowForgeTag is ShadowForge (ShadowForge.php:32). args mirrors the PHP's `private $arguments`,
// which the class stores and never reads; it is nil for the standalone/gallery render.
type ShadowForgeTag struct {
	e    *Engine
	args *TagArguments
}

// shadowDefaultSuffix is the path shadow_path() appends to $HOME (ShadowForge.php:41).
const shadowDefaultSuffix = "/code/installed/jazz-project/config/forge/shadow_forge/shadow_index.db"

// shadowPath is ShadowForge::shadow_path (ShadowForge.php:38-42):
//
//	$p = getenv('SHADOW_FORGE_DB');
//	if ($p !== false && $p !== '') { return $p; }
//	return getenv('HOME') . '/code/.../shadow_index.db';
//
// PHP's getenv returns false for an UNSET variable and "" for one set-but-empty, and the guard
// rejects both — so `os.Getenv(...) != ""` is that whole condition, since Go collapses the two
// cases to "". See the file header for why this reads the environment here rather than Config.
func shadowPath() string {
	if p := os.Getenv("SHADOW_FORGE_DB"); p != "" {
		return p
	}
	return os.Getenv("HOME") + shadowDefaultSuffix
}

// The two missing-dependency states, kept as named builders so the two call sites cannot drift
// apart from each other or from ShadowForge.php:47 and :54.
func shadowNotBuilt(path string) string {
	return "<p class='cy-form-error'>shadow forge not built yet at <code>" + esc(path) +
		"</code> &mdash; run forge/shadow_forge.py</p>"
}

func shadowNotReadable(path string) string {
	return "<p class='cy-form-error'>shadow forge not readable at <code>" + esc(path) +
		"</code> &mdash; run forge/shadow_forge.py</p>"
}

// openShadow is ShadowForge.php:46-55 — the is_file/is_readable test AND the PDO open, kept as the
// two SEPARATE outcomes the PHP has. ok=false with the caller's message already chosen by `built`:
//
//	built=false -> "not built yet"   (is_file/is_readable failed)
//	built=true  -> "not readable"    (the open or the PRAGMA failed)
//
// engine.go's openReflection cannot express that split, which is why this exists. See "DEGRADATION"
// in the file header. Nothing here creates a file: the is_file gate runs before any open, and
// openDB never creates (engine.go:1177-1179).
func openShadow(cfg Config, path string) (db *sql.DB, built bool, ok bool) {
	// is_file($path): a REGULAR file, symlinks followed (os.Stat follows, as PHP's stat does).
	st, err := os.Stat(path)
	if err != nil || !st.Mode().IsRegular() {
		return nil, false, false
	}
	// is_readable($path): ask the question by asking it. See the file header for why this is not a
	// Stat mode check and not syscall.Access.
	f, err := os.Open(path)
	if err != nil {
		return nil, false, false
	}
	f.Close()

	// new PDO('sqlite:'.$path) — read-only here, and it never creates.
	db, err = openDB(cfg, path)
	if err != nil {
		return nil, true, false
	}
	// PRAGMA query_only=1 (ShadowForge.php:52). Redundant against a mode=ro handle, but the PHP
	// states the guarantee at this point and so does this.
	if _, err := db.Exec("PRAGMA query_only=1"); err != nil {
		db.Close()
		return nil, true, false
	}
	return db, true, true
}

// GetDocument is ShadowForge::get_document() (ShadowForge.php:44-67).
//
//	$path = self::shadow_path();
//	if (!is_file($path) || !is_readable($path)) { return <not built yet>; }
//	try { $sdb = new PDO(...); ...; $sdb->exec('PRAGMA query_only=1'); }
//	catch (\Throwable $e) { return <not readable>; }
//	try {
//	    if (isset($_GET['shadow']) && $_GET['shadow'] !== '') return summary . by_shadow($_GET['shadow']);
//	    if (isset($_GET['file'])   && $_GET['file']   !== '') return summary . by_file($_GET['file']);
//	    return summary . facet_form . deficits . spec_cited;
//	} catch (\Throwable $e) { return <error div>; }
//
// Three details that must survive the port, because each changes the bytes:
//
//  1. THE TWO MISSING-DB MESSAGES ARE DIFFERENT STRINGS. See "DEGRADATION" in the file header.
//  2. `isset($k) && $k !== ''` IS EXACTLY `getStr(k) != ""`. A key absent yields "" and a key
//     present-but-empty yields "" (engine.go:911-932), and the PHP rejects both — so the two-part
//     PHP test collapses to one Go test with no branch lost. MEASURED: ?shadow= and ?file= each
//     render the DEFAULT view's full 27,288 bytes on the live PHP, identical to the bare gate.
//  3. THE ERROR ARM WRAPS ONLY THE VIEWS, NOT THE OPEN. A throw from the open is already the "not
//     readable" string; only a throw from the SQL reaches the error div.
func (t *ShadowForgeTag) GetDocument() (out string) {
	defer catchThrowable(&out, "ShadowForge")

	path := shadowPath()
	db, built, ok := openShadow(t.e.cfg, path)
	if !ok {
		if !built {
			return shadowNotBuilt(path)
		}
		return shadowNotReadable(path)
	}
	defer db.Close()

	summary, err := t.summary(db)
	if err != nil {
		return throwableHTML("ShadowForge", err)
	}

	if shadow := t.e.getStr("shadow"); shadow != "" {
		body, err := t.byShadow(db, shadow)
		if err != nil {
			return throwableHTML("ShadowForge", err)
		}
		return summary + body
	}
	if file := t.e.getStr("file"); file != "" {
		body, err := t.byFile(db, file)
		if err != nil {
			return throwableHTML("ShadowForge", err)
		}
		return summary + body
	}

	facets, err := t.facetForm(db)
	if err != nil {
		return throwableHTML("ShadowForge", err)
	}
	deficits, err := t.deficits(db)
	if err != nil {
		return throwableHTML("ShadowForge", err)
	}
	cited, err := t.specCited(db)
	if err != nil {
		return throwableHTML("ShadowForge", err)
	}
	return summary + facets + deficits + cited
}

// sfScalar is ShadowForge::scalar (ShadowForge.php:69-72):
//
//	$v = $sdb->query($sql)->fetchColumn();
//	return ($v === false || $v === null) ? 0 : $v;
//
// The 0 is an INT, so it renders as "0" and not "" — which is why this cannot just return the nil.
// fetchColumn's `false` is "no rows"; engine.go's scalar reports that as a nil too, so both PHP
// cases collapse onto the same Go check. (For COUNT(*) neither is reachable — a COUNT always
// returns exactly one non-null row — but by_file's fetchColumn genuinely can, so the rule is kept.)
//
// The error is PROPAGATED, not swallowed into a 0: under ERRMODE_EXCEPTION (ShadowForge.php:51) a
// failing query THROWS and lands in the error div. See "THAT IS ALSO WHY THIS FILE DOES NOT USE
// scalarOrZero" in the file header.
func sfScalar(db *sql.DB, query string) (any, error) {
	v, err := scalar(db, query)
	if err != nil {
		return nil, err
	}
	if v == nil {
		return int64(0), nil
	}
	return v, nil
}

// sfPct is ShadowForge::pct (ShadowForge.php:74-76):
//
//	return ($den > 0) ? round(100 * $num / $den, 1) : 0;
//
// It returns `any` because the PHP returns two TYPES — a float from round(), an int from the `: 0`
// arm — and esc((string)$v) renders them through different formatters. See "SF-1 / SF-3" in the
// file header for the full argument, including the proof that the exact integer computation below
// equals PHP's round() for every integer num/den, and why a tie is unreachable for this database.
func sfPct(num, den any) any {
	n, d := toInt(num), toInt(den)
	if d <= 0 {
		return int64(0) // the PHP's `: 0` — an INT, so it renders "0"
	}
	return sfRound1(n, d)
}

// sfRound1 is round(100*n/d, 1) for integers, computed with no floating point until the final
// division: k = round_half_away_from_zero(1000*n/d), then k/10.
//
// The sign handling is defensive rather than reachable — every caller passes COUNT(*) results, which
// are non-negative — but it costs two branches and keeps the "half AWAY FROM ZERO" rule true for
// negatives instead of silently becoming "half up" if this is ever reused.
//
// The final `float64(k) / 10` is the same expression PHP's round() ends on (`tmp_value / f1`, with
// f1 = php_intpow10(1) = 10.0), so the two produce the identical double, not merely equal values.
func sfRound1(n, d int64) float64 {
	neg := false
	if n < 0 {
		neg, n = true, -n
	}
	if d < 0 {
		neg, d = !neg, -d
	}
	num := n * 1000
	k, r := num/d, num%d
	if 2*r >= d { // half away from zero
		k++
	}
	f := float64(k) / 10
	if neg {
		f = -f
	}
	return f
}

// summary is ShadowForge::summary (ShadowForge.php:78-110) — SF-1 coverage, SF-3 spec-citation and
// SF-6's deficit count with per-reason and per-repo breakdowns.
//
// The five scalars are read in the PHP's order. `if ($by)` / `if ($byrepo)` are PHP truthiness on an
// array, i.e. "non-empty", which is len(...) > 0 here.
func (t *ShadowForgeTag) summary(db *sql.DB) (string, error) {
	nonshadow, err := sfScalar(db, "SELECT COUNT(*) FROM sf_file WHERE is_shadow=0")
	if err != nil {
		return "", err
	}
	covered, err := sfScalar(db, "SELECT COUNT(DISTINCT covers) FROM sf_shadow")
	if err != nil {
		return "", err
	}
	allfiles, err := sfScalar(db, "SELECT COUNT(*) FROM sf_file")
	if err != nil {
		return "", err
	}
	cited, err := sfScalar(db, "SELECT COUNT(*) FROM sf_file WHERE cites_spec=1")
	if err != nil {
		return "", err
	}
	deficits, err := sfScalar(db, "SELECT COUNT(*) FROM sf_deficit")
	if err != nil {
		return "", err
	}

	out := "<h2>Summary</h2>\n<ul class='srclist'>\n"
	out += "<li><strong>SF-1 test coverage:</strong> " + esc(sfPct(covered, nonshadow)) + "% &mdash; <strong>" +
		esc(covered) + "</strong> of <strong>" + esc(nonshadow) + "</strong> non-shadow files covered by a shadow-doc</li>\n"
	out += "<li><strong>SF-3 spec-citation:</strong> " + esc(sfPct(cited, allfiles)) + "% &mdash; <strong>" +
		esc(cited) + "</strong> of <strong>" + esc(allfiles) + "</strong> files cite a spec</li>\n"
	out += "<li><strong>SF-6 deficits:</strong> <strong>" + esc(deficits) + "</strong> file(s) lacking a test and/or a spec</li>\n"

	by, err := queryRows(db, "SELECT reason, COUNT(*) AS n FROM sf_deficit GROUP BY reason ORDER BY reason")
	if err != nil {
		return "", err
	}
	if len(by) > 0 {
		var parts []string
		for _, r := range by {
			parts = append(parts, "<a href='?page=shadowforge&reason="+esc(phpURLEncode(phpString(r["reason"])))+"'>"+
				esc(r["reason"])+"</a>&nbsp;"+esc(r["n"]))
		}
		out += "<li>by reason: " + strings.Join(parts, " &middot; ") + "</li>\n"
	}

	byrepo, err := queryRows(db, "SELECT repo, COUNT(*) AS n FROM sf_deficit GROUP BY repo ORDER BY n DESC, repo")
	if err != nil {
		return "", err
	}
	if len(byrepo) > 0 {
		var rparts []string
		for _, r := range byrepo {
			rparts = append(rparts, "<a href='?page=shadowforge&repo="+esc(phpURLEncode(phpString(r["repo"])))+"'>"+
				esc(r["repo"])+"</a>&nbsp;"+esc(r["n"]))
		}
		out += "<li>by repo: " + strings.Join(rparts, " &middot; ") + "</li>\n"
	}
	return out + "</ul>\n", nil
}

// shadowReasons is the HARDCODED reason list of the facet form's first select (ShadowForge.php:119).
// It is the PHP's literal array, NOT a query — the form offers these four whether or not the data
// holds them, and the leading "" is the "(any)" option.
var shadowReasons = []string{"", "no-test", "no-spec", "no-test+no-spec"}

// facetForm is ShadowForge::facet_form (ShadowForge.php:112-135) — the reason/repo/ext form, with
// the current selection preserved.
//
// The two selects differ in a way that is easy to flatten and must not be: the REASON options come
// from the hardcoded list above and their "(any)" entry is produced INSIDE the loop by relabelling
// the empty string (`$lbl = ($r === '') ? '(any)' : $r;`), while the REPO options come from the DB
// and their "(any)" entry is written out BEFORE the loop (ShadowForge.php:125). Same rendered shape,
// two different constructions; both are kept.
//
// `((string) $rp === $repo)` is a strict compare AFTER a (string) cast, which is phpString here —
// so a repo stored as an INTEGER still matches the string from the query string, as PHP's cast makes
// it.
func (t *ShadowForgeTag) facetForm(db *sql.DB) (string, error) {
	reason := t.e.getStr("reason")
	repo := t.e.getStr("repo")

	out := "<form method='get' class='shadowforge-facets' style='margin:.5rem 0'>"
	out += "<input type='hidden' name='page' value='shadowforge'>"
	out += " reason <select name='reason'>"
	for _, r := range shadowReasons {
		sel := ""
		if r == reason {
			sel = " selected"
		}
		lbl := r
		if r == "" {
			lbl = "(any)"
		}
		out += "<option value='" + esc(r) + "'" + sel + ">" + esc(lbl) + "</option>"
	}

	out += "</select> repo <select name='repo'>"
	repoAny := ""
	if repo == "" {
		repoAny = " selected"
	}
	out += "<option value=''" + repoAny + ">(any)</option>"
	repos, err := queryColumn(db, "SELECT DISTINCT repo FROM sf_file ORDER BY repo")
	if err != nil {
		return "", err
	}
	for _, rp := range repos {
		sel := ""
		if phpString(rp) == repo {
			sel = " selected"
		}
		out += "<option value='" + esc(rp) + "'" + sel + ">" + esc(rp) + "</option>"
	}

	ext := t.e.getStr("ext")
	out += "</select> ext <input type='text' name='ext' value='" + esc(ext) + "' size='6' placeholder='py'>"
	out += " <button type='submit'>filter</button></form>\n"
	return out, nil
}

// deficits is ShadowForge::deficits (ShadowForge.php:137-171) — the DEFAULT view's backlog, with the
// three optional facets applied. See "FACETS ARE BOUND" in the file header for why each name is
// bound once and appears twice.
//
// The ext facet is the reason for the LEFT JOIN: `ext` lives on sf_file, not sf_deficit. It is a
// LEFT join, so a deficit whose path has no sf_file row still appears when no ext facet is set (f.ext
// is NULL, and the guard short-circuits before comparing it) and disappears the moment one is — which
// is the PHP's behaviour, reproduced by running the PHP's query rather than by reasoning about it.
func (t *ShadowForgeTag) deficits(db *sql.DB) (string, error) {
	reason := t.e.getStr("reason")
	repo := t.e.getStr("repo")
	ext := t.e.getStr("ext")

	rows, err := queryRows(db,
		"SELECT d.path AS path, d.repo AS repo, d.reason AS reason, d.detail AS detail\n"+
			"                 FROM sf_deficit d LEFT JOIN sf_file f ON f.path = d.path\n"+
			"                 WHERE (COALESCE(:reason,'')='' OR d.reason=:reason)\n"+
			"                   AND (COALESCE(:repo,'')='' OR d.repo=:repo)\n"+
			"                   AND (COALESCE(:ext,'')='' OR f.ext=:ext)\n"+
			"                 ORDER BY d.reason, d.repo, d.path LIMIT 300",
		sql.Named("reason", reason), sql.Named("repo", repo), sql.Named("ext", ext))
	if err != nil {
		return "", err
	}

	var facet []string
	if reason != "" {
		facet = append(facet, "reason="+esc(reason))
	}
	if repo != "" {
		facet = append(facet, "repo="+esc(repo))
	}
	if ext != "" {
		facet = append(facet, "ext="+esc(ext))
	}
	suffix := ""
	if len(facet) > 0 {
		suffix = " &middot; " + strings.Join(facet, " &middot; ") + " <a href='?page=shadowforge'>&times;</a>"
	}
	out := "<h2>Deficit backlog" + suffix + "</h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no deficits)</p>\n", nil
	}
	out += "<table class='shadowforge-deficits' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += "<tr><th style='text-align:left'>path</th><th style='text-align:left'>repo</th><th style='text-align:left'>reason</th><th style='text-align:left'>detail</th></tr>\n"
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=shadowforge&file=" + esc(phpURLEncode(phpString(r["path"]))) + "'>" + esc(r["path"]) + "</a></td>" +
			"<td><a href='?page=shadowforge&repo=" + esc(phpURLEncode(phpString(r["repo"]))) + "'>" + esc(r["repo"]) + "</a></td>" +
			"<td><a href='?page=shadowforge&reason=" + esc(phpURLEncode(phpString(r["reason"]))) + "'>" + esc(r["reason"]) + "</a></td>" +
			"<td>" + esc(r["detail"]) + "</td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// byFile is ShadowForge::by_file (ShadowForge.php:173-192) — ?file=<path>: which shadow-docs cover
// this file, plus the file's own spec_refs.
//
// The spec_refs line's guard is `$fref !== false && $fref !== null && $fref !== ''` — three STRICT
// comparisons. false is fetchColumn's "no such file row" and null is a SQL NULL; engine.go's scalar
// reports both as nil, so one nil check covers two PHP cases. The `!== ''` arm is strict, so it
// rejects ONLY the empty string: a spec_refs of integer 0 is `0 !== ''` -> true and the PHP prints
// it, which phpString(int64(0)) == "0" != "" reproduces. Testing emptiness any looser (PHP's
// empty(), or a truthiness test) would silently drop that row's "<code>0</code>".
func (t *ShadowForgeTag) byFile(db *sql.DB, file string) (string, error) {
	out := "<h2>Shadows covering <code>" + esc(file) + "</code> <a href='?page=shadowforge'>&times;</a></h2>\n"

	fref, err := scalar(db, "SELECT spec_refs FROM sf_file WHERE path=:file LIMIT 1", sql.Named("file", file))
	if err != nil {
		return "", err
	}
	if fref != nil && phpString(fref) != "" {
		out += "<p>file spec_refs: <code>" + esc(fref) + "</code></p>\n"
	}

	rows, err := queryRows(db, "SELECT shadow, spec_refs FROM sf_shadow WHERE covers=:file ORDER BY shadow LIMIT 200",
		sql.Named("file", file))
	if err != nil {
		return "", err
	}
	if len(rows) == 0 {
		return out + "<p>(no shadow-doc covers this file)</p>\n", nil
	}
	out += "<table class='shadowforge-covers' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += "<tr><th style='text-align:left'>shadow</th><th style='text-align:left'>spec_refs</th></tr>\n"
	for _, r := range rows {
		out += "<tr><td><a href='?page=shadowforge&shadow=" + esc(phpURLEncode(phpString(r["shadow"]))) + "'>" +
			esc(r["shadow"]) + "</a></td><td><code>" + esc(r["spec_refs"]) + "</code></td></tr>\n"
	}
	return out + "</table>\n", nil
}

// byShadow is ShadowForge::by_shadow (ShadowForge.php:194-210) — ?shadow=<name>: every file a given
// shadow-doc covers. The inverse of byFile, and unlike it, it reads no second scalar.
func (t *ShadowForgeTag) byShadow(db *sql.DB, shadow string) (string, error) {
	out := "<h2>Files covered by <code>" + esc(shadow) + "</code> <a href='?page=shadowforge'>&times;</a></h2>\n"

	rows, err := queryRows(db, "SELECT covers, spec_refs FROM sf_shadow WHERE shadow=:shadow ORDER BY covers LIMIT 200",
		sql.Named("shadow", shadow))
	if err != nil {
		return "", err
	}
	if len(rows) == 0 {
		return out + "<p>(no files covered by this shadow-doc)</p>\n", nil
	}
	out += "<table class='shadowforge-covered' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += "<tr><th style='text-align:left'>covers</th><th style='text-align:left'>spec_refs</th></tr>\n"
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=shadowforge&file=" + esc(phpURLEncode(phpString(r["covers"]))) + "'>" + esc(r["covers"]) + "</a></td>" +
			"<td><code>" + esc(r["spec_refs"]) + "</code></td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}

// specCited is ShadowForge::spec_cited (ShadowForge.php:212-226) — the exemplars that DO cite a
// spec. Unfaceted and unbound: a plain query with a fixed LIMIT 40.
func (t *ShadowForgeTag) specCited(db *sql.DB) (string, error) {
	rows, err := queryRows(db, "SELECT path, spec_refs FROM sf_file WHERE cites_spec=1 ORDER BY path LIMIT 40")
	if err != nil {
		return "", err
	}
	out := "<h2>Spec-cited exemplars</h2>\n"
	if len(rows) == 0 {
		return out + "<p>(no files cite a spec yet)</p>\n", nil
	}
	out += "<table class='shadowforge-cited' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n"
	out += "<tr><th style='text-align:left'>path</th><th style='text-align:left'>spec_refs</th></tr>\n"
	for _, r := range rows {
		out += "<tr>" +
			"<td><a href='?page=shadowforge&file=" + esc(phpURLEncode(phpString(r["path"]))) + "'>" + esc(r["path"]) + "</a></td>" +
			"<td><code>" + esc(r["spec_refs"]) + "</code></td>" +
			"</tr>\n"
	}
	return out + "</table>\n", nil
}
