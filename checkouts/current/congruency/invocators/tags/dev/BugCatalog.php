<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * BugCatalog — the unified BUG CATALOG on ?page=bugs. Repurposes congruency's own bug-report schema
 * (tooling/congruencey-bugs/bugs.json: id,title,severity,file,repro,success) into a data-driven
 * `bugs` table unifying TWO sources: 'congruency' (the curated + reproduced bugs, each with a runnable
 * repro path) and 'corpus' (corpus-wide consistent-bug pattern findings, carrying a fanout/repos
 * consistency metric + an anti-pattern id).
 *
 * Invoked as <<<BugCatalog>>>. Opens the STANDARD congruency PDO (CONGRUENCY_SQLITE — bugs live in
 * the normal congruency db, NOT a foreign one). Reads ?source= ('' | congruency | corpus) and
 * ?severity= ('' | critical | high | medium | low), renders a GET form preserving the current facet
 * selection + a per-severity/source summary line + the colour-coded catalog table. If the table is
 * empty it degrades gracefully ('no bugs recorded yet — ingest with bug.record').
 *
 * SECURITY: EVERY value read from the bugs table (titles CONTAIN literal <<<Tag>>> and <script> by
 * design) is htmlspecialchars()'d before it flows back through execute_all_tags, so a stored tag /
 * script stays inert (escape-first). Facets are bound, never interpolated.
 */
if (!interface_exists('Tag_Interface')) { interface Tag_Interface { public function get_document(); } }
if (!class_exists("BugCatalog")) {
    class BugCatalog implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

        private static function severity_color($s) {
            switch ((string) $s) {
                case 'critical': return '#c62828';   // red
                case 'high':     return '#e65100';   // orange
                case 'medium':   return '#b5a300';   // yellow
                case 'low':      return '#777';      // grey
                default:         return '#555';
            }
        }

        public function get_document() {
            $source   = isset($_GET['source'])   ? (string) $_GET['source']   : '';
            $severity = isset($_GET['severity']) ? (string) $_GET['severity'] : '';
            if (!in_array($source,   array('', 'congruency', 'corpus'), true)) { $source = ''; }
            if (!in_array($severity, array('', 'critical', 'high', 'medium', 'low'), true)) { $severity = ''; }

            $form = $this->form($source, $severity);
            if (!defined('CONGRUENCY_SQLITE')) {
                return $form . "<p class='cy-form-error'>BugCatalog: no DB.</p>";
            }
            try {
                $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
                $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            } catch (\Throwable $e) {
                return $form . "<div class='cy-form-error'>BugCatalog error: " . self::esc($e->getMessage()) . "</div>";
            }
            try {
                $total = (int) $db->query("SELECT COUNT(*) FROM bugs")->fetchColumn();
            } catch (\Throwable $e) {
                return $form . "<p class='cy-form-error'>no bugs table yet &mdash; ingest with <code>bug.record</code></p>";
            }
            if ($total === 0) {
                return $form . "<p>no bugs recorded yet &mdash; ingest with <code>bug.record</code> (source=congruency|corpus).</p>\n";
            }
            try {
                return $form . $this->summary($db) . $this->table($db, $source, $severity);
            } catch (\Throwable $e) {
                return $form . "<div class='cy-form-error'>BugCatalog error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        private function form($source, $severity) {
            $out  = "<form method='get' action=''>\n";
            $out .= "<input type='hidden' name='page' value='bugs'>\n";
            $out .= "<select name='source'>\n";
            foreach (array('' => '(all sources)', 'congruency' => 'congruency', 'corpus' => 'corpus') as $v => $lab) {
                $sel = ($source === (string) $v) ? " selected" : "";
                $out .= "<option value='" . self::esc($v) . "'" . $sel . ">" . self::esc($lab) . "</option>\n";
            }
            $out .= "</select>\n";
            $out .= "<select name='severity'>\n";
            foreach (array('' => '(any severity)', 'critical' => 'critical', 'high' => 'high', 'medium' => 'medium', 'low' => 'low') as $v => $lab) {
                $sel = ($severity === (string) $v) ? " selected" : "";
                $out .= "<option value='" . self::esc($v) . "'" . $sel . ">" . self::esc($lab) . "</option>\n";
            }
            $out .= "</select>\n";
            $out .= "<button type='submit'>Filter</button>\n</form>\n";
            return $out;
        }

        private function summary($db) {
            $total = (int) $db->query("SELECT COUNT(*) FROM bugs")->fetchColumn();
            $bysev = $db->query("SELECT severity, COUNT(*) AS n FROM bugs GROUP BY severity")->fetchAll(PDO::FETCH_ASSOC);
            $bysrc = $db->query("SELECT source, COUNT(*) AS n FROM bugs GROUP BY source")->fetchAll(PDO::FETCH_ASSOC);
            $sevparts = array();
            foreach ($bysev as $r) {
                $sevparts[] = "<span style='color:" . self::severity_color($r['severity']) . "'>" . self::esc($r['severity']) . "</span>&nbsp;" . self::esc($r['n']);
            }
            $srcparts = array();
            foreach ($bysrc as $r) {
                $srcparts[] = self::esc($r['source']) . "&nbsp;" . self::esc($r['n']);
            }
            $out = "<p class='bug-summary'><strong>" . self::esc($total) . "</strong> bugs";
            if ($sevparts) { $out .= " &mdash; by severity: " . implode(" &middot; ", $sevparts); }
            if ($srcparts) { $out .= " &mdash; by source: " . implode(" &middot; ", $srcparts); }
            $out .= "</p>\n";
            return $out;
        }

        private function table($db, $source, $severity) {
            $sql = "SELECT bug_id, source, title, severity, location, repro, success, fanout, repos, status, pattern
                    FROM bugs WHERE (:source='' OR source=:source) AND (:severity='' OR severity=:severity)
                    ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, source, bug_id LIMIT 300";
            $st = $db->prepare($sql);
            $st->execute(array(':source' => $source, ':severity' => $severity));
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);

            $out = "<h2>Bugs";
            if ($source   !== '') { $out .= " &middot; " . self::esc($source); }
            if ($severity !== '') { $out .= " &middot; " . self::esc($severity); }
            if ($source !== '' || $severity !== '') { $out .= " <a href='?page=bugs'>&times;</a>"; }
            $out .= "</h2>\n";
            if (!$rows) { return $out . "<p>(no bugs match this filter)</p>\n"; }

            $out .= "<table class='bug-catalog' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= "<tr><th style='text-align:left'>id</th><th style='text-align:left'>severity</th><th style='text-align:left'>title</th><th style='text-align:left'>location</th><th style='text-align:left'>source</th><th style='text-align:left'>detail</th><th style='text-align:left'>status</th></tr>\n";
            foreach ($rows as $r) {
                $c = self::severity_color($r['severity']);
                if ((string) $r['source'] === 'corpus') {
                    $detail = "fanout " . self::esc($r['fanout']) . " / " . self::esc($r['repos']) . " repos";
                    if ($r['pattern'] !== null && $r['pattern'] !== '') { $detail .= " <code>" . self::esc($r['pattern']) . "</code>"; }
                } else {
                    $detail = ($r['repro'] !== null && $r['repro'] !== '') ? "<code>" . self::esc($r['repro']) . "</code>" : self::esc($r['success']);
                }
                $out .= "<tr>"
                      . "<td><code>" . self::esc($r['bug_id']) . "</code></td>"
                      . "<td class='bug-sev bug-sev-" . self::esc($r['severity']) . "' style='color:" . $c . ";font-weight:600'>" . self::esc($r['severity']) . "</td>"
                      . "<td>" . self::esc($r['title']) . "</td>"
                      . "<td>" . self::esc($r['location']) . "</td>"
                      . "<td>" . self::esc($r['source']) . "</td>"
                      . "<td>" . $detail . "</td>"
                      . "<td>" . self::esc($r['status']) . "</td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }
    }
}
?>
