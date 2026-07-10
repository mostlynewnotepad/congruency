<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * TicketGraphList — the provenance-explorer entry/router.
 *
 * <<<TicketGraphList>>> renders the LIST of ticket-graphs (every ticket is the
 * root of its provenance graph). With ?ticket=<id> it bridges that request into
 * the composable, argument-driven <<<TicketGraph(id)>>> tag — whose output is
 * re-parsed by the tag engine, so the graph and its per-slot <<<GraphNode>>>
 * children render themselves. This tag only routes; the graph is built from
 * argument-taking tags, not inline HTML (cf. the split from the earlier monolith).
 */
if (!class_exists("TicketGraphList")) {
    class TicketGraphList implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string)$s, ENT_QUOTES); }

        private static function st_colour($st) {
            $map = array('OPEN' => '#1a7a3a', 'REQUESTED' => '#5a6a8a', 'APPROVED' => '#1a5a7a',
                         'VERIFIED' => '#2a7a5a', 'PUBLISHED' => '#3a7a3a', 'CLOSED' => '#888',
                         'SUPERSEDED' => '#b06a2a', 'REFUSED' => '#b00020');
            $st = strtoupper((string)$st);
            return isset($map[$st]) ? $map[$st] : '#666';
        }

        public function get_document() {
            $tid = isset($_GET['ticket']) ? (int)$_GET['ticket'] : 0;
            if ($tid > 0) {
                // delegate to the composable graph tag; the engine re-parses this output
                return "<<<TicketGraph(" . $tid . ")>>>";
            }
            try {
                if (!defined('CONGRUENCY_SQLITE')) { return "<!-- TicketGraphList: no DB -->"; }
                $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
                $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                return $this->roots($db);
            } catch (\Throwable $e) {
                return "<p style='color:#b00020'>TicketGraphList: " . self::esc($e->getMessage()) . "</p>";
            }
        }

        // ---- the list of graph-roots (each ticket) ----
        private function roots($db) {
            $rows = $db->query("SELECT id, component, status, title FROM tickets ORDER BY id DESC")
                       ->fetchAll(PDO::FETCH_ASSOC);
            $runs = array();
            foreach ($db->query("SELECT ticket_id, COUNT(*) c FROM crank_runs GROUP BY ticket_id")
                        ->fetchAll(PDO::FETCH_ASSOC) as $r) {
                $runs[(int)$r['ticket_id']] = (int)$r['c'];
            }
            $out  = "<style>";
            $out .= ".gr{display:grid;gap:.55rem}";
            $out .= ".g{border:1px solid #d8d2c4;border-left:5px solid #999;border-radius:6px;padding:.55rem .85rem;background:#fffdf8}";
            $out .= ".g a.t{font-size:1rem;color:#8a5a1a;text-decoration:none}";
            $out .= ".g .id{font:600 .7rem/1 monospace;color:#555;letter-spacing:.05em}";
            $out .= ".g .st{float:right;font:600 .6rem/1.6 sans-serif;text-transform:uppercase;color:#fff;padding:.1rem .45rem;border-radius:3px}";
            $out .= ".g .n{font:.68rem/1.4 sans-serif;color:#666;margin-left:.5rem}";
            $out .= "</style>\n";
            $out .= "<p style='font-size:.85rem;color:#555'><strong>" . count($rows)
                  . "</strong> ticket-graphs &mdash; each ticket is the root of its provenance graph. Click one to walk it.</p>\n";
            $out .= "<div class='gr'>\n";
            foreach ($rows as $r) {
                $id  = (int)$r['id'];
                $stc = self::st_colour($r['status']);
                $nr  = isset($runs[$id]) ? $runs[$id] : 0;
                $out .= "  <div class='g' style='border-left-color:$stc'>";
                $out .= "<span class='st' style='background:$stc'>" . self::esc($r['status']) . "</span>";
                $out .= "<span class='id'>#" . $id . "</span> ";
                $out .= "<a class='t' href='?page=graphs&amp;ticket=" . $id . "'>" . self::esc($r['title']) . "</a>";
                $out .= "<span class='n'>" . self::esc($r['component']) . " &middot; " . $nr . " run" . ($nr == 1 ? '' : 's') . "</span>";
                $out .= "</div>\n";
            }
            $out .= "</div>\n";
            return $out;
        }
    }
}
?>
