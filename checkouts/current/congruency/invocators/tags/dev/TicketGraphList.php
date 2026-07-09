<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * TicketGraphList — the provenance-explorer entry tag.
 *
 * Implements Tag_Interface; invoked as <<<TicketGraphList>>>. Treats every
 * ticket as the ROOT of a provenance graph — the ticket-class model, where a
 * ticket is an aggregate that CONTAINS its goal, mandate, patch, approval,
 * runs, guarantees, artifacts and (owned) child tickets. With no ?ticket= it
 * renders the LIST of graph-roots; with ?ticket=<id> it walks that one ticket's
 * graph: the contained things recorded TODAY (goal/patch/approval/runs), plus
 * the ticket-class slots shown empty so the fan-out is visible and honest.
 *
 * Reads the unified congruency DB (CONGRUENCY_SQLITE) — the same file the CMS,
 * tickets, gate and crank_runs share. Every value is htmlspecialchars()'d so
 * the tag engine never re-parses the output and recurses (cf. TicketList).
 */
if (!class_exists("TicketGraphList")) {
    class TicketGraphList implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string)$s, ENT_QUOTES); }

        private function db() {
            if (!defined('CONGRUENCY_SQLITE')) { return null; }
            $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
            $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            return $db;
        }

        // lifecycle-state colour (the ticket-class states, plus the legacy OPEN/closed)
        private static function st_colour($st) {
            $map = array('OPEN' => '#1a7a3a', 'REQUESTED' => '#5a6a8a', 'APPROVED' => '#1a5a7a',
                         'VERIFIED' => '#2a7a5a', 'PUBLISHED' => '#3a7a3a', 'CLOSED' => '#888',
                         'SUPERSEDED' => '#b06a2a', 'REFUSED' => '#b00020');
            $st = strtoupper((string)$st);
            return isset($map[$st]) ? $map[$st] : '#666';
        }

        private function css() {
            return "<style>"
                 . ".gr{display:grid;gap:.55rem}"
                 . ".g{border:1px solid #d8d2c4;border-left:5px solid #999;border-radius:6px;padding:.55rem .85rem;background:#fffdf8}"
                 . ".g a.t{font-size:1rem;color:#8a5a1a;text-decoration:none}"
                 . ".g .id{font:600 .7rem/1 monospace;color:#555;letter-spacing:.05em}"
                 . ".g .st{float:right;font:600 .6rem/1.6 sans-serif;text-transform:uppercase;color:#fff;padding:.1rem .45rem;border-radius:3px}"
                 . ".g .cm{font:.7rem/1 monospace;color:#8a5a1a}"
                 . ".g .n{font:.68rem/1.4 sans-serif;color:#666;margin-left:.5rem}"
                 . ".node{border:1px solid #d8d2c4;border-radius:6px;padding:.5rem .8rem;margin:.4rem 0;background:#fffdf8}"
                 . ".node h3{margin:.1rem 0;font:600 .74rem sans-serif;text-transform:uppercase;letter-spacing:.04em;color:#555}"
                 . ".empty{color:#999;font-style:italic}"
                 . "</style>\n";
        }

        public function get_document() {
            try {
                $db = $this->db();
                if ($db === null) { return "<!-- TicketGraphList: no DB -->"; }
                $tid = isset($_GET['ticket']) ? (int)$_GET['ticket'] : 0;
                return $tid > 0 ? $this->walk($db, $tid) : $this->roots($db);
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
            $out  = $this->css();
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

        // ---- one ticket's graph (the walk) ----
        private function walk($db, $tid) {
            $t = $db->query("SELECT * FROM tickets WHERE id=" . (int)$tid)->fetch(PDO::FETCH_ASSOC);
            $out  = $this->css();
            $out .= "<p><a href='?page=graphs'>&larr; all ticket-graphs</a></p>\n";
            if (!$t) { return $out . "<p class='empty'>No ticket #" . (int)$tid . ".</p>"; }

            $stc = self::st_colour($t['status']);
            $out .= "<div class='g' style='border-left-color:$stc'>";
            $out .= "<span class='st' style='background:$stc'>" . self::esc($t['status']) . "</span>";
            $out .= "<span class='id'>#" . (int)$tid . "</span> <span class='cm'>" . self::esc($t['component']) . "</span>";
            $out .= "<h2 style='font-weight:normal;margin:.2rem 0'>" . self::esc($t['title']) . "</h2></div>\n";

            $body  = isset($t['body']) ? (string)$t['body'] : '';
            $out  .= "<div class='node'><h3>goal</h3>"
                   . ($body !== '' ? "<div>" . self::esc($body) . "</div>" : "<span class='empty'>&mdash;</span>") . "</div>\n";

            $patch = isset($t['patch']) ? (string)$t['patch'] : '';
            $out  .= "<div class='node'><h3>patch</h3>"
                   . ($patch !== '' ? "bound &middot; " . strlen($patch) . " bytes" : "<span class='empty'>none</span>") . "</div>\n";

            $sig = isset($t['approval_sig']) ? (string)$t['approval_sig'] : '';
            $out .= "<div class='node'><h3>approval</h3>"
                  . ($sig !== '' ? "wallet-signed" : "<span class='empty'>unapproved</span>") . "</div>\n";

            $rr = $db->query("SELECT version, ok, digest FROM crank_runs WHERE ticket_id=" . (int)$tid . " ORDER BY id DESC")
                     ->fetchAll(PDO::FETCH_ASSOC);
            $out .= "<div class='node'><h3>runs</h3>";
            if ($rr) {
                foreach ($rr as $r) {
                    $out .= "<div>v" . self::esc($r['version']) . " &middot; "
                          . ((int)$r['ok'] ? "green" : "failed") . " &middot; <code>"
                          . self::esc(substr((string)$r['digest'], 0, 12)) . "</code></div>";
                }
            } else {
                $out .= "<span class='empty'>no runs recorded</span>";
            }
            $out .= "</div>\n";

            // ticket-class slots not yet stored — rendered so the fan-out is visible and honest
            $slots = array('mandate (clauses)', 'manifestations', 'guarantees',
                           'journey (blunders &amp; successes)', 'artifacts (forge)', 'children');
            foreach ($slots as $slot) {
                $out .= "<div class='node'><h3>" . $slot . "</h3>"
                      . "<span class='empty'>not yet recorded &mdash; lands with the ticket-class build</span></div>\n";
            }
            return $out;
        }
    }
}
?>
