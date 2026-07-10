<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * OmniExplorer — congruency reflects the omni-git INDEX (~/bin/config/forge/omni_index.db), a
 * SEPARATE sqlite database from CONGRUENCY_SQLITE, built by jazz-forge's omni_index.py. It answers
 * "each file maps to one or more repositories at different times": occ holds one row per (blob,path)
 * OCCURRENCE across every snapshot, so a single path fans out to many (repo,ts) pairs.
 *
 * Invoked as <<<OmniExplorer>>> on ?page=omni. Data source: omni_index.db, resolved from
 * getenv('OMNI_INDEX_DB') ?: $HOME/bin/config/forge/omni_index.db, opened through a SECOND PDO
 * handle with `PRAGMA query_only=1` so the reflection can NEVER mutate the index. Absent/unreadable
 * -> the page degrades gracefully ("omni index not found at <path>"), it never crashes the page.
 *   ?page=omni                 -> most widely-copied files + repos
 *   ?page=omni&path=<file>     -> every repo/snapshot that path appears in (exact; LIKE fallback)
 *   ?page=omni&repo=<repo>     -> files in that repo snapshot
 *   ?page=omni&sha=<blob>      -> every place that exact blob lives (rename/copy view)
 *
 * SECURITY: EVERY value read from omni_index.db (paths, repos, ts, sha) is htmlspecialchars()'d
 * before it flows back through execute_all_tags, so a stored <<<Tag>>> / <script> in a path stays
 * inert (escape-first). Facets are bound, never interpolated. The index is opened read-only.
 */
if (!class_exists("OmniExplorer")) {
    class OmniExplorer implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

        private static function omni_path() {
            $p = getenv('OMNI_INDEX_DB');
            if ($p !== false && $p !== '') { return $p; }
            return getenv('HOME') . '/bin/config/forge/omni_index.db';
        }

        public function get_document() {
            $form = $this->lookup_form();
            $path = self::omni_path();
            if (!is_file($path) || !is_readable($path)) {
                return $form . "<p class='cy-form-error'>omni index not found at <code>" . self::esc($path) . "</code></p>";
            }
            try {
                $odb = new PDO('sqlite:' . $path);
                $odb->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                $odb->exec('PRAGMA query_only=1');   // read-only: the reflection can never mutate the index
            } catch (\Throwable $e) {
                return $form . "<p class='cy-form-error'>omni index not readable at <code>" . self::esc($path) . "</code></p>";
            }
            try {
                return $form . $this->summary($odb) . $this->body($odb);
            } catch (\Throwable $e) {
                return $form . "<div class='cy-form-error'>OmniExplorer error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        private function lookup_form() {
            $cur = isset($_GET['path']) ? (string) $_GET['path'] : '';
            return "<form method='get' class='omni-lookup' style='margin:.5rem 0'>"
                 . "<input type='hidden' name='page' value='omni'>"
                 . "<input type='text' name='path' value='" . self::esc($cur) . "' placeholder='src/app.py' size='40'>"
                 . " <button type='submit'>look up file</button>"
                 . "</form>\n";
        }

        private static function scalar($odb, $sql) {
            $v = $odb->query($sql)->fetchColumn();
            return ($v === false || $v === null) ? 0 : $v;
        }

        private function summary($odb) {
            $occ   = self::scalar($odb, "SELECT COUNT(*) FROM occ");
            $paths = self::scalar($odb, "SELECT COUNT(DISTINCT path) FROM occ");
            $repos = self::scalar($odb, "SELECT COUNT(DISTINCT repo) FROM occ");
            $blobs = self::scalar($odb, "SELECT COUNT(*) FROM blob");
            return "<p class='omni-summary'><strong>" . self::esc($occ) . "</strong> occurrences &middot; <strong>"
                 . self::esc($paths) . "</strong> distinct paths &middot; <strong>" . self::esc($repos)
                 . "</strong> repos &middot; <strong>" . self::esc($blobs) . "</strong> blobs</p>\n";
        }

        private function body($odb) {
            if (isset($_GET['path']) && $_GET['path'] !== '') { return $this->by_path($odb, (string) $_GET['path']); }
            if (isset($_GET['repo']) && $_GET['repo'] !== '') { return $this->by_repo($odb, (string) $_GET['repo']); }
            if (isset($_GET['sha'])  && $_GET['sha']  !== '') { return $this->by_sha($odb,  (string) $_GET['sha']); }
            return $this->overview($odb);
        }

        private static function th($cols) {
            $out = "<tr>";
            foreach ($cols as $c) { $out .= "<th style='text-align:left'>" . self::esc($c) . "</th>"; }
            return $out . "</tr>\n";
        }

        // ?path=<file> — every repo/snapshot the file appears in: file -> repos@times.
        private function by_path($odb, $p) {
            $st = $odb->prepare("SELECT repo, ts, substr(sha,1,10) AS sha, size FROM occ WHERE path=:path ORDER BY ts DESC, repo LIMIT 200");
            $st->execute(array(':path' => $p));
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);
            if ($rows) {
                $out  = "<h2>" . self::esc($p) . " appears in " . count($rows) . " repos/snapshots</h2>\n";
                $out .= "<table class='omni-occ' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
                $out .= self::th(array('repo', 'ts', 'sha', 'size'));
                foreach ($rows as $r) {
                    $out .= "<tr>"
                          . "<td><a href='?page=omni&repo=" . self::esc(urlencode($r['repo'])) . "'>" . self::esc($r['repo']) . "</a></td>"
                          . "<td>" . self::esc($r['ts']) . "</td>"
                          . "<td><code>" . self::esc($r['sha']) . "</code></td>"
                          . "<td>" . self::esc($r['size']) . "</td>"
                          . "</tr>\n";
                }
                return $out . "</table>\n";
            }
            // no exact hit -> candidate paths (LIKE), each links back to an exact lookup
            $st = $odb->prepare("SELECT DISTINCT path FROM occ WHERE path LIKE :like ORDER BY path LIMIT 60");
            $st->execute(array(':like' => '%' . $p . '%'));
            $cands = $st->fetchAll(PDO::FETCH_COLUMN);
            $out = "<h2>No exact match for <code>" . self::esc($p) . "</code></h2>\n";
            if (!$cands) { return $out . "<p>(no candidate paths)</p>\n"; }
            $out .= "<p>candidate paths:</p>\n<ul class='srclist'>\n";
            foreach ($cands as $c) {
                $out .= "<li><a href='?page=omni&path=" . self::esc(urlencode($c)) . "'>" . self::esc($c) . "</a></li>\n";
            }
            return $out . "</ul>\n";
        }

        // ?repo=<repo> — the files in one repo snapshot.
        private function by_repo($odb, $repo) {
            $st = $odb->prepare("SELECT DISTINCT path, substr(sha,1,10) AS sha, size FROM occ WHERE repo=:repo ORDER BY path LIMIT 200");
            $st->execute(array(':repo' => $repo));
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);
            $out = "<h2>files in <code>" . self::esc($repo) . "</code> <a href='?page=omni'>&times;</a></h2>\n";
            if (!$rows) { return $out . "<p>(no files)</p>\n"; }
            $out .= "<table class='omni-repo' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= self::th(array('path', 'sha', 'size'));
            foreach ($rows as $r) {
                $out .= "<tr>"
                      . "<td><a href='?page=omni&path=" . self::esc(urlencode($r['path'])) . "'>" . self::esc($r['path']) . "</a></td>"
                      . "<td><code>" . self::esc($r['sha']) . "</code></td>"
                      . "<td>" . self::esc($r['size']) . "</td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }

        // ?sha=<blob> — every place that exact blob lives (rename/copy view).
        private function by_sha($odb, $sha) {
            $st = $odb->prepare("SELECT DISTINCT path, repo, ts FROM occ WHERE sha=:sha ORDER BY repo LIMIT 200");
            $st->execute(array(':sha' => $sha));
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);
            $out = "<h2>blob <code>" . self::esc($sha) . "</code> <a href='?page=omni'>&times;</a></h2>\n";
            if (!$rows) { return $out . "<p>(no occurrences)</p>\n"; }
            $out .= "<table class='omni-sha' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= self::th(array('path', 'repo', 'ts'));
            foreach ($rows as $r) {
                $out .= "<tr>"
                      . "<td><a href='?page=omni&path=" . self::esc(urlencode($r['path'])) . "'>" . self::esc($r['path']) . "</a></td>"
                      . "<td><a href='?page=omni&repo=" . self::esc(urlencode($r['repo'])) . "'>" . self::esc($r['repo']) . "</a></td>"
                      . "<td>" . self::esc($r['ts']) . "</td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }

        // default — most widely-copied files + the repo list.
        private function overview($odb) {
            $wide = $odb->query("SELECT path, COUNT(DISTINCT repo) AS nr FROM occ GROUP BY path ORDER BY nr DESC LIMIT 30")->fetchAll(PDO::FETCH_ASSOC);
            $out = "<h2>Most widely-copied files</h2>\n";
            if (!$wide) {
                $out .= "<p>(empty index)</p>\n";
            } else {
                $out .= "<table class='omni-wide' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
                $out .= self::th(array('path', 'repos'));
                foreach ($wide as $r) {
                    $out .= "<tr>"
                          . "<td><a href='?page=omni&path=" . self::esc(urlencode($r['path'])) . "'>" . self::esc($r['path']) . "</a></td>"
                          . "<td>" . self::esc($r['nr']) . "</td>"
                          . "</tr>\n";
                }
                $out .= "</table>\n";
            }
            $repos = $odb->query("SELECT DISTINCT repo FROM occ ORDER BY repo LIMIT 60")->fetchAll(PDO::FETCH_COLUMN);
            $out .= "<h2>Repos</h2>\n";
            if (!$repos) { return $out . "<p>(no repos)</p>\n"; }
            $out .= "<ul class='srclist'>\n";
            foreach ($repos as $rp) {
                $out .= "<li><a href='?page=omni&repo=" . self::esc(urlencode($rp)) . "'>" . self::esc($rp) . "</a></li>\n";
            }
            return $out . "</ul>\n";
        }
    }
}
?>
