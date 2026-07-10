<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * SemanticSearch — the native vector-store browser: semantic search over the
 * documentation corpus (repo_docs), served on ?page=search.
 *
 * Invoked as <<<SemanticSearch>>>. Reads ?q= (the query) and optional ?repo=
 * (a repo filter). ALWAYS renders a GET search form + a search.stats coverage
 * line. When q is set it embeds "search_query: <q>" via the local Ollama
 * nomic-embed-text endpoint (OpenAI-compatible /v1/embeddings), L2-normalizes
 * it, pulls the stored chunk vectors from `embeddings` (0019_vector_store.sql)
 * and cosine-ranks them through the pure static rank() method, rendering the
 * top 8 hits as links into ?page=repodocs.
 *
 * SECURITY: ALL data-derived output is htmlspecialchars()'d before it flows
 * back through execute_all_tags, so a doc chunk containing a literal <<<Tag>>>
 * or <script> stays inert (escape-first, same invariant as RepoDocs). The
 * embedder is best-effort: any curl/parse failure degrades to an "offline"
 * notice and never crashes the page. rank()/cosine() are pure + static so the
 * shadow can prove the ranking math with no embedding service (__rank_selftest).
 */
if (!interface_exists('Tag_Interface')) { interface Tag_Interface { public function get_document(); } }
if (!class_exists("SemanticSearch")) {
    class SemanticSearch implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

        public function get_document() {
            try {
                $q = isset($_GET['q']) ? (string) $_GET['q'] : '';
                $repo = isset($_GET['repo']) ? (string) $_GET['repo'] : '';
                $out = $this->form($q, $repo);
                if (!defined('CONGRUENCY_SQLITE')) { return $out . "<p>SemanticSearch: no DB.</p>"; }
                $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
                $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                $out .= $this->stats($db);
                if ($q === '') { return $out; }

                $qv = self::embed($q);
                if ($qv === null) {
                    return $out . "<p class='cy-form-error'>embedding service offline (start Ollama + <code>ollama pull nomic-embed-text</code>)</p>";
                }

                if ($repo !== '') {
                    $st = $db->prepare("SELECT repo, path, section, text, vector FROM embeddings WHERE repo=?");
                    $st->execute(array($repo));
                    $raw = $st->fetchAll(PDO::FETCH_ASSOC);
                } else {
                    $raw = $db->query("SELECT repo, path, section, text, vector FROM embeddings")->fetchAll(PDO::FETCH_ASSOC);
                }
                $rows = array();
                foreach ($raw as $r) {
                    $vec = json_decode((string) $r['vector'], true);
                    if (!is_array($vec)) { continue; }
                    $rows[] = array('repo' => $r['repo'], 'path' => $r['path'], 'section' => $r['section'],
                                    'text' => $r['text'], 'vector' => $vec);
                }
                if (!$rows) {
                    return $out . "<p>No embeddings stored yet &mdash; ingest chunks through the <code>search.record</code> route.</p>";
                }

                $hits = self::rank($qv, $rows, 8);
                $out .= "<ol class='srclist'>\n";
                foreach ($hits as $h) {
                    $snippet = substr((string) $h['text'], 0, 160);
                    $out .= "<li><code>" . self::esc(sprintf('%.3f', $h['score'])) . "</code> "
                          . "<a href='?page=repodocs&repo=" . self::esc(urlencode((string) $h['repo']))
                          . "&doc=" . self::esc(urlencode((string) $h['path'])) . "'>"
                          . self::esc($h['repo']) . " / " . self::esc($h['path']) . "</a> "
                          . "<span style='color:#888'>" . self::esc($h['section']) . "</span>"
                          . "<br><span>" . self::esc($snippet) . "</span></li>\n";
                }
                return $out . "</ol>\n";
            } catch (\Throwable $e) {
                return "<div class='cy-form-error'>SemanticSearch error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        private function form($q, $repo) {
            $out = "<form method='get' action=''>\n";
            $out .= "<input type='hidden' name='page' value='search'>\n";
            if ($repo !== '') { $out .= "<input type='hidden' name='repo' value='" . self::esc($repo) . "'>\n"; }
            $out .= "<input type='text' name='q' value='" . self::esc($q) . "' size='48' placeholder='search the docs by meaning...'>\n";
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

/* CLI self-test hook: the vector-search shadow drives rank() from php with NO embedding service.
   Reads JSON {q:[...],rows:[...],k:int} from stdin, echoes json_encode(self::rank(...)). */
if (php_sapi_name() === 'cli' && (isset($argv[1]) ? $argv[1] : '') === '__rank_selftest') {
    $in = json_decode(file_get_contents('php://stdin'), true);
    $q = (isset($in['q']) && is_array($in['q'])) ? $in['q'] : array();
    $rows = (isset($in['rows']) && is_array($in['rows'])) ? $in['rows'] : array();
    $k = isset($in['k']) ? (int) $in['k'] : 0;
    echo json_encode(SemanticSearch::rank($q, $rows, $k));
    exit;
}
?>
