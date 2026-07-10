<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * SemanticSearch — multi-axis search over the documentation corpus (repo_docs +
 * the vector store), served on ?page=search.
 *
 * Invoked as <<<SemanticSearch>>>. Reads ?q= (query), ?axis= (meaning|keyword|
 * both; default meaning), ?repo= (repo facet) and ?kind= (type facet). ALWAYS
 * renders a GET form (text box + axis selector + repo/kind selects, selection
 * preserved) and a search.stats coverage line.
 *   axis=meaning  embeds "search_query: <q>" via the local Ollama nomic-embed-
 *                 text endpoint, L2-normalizes it and cosine-ranks the stored
 *                 chunk vectors (embeddings) through the pure static rank().
 *   axis=keyword  runs a robust LIKE full-text query over repo_docs (repo/kind
 *                 scoped), ranked by a simple term-frequency relevance score.
 *   axis=both     runs BOTH and merges via the pure static merge(): deduped by
 *                 (repo,path), scores combined so a doc found by BOTH axes
 *                 outranks one found by only one.
 *
 * SECURITY: ALL data-derived output is htmlspecialchars()'d before it flows
 * back through execute_all_tags, so a doc body containing a literal <<<Tag>>>
 * or <script> stays inert (escape-first). The embedder is best-effort: any
 * curl/parse failure degrades to an "offline" notice and never crashes the
 * page. rank()/cosine()/keywordScore()/merge() are pure + static so the shadow
 * can prove the ranking + merge math with no services (__rank_selftest /
 * __merge_selftest).
 */
if (!interface_exists('Tag_Interface')) { interface Tag_Interface { public function get_document(); } }
if (!class_exists("SemanticSearch")) {
    class SemanticSearch implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

        public function get_document() {
            try {
                // defense-in-depth: nudge a small working limit up a little; the REAL fix is
                // the streaming, bounded-memory semanticHits below -- do not rely on this bump.
                $mlRaw = (string) ini_get('memory_limit');
                $mlMb  = (int) $mlRaw;
                if (strtoupper(substr($mlRaw, -1)) === 'G') { $mlMb *= 1024; }
                if ($mlMb > 0 && $mlMb < 256) { @ini_set('memory_limit', '256M'); }
                $q    = isset($_GET['q'])    ? (string) $_GET['q']    : '';
                $axis = isset($_GET['axis']) ? (string) $_GET['axis'] : 'meaning';
                if (!in_array($axis, array('meaning', 'keyword', 'both'), true)) { $axis = 'meaning'; }
                $repo = isset($_GET['repo']) ? (string) $_GET['repo'] : '';
                $kind = isset($_GET['kind']) ? (string) $_GET['kind'] : '';

                if (!defined('CONGRUENCY_SQLITE')) {
                    return $this->form(array(), $q, $axis, $repo, $kind) . "<p>SemanticSearch: no DB.</p>";
                }
                $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
                $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

                $out  = $this->form(self::repos($db), $q, $axis, $repo, $kind);
                $out .= $this->stats($db);
                if ($q === '') { return $out; }

                $semantic = array();
                $keyword  = array();
                $notes    = array();

                if ($axis === 'meaning' || $axis === 'both') {
                    $qv = self::embed($q);
                    if ($qv === null) {
                        $notes[] = "embedding service offline (start Ollama + <code>ollama pull nomic-embed-text</code>)";
                    } else {
                        $semantic = self::semanticHits($db, $qv, $repo);
                    }
                }
                if ($axis === 'keyword' || $axis === 'both') {
                    $keyword = self::keywordHits($db, $q, $repo, $kind);
                }

                if ($axis === 'meaning')     { $hits = $semantic; }
                elseif ($axis === 'keyword') { $hits = $keyword; }
                else                         { $hits = self::merge($semantic, $keyword, 12); }

                foreach ($notes as $n) { $out .= "<p class='cy-form-error'>" . $n . "</p>\n"; }
                if (!$hits) {
                    return $out . "<p>No matches &mdash; try another axis or a broader query.</p>\n";
                }
                $out .= "<ol class='srclist'>\n";
                foreach ($hits as $h) {
                    $snippet = substr((string) (isset($h['text']) ? $h['text'] : ''), 0, 240);
                    $ax = isset($h['axis']) ? $h['axis'] : $axis;
                    $out .= "<li><span class='cy-axis'>[" . self::esc($ax) . "]</span> "
                          . "<code>" . self::esc(sprintf('%.3f', isset($h['score']) ? $h['score'] : 0)) . "</code> "
                          . "<a href='?page=repodocs&repo=" . self::esc(urlencode((string) $h['repo']))
                          . "&doc=" . self::esc(urlencode((string) $h['path'])) . "'>"
                          . self::esc($h['repo']) . " / " . self::esc($h['path']) . "</a> "
                          . "<span style='color:#888'>" . self::esc(isset($h['section']) ? $h['section'] : '') . "</span>"
                          . "<br><span>" . self::esc($snippet) . "</span></li>\n";
                }
                return $out . "</ol>\n";
            } catch (\Throwable $e) {
                return "<div class='cy-form-error'>SemanticSearch error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        private static function repos($db) {
            try {
                $rows = $db->query("SELECT DISTINCT repo FROM repo_docs ORDER BY repo")->fetchAll(PDO::FETCH_COLUMN);
                return is_array($rows) ? $rows : array();
            } catch (\Throwable $e) { return array(); }
        }

        private function form($repos, $q, $axis, $repo, $kind) {
            $out  = "<form method='get' action=''>\n";
            $out .= "<input type='hidden' name='page' value='search'>\n";
            $out .= "<input type='text' name='q' value='" . self::esc($q) . "' size='40' placeholder='search the docs...'>\n";
            $out .= "<select name='axis'>\n";
            foreach (array('meaning', 'keyword', 'both') as $v) {
                $sel = ($axis === $v) ? " selected" : "";
                $out .= "<option value='" . self::esc($v) . "'" . $sel . ">" . self::esc($v) . "</option>\n";
            }
            $out .= "</select>\n";
            $out .= "<select name='repo'>\n<option value=''>(all repos)</option>\n";
            foreach ($repos as $r) {
                $sel = ($repo === (string) $r) ? " selected" : "";
                $out .= "<option value='" . self::esc($r) . "'" . $sel . ">" . self::esc($r) . "</option>\n";
            }
            $out .= "</select>\n";
            $out .= "<select name='kind'>\n";
            foreach (array('' => '(any type)', 'md' => 'md', 'text' => 'text') as $v => $lab) {
                $sel = ($kind === (string) $v) ? " selected" : "";
                $out .= "<option value='" . self::esc($v) . "'" . $sel . ">" . self::esc($lab) . "</option>\n";
            }
            $out .= "</select>\n";
            $out .= "<button type='submit'>Search</button>\n</form>\n";
            return $out;
        }

        private function stats($db) {
            try {
                $rows = $db->query("SELECT model, COUNT(*) AS chunks, COUNT(DISTINCT repo||'/'||path) AS docs FROM embeddings GROUP BY model")->fetchAll(PDO::FETCH_ASSOC);
            } catch (\Throwable $e) { return ""; }
            if (!$rows) { return "<p style='color:#888'>Vector store empty &mdash; no embeddings ingested yet.</p>\n"; }
            $parts = array();
            foreach ($rows as $r) {
                $parts[] = self::esc($r['model']) . ": " . self::esc($r['chunks']) . " chunks / " . self::esc($r['docs']) . " docs";
            }
            return "<p style='color:#888'>Vector store &mdash; " . implode("; ", $parts) . "</p>\n";
        }

        /* semantic axis: STREAM the stored chunk vectors (repo-scoped when set) one row at a
           time, cosine-scoring each against $qv and keeping only a bounded top-12 -- O(k)
           memory, the full set is never materialized. Each hit tagged axis=meaning; each
           vector is decoded, scored, then dropped. */
        private static function semanticHits($db, array $qv, $repo) {
            if ($repo !== '') {
                $st = $db->prepare("SELECT repo, path, section, text, vector FROM embeddings WHERE repo=?");
                $st->execute(array($repo));
            } else {
                $st = $db->query("SELECT repo, path, section, text, vector FROM embeddings");
            }
            $k = 12;
            $top = array();
            while (($r = $st->fetch(PDO::FETCH_ASSOC)) !== false) {
                $vec = json_decode((string) $r['vector'], true);
                if (!is_array($vec)) { continue; }
                $score = self::cosine($qv, $vec);
                unset($vec);
                $n = count($top);
                if ($n >= $k && $score <= $top[$n - 1]['score']) { continue; }
                $hit = array('repo' => $r['repo'], 'path' => $r['path'], 'section' => $r['section'],
                             'text' => $r['text'], 'score' => $score, 'axis' => 'meaning');
                $i = $n;
                while ($i > 0 && $top[$i - 1]['score'] < $score) { $i--; }
                array_splice($top, $i, 0, array($hit));
                if (count($top) > $k) { array_pop($top); }
            }
            return $top;
        }

        /* keyword axis: robust LIKE full-text over repo_docs (repo/kind scoped), ranked by a simple
           term-frequency + earliness relevance score. Each hit tagged axis=keyword. */
        private static function keywordHits($db, $q, $repo, $kind) {
            if ($q === '') { return array(); }
            $sql = "SELECT repo, path, kind, body FROM repo_docs WHERE body LIKE :like";
            $args = array(':like' => '%' . $q . '%');
            if ($repo !== '') { $sql .= " AND repo=:repo"; $args[':repo'] = $repo; }
            if ($kind !== '') { $sql .= " AND kind=:kind"; $args[':kind'] = $kind; }
            $sql .= " ORDER BY repo, path LIMIT 40";
            $st = $db->prepare($sql);
            $st->execute($args);
            $raw = $st->fetchAll(PDO::FETCH_ASSOC);
            $hits = array();
            foreach ($raw as $r) {
                $body = (string) $r['body'];
                $hits[] = array('repo' => $r['repo'], 'path' => $r['path'], 'section' => $r['kind'],
                                'text' => substr($body, 0, 240), 'score' => self::keywordScore($body, $q),
                                'axis' => 'keyword');
            }
            usort($hits, function ($a, $b) {
                if ($a['score'] == $b['score']) { return 0; }
                return ($a['score'] < $b['score']) ? 1 : -1;
            });
            return $hits;
        }

        /* PURE keyword relevance: term frequency (dominant) + earliness of the first match, both from
           a case-folded body. Positive when the term occurs; 0 otherwise. No DB, no network. */
        public static function keywordScore($body, $q): float {
            $bl = strtolower((string) $body);
            $ql = strtolower((string) $q);
            if ($ql === '') { return 0.0; }
            $count = substr_count($bl, $ql);
            if ($count === 0) { return 0.0; }
            $pos = strpos($bl, $ql);
            $len = strlen($bl);
            $earliness = ($len > 0) ? (1.0 - ($pos / $len)) : 1.0;
            return (float) $count + $earliness;
        }

        /* PURE merge of the two axes: dedupe by (repo,path), COMBINE scores (semantic + keyword), and
           order so a doc found by BOTH axes always outranks one found by only one, then by combined
           score DESC. Returns the top-$k. No DB, no network — the shadow drives this (__merge_selftest). */
        public static function merge(array $semanticHits, array $keywordHits, int $k): array {
            $acc = array();
            $ingest = function ($hit, $axis) use (&$acc) {
                $repo = isset($hit['repo']) ? (string) $hit['repo'] : '';
                $path = isset($hit['path']) ? (string) $hit['path'] : '';
                $score = isset($hit['score']) ? (float) $hit['score'] : 0.0;
                $key = $repo . "\0" . $path;
                if (!isset($acc[$key])) {
                    $acc[$key] = array('repo' => $repo, 'path' => $path, 'section' => '', 'text' => '',
                                       'semantic' => 0.0, 'keyword' => 0.0,
                                       'from_semantic' => false, 'from_keyword' => false);
                }
                if (isset($hit['section']) && $acc[$key]['section'] === '') { $acc[$key]['section'] = (string) $hit['section']; }
                if (isset($hit['text']) && $acc[$key]['text'] === '') { $acc[$key]['text'] = (string) $hit['text']; }
                if ($score > $acc[$key][$axis]) { $acc[$key][$axis] = $score; }
                $acc[$key]['from_' . $axis] = true;
            };
            foreach ($semanticHits as $h) { $ingest($h, 'semantic'); }
            foreach ($keywordHits as $h) { $ingest($h, 'keyword'); }

            $merged = array();
            foreach ($acc as $e) {
                $both = ($e['from_semantic'] && $e['from_keyword']);
                $e['both']  = $both;
                $e['axis']  = $both ? 'both' : ($e['from_semantic'] ? 'meaning' : 'keyword');
                $e['score'] = (float) $e['semantic'] + (float) $e['keyword'];
                $merged[] = $e;
            }
            usort($merged, function ($a, $b) {
                if ($a['both'] !== $b['both']) { return $a['both'] ? -1 : 1; }
                if ($a['score'] == $b['score']) { return 0; }
                return ($a['score'] < $b['score']) ? 1 : -1;
            });
            if ($k >= 0 && count($merged) > $k) { $merged = array_slice($merged, 0, $k); }
            return $merged;
        }

        /* Embed the query via Ollama's OpenAI-compatible endpoint. Returns an L2-normalized float
           array, or null on ANY curl/parse failure (the page degrades gracefully, never crashes). */
        private static function embed($q) {
            $payload = json_encode(array('model' => 'nomic-embed-text', 'input' => 'search_query: ' . $q));
            $body = false;
            if (function_exists('curl_init')) {
                $ch = curl_init('http://localhost:11434/v1/embeddings');
                curl_setopt($ch, CURLOPT_POST, true);
                curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);
                curl_setopt($ch, CURLOPT_HTTPHEADER, array('Content-Type: application/json'));
                curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
                curl_setopt($ch, CURLOPT_TIMEOUT, 10);
                $body = curl_exec($ch);
                curl_close($ch);
            }
            if ($body === false || $body === null) {
                $ctx = stream_context_create(array('http' => array(
                    'method' => 'POST',
                    'header' => "Content-Type: application/json\r\n",
                    'content' => $payload,
                    'timeout' => 10,
                )));
                $body = @file_get_contents('http://localhost:11434/v1/embeddings', false, $ctx);
            }
            if ($body === false || $body === null) { return null; }
            $data = json_decode((string) $body, true);
            if (!is_array($data) || !isset($data['data'][0]['embedding']) || !is_array($data['data'][0]['embedding'])) {
                return null;
            }
            $vec = array();
            foreach ($data['data'][0]['embedding'] as $x) { $vec[] = (float) $x; }
            return self::l2normalize($vec);
        }

        private static function l2normalize(array $v) {
            $n = 0.0;
            foreach ($v as $x) { $n += ((float) $x) * ((float) $x); }
            $n = sqrt($n);
            if ($n == 0.0) { return $v; }
            $out = array();
            foreach ($v as $x) { $out[] = ((float) $x) / $n; }
            return $out;
        }

        /* PURE ranking: return the top-$k $rows by cosine($queryVec, row.vector) DESC, each with an
           added 'score' key. No DB, no network — the shadow drives this directly (nearest first). */
        public static function rank(array $queryVec, array $rows, int $k): array {
            $scored = array();
            foreach ($rows as $row) {
                $vec = (isset($row['vector']) && is_array($row['vector'])) ? $row['vector'] : array();
                $row['score'] = self::cosine($queryVec, $vec);
                $scored[] = $row;
            }
            usort($scored, function ($a, $b) {
                if ($a['score'] == $b['score']) { return 0; }
                return ($a['score'] < $b['score']) ? 1 : -1;
            });
            if ($k >= 0 && count($scored) > $k) { $scored = array_slice($scored, 0, $k); }
            return $scored;
        }

        /* cosine = dot(a,b) / (|a| |b|). Both may already be L2-normed; normalize defensively. */
        public static function cosine(array $a, array $b): float {
            $n = min(count($a), count($b));
            $dot = 0.0;
            for ($i = 0; $i < $n; $i++) { $dot += ((float) $a[$i]) * ((float) $b[$i]); }
            $na = 0.0;
            foreach ($a as $x) { $na += ((float) $x) * ((float) $x); }
            $nb = 0.0;
            foreach ($b as $y) { $nb += ((float) $y) * ((float) $y); }
            $na = sqrt($na); $nb = sqrt($nb);
            if ($na == 0.0 || $nb == 0.0) { return 0.0; }
            return $dot / ($na * $nb);
        }
    }
}

/* CLI self-test hooks: the shadows drive rank()/merge() from php with NO embedding service. */
if (php_sapi_name() === 'cli' && (isset($argv[1]) ? $argv[1] : '') === '__rank_selftest') {
    $in = json_decode(file_get_contents('php://stdin'), true);
    $q = (isset($in['q']) && is_array($in['q'])) ? $in['q'] : array();
    $rows = (isset($in['rows']) && is_array($in['rows'])) ? $in['rows'] : array();
    $k = isset($in['k']) ? (int) $in['k'] : 0;
    echo json_encode(SemanticSearch::rank($q, $rows, $k));
    exit;
}
if (php_sapi_name() === 'cli' && (isset($argv[1]) ? $argv[1] : '') === '__merge_selftest') {
    $in = json_decode(file_get_contents('php://stdin'), true);
    $sem = (isset($in['semantic']) && is_array($in['semantic'])) ? $in['semantic'] : array();
    $kw  = (isset($in['keyword']) && is_array($in['keyword'])) ? $in['keyword'] : array();
    $k = isset($in['k']) ? (int) $in['k'] : 0;
    echo json_encode(SemanticSearch::merge($sem, $kw, $k));
    exit;
}
if (php_sapi_name() === 'cli' && (isset($argv[1]) ? $argv[1] : '') === '__semantic_selftest') {
    $in = json_decode(file_get_contents('php://stdin'), true);
    $qv = (isset($in['qv']) && is_array($in['qv'])) ? $in['qv'] : array();
    $repo = isset($in['repo']) ? (string) $in['repo'] : '';
    $dbPath = isset($in['db']) ? (string) $in['db'] : '';
    $db = new PDO('sqlite:' . $dbPath);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $ref = new ReflectionMethod('SemanticSearch', 'semanticHits');
    $ref->setAccessible(true);
    echo json_encode($ref->invoke(null, $db, $qv, $repo));
    exit;
}

?>
