<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * GraphNode — one node of a ticket-graph, argument-driven: <<<GraphNode(runs,186)>>>.
 *
 * Two args (slot, id) via the TagArguments pop() order. Dispatches on the slot
 * and renders that ONE contained relation for the ticket. Slots backed by data
 * today (goal/patch/approval/runs) render it; ticket-class slots not yet stored
 * render an explicit fan-out placeholder. Each new ticket-class table adds one
 * case to render() — the whole iterative fan-out lives in this one switch.
 */
if (!class_exists("GraphNode")) {
    class GraphNode implements Tag_Interface {

        private $slot;
        private $id;

        public function __construct($arguments) {
            // pop() returns args left-to-right: first the slot, then the id
            $this->slot = $arguments ? (string)$arguments->pop() : '';
            $this->id   = $arguments ? (int)$arguments->pop() : 0;
        }

        private static function esc($s) { return htmlspecialchars((string)$s, ENT_QUOTES); }

        private static $labels = array(
            'goal' => 'goal', 'patch' => 'patch', 'approval' => 'approval', 'runs' => 'runs',
            'mandate' => 'mandate (clauses)', 'manifestations' => 'manifestations',
            'guarantees' => 'guarantees', 'journey' => 'journey (blunders &amp; successes)',
            'artifacts' => 'artifacts (forge)', 'children' => 'children',
        );

        private function db() {
            if (!defined('CONGRUENCY_SQLITE')) { return null; }
            $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
            $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            return $db;
        }

        public function get_document() {
            $slot  = $this->slot;
            $label = isset(self::$labels[$slot]) ? self::$labels[$slot] : self::esc($slot);
            try {
                $body = $this->render($slot, (int)$this->id);
            } catch (\Throwable $e) {
                $body = "<span style='color:#b00020'>" . self::esc($e->getMessage()) . "</span>";
            }
            return "<div class='node'><h3>" . $label . "</h3>" . $body . "</div>\n";
        }

        // one contained relation. New ticket-class tables slot in as new cases.
        private function render($slot, $id) {
            $db = $this->db();
            if ($db === null) { return "<span class='empty'>no DB</span>"; }
            switch ($slot) {
                case 'goal':
                    $b = $db->query("SELECT body FROM tickets WHERE id=" . $id)->fetchColumn();
                    return ($b !== false && $b !== '') ? "<div>" . self::esc($b) . "</div>"
                                                       : "<span class='empty'>&mdash;</span>";
                case 'patch':
                    $p = (string)$db->query("SELECT patch FROM tickets WHERE id=" . $id)->fetchColumn();
                    return $p !== '' ? "bound &middot; " . strlen($p) . " bytes"
                                     : "<span class='empty'>none</span>";
                case 'approval':
                    $s = (string)$db->query("SELECT approval_sig FROM tickets WHERE id=" . $id)->fetchColumn();
                    return $s !== '' ? "wallet-signed" : "<span class='empty'>unapproved</span>";
                case 'runs':
                    $rr = $db->query("SELECT version, ok, digest FROM crank_runs WHERE ticket_id=" . $id . " ORDER BY id DESC")
                             ->fetchAll(PDO::FETCH_ASSOC);
                    if (!$rr) { return "<span class='empty'>no runs recorded</span>"; }
                    $o = "";
                    foreach ($rr as $r) {
                        $o .= "<div>v" . self::esc($r['version']) . " &middot; "
                            . ((int)$r['ok'] ? "green" : "failed") . " &middot; <code>"
                            . self::esc(substr((string)$r['digest'], 0, 12)) . "</code></div>";
                    }
                    return $o;
                case 'mandate':
                    $cl = $db->query("SELECT clause FROM mandates WHERE ticket_id=" . $id . " ORDER BY seq")
                             ->fetchAll(PDO::FETCH_COLUMN);
                    if (!$cl) { return "<span class='empty'>not yet recorded &mdash; lands with the ticket-class build</span>"; }
                    $o = "<ol style='margin:.2rem 0 0 1.1rem;padding:0'>";
                    foreach ($cl as $c) { $o .= "<li>" . self::esc($c) . "</li>"; }
                    return $o . "</ol>";
                case 'guarantees':
                    // coverage view: each mandate clause verified by its bound guarantees, or a gap
                    $cl = $db->query("SELECT seq, clause FROM mandates WHERE ticket_id=" . $id . " ORDER BY seq")
                             ->fetchAll(PDO::FETCH_ASSOC);
                    $gz = $db->query("SELECT clause_seq, guarantee FROM guarantees WHERE ticket_id=" . $id . " ORDER BY id")
                             ->fetchAll(PDO::FETCH_ASSOC);
                    if (!$gz) { return "<span class='empty'>not yet recorded &mdash; lands with the ticket-class build</span>"; }
                    $by = array();
                    foreach ($gz as $g) { $k = ($g['clause_seq'] === null) ? 0 : (int)$g['clause_seq']; $by[$k][] = $g['guarantee']; }
                    $covered = 0;
                    $rows = "";
                    foreach ($cl as $c) {
                        $seq = (int)$c['seq'];
                        $gs  = isset($by[$seq]) ? $by[$seq] : array();
                        if ($gs) {
                            $covered++;
                            $rows .= "<div>✓ <b>" . self::esc($c['clause']) . "</b>";
                            foreach ($gs as $g) { $rows .= "<div style='margin-left:1rem;color:#555;font-size:.8rem'>&mdash; " . self::esc($g) . "</div>"; }
                            $rows .= "</div>";
                        } else {
                            $rows .= "<div style='color:#b00020'>✗ <b>UNVERIFIED</b> &mdash; " . self::esc($c['clause']) . "</div>";
                        }
                    }
                    $head = "<div style='font-size:.8rem;color:#555;margin-bottom:.3rem'>" . $covered . "/" . count($cl) . " clauses verified</div>";
                    if (isset($by[0])) { $rows .= "<div style='margin-top:.4rem;font-size:.75rem;color:#888'>" . count($by[0]) . " guarantee(s) not bound to a clause</div>"; }
                    return $head . $rows;
                default:
                    // mandate / manifestations / guarantees / journey / artifacts / children
                    return "<span class='empty'>not yet recorded &mdash; lands with the ticket-class build</span>";
            }
        }
    }
}
?>
