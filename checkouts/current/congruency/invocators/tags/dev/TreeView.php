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
 *   ?page=tree&repo=X[&path=D]  -> git --git-dir=<remote> ls-tree <head> <D>/  (dirs drill in, files -> blob)
 *   ?page=tree&repo=X&blob=P    -> git --git-dir=<remote> show <head>:P  in a line-numbered <pre>
 *
 * SECURITY: the repo name is validated against the DB whitelist (never trusted
 * from ?repo=); EVERY git argument is escapeshellarg()'d; only read-only
 * subcommands (ls-tree, show) are ever run; all output is htmlspecialchars()'d
 * before it flows back through execute_all_tags (so any literal <<<...>>> in
 * source stays inert).
 */
if (!class_exists("TreeView")) {
    class TreeView implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

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
                $commit = (string) $repos[$repo]['head_commit'];

                $blob = isset($_GET['blob']) ? (string) $_GET['blob'] : '';
                if ($blob !== '') { return $this->viewBlob($repo, $gitdir, $commit, $blob); }

                $path = isset($_GET['path']) ? (string) $_GET['path'] : '';
                return $this->viewTree($repo, $gitdir, $commit, $path);
            } catch (\Throwable $e) {
                return "<div class='cy-form-error'>TreeView error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        private function index($repos) {
            if (!$repos) { return "<p>No repos registered.</p>"; }
            $out = "<p>Registered repos &mdash; browse each one's real source tree, read straight from its forge remote.</p>\n<ul class='srclist'>\n";
            foreach ($repos as $name => $r) {
                $out .= "<li>&#128193; <a href='?page=tree&repo=" . self::esc(urlencode($name)) . "'>" . self::esc($name) . "</a> "
                      . "<span style='color:#888;font-size:.85em'>@ " . self::esc(substr((string) $r['head_commit'], 0, 12)) . "</span></li>\n";
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
            // read-only plumbing: git --git-dir=<remote> ls-tree <commit> <path>/   (every arg escapeshellarg'd)
            $spec = ($path === '') ? '' : (rtrim($path, '/') . '/');
            $cmd = "git --git-dir=" . escapeshellarg($gitdir) . " ls-tree " . escapeshellarg($commit);
            if ($spec !== '') { $cmd .= " " . escapeshellarg($spec); }
            $cmd .= " 2>/dev/null";
            $lines = array(); $rc = 0;
            exec($cmd, $lines, $rc);

            $out = $this->crumbs($repo, $path);
            if ($rc !== 0) {
                return $out . "<p>Could not read the tree at <code>" . self::esc($path) . "</code>.</p>";
            }
            $dirs = array(); $files = array();
            foreach ($lines as $ln) {
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
            // read-only plumbing: git --git-dir=<remote> show <commit>:<path>   (the <commit>:<path> ref is one escapeshellarg'd arg)
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
    }
}
?>
