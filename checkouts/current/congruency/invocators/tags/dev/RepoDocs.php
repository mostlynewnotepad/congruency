<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * RepoDocs — per-repo documentation browser (docs/ + README), ingested and
 * associated with each repo (feature c).
 *
 * Invoked as <<<RepoDocs>>> on ?page=repodocs. Data source: the `repo_docs`
 * table (repo, path, kind, body) from 0017_repo_docs.sql — congruency holds the
 * doc bodies (ingested through the doc.record token route), served read-only.
 *   ?page=repodocs                -> index: every repo that has docs (SELECT DISTINCT repo)
 *   ?page=repodocs&repo=X         -> whitelist X against repo_docs; list its docs (path, kind)
 *   ?page=repodocs&repo=X&doc=P   -> read the body; 'md' -> minimal markdown (like DocList), else <pre>
 *
 * SECURITY: repo/path are validated against the DB (never trusted from ?repo=/?doc=);
 * ALL output is htmlspecialchars()'d before it flows back through execute_all_tags,
 * so any literal <<<...>>> in a doc stays inert. Escape-first markdown, same as DocList.
 */
if (!class_exists("RepoDocs")) {
    class RepoDocs implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

        public function get_document() {
            try {
                if (!defined('CONGRUENCY_SQLITE')) { return "<p>RepoDocs: no DB.</p>"; }
                $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
                $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

                $repo = isset($_GET['repo']) ? (string) $_GET['repo'] : '';
                if ($repo === '') { return $this->index($db); }

                // whitelist: ONLY repos that actually have docs in the DB may be browsed
                $rs = $db->prepare("SELECT DISTINCT repo FROM repo_docs WHERE repo=?");
                $rs->execute(array($repo));
                if (!$rs->fetchColumn()) {
                    return "<p><strong>No such documented repo.</strong> <a href='?page=repodocs'>&larr; repos</a></p>";
                }

                $doc = isset($_GET['doc']) ? (string) $_GET['doc'] : '';
                if ($doc !== '') { return $this->view($db, $repo, $doc); }
                return $this->listDocs($db, $repo);
            } catch (\Throwable $e) {
                return "<div class='cy-form-error'>RepoDocs error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        private function index($db) {
            $rows = $db->query("SELECT DISTINCT repo FROM repo_docs ORDER BY repo")->fetchAll(PDO::FETCH_COLUMN);
            if (!$rows) { return "<p>No repo documentation ingested yet.</p>"; }
            $out = "<p>Repos with ingested documentation &mdash; browse each one's <code>docs/</code> and README.</p>\n<ul class='srclist'>\n";
            foreach ($rows as $name) {
                $out .= "<li>&#128218; <a href='?page=repodocs&repo=" . self::esc(urlencode($name)) . "'>" . self::esc($name) . "</a></li>\n";
            }
            return $out . "</ul>\n";
        }

        private function listDocs($db, $repo) {
            $st = $db->prepare("SELECT path, kind FROM repo_docs WHERE repo=? ORDER BY path");
            $st->execute(array($repo));
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);
            $out = "<p><a href='?page=repodocs'>&larr; repos</a> &middot; <strong>" . self::esc($repo) . "</strong></p>\n";
            if (!$rows) { return $out . "<p>(no docs)</p>"; }
            $out .= "<ul class='doclist'>\n";
            foreach ($rows as $r) {
                $out .= "<li>&#128196; <a href='?page=repodocs&repo=" . self::esc(urlencode($repo)) . "&doc=" . self::esc(urlencode($r['path'])) . "'>" . self::esc($r['path']) . "</a> "
                      . "<span style='color:#888;font-size:.85em'>" . self::esc($r['kind']) . "</span></li>\n";
            }
            return $out . "</ul>\n";
        }

        private function view($db, $repo, $path) {
            // read the latest body for this registered repo/path (both from the DB, never trusted raw)
            $st = $db->prepare("SELECT body, kind FROM repo_docs WHERE repo=? AND path=? ORDER BY id DESC LIMIT 1");
            $st->execute(array($repo, $path));
            $row = $st->fetch(PDO::FETCH_ASSOC);
            $back = "<p><a href='?page=repodocs&repo=" . self::esc(urlencode($repo)) . "'>&larr; " . self::esc($repo) . " docs</a> &middot; <strong>" . self::esc($path) . "</strong></p>\n";
            if (!$row) { return $back . "<p>No such doc <code>" . self::esc($path) . "</code>.</p>"; }
            $rendered = ($row['kind'] === 'md')
                ? self::markdown($row['body'])
                : "<pre style='background:#f4f1e8;padding:.6rem;overflow:auto'>" . self::esc($row['body']) . "</pre>";
            return $back . "<div class='doc prose'>\n" . $rendered . "</div>\n";
        }

        /* Minimal markdown subset. ESCAPE FIRST (so HTML and '<<<Tag>>>' examples stay literal), then apply:
           #.. -> h1-h6, blank-line paragraphs, ``` / 4-space indent -> <pre><code>, `x` -> <code>, [t](u) -> <a>. */
        private static function markdown($text) {
            $esc = htmlspecialchars((string) $text, ENT_QUOTES);
            $lines = explode("\n", str_replace("\r", "", $esc));
            $out = ""; $para = array(); $inFence = false; $code = "";
            $flush = function () use (&$para, &$out) {
                if ($para) { $out .= "<p>" . self::inline(implode(" ", $para)) . "</p>\n"; $para = array(); }
            };
            foreach ($lines as $ln) {
                if (preg_match('/^\s*```/', $ln)) {
                    if (!$inFence) { $flush(); $inFence = true; $code = ""; }
                    else { $out .= "<pre><code>" . $code . "</code></pre>\n"; $inFence = false; }
                    continue;
                }
                if ($inFence) { $code .= $ln . "\n"; continue; }
                if (preg_match('/^(#{1,6})\s+(.*)$/', $ln, $m)) {
                    $flush(); $h = strlen($m[1]); $out .= "<h$h>" . self::inline($m[2]) . "</h$h>\n"; continue;
                }
                if (preg_match('/^    (.*)$/', $ln, $m)) {
                    $flush(); $out .= "<pre><code>" . $m[1] . "</code></pre>\n"; continue;
                }
                if (trim($ln) === "") { $flush(); continue; }
                $para[] = $ln;
            }
            $flush();
            if ($inFence) { $out .= "<pre><code>" . $code . "</code></pre>\n"; }
            return $out;
        }

        private static function inline($s) {
            $codes = array();
            $s = preg_replace_callback('/`([^`]+)`/', function ($m) use (&$codes) {
                $k = "\x01" . count($codes) . "\x01";
                $codes[$k] = "<code>" . $m[1] . "</code>";
                return $k;
            }, $s);
            $s = preg_replace('/\*\*(.+?)\*\*/', '<strong>$1</strong>', $s);
            $s = preg_replace('/(^|[^*])\*([^*\s][^*]*)\*/', '$1<em>$2</em>', $s);
            $s = preg_replace('/\[([^\]]+)\]\(([^)\s]+)\)/', '<a href="$2">$1</a>', $s);
            foreach ($codes as $k => $v) { $s = str_replace($k, $v, $s); }
            return $s;
        }
    }
}
?>
