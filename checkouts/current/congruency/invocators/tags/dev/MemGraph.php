<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * MemGraph — congruency reflects the RFC-0031 memory-and-spec graph
 * (~/bin/config/forge/mem_graph.db), a SEPARATE sqlite database from CONGRUENCY_SQLITE, built by
 * jazz-forge's forge/mem_graph.py. It is the property graph that unifies the omni corpus, spec-drift,
 * the memory timeline, the shadow-forge, and semantic near-duplicates:
 *   node(id, kind, label, attrs, ts)      -- kinds: file/path/blob/snap/mem/event/shadow
 *   edge(src, dst, kind, weight, ts, attrs) -- kinds: contains/has_version/instance_of/succeeds/then/
 *                                              drifts/shadow_of/evolved_from/similar_to
 *   drift(path, ...)                       -- the lifted spec-drift metric (pingpong_raw + wobble/spread)
 *   meta(built_at, n_nodes, n_edges, sources) -- freshness stamp
 *
 * Invoked as <<<MemGraph>>> on ?page=memgraph. Data source: mem_graph.db, resolved from
 * getenv('MEM_GRAPH_DB') ?: $HOME/bin/config/forge/mem_graph.db, opened through a SECOND PDO handle
 * with `PRAGMA query_only=1` so the reflection can NEVER mutate the graph. Absent/unreadable -> the
 * page degrades gracefully ("memory graph not built yet at <path>"), it never crashes the page.
 *   ?page=memgraph            -> summary + high-drift + near-duplicates + most-connected nodes
 *   ?page=memgraph&node=<id>  -> that node's own row + its outgoing/incoming edges (bound :node)
 *
 * SECURITY: EVERY value read from mem_graph.db (ids, labels, attrs, paths, edge kinds, weights) is
 * htmlspecialchars()'d before it flows back through execute_all_tags, so a stored <<<Tag>>> /
 * <script> in a node id or attrs stays inert (escape-first). The node facet is bound, never
 * interpolated. The graph is opened read-only. MG-9: pingpong_raw is labelled raw / branch-interleaved,
 * not settled truth.
 */
if (!class_exists("MemGraph")) {
    class MemGraph implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

        private static function mem_path() {
            $p = getenv('MEM_GRAPH_DB');
            if ($p !== false && $p !== '') { return $p; }
            return getenv('HOME') . '/bin/config/forge/mem_graph.db';
        }

        public function get_document() {
            $form = $this->lookup_form();
            $path = self::mem_path();
            if (!is_file($path) || !is_readable($path)) {
                return $form . "<p class='cy-form-error'>memory graph not built yet at <code>" . self::esc($path) . "</code> &mdash; run forge/mem_graph.py</p>";
            }
            try {
                $mdb = new PDO('sqlite:' . $path);
                $mdb->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                $mdb->exec('PRAGMA query_only=1');   // read-only: the reflection can never mutate the graph
            } catch (\Throwable $e) {
                return $form . "<p class='cy-form-error'>memory graph not readable at <code>" . self::esc($path) . "</code></p>";
            }
            try {
                return $form . $this->summary($mdb) . $this->body($mdb);
            } catch (\Throwable $e) {
                return $form . "<div class='cy-form-error'>MemGraph error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        private function lookup_form() {
            $cur = isset($_GET['node']) ? (string) $_GET['node'] : '';
            return "<form method='get' class='memgraph-lookup' style='margin:.5rem 0'>"
                 . "<input type='hidden' name='page' value='memgraph'>"
                 . "<input type='text' name='node' value='" . self::esc($cur) . "' placeholder='node id' size='40'>"
                 . " <button type='submit'>look up node</button>"
                 . "</form>\n";
        }

        private static function scalar($mdb, $sql) {
            $v = $mdb->query($sql)->fetchColumn();
            return ($v === false || $v === null) ? 0 : $v;
        }

        private static function th($cols) {
            $out = "<tr>";
            foreach ($cols as $c) { $out .= "<th style='text-align:left'>" . self::esc($c) . "</th>"; }
            return $out . "</tr>\n";
        }

        private function summary($mdb) {
            $nodes = self::scalar($mdb, "SELECT COUNT(*) FROM node");
            $edges = self::scalar($mdb, "SELECT COUNT(*) FROM edge");
            $out = "<h2>Summary</h2>\n<ul class='srclist'>\n";
            try {
                $m = $mdb->query("SELECT built_at, n_nodes, n_edges FROM meta LIMIT 1")->fetch(PDO::FETCH_ASSOC);
            } catch (\Throwable $e) { $m = false; }
            if ($m) {
                $out .= "<li>built <strong>" . self::esc($m['built_at']) . "</strong> &middot; meta says <strong>"
                      . self::esc($m['n_nodes']) . "</strong> nodes / <strong>" . self::esc($m['n_edges']) . "</strong> edges</li>\n";
            }
            $out .= "<li><strong>" . self::esc($nodes) . "</strong> nodes &middot; <strong>" . self::esc($edges) . "</strong> edges (live count)</li>\n";
            $out .= "</ul>\n";

            $nk = $mdb->query("SELECT kind, COUNT(*) AS n FROM node GROUP BY kind ORDER BY 2 DESC")->fetchAll(PDO::FETCH_ASSOC);
            if ($nk) {
                $parts = array();
                foreach ($nk as $r) { $parts[] = "<strong>" . self::esc($r['n']) . "</strong>&nbsp;<a href='?page=memgraph&nodekind=" . self::esc(urlencode($r['kind'])) . "'>" . self::esc($r['kind']) . "</a>"; }
                $out .= "<p><strong>nodes by kind:</strong> " . implode(" &middot; ", $parts) . "</p>\n";
            }
            $ek = $mdb->query("SELECT kind, COUNT(*) AS n FROM edge GROUP BY kind ORDER BY 2 DESC")->fetchAll(PDO::FETCH_ASSOC);
            if ($ek) {
                $parts = array();
                foreach ($ek as $r) { $parts[] = "<strong>" . self::esc($r['n']) . "</strong>&nbsp;<a href='?page=memgraph&edge=" . self::esc(urlencode($r['kind'])) . "'>" . self::esc($r['kind']) . "</a>"; }
                $out .= "<p><strong>edges by kind:</strong> " . implode(" &middot; ", $parts) . "</p>\n";
            }
            return $out;
        }

        private function body($mdb) {
            if (isset($_GET['node']) && $_GET['node'] !== '') { return $this->by_node($mdb, (string) $_GET['node']); }
            if (isset($_GET['edge']) && $_GET['edge'] !== '') { return $this->by_edge($mdb, (string) $_GET['edge']); }
            if (isset($_GET['nodekind']) && $_GET['nodekind'] !== '') { return $this->by_nodekind($mdb, (string) $_GET['nodekind']); }
            return $this->high_drift($mdb) . $this->near_dupes($mdb) . $this->most_connected($mdb);
        }

        // ?nodekind=<kind> - all nodes of one kind (bound :nodekind); each links to its node view.
        private function by_nodekind($mdb, $kind) {
            $out = "<h2>nodes of kind <code>" . self::esc($kind) . "</code> <a href='?page=memgraph'>&times;</a></h2>\n";
            $st = $mdb->prepare("SELECT id, label FROM node WHERE kind=:nodekind ORDER BY id LIMIT 200");
            $st->execute(array(':nodekind' => $kind));
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);
            if (!$rows) { return $out . "<p>(no nodes of this kind)</p>\n"; }
            $out .= "<table class='memgraph-nodekind' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= self::th(array('id', 'label'));
            foreach ($rows as $r) {
                $out .= "<tr>"
                      . "<td><a href='?page=memgraph&node=" . self::esc(urlencode($r['id'])) . "'>" . self::esc($r['id']) . "</a></td>"
                      . "<td>" . self::esc($r['label']) . "</td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }

        // ?edge=<kind> - all edges of one kind (bound :edge), strongest weight first; endpoints link to node view.
        private function by_edge($mdb, $kind) {
            $out = "<h2>edges of kind <code>" . self::esc($kind) . "</code> <a href='?page=memgraph'>&times;</a></h2>\n";
            $st = $mdb->prepare("SELECT src, dst, round(weight,4) AS w FROM edge WHERE kind=:edge ORDER BY weight DESC, src LIMIT 200");
            $st->execute(array(':edge' => $kind));
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);
            if (!$rows) { return $out . "<p>(no edges of this kind)</p>\n"; }
            $out .= "<table class='memgraph-edge' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= self::th(array('src', 'dst', 'weight'));
            foreach ($rows as $r) {
                $out .= "<tr>"
                      . "<td><a href='?page=memgraph&node=" . self::esc(urlencode($r['src'])) . "'>" . self::esc($r['src']) . "</a></td>"
                      . "<td><a href='?page=memgraph&node=" . self::esc(urlencode($r['dst'])) . "'>" . self::esc($r['dst']) . "</a></td>"
                      . "<td>" . self::esc($r['w']) . "</td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }

        // ?node=<id> — the node's own row + its outgoing (dst) / incoming (src) edges. :node is bound.
        private function by_node($mdb, $node) {
            $out = "<h2>node <code>" . self::esc($node) . "</code> <a href='?page=memgraph'>&times;</a></h2>\n";
            $st = $mdb->prepare("SELECT kind, label, attrs FROM node WHERE id=:node");
            $st->execute(array(':node' => $node));
            $n = $st->fetch(PDO::FETCH_ASSOC);
            if ($n) {
                $out .= "<p>kind <strong>" . self::esc($n['kind']) . "</strong> &middot; label <strong>" . self::esc($n['label'])
                      . "</strong></p>\n<pre style='white-space:pre-wrap;font-size:.8rem'>" . self::esc($n['attrs']) . "</pre>\n";
            } else {
                $out .= "<p>(no such node)</p>\n";
            }
            $st = $mdb->prepare("SELECT kind, dst FROM edge WHERE src=:node ORDER BY kind LIMIT 100");
            $st->execute(array(':node' => $node));
            $og = $st->fetchAll(PDO::FETCH_ASSOC);
            $out .= "<h3>outgoing (" . count($og) . ")</h3>\n";
            if (!$og) {
                $out .= "<p>(none)</p>\n";
            } else {
                $out .= "<table class='memgraph-out' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
                $out .= self::th(array('kind', 'dst'));
                foreach ($og as $r) {
                    $out .= "<tr><td>" . self::esc($r['kind']) . "</td>"
                          . "<td><a href='?page=memgraph&node=" . self::esc(urlencode($r['dst'])) . "'>" . self::esc($r['dst']) . "</a></td></tr>\n";
                }
                $out .= "</table>\n";
            }
            $st = $mdb->prepare("SELECT kind, src FROM edge WHERE dst=:node ORDER BY kind LIMIT 100");
            $st->execute(array(':node' => $node));
            $ic = $st->fetchAll(PDO::FETCH_ASSOC);
            $out .= "<h3>incoming (" . count($ic) . ")</h3>\n";
            if (!$ic) {
                $out .= "<p>(none)</p>\n";
            } else {
                $out .= "<table class='memgraph-in' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
                $out .= self::th(array('kind', 'src'));
                foreach ($ic as $r) {
                    $out .= "<tr><td>" . self::esc($r['kind']) . "</td>"
                          . "<td><a href='?page=memgraph&node=" . self::esc(urlencode($r['src'])) . "'>" . self::esc($r['src']) . "</a></td></tr>\n";
                }
                $out .= "</table>\n";
            }
            return $out;
        }

        // HIGH-DRIFT — the lifted spec-drift metric. pingpong_raw is raw / branch-interleaved (MG-9),
        // NOT settled truth. Rendered with dynamic columns since drift carries some NULL metrics.
        private function high_drift($mdb) {
            $out = "<h2>High-drift paths <span style='color:#888;font-size:.8em'>(pingpong_raw: raw / branch-interleaved &mdash; not settled truth)</span></h2>\n";
            try {
                $rows = $mdb->query("SELECT * FROM drift ORDER BY COALESCE(pingpong_raw,0) DESC LIMIT 30")->fetchAll(PDO::FETCH_ASSOC);
            } catch (\Throwable $e) {
                return $out . "<p>(no drift table)</p>\n";
            }
            if (!$rows) { return $out . "<p>(no drift rows)</p>\n"; }
            $cols = array_keys($rows[0]);
            $out .= "<table class='memgraph-drift' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n<tr>";
            foreach ($cols as $c) {
                $lbl = ($c === 'pingpong_raw') ? 'pingpong_raw (raw / branch-interleaved)' : $c;
                $out .= "<th style='text-align:left'>" . self::esc($lbl) . "</th>";
            }
            $out .= "</tr>\n";
            foreach ($rows as $r) {
                $out .= "<tr>";
                foreach ($cols as $c) {
                    $v = $r[$c];
                    $out .= "<td>" . self::esc($v === null ? '' : $v) . "</td>";
                }
                $out .= "</tr>\n";
            }
            return $out . "</table>\n";
        }

        // NEAR-DUPLICATES — the cross-repo similar_to layer, strongest similarity first.
        private function near_dupes($mdb) {
            $rows = $mdb->query("SELECT src, dst, round(weight,4) AS w FROM edge WHERE kind='similar_to' ORDER BY weight DESC LIMIT 30")->fetchAll(PDO::FETCH_ASSOC);
            $out = "<h2>Near-duplicates <span style='color:#888;font-size:.8em'>(similar_to)</span></h2>\n";
            if (!$rows) { return $out . "<p>(no similar_to edges)</p>\n"; }
            $out .= "<table class='memgraph-sim' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= self::th(array('src', 'dst', 'weight'));
            foreach ($rows as $r) {
                $out .= "<tr>"
                      . "<td><a href='?page=memgraph&node=" . self::esc(urlencode($r['src'])) . "'>" . self::esc($r['src']) . "</a></td>"
                      . "<td><a href='?page=memgraph&node=" . self::esc(urlencode($r['dst'])) . "'>" . self::esc($r['dst']) . "</a></td>"
                      . "<td>" . self::esc($r['w']) . "</td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }

        // DEFAULT — the most-connected nodes (by outgoing edge count); each links to its node view.
        private function most_connected($mdb) {
            $rows = $mdb->query("SELECT src, COUNT(*) AS c FROM edge GROUP BY src ORDER BY c DESC LIMIT 20")->fetchAll(PDO::FETCH_ASSOC);
            $out = "<h2>Most-connected nodes</h2>\n";
            if (!$rows) { return $out . "<p>(no edges)</p>\n"; }
            $out .= "<table class='memgraph-conn' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= self::th(array('node', 'out-edges'));
            foreach ($rows as $r) {
                $out .= "<tr>"
                      . "<td><a href='?page=memgraph&node=" . self::esc(urlencode($r['src'])) . "'>" . self::esc($r['src']) . "</a></td>"
                      . "<td>" . self::esc($r['c']) . "</td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }
    }
}
?>
