<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * TreeView — browse a registered repo's REAL source tree from forge's bare remote.
 *
 * Invoked as <<<TreeView>>> on ?page=tree. Data source: the `repos` table
 * (name, forge_remote, head_commit) from 0015_repos.sql — congruency holds the
 * metadata/provenance, forge holds the blobs. Reads trees/blobs straight from the
 * bare git remote with read-only plumbing:
 *   ?page=tree                  -> index: every registered repo as a link
 *   ?page=tree&repo=X[&path=D]  -> git --git-dir=<remote> ls-tree <sha> <D>/  (dirs drill in, files -> blob)
 *   ?page=tree&repo=X&blob=P    -> git --git-dir=<remote> show <sha>:P  in a line-numbered <pre>
 *
 * ── WHY REF RESOLUTION IS A SEPARATE METHOD ──────────────────────────────────
 * `repos.head_commit` is NOT trustworthy input. 183 of the 263 registered repos store the
 * literal 4-character string 'HEAD' instead of a sha. Those repos' bare remotes carry a
 * DANGLING symref: .git/HEAD points at refs/heads/master, which does not exist (their real
 * branch is `main`). Run `git rev-parse HEAD` on such a remote and it prints the literal text
 * "HEAD" on stdout — so whatever populated the registry read stdout, saw four plausible
 * characters, and stored them. Feeding that string to `ls-tree` yields
 * "fatal: Not a valid object name HEAD", which is how 180 of 264 forge repos became unbrowsable.
 *
 * This tag therefore NEVER hands the column's contents to git. resolveRef() (below) is the one
 * small, separately testable method that turns (repo, gitdir, head_commit) into a typed outcome
 * carrying a validated 40-hex sha — or a named 'no_refs' failure. Every candidate is validated
 * with `rev-parse --verify --quiet <ref>^{commit}` and only the resulting 40-hex sha is used
 * thereafter; a symbolic name is never passed downstream.
 *
 * The tier order COPIES the chain that already exists in tools/ingest_repo_docs.py — see its
 * FALLBACK_REFS (:110) and resolve_tip(): stored head_commit (skipping the literal 'HEAD'
 * placeholder), then HEAD, refs/heads/{main,master,source,trunk}, then the first ref under
 * refs/heads/. This is deliberately NOT a data repair: the 183 rows are left exactly as they
 * are. ingest_repo_docs.py documents the identical 183/263 finding and routes around the column,
 * and tools/forge_refactor_ticketer.py resolves tips itself ("TIP BEATS OMNI"); TreeView was the
 * last consumer that trusted the value.
 *
 * ── TELEMETRY ────────────────────────────────────────────────────────────────
 * Every resolution appends ONE row to the existing `events` table (id, ts, component, event,
 * status, ms, meta) with component='TreeView', event='ref_resolve', status='ok'|'fallback'|
 * 'no_refs', ms=resolution wall time, and meta={repo, tier, resolved_sha, head_commit_rejected}.
 * Before this, the fallback happened silently and nobody learned the registry was corrupt; now
 * the tier distribution is queryable, e.g.:
 *   SELECT json_extract(meta,'$.tier') AS tier, COUNT(*) FROM events
 *    WHERE component='TreeView' AND event='ref_resolve' GROUP BY tier ORDER BY 2 DESC;
 * recordResolve() swallows every failure (a telemetry problem must never break the page) and
 * returns bool so tests can assert it. This is NOT front_telemetry — that sink is the front-end
 * page beacon (boot/rest.php:120-137) and has the wrong shape.
 *
 * ── SECURITY (posture unchanged) ─────────────────────────────────────────────
 * The repo name is validated against the DB whitelist (never trusted from ?repo=); EVERY git
 * argument is escapeshellarg()'d; only read-only subcommands are ever run — git() enforces that
 * with an allowlist (ls-tree, show, rev-parse, for-each-ref) rather than merely promising it;
 * all output is htmlspecialchars()'d before it flows back through execute_all_tags (so any
 * literal <<<...>>> in source stays inert).
 *
 * ── TESTS ────────────────────────────────────────────────────────────────────
 * Run them (mirrors SemanticSearch.php's CLI selftest hook):
 *   php TreeView.php __selftest              # synthetic + security + telemetry + page render + live
 *   php TreeView.php __selftest --db=<path>  # live layer with registry tier attribution
 * Layers: (A) synthetic throwaway bare repos covering every resolution shape, (B) shell-metachar
 * injection, (C) telemetry against a temp db, (D) an end-to-end get_document() page render,
 * (E) the live 264 forge remotes (read-only, immutable=1 — creates no -wal/-shm sidecars and
 * never writes the db). Exits 0 all-pass, 1 otherwise.
 */
if (!interface_exists('Tag_Interface')) { interface Tag_Interface { public function get_document(); } }
if (!class_exists("TreeView")) {
    class TreeView implements Tag_Interface {

        /* Tip resolution after `repos.head_commit`, copied from tools/ingest_repo_docs.py:110
           (FALLBACK_REFS) so both tools resolve every repo to the same commit. */
        const FALLBACK_REFS = array('HEAD', 'refs/heads/main', 'refs/heads/master', 'refs/heads/source', 'refs/heads/trunk');

        /* The ONLY git subcommands this tag may run. All are read-only; git() refuses anything else. */
        const READONLY_GIT = array('ls-tree', 'show', 'rev-parse', 'for-each-ref');

        /* Label for tier (d) — "the first ref under refs/heads/" — in the attempted-tier trail. */
        const TIER_FIRST_REF = 'refs/heads/* (first ref)';

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

        // ── read-only git plumbing ───────────────────────────────────────────────────────────

        /* Run one read-only git command against the bare remote. EVERY argument (the git-dir and
           each element of $args) is escapeshellarg()'d, and $args[0] must be in READONLY_GIT, so
           a write subcommand cannot be issued from this class even by a future edit.
           Returns array('rc' => int, 'out' => array<string> stdout lines). rc 126 = refused. */
        private static function git($gitdir, array $args) {
            if (!$args || !in_array($args[0], self::READONLY_GIT, true)) {
                return array('rc' => 126, 'out' => array());
            }
            $cmd = "git --git-dir=" . escapeshellarg((string) $gitdir);
            foreach ($args as $a) { $cmd .= " " . escapeshellarg((string) $a); }
            $cmd .= " 2>/dev/null";
            $out = array(); $rc = 0;
            exec($cmd, $out, $rc);
            return array('rc' => $rc, 'out' => $out);
        }

        /* The 40-hex commit sha `$ref` names in this remote, or null.

           `^{commit}` makes a tag, a tree, or a dangling symref fail HERE rather than surface later
           as an unreadable tree, and --verify --quiet turns "not a valid object" into rc 1 + empty
           stdout instead of an error page. The 40-hex test is the belt-and-braces guard that stops
           a symbolic name (notably the literal 'HEAD') from ever being used as a sha downstream.
           Mirrors ingest_repo_docs.py's rev_parse(). */
        public static function revParse($gitdir, $ref) {
            $ref = (string) $ref;
            if ($ref === '') { return null; }
            $r = self::git($gitdir, array('rev-parse', '--verify', '--quiet', $ref . '^{commit}'));
            if ($r['rc'] !== 0 || !$r['out']) { return null; }
            $sha = trim((string) $r['out'][0]);
            return preg_match('/^[0-9a-f]{40}$/', $sha) ? $sha : null;
        }

        /* Tier (d): the first ref under refs/heads/ that actually resolves, or null if the remote
           has none. for-each-ref sorts by refname, so this is deterministic. Mirrors
           ingest_repo_docs.py's first_branch(). */
        public static function firstBranch($gitdir) {
            $r = self::git($gitdir, array('for-each-ref', '--format=%(refname)', 'refs/heads/'));
            foreach ($r['out'] as $ref) {
                $ref = trim((string) $ref);
                if ($ref !== '' && self::revParse($gitdir, $ref) !== null) { return $ref; }
            }
            return null;
        }

        // ── THE resolver ─────────────────────────────────────────────────────────────────────

        /* Resolve the commit to browse for one repo. This is the whole point of the tag: it is
           pure (no DB, no page state, no telemetry) so it can be driven directly by the selftest
           and by any other caller.

           Returns a typed outcome array — always these keys, never an exception:
             repo                 string   the repo name, so a failure names itself
             status               string   'ok'      resolved from repos.head_commit (registry was right)
                                           'fallback' resolved from a later tier (registry was NOT usable)
                                           'no_refs'  nothing resolved (bare remote carries no refs)
             tier                 string|null  which tier won: 'head_commit', 'HEAD', 'refs/heads/main',
                                               ... or the concrete refname found by tier (d)
             sha                  string|null  the validated 40-hex commit sha; null iff 'no_refs'
             head_commit          string   the raw registry value, verbatim (for display/diagnosis)
             head_commit_rejected bool     true iff a non-empty head_commit was NOT what resolved
             tiers_tried          array    the tiers attempted, in order — the failure trail
             ms                   float    resolution wall time in milliseconds

           Tier order (copied from ingest_repo_docs.py resolve_tip(), do not reinvent):
             (a) repos.head_commit — only if it resolves. The literal 'HEAD' is not tried as a
                 stored value: it is the placeholder the 183 corrupt rows carry, not a sha, and
                 tier (b) covers it anyway. Any OTHER stored junk is rejected by the rev-parse
                 guard below, which is what makes the column safe to read at all.
             (b) HEAD
             (c) refs/heads/main, refs/heads/master, refs/heads/source, refs/heads/trunk
             (d) the first ref under refs/heads/ */
        public static function resolveRef($repo, $gitdir, $head_commit) {
            $t0 = microtime(true);
            $stored = trim((string) $head_commit);

            $cands = array();                                    // array(tier label, ref to try)
            if ($stored !== '' && $stored !== 'HEAD') { $cands[] = array('head_commit', $stored); }
            foreach (self::FALLBACK_REFS as $ref) { $cands[] = array($ref, $ref); }

            $tried = array(); $sha = null; $tier = null;
            foreach ($cands as $c) {
                $tried[] = $c[0];
                $s = self::revParse($gitdir, $c[1]);
                if ($s !== null) { $sha = $s; $tier = $c[0]; break; }
            }
            if ($sha === null) {                                 // tier (d)
                $tried[] = self::TIER_FIRST_REF;
                $ref = self::firstBranch($gitdir);
                if ($ref !== null) { $sha = self::revParse($gitdir, $ref); $tier = $ref; }
            }

            return array(
                'repo'                 => (string) $repo,
                'status'               => ($sha === null) ? 'no_refs' : (($tier === 'head_commit') ? 'ok' : 'fallback'),
                'tier'                 => $sha === null ? null : $tier,
                'sha'                  => $sha,
                'head_commit'          => $stored,
                'head_commit_rejected' => ($stored !== '' && $tier !== 'head_commit'),
                'tiers_tried'          => $tried,
                'ms'                   => round((microtime(true) - $t0) * 1000, 3),
            );
        }

        /* One plain-text line explaining an outcome — names the repo AND every tier attempted, so
           a failure is legible without this file. Used by the no-refs page and by the selftest. */
        public static function describe(array $o) {
            $trail = implode(' -> ', $o['tiers_tried']);
            if ($o['status'] === 'no_refs') {
                return sprintf('repo %s has no refs under refs/heads (bare remote is empty); tried: %s',
                               $o['repo'], $trail);
            }
            return sprintf('repo %s resolved to %s via tier %s (%s); tried: %s',
                           $o['repo'], $o['sha'], $o['tier'], $o['status'], $trail);
        }

        // ── telemetry ────────────────────────────────────────────────────────────────────────

        /* Append ONE row per resolution to the existing `events` table. Returns true if the row
           landed, false otherwise — and NEVER throws or emits: a telemetry failure (read-only db,
           missing table, locked file) must not break a page that otherwise renders fine. The meta
           keys are exactly the four the ref_resolve contract specifies. */
        private static function recordResolve($db, array $o) {
            try {
                if (!($db instanceof PDO)) { return false; }
                $meta = json_encode(array(
                    'repo'                 => $o['repo'],
                    'tier'                 => $o['tier'],
                    'resolved_sha'         => $o['sha'],
                    'head_commit_rejected' => $o['head_commit_rejected'],
                ), JSON_UNESCAPED_SLASHES);
                $st = $db->prepare("INSERT INTO events (ts, component, event, status, ms, meta) VALUES (?,?,?,?,?,?)");
                return (bool) $st->execute(array(microtime(true), 'TreeView', 'ref_resolve',
                                                 $o['status'], $o['ms'], $meta));
            } catch (\Throwable $e) {
                return false;
            }
        }

        // ── page ─────────────────────────────────────────────────────────────────────────────

        public function get_document() {
            try {
                if (!defined('CONGRUENCY_SQLITE')) { return "<p>TreeView: no DB.</p>"; }
                $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
                $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

                // whitelist: ONLY repos actually registered in the DB may be browsed
                $repos = array();
                foreach ($db->query("SELECT name, forge_remote, head_commit FROM repos ORDER BY name")->fetchAll(PDO::FETCH_ASSOC) as $r) {
                    $repos[$r['name']] = $r;
                }

                $repo = isset($_GET['repo']) ? (string) $_GET['repo'] : '';
                if ($repo === '') { return $this->index($repos); }
                if (!isset($repos[$repo])) {
                    return "<p><strong>No such registered repo.</strong> <a href='?page=tree'>&larr; repos</a></p>";
                }
                $gitdir = (string) $repos[$repo]['forge_remote'];

                // NEVER `(string) $repos[$repo]['head_commit']` straight into git: 183 rows hold the
                // literal 'HEAD'. Resolve to a validated sha, and record the tier either way.
                $res = self::resolveRef($repo, $gitdir, $repos[$repo]['head_commit']);
                self::recordResolve($db, $res);

                $blob = isset($_GET['blob']) ? (string) $_GET['blob'] : '';
                $path = isset($_GET['path']) ? (string) $_GET['path'] : '';
                if ($res['status'] === 'no_refs') {
                    return $this->crumbs($repo, $blob !== '' ? $blob : $path) . $this->noRefsNotice($res);
                }
                $commit = $res['sha'];

                if ($blob !== '') { return $this->viewBlob($repo, $gitdir, $commit, $blob) . $this->provenance($res); }
                return $this->viewTree($repo, $gitdir, $commit, $path) . $this->provenance($res);
            } catch (\Throwable $e) {
                return "<div class='cy-form-error'>TreeView error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        /* The typed, named failure for a repo whose bare remote carries no refs at all (3 of the
           264 forge remotes). Names the repo and every tier tried — never "Could not read the
           tree at .". */
        private function noRefsNotice(array $o) {
            // escape each tier, THEN join with the arrow entity — escaping the joined string would
            // turn the separator into a literal "&rarr;" on the page
            $tiers = array();
            foreach ($o['tiers_tried'] as $t) { $tiers[] = "<code>" . self::esc($t) . "</code>"; }
            return "<div class='cy-form-error'><strong>Nothing to browse in " . self::esc($o['repo']) . ".</strong> "
                 . "This repo has no refs under <code>refs/heads/</code> &mdash; its bare remote is empty, "
                 . "so there is no commit to read a tree from. This is the repo's real state, not a lookup error.<br>"
                 . "<span style='font-size:.85em'>Resolution tiers attempted, in order: "
                 . implode(' &rarr; ', $tiers) . "."
                 . ($o['head_commit'] !== '' ? " Registry <code>head_commit</code> was <code>" . self::esc($o['head_commit']) . "</code>." : "")
                 . "</span> <a href='?page=tree'>&larr; repos</a></div>";
        }

        /* A one-line footer naming the commit shown and how it was found. When the registry value
           was unusable this is where the corruption becomes visible on the page itself. */
        private function provenance(array $o) {
            $s = "<p style='color:#888;font-size:.8em;margin-top:.8rem'>@ <code>" . self::esc(substr($o['sha'], 0, 12))
               . "</code> via <code>" . self::esc($o['tier']) . "</code>";
            if ($o['head_commit_rejected']) {
                $s .= " &mdash; registry <code>head_commit</code> (<code>" . self::esc($o['head_commit'])
                    . "</code>) is not a commit in this remote, so it was not used";
            }
            return $s . "</p>\n";
        }

        private function index($repos) {
            if (!$repos) { return "<p>No repos registered.</p>"; }
            $out = "<p>Registered repos &mdash; browse each one's real source tree, read straight from its forge remote.</p>\n<ul class='srclist'>\n";
            foreach ($repos as $name => $r) {
                // the registry's recorded value, shown verbatim and NOT resolved (resolving every
                // repo here would run 263 git processes and file 263 ref_resolve rows per page view)
                $out .= "<li>&#128193; <a href='?page=tree&repo=" . self::esc(urlencode($name)) . "'>" . self::esc($name) . "</a> "
                      . "<span style='color:#888;font-size:.85em' title='registry head_commit (resolved on open)'>@ "
                      . self::esc(substr((string) $r['head_commit'], 0, 12)) . "</span></li>\n";
            }
            return $out . "</ul>\n";
        }

        // breadcrumb: repos > <repo> > seg > seg ... (final segment plain text)
        private function crumbs($repo, $path) {
            $out = "<p style='font-size:.9rem'><a href='?page=tree'>repos</a> &rsaquo; "
                 . "<a href='?page=tree&repo=" . self::esc(urlencode($repo)) . "'>" . self::esc($repo) . "</a>";
            $segs = ($path === '') ? array() : explode('/', trim($path, '/'));
            $last = count($segs) - 1;
            $acc = '';
            foreach ($segs as $i => $s) {
                if ($s === '') { continue; }
                $acc = ($acc === '') ? $s : ($acc . '/' . $s);
                $out .= " &rsaquo; ";
                if ($i === $last) {
                    $out .= self::esc($s);
                } else {
                    $out .= "<a href='?page=tree&repo=" . self::esc(urlencode($repo)) . "&path=" . self::esc(urlencode($acc)) . "'>" . self::esc($s) . "</a>";
                }
            }
            return $out . "</p>\n";
        }

        private function viewTree($repo, $gitdir, $commit, $path) {
            // read-only plumbing: git --git-dir=<remote> ls-tree <sha> <path>/   (every arg escapeshellarg'd)
            $spec = ($path === '') ? '' : (rtrim($path, '/') . '/');
            $args = array('ls-tree', $commit);
            if ($spec !== '') { $args[] = $spec; }
            $r = self::git($gitdir, $args);

            $out = $this->crumbs($repo, $path);
            if ($r['rc'] !== 0) {
                return $out . "<p>Could not read the tree at <code>" . self::esc($path) . "</code> in commit <code>"
                     . self::esc(substr((string) $commit, 0, 12)) . "</code>. The commit resolved, so this path "
                     . "probably does not exist there. <a href='?page=tree&repo=" . self::esc(urlencode($repo)) . "'>&larr; tree root</a></p>";
            }
            $dirs = array(); $files = array();
            foreach ($r['out'] as $ln) {
                // <mode> SP <type> SP <object> TAB <name>
                $tab = strpos($ln, "\t");
                if ($tab === false) { continue; }
                $meta = substr($ln, 0, $tab);
                $name = substr($ln, $tab + 1);
                $parts = preg_split('/\s+/', $meta);
                $type = isset($parts[1]) ? $parts[1] : '';
                $base = basename($name);
                if ($type === 'tree') {
                    $dirs[] = array('name' => $base, 'full' => $name);
                } else if ($type === 'blob') {
                    $files[] = array('name' => $base, 'full' => $name);
                }
            }
            if (!$dirs && !$files) { return $out . "<p>(empty tree)</p>"; }
            $out .= "<ul class='srclist'>\n";
            foreach ($dirs as $d) {
                $out .= "<li>&#128193; <a href='?page=tree&repo=" . self::esc(urlencode($repo)) . "&path=" . self::esc(urlencode($d['full'])) . "'>" . self::esc($d['name']) . "/</a></li>\n";
            }
            foreach ($files as $f) {
                $out .= "<li>&#128196; <a href='?page=tree&repo=" . self::esc(urlencode($repo)) . "&blob=" . self::esc(urlencode($f['full'])) . "'>" . self::esc($f['name']) . "</a></li>\n";
            }
            return $out . "</ul>\n";
        }

        private function viewBlob($repo, $gitdir, $commit, $blob) {
            // read-only plumbing: git --git-dir=<remote> show <sha>:<path>   (the <sha>:<path> ref is one escapeshellarg'd arg)
            $cmd = "git --git-dir=" . escapeshellarg($gitdir) . " show " . escapeshellarg($commit . ':' . $blob) . " 2>/dev/null";
            $body = shell_exec($cmd);
            $out = $this->crumbs($repo, $blob);
            if ($body === null) {
                return $out . "<p>Could not read <code>" . self::esc($blob) . "</code>. <a href='?page=tree&repo=" . self::esc(urlencode($repo)) . "'>&larr; tree</a></p>";
            }
            $head = "<p><strong>" . self::esc($blob) . "</strong> <span style='color:#888'>@ " . self::esc(substr($commit, 0, 12)) . "</span></p>\n";
            $esc = self::esc($body);
            $lines = explode("\n", $esc);
            $code = "<pre style='background:#f4f1e8;border:1px solid #d8d2c4;padding:.6rem;overflow:auto;font-size:.82rem;line-height:1.4'>";
            $n = 1;
            foreach ($lines as $ln) {
                $code .= "<span style='color:#b0a890;user-select:none'>" . sprintf('%4d', $n++) . "</span>  " . $ln . "\n";
            }
            $code .= "</pre>\n";
            return $out . $head . $code;
        }

        // ── selftest ─────────────────────────────────────────────────────────────────────────
        // Driven by `php TreeView.php __selftest` (hook at the bottom of this file). Layers A-D
        // are hermetic: throwaway bare repos + a throwaway db in a temp dir, no network, no live
        // db. Layer E is read-only against the real forge remotes.

        private static $pass = 0;
        private static $fail = 0;

        private static function ok($cond, $what, $got = null) {
            if ($cond) { self::$pass++; return true; }
            self::$fail++;
            echo "  FAIL: " . $what . ($got === null ? "" : ("\n        got: " . $got)) . "\n";
            return false;
        }

        private static function eq($want, $got, $what) {
            return self::ok($want === $got, $what, var_export($got, true) . " (want " . var_export($want, true) . ")");
        }

        /* Fixture builder — NOT the page path, so it may use write subcommands. Builds a bare repo
           whose refs/heads/<branch> carries one commit adding <file>, then points .git/HEAD at
           <headref> without creating it when $dangling is true (the live 180-repo shape). */
        private static function mkBare($tmp, $name, $branch, $headref, $file = 'README.md') {
            $work = $tmp . '/work_' . $name;
            $bare = $tmp . '/' . $name . '.git';
            $q = 'escapeshellarg';
            mkdir($work, 0700, true);
            file_put_contents($work . '/' . $file, "fixture " . $name . "\n");
            $ident = "-c user.email=selftest@congruency -c user.name=selftest -c commit.gpgsign=false";
            exec("git init --quiet -b " . $q($branch) . " " . $q($work) . " 2>/dev/null");
            exec("git -C " . $q($work) . " add -A 2>/dev/null");
            exec("git -C " . $q($work) . " " . $ident . " commit -q -m fixture 2>/dev/null");
            exec("git clone --bare --quiet " . $q($work) . " " . $q($bare) . " 2>/dev/null");
            if ($headref !== null) {
                exec("git --git-dir=" . $q($bare) . " symbolic-ref HEAD " . $q($headref) . " 2>/dev/null");
            }
            $sha = array(); exec("git --git-dir=" . $q($bare) . " rev-parse " . $q('refs/heads/' . $branch) . " 2>/dev/null", $sha);
            return array('dir' => $bare, 'sha' => trim(isset($sha[0]) ? $sha[0] : ''));
        }

        private static function rmTree($p) {
            if (!file_exists($p)) { return; }
            $it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($p, FilesystemIterator::SKIP_DOTS),
                                                RecursiveIteratorIterator::CHILD_FIRST);
            foreach ($it as $f) { $f->isDir() ? @rmdir($f->getPathname()) : @unlink($f->getPathname()); }
            @rmdir($p);
        }

        /* Walk up from this file looking for $rel — finds config/forge/remotes (and the state db)
           from a normal checkout AND from a pair_loop worktree, where the root sits two levels
           deeper. Mirrors ingest_repo_docs.py's find_registry() walk-up. Returns null if absent. */
        private static function findUp($rel, $isDir) {
            $d = __DIR__;
            while (true) {
                $c = $d . '/' . $rel;
                if ($isDir ? is_dir($c) : is_file($c)) { return $c; }
                $n = dirname($d);
                if ($n === $d) { return null; }
                $d = $n;
            }
        }

        public static function __selftest($args) {
            $dbArg = null; $remArg = null;
            foreach ($args as $a) {
                if (strpos($a, '--db=') === 0)      { $dbArg  = substr($a, 5); }
                if (strpos($a, '--remotes=') === 0) { $remArg = substr($a, 10); }
            }
            $tmp = sys_get_temp_dir() . '/treeview_selftest_' . getmypid() . '_' . mt_rand(1000, 9999);
            mkdir($tmp, 0700, true);
            try {
                self::layerSynthetic($tmp);
                self::layerSecurity($tmp);
                self::layerTelemetry($tmp);
                self::layerPage($tmp);
                self::layerLive($remArg, $dbArg);
            } catch (\Throwable $e) {
                self::$fail++;
                echo "  FAIL: selftest threw: " . $e->getMessage() . "\n";
            }
            self::rmTree($tmp);
            echo "\n" . (self::$fail === 0 ? "PASS" : "FAIL") . ": " . self::$pass . " passed, " . self::$fail . " failed\n";
            return self::$fail === 0 ? 0 : 1;
        }

        /* Layer A — every resolution shape, on throwaway bare repos. */
        private static function layerSynthetic($tmp) {
            echo "A. synthetic resolution (throwaway bare repos)\n";

            // the LIVE 180-repo shape: HEAD dangles at a master that does not exist, real branch is
            // main, and the registry stored the literal 'HEAD'.
            $r = self::mkBare($tmp, 'dangling_main', 'main', 'refs/heads/master');
            $o = self::resolveRef('dangling_main', $r['dir'], 'HEAD');
            self::eq('fallback', $o['status'], 'dangling symref + head_commit=HEAD -> fallback');
            self::eq('refs/heads/main', $o['tier'], 'dangling symref -> tier refs/heads/main');
            self::eq($r['sha'], $o['sha'], 'dangling symref -> resolves to the main sha');
            self::eq(true, $o['head_commit_rejected'], 'literal HEAD is reported rejected');
            self::ok(preg_match('/^[0-9a-f]{40}$/', (string) $o['sha']) === 1, 'resolved value is a 40-hex sha');
            self::ok(self::revParse($r['dir'], 'HEAD') === null, 'a dangling HEAD does not rev-parse to a sha');

            // head_commit holds a real sha and resolves -> tier (a), the registry was right
            $r2 = self::mkBare($tmp, 'head_ok', 'main', null);
            $o2 = self::resolveRef('head_ok', $r2['dir'], $r2['sha']);
            self::eq('ok', $o2['status'], 'valid head_commit sha -> status ok');
            self::eq('head_commit', $o2['tier'], 'valid head_commit sha -> tier head_commit');
            self::eq($r2['sha'], $o2['sha'], 'valid head_commit sha -> that sha');
            self::eq(false, $o2['head_commit_rejected'], 'valid head_commit is not reported rejected');
            self::eq(array('head_commit'), $o2['tiers_tried'], 'a tier-(a) hit tries exactly one tier');

            // HEAD resolves normally but the registry still stored the literal 'HEAD' -> tier (b).
            // Proves the placeholder never wins tier (a) even when the string happens to resolve.
            $o3 = self::resolveRef('head_ok', $r2['dir'], 'HEAD');
            self::eq('fallback', $o3['status'], 'working HEAD + head_commit=HEAD -> fallback, not ok');
            self::eq('HEAD', $o3['tier'], 'working HEAD + head_commit=HEAD -> tier HEAD');
            self::eq(true, $o3['head_commit_rejected'], 'placeholder rejected even when HEAD resolves');
            self::eq($r2['sha'], $o3['sha'], 'tier HEAD resolves to the branch sha');

            // main-only / master-only, with an empty registry value (nothing to reject)
            $o4 = self::resolveRef('main_only', $r['dir'], '');
            self::eq('refs/heads/main', $o4['tier'], 'main-only + empty head_commit -> tier refs/heads/main');
            self::eq(false, $o4['head_commit_rejected'], 'an empty head_commit rejects nothing');

            $r5 = self::mkBare($tmp, 'master_only', 'master', 'refs/heads/main');
            $o5 = self::resolveRef('master_only', $r5['dir'], '');
            self::eq('refs/heads/master', $o5['tier'], 'master-only -> tier refs/heads/master');
            self::eq($r5['sha'], $o5['sha'], 'master-only -> the master sha');

            // NO refs at all -> the typed, named outcome (the 3 live repos)
            $bare = $tmp . '/empty.git';
            exec("git init --bare --quiet " . escapeshellarg($bare) . " 2>/dev/null");
            $o6 = self::resolveRef('empty_repo', $bare, 'HEAD');
            self::eq('no_refs', $o6['status'], 'no refs -> status no_refs');
            self::eq(null, $o6['sha'], 'no refs -> no sha');
            self::eq(null, $o6['tier'], 'no refs -> no tier');
            self::ok(count($o6['tiers_tried']) === 6, 'no refs -> all 6 tiers attempted', implode(',', $o6['tiers_tried']));
            self::eq(self::TIER_FIRST_REF, $o6['tiers_tried'][5], 'the last tier attempted is the first-ref sweep');
            $msg = self::describe($o6);
            self::ok(strpos($msg, 'empty_repo') !== false, 'the no-refs message names the repo', $msg);
            self::ok(strpos($msg, 'no refs under refs/heads') !== false, 'the no-refs message names the cause', $msg);
            self::ok(strpos($msg, 'refs/heads/trunk') !== false, 'the no-refs message names the tiers tried', $msg);

            // a stale but well-formed sha in the registry -> rejected by the rev-parse guard
            $o7 = self::resolveRef('stale', $r['dir'], str_repeat('a', 40));
            self::eq('fallback', $o7['status'], 'stale head_commit sha -> fallback');
            self::eq('refs/heads/main', $o7['tier'], 'stale head_commit sha -> falls through to main');
            self::eq(true, $o7['head_commit_rejected'], 'stale head_commit sha is reported rejected');
            self::eq('head_commit', $o7['tiers_tried'][0], 'a non-HEAD head_commit IS attempted first');

            // tier (d): the only branch is one no FALLBACK_REFS entry names (the live refs/heads/stable shape)
            $r8 = self::mkBare($tmp, 'odd_branch', 'stable', 'refs/heads/master');
            $o8 = self::resolveRef('odd_branch', $r8['dir'], 'HEAD');
            self::eq('refs/heads/stable', $o8['tier'], 'unnamed branch -> tier (d) reports the concrete refname');
            self::eq($r8['sha'], $o8['sha'], 'unnamed branch -> the stable sha');
            self::eq('fallback', $o8['status'], 'unnamed branch -> fallback');

            self::ok(is_float($o8['ms']) && $o8['ms'] >= 0, 'resolution reports a wall time in ms', var_export($o8['ms'], true));
        }

        /* Layer B — the security posture is enforced, not just claimed. */
        private static function layerSecurity($tmp) {
            echo "B. security posture\n";
            $canary = $tmp . '/pwned';

            // a shell metachar in the git-dir must be escaped into an (absurd) path, never executed
            $evil = $tmp . "/x.git; touch " . $canary;
            $o = self::resolveRef('evil', $evil, 'HEAD');
            self::eq('no_refs', $o['status'], 'a metachar git-dir resolves nothing');
            self::ok(!file_exists($canary), 'a metachar git-dir does NOT execute (escapeshellarg holds)');

            // same for the value read out of the registry column
            $r = self::mkBare($tmp, 'sec', 'main', null);
            $o2 = self::resolveRef('sec', $r['dir'], "HEAD; touch " . $canary);
            self::ok(!file_exists($canary), 'a metachar head_commit does NOT execute');
            self::eq($r['sha'], $o2['sha'], 'a metachar head_commit is rejected and the repo still resolves');
            self::eq(true, $o2['head_commit_rejected'], 'a metachar head_commit is reported rejected');

            // the read-only allowlist refuses a write subcommand
            $ref = new ReflectionMethod('TreeView', 'git');
            $ref->setAccessible(true);
            $w = $ref->invoke(null, $r['dir'], array('update-ref', 'refs/heads/main', str_repeat('b', 40)));
            self::eq(126, $w['rc'], 'a non-read-only subcommand is refused by the allowlist');
            self::eq($r['sha'], self::revParse($r['dir'], 'refs/heads/main'), 'the refused write did not happen');
            self::eq(4, count(self::READONLY_GIT), 'the allowlist is exactly ls-tree/show/rev-parse/for-each-ref');
        }

        /* A throwaway db carrying the REAL schema of the two tables this tag touches
           (events from the state db; repos from 0015_repos.sql). */
        private static function mkDb($tmp, $name) {
            $p = $tmp . '/' . $name . '.sqlite';
            $db = new PDO('sqlite:' . $p);
            $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            $db->exec("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
                       component TEXT, event TEXT NOT NULL, status TEXT, ms REAL, meta TEXT)");
            $db->exec("CREATE TABLE repos (name TEXT PRIMARY KEY, forge_remote TEXT, head_commit TEXT)");
            return array($p, $db);
        }

        /* Layer C — one ref_resolve row per resolution, right shape, and it never throws. */
        private static function layerTelemetry($tmp) {
            echo "C. telemetry -> events\n";
            list($p, $db) = self::mkDb($tmp, 'telemetry');
            $rec = new ReflectionMethod('TreeView', 'recordResolve');
            $rec->setAccessible(true);

            $r = self::mkBare($tmp, 'tel', 'main', 'refs/heads/master');
            $o = self::resolveRef('tel', $r['dir'], 'HEAD');
            self::eq(true, $rec->invoke(null, $db, $o), 'recordResolve reports the row landed');

            $row = $db->query("SELECT * FROM events")->fetchAll(PDO::FETCH_ASSOC);
            self::eq(1, count($row), 'exactly ONE events row per resolution');
            $e = $row[0];
            self::eq('TreeView', $e['component'], "component = 'TreeView'");
            self::eq('ref_resolve', $e['event'], "event = 'ref_resolve'");
            self::eq('fallback', $e['status'], "status = 'fallback' for a fallback resolution");
            self::ok(is_numeric($e['ms']) && (float) $e['ms'] >= 0, 'ms is the resolution wall time', var_export($e['ms'], true));
            self::ok(is_numeric($e['ts']) && (float) $e['ts'] > 1600000000, 'ts is an epoch float', var_export($e['ts'], true));
            $m = json_decode($e['meta'], true);
            self::ok(is_array($m), 'meta is valid json', (string) $e['meta']);
            self::eq(array('repo', 'tier', 'resolved_sha', 'head_commit_rejected'), array_keys($m), 'meta carries exactly the 4 contract keys');
            self::eq('tel', $m['repo'], 'meta.repo');
            self::eq('refs/heads/main', $m['tier'], 'meta.tier names the tier that won');
            self::eq($r['sha'], $m['resolved_sha'], 'meta.resolved_sha');
            self::eq(true, $m['head_commit_rejected'], 'meta.head_commit_rejected is true for a literal-HEAD row');

            // a no_refs resolution is recorded too — that is how the 3 empty remotes stay visible
            $bare = $tmp . '/tel_empty.git';
            exec("git init --bare --quiet " . escapeshellarg($bare) . " 2>/dev/null");
            $rec->invoke(null, $db, self::resolveRef('tel_empty', $bare, 'HEAD'));
            $n = $db->query("SELECT * FROM events WHERE status='no_refs'")->fetchAll(PDO::FETCH_ASSOC);
            self::eq(1, count($n), 'a no_refs resolution is recorded as well');
            $nm = json_decode($n[0]['meta'], true);
            self::eq(null, $nm['tier'], 'meta.tier is null when nothing resolved');
            self::eq(null, $nm['resolved_sha'], 'meta.resolved_sha is null when nothing resolved');

            // the tier distribution the ticket wants queryable
            $q = $db->query("SELECT json_extract(meta,'\$.tier') AS tier, COUNT(*) c FROM events
                             WHERE component='TreeView' AND event='ref_resolve' GROUP BY tier")->fetchAll(PDO::FETCH_ASSOC);
            self::eq(2, count($q), 'the fallback tier distribution is queryable from events');

            // TELEMETRY MUST NEVER THROW: a db with no events table, and a non-PDO handle
            $broken = new PDO('sqlite:' . $tmp . '/broken.sqlite');
            $broken->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            self::eq(false, $rec->invoke(null, $broken, $o), 'a missing events table returns false, does not throw');
            self::eq(false, $rec->invoke(null, null, $o), 'a null db handle returns false, does not throw');

            // and a read-only db must not break it either
            $ro = new PDO('sqlite:file:' . $p . '?mode=ro');
            $ro->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            self::eq(false, $rec->invoke(null, $ro, $o), 'a read-only db returns false, does not throw');
        }

        /* Layer D — the real get_document() page path, end to end, on the live-corruption shape. */
        private static function layerPage($tmp) {
            echo "D. page render (end-to-end get_document)\n";
            list($p, $db) = self::mkDb($tmp, 'page');

            $good  = self::mkBare($tmp, 'page_broken', 'main', 'refs/heads/master', 'install.py');
            $empty = $tmp . '/page_empty.git';
            exec("git init --bare --quiet " . escapeshellarg($empty) . " 2>/dev/null");
            $ins = $db->prepare("INSERT INTO repos (name, forge_remote, head_commit) VALUES (?,?,?)");
            $ins->execute(array('page_broken', $good['dir'], 'HEAD'));    // the 183-row shape
            $ins->execute(array('page_empty', $empty, 'HEAD'));           // the 3-repo shape

            if (!defined('CONGRUENCY_SQLITE')) { define('CONGRUENCY_SQLITE', $p); }
            if (CONGRUENCY_SQLITE !== $p) {
                self::ok(false, 'page layer needs CONGRUENCY_SQLITE unset before the selftest runs');
                return;
            }

            // the previously-broken shape now renders its REAL tree
            $_GET = array('page' => 'tree', 'repo' => 'page_broken');
            $t = new TreeView(array());
            $html = $t->get_document();
            self::ok(strpos($html, 'install.py') !== false, 'a dangling-symref repo renders its real tree', $html);
            self::ok(strpos($html, 'Could not read the tree at') === false, 'the old useless message is gone', $html);
            self::ok(strpos($html, 'refs/heads/main') !== false, 'the page names the tier it resolved through', $html);
            self::ok(strpos($html, substr($good['sha'], 0, 12)) !== false, 'the page names the commit it is showing', $html);

            // and the render filed exactly one telemetry row
            $rows = $db->query("SELECT * FROM events WHERE event='ref_resolve'")->fetchAll(PDO::FETCH_ASSOC);
            self::eq(1, count($rows), 'rendering the page filed exactly one ref_resolve row');
            self::eq('fallback', $rows[0]['status'], 'the rendered page filed status=fallback');

            // a blob view resolves through the same sha
            $_GET = array('page' => 'tree', 'repo' => 'page_broken', 'blob' => 'install.py');
            $html = $t->get_document();
            self::ok(strpos($html, 'fixture page_broken') !== false, 'a blob renders from the resolved sha', $html);

            // the no-refs repo fails CLEANLY, naming itself and the tiers
            $_GET = array('page' => 'tree', 'repo' => 'page_empty');
            $html = $t->get_document();
            self::ok(strpos($html, 'page_empty') !== false, 'the no-refs page names the repo', $html);
            self::ok(strpos($html, 'no refs under') !== false, 'the no-refs page names the cause', $html);
            self::ok(strpos($html, 'refs/heads/trunk') !== false, 'the no-refs page names the tiers attempted', $html);
            self::ok(strpos($html, 'Could not read the tree at') === false, 'the no-refs page is NOT the old message', $html);
            self::ok(strpos($html, '&amp;rarr;') === false, 'the tier trail is not double-escaped into a literal entity', $html);
            $rows = $db->query("SELECT * FROM events WHERE status='no_refs'")->fetchAll(PDO::FETCH_ASSOC);
            self::eq(1, count($rows), 'the no-refs render filed a no_refs row');

            // an unregistered repo is still rejected by the whitelist, and files no telemetry
            $_GET = array('page' => 'tree', 'repo' => '../../etc');
            $html = $t->get_document();
            self::ok(strpos($html, 'No such registered repo') !== false, 'the DB whitelist still gates ?repo=', $html);
            self::eq(3, (int) $db->query("SELECT COUNT(*) FROM events")->fetchColumn(), 'an unregistered repo files no telemetry');

            // output is escaped before it re-enters execute_all_tags
            self::ok(strpos($t->get_document(), '<<<') === false, 'no raw tag delimiters leak from the page');

            // THE REGISTRY IS NEVER WRITTEN: this tag only ever SELECTs from repos
            self::eq(2, (int) $db->query("SELECT COUNT(*) FROM repos")->fetchColumn(), 'repos row count unchanged by rendering');
            self::eq(2, (int) $db->query("SELECT COUNT(*) FROM repos WHERE head_commit='HEAD'")->fetchColumn(),
                     "repos.head_commit='HEAD' rows are left exactly as they were");
            $_GET = array();
        }

        /* Layer E — the real forge remotes. READ-ONLY: resolveRef() runs no write subcommand and
           the registry is opened immutable=1, which reads the committed data of this WAL db while
           creating NO -wal/-shm sidecars and never writing it. */
        private static function layerLive($remArg, $dbArg) {
            echo "E. live forge remotes (read-only)\n";
            $rem = $remArg !== null ? $remArg : self::findUp('config/forge/remotes', true);
            if ($rem === null || !is_dir($rem)) {
                self::ok(false, 'live remotes dir not found — pass --remotes=<dir>', var_export($rem, true));
                return;
            }
            $dirs = array();
            foreach (scandir($rem) as $f) {
                if (substr($f, -4) === '.git' && is_dir($rem . '/' . $f)) { $dirs[] = $f; }
            }
            sort($dirs);
            self::eq(264, count($dirs), 'the forge carries 264 bare remotes');

            // registry head_commits, if the state db is reachable (it is untracked, so a pair_loop
            // worktree will not have one — the distribution below is asserted either way)
            // NB: deliberately NOT CONGRUENCY_SQLITE — layer D defines that constant to point at its
            // own throwaway db, and a constant cannot be undefined. Only --db or the walk-up.
            $dbp = $dbArg !== null ? $dbArg : self::findUp('checkouts/current/state/congruency.sqlite', false);
            $hc = array(); $ro = null; $before = null;
            if ($dbp !== null && is_file($dbp)) {
                $ro = new PDO('sqlite:file:' . $dbp . '?immutable=1');
                $ro->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                foreach ($ro->query("SELECT name, head_commit FROM repos")->fetchAll(PDO::FETCH_ASSOC) as $r) {
                    $hc[$r['name']] = $r['head_commit'];
                }
                self::eq(263, count($hc), 'the registry carries 263 repo rows');
                $before = (int) $ro->query("SELECT COUNT(*) FROM repos WHERE head_commit='HEAD'")->fetchColumn();
                self::eq(183, $before, "183 registry rows store the literal 'HEAD' before the run");
            } else {
                echo "  note: state db not found (it is untracked, so absent from a pair_loop worktree).\n"
                   . "        Tier attribution needs it: re-run with --db=<path to congruency.sqlite>.\n";
            }

            $resolved = 0; $norefs = array(); $tiers = array();
            foreach ($dirs as $d) {
                $name = substr($d, 0, -4);
                $o = self::resolveRef($name, $rem . '/' . $d, isset($hc[$name]) ? $hc[$name] : '');
                if ($o['status'] === 'no_refs') {
                    $norefs[] = $name;
                } else if (preg_match('/^[0-9a-f]{40}$/', (string) $o['sha'])) {
                    $resolved++;
                    $t = $o['tier'];
                    $tiers[$t] = (isset($tiers[$t]) ? $tiers[$t] : 0) + 1;
                }
            }
            self::eq(261, $resolved, '261 of 264 remotes resolve to a 40-hex sha');
            self::eq(3, count($norefs), '3 remotes report no_refs', implode(', ', $norefs));
            arsort($tiers);
            foreach ($tiers as $t => $c) { echo "     tier " . str_pad($t, 24) . " " . $c . "\n"; }
            foreach ($norefs as $n) { echo "     no_refs: " . $n . "\n"; }

            // the acceptance repo from the ticket
            $jw = $rem . '/code__rebuild__jazz_wallet.git';
            if (is_dir($jw)) {
                $o = self::resolveRef('code__rebuild__jazz_wallet', $jw, isset($hc['code__rebuild__jazz_wallet']) ? $hc['code__rebuild__jazz_wallet'] : 'HEAD');
                self::eq('fallback', $o['status'], 'code__rebuild__jazz_wallet resolves by fallback');
                self::eq('refs/heads/main', $o['tier'], 'code__rebuild__jazz_wallet resolves via refs/heads/main');
                $t = self::git($jw, array('ls-tree', '--name-only', $o['sha']));
                self::eq(array('README.md', 'deferred', 'install.json', 'install.py', 'src', 'tests'), $t['out'],
                         'code__rebuild__jazz_wallet tree is readable at the resolved sha');
            }

            // THE REGISTRY IS UNCHANGED — the whole point: this ticket repairs no data
            if ($ro !== null) {
                $ro2 = new PDO('sqlite:file:' . $dbp . '?immutable=1');
                $ro2->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                $after = (int) $ro2->query("SELECT COUNT(*) FROM repos WHERE head_commit='HEAD'")->fetchColumn();
                self::eq(183, $after, "183 registry rows STILL store the literal 'HEAD' after the run");
                self::eq($before, $after, 'the resolver repaired nothing');
                self::ok(!file_exists($dbp . '-wal') && !file_exists($dbp . '-shm'),
                         'reading the live WAL db created no -wal/-shm sidecars');
            }
        }
    }
}

/* CLI selftest hook — mirrors SemanticSearch.php:339. Inert under any web SAPI. */
if (php_sapi_name() === 'cli' && (isset($argv[1]) ? $argv[1] : '') === '__selftest') {
    exit(TreeView::__selftest(array_slice($argv, 2)));
}
?>
