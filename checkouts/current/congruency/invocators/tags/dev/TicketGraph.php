<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * TicketGraph — one ticket's provenance graph, argument-driven: <<<TicketGraph(186)>>>.
 *
 * Takes the ticket id as a tag argument (not $_GET), so it renders standalone.
 * Emits the graph-root header, then one <<<GraphNode(slot,id)>>> per contained
 * slot of the ticket-class aggregate; the tag engine re-parses this output and
 * executes each node tag. Fanning out a new ticket-class table = adding its slot
 * to $slots here and a case to GraphNode — nothing else changes.
 */
if (!class_exists("TicketGraph")) {
    class TicketGraph implements Tag_Interface {

        private $id;
        public function __construct($arguments) { $this->id = $arguments ? (int)$arguments->pop() : 0; }
        private static function esc($s) { return htmlspecialchars((string)$s, ENT_QUOTES); }

        // the ordered slots the ticket-class aggregate contains (goal .. children)
        private static $slots = array('goal', 'patch', 'approval', 'runs',
                                      'mandate', 'manifestations', 'guarantees', 'journey', 'artifacts', 'source', 'children');

        private static function st_colour($st) {
            $map = array('OPEN' => '#1a7a3a', 'REQUESTED' => '#5a6a8a', 'APPROVED' => '#1a5a7a',
                         'VERIFIED' => '#2a7a5a', 'PUBLISHED' => '#3a7a3a', 'CLOSED' => '#888',
                         'SUPERSEDED' => '#b06a2a', 'REFUSED' => '#b00020');
            $st = strtoupper((string)$st);
            return isset($map[$st]) ? $map[$st] : '#666';
        }

        private function css() {
            return "<style>"
                 . ".g{border:1px solid #d8d2c4;border-left:5px solid #999;border-radius:6px;padding:.55rem .85rem;background:#fffdf8}"
                 . ".g .id{font:600 .7rem/1 monospace;color:#555;letter-spacing:.05em}"
                 . ".g .cm{font:.7rem/1 monospace;color:#8a5a1a}"
                 . ".g .st{float:right;font:600 .6rem/1.6 sans-serif;text-transform:uppercase;color:#fff;padding:.1rem .45rem;border-radius:3px}"
                 . ".node{border:1px solid #d8d2c4;border-radius:6px;padding:.5rem .8rem;margin:.4rem 0;background:#fffdf8}"
                 . ".node h3{margin:.1rem 0;font:600 .74rem sans-serif;text-transform:uppercase;letter-spacing:.04em;color:#555}"
                 . ".empty{color:#999;font-style:italic}"
                 . "</style>\n";
        }

        public function get_document() {
            $id  = (int)$this->id;
            $out = $this->css();
            $out .= "<p><a href='?page=graphs'>&larr; all ticket-graphs</a></p>\n";
            try {
                if (!defined('CONGRUENCY_SQLITE')) { return $out . "<!-- TicketGraph: no DB -->"; }
                $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
                $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                $t = $db->query("SELECT status, component, title FROM tickets WHERE id=" . $id)->fetch(PDO::FETCH_ASSOC);
            } catch (\Throwable $e) {
                return $out . "<p style='color:#b00020'>TicketGraph: " . self::esc($e->getMessage()) . "</p>";
            }
            if (!$t) { return $out . "<p class='empty'>No ticket #" . $id . ".</p>"; }

            $stc = self::st_colour($t['status']);
            $out .= "<div class='g' style='border-left-color:$stc'>";
            $out .= "<span class='st' style='background:$stc'>" . self::esc($t['status']) . "</span>";
            $out .= "<span class='id'>#" . $id . "</span> <span class='cm'>" . self::esc($t['component']) . "</span>";
            $out .= "<h2 style='font-weight:normal;margin:.2rem 0'>" . self::esc($t['title']) . "</h2></div>\n";

            // emit one node tag per slot — the engine expands each <<<GraphNode(slot)(id)>>>.
            // congruency args are CHAINED single parens (FUNCTION_ARGUMENTS), not comma-separated.
            foreach (self::$slots as $slot) {
                $out .= "<<<GraphNode(" . $slot . ")(" . $id . ")>>>\n";
            }
            return $out;
        }
    }
}
?>
