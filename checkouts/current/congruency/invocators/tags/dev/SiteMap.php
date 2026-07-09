<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * SiteMap — the "list all pages" tag, used as the site navigation.
 *
 * Implements Tag_Interface; invoked as <<<SiteMap>>>. Reads every Document
 * (page) from CONGRUENCY_SQLITE and renders an inline menu of links, so the
 * nav is generated from the pages that actually exist rather than hardcoded.
 * Terminal/internal pages (the order wizard's tail, the 404) are blocklisted;
 * a small label map keeps the friendly names.
 */
if (!class_exists("SiteMap")) {
    class SiteMap implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string)$s, ENT_QUOTES); }

        public function get_document() {
            try {
                if (!defined('CONGRUENCY_SQLITE')) { return "<!-- SiteMap: no DB -->"; }
                $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
                $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                $have = array();
                foreach ($db->query("SELECT DocumentID FROM Documents")->fetchAll(PDO::FETCH_COLUMN) as $id) { $have[$id] = 1; }

                // home/about/order-wizard dropped from the nav (still reachable via Pages);
                // the nav now leads with Pages (all pages) and Tags (all tags).
                $block = array('invalid' => 1, 'thanks' => 1, 'ticketDone' => 1, 'tagDone' => 1, 'order' => 1,
                               'catalog' => 1, 'about' => 1, 'config' => 1, 'categoryDone' => 1, 'annotateDone' => 1);
                $label = array('pages' => 'Pages', 'tags' => 'Tags', 'bugs' => 'bug report',
                               'source' => 'Source', 'docs' => 'Docs', 'annotations' => 'Annotations',
                               'database' => 'Database', 'graphs' => 'Graphs');
                $order = array('pages', 'tags', 'bugs', 'forms', 'tickets', 'graphs', 'memories', 'source', 'docs', 'annotations', 'database');

                $ids = array();
                foreach ($order as $id) { if (isset($have[$id]) && !isset($block[$id])) { $ids[] = $id; unset($have[$id]); } }
                foreach (array_keys($have) as $id) { if (!isset($block[$id])) { $ids[] = $id; } }  // any extras, after

                $links = array();
                foreach ($ids as $id) {
                    $text = isset($label[$id]) ? $label[$id] : $id;
                    $links[] = "<a href='?page=" . self::esc($id) . "'>" . self::esc($text) . "</a>";
                }
                return implode(" &nbsp;&middot;&nbsp; ", $links);   // nav styling (incl. all-caps) lives in <<<Style>>>
            } catch (\Throwable $e) {
                return "<!-- SiteMap error: " . self::esc($e->getMessage()) . " -->";
            }
        }
    }
}
?>
