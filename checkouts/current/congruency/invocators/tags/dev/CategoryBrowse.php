<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * CategoryBrowse — the category-browse view: every category and its tagged pages
 * in one expanded pass.
 *
 * Categories are the tag layer for pages. A page is tagged by an `annotations`
 * row whose `tag` is the category name and whose `target` is "page:<DocumentID>"
 * (written by TagPageHandler; the same shape CategoryPages reads). There is no
 * Page_Categories join table — the link lives in `annotations`.
 *
 * CategoryPages shows one category at a time (index, then drill in). CategoryBrowse
 * complements it by rendering the whole map at once: each category as a heading with
 * its page count, and beneath it the pages tagged with that category as links to
 * ?page=<DocumentID>. Empty categories are shown too, marked as holding no pages yet.
 *
 * Invoked as <<<CategoryBrowse>>> for the full browse, or <<<CategoryBrowse(specifications)>>>
 * (or ?category=specifications) to focus a single category. It reads only; tagging is
 * done through TagPageForm/TagPageHandler at ?page=pages.
 */
if (!class_exists("CategoryBrowse")) {
    class CategoryBrowse implements Tag_Interface {

        private $category;
        public function __construct($arguments) {
            // arguments may be null when rendered standalone (e.g. by TagList: new CategoryBrowse(null))
            $this->category = (isset($arguments) && method_exists($arguments, 'top')) ? $arguments->top() : '';
        }
        private static function esc($s) { return htmlspecialchars((string)$s, ENT_QUOTES); }

        private function db() {
            $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
            $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            return $db;
        }

        // The pages tagged with one category name, as <li> links. Mirrors CategoryPages:
        // 'page:' is 5 chars, so substr(target,6) is the DocumentID (SQLite substr is 1-indexed).
        private function pagesFor($db, $name) {
            $st = $db->prepare("SELECT d.DocumentID, d.Title FROM annotations a
                JOIN Documents d ON d.DocumentID=substr(a.target, 6)
                WHERE a.tag=? AND a.target LIKE 'page:%' ORDER BY d.DocumentID");
            $st->execute(array($name));
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);
            if (!$rows) { return "<p style='margin:.2rem 0 .2rem 1rem;color:#888'><em>no pages tagged yet</em></p>"; }
            $out = "<ul style='margin:.2rem 0 .6rem'>";
            foreach ($rows as $r) {
                $title = ($r['Title'] !== null && $r['Title'] !== '') ? $r['Title'] : $r['DocumentID'];
                $out .= "<li><a href='?page=" . self::esc($r['DocumentID']) . "'>" . self::esc($title) . "</a></li>";
            }
            return $out . "</ul>";
        }

        // One category block: heading (links into CategoryPages' single view) + its pages.
        private function section($db, $name, $description, $n) {
            $head = "<h3 style='margin:.8rem 0 .2rem;font-weight:normal'>"
                  . "<a href='?page=pages&category=" . self::esc($name) . "'>" . self::esc($name) . "</a>"
                  . " <span style='color:#888;font-size:.85rem'>(" . (int)$n . ")</span></h3>";
            if ($description !== null && $description !== '') {
                $head .= "<p style='margin:.1rem 0 .3rem;color:#666;font-size:.9rem'>" . self::esc($description) . "</p>";
            }
            return $head . $this->pagesFor($db, $name);
        }

        public function get_document() {
            try {
                if (!defined('CONGRUENCY_SQLITE')) { return "<p>CategoryBrowse: no DB.</p>"; }
                $db = $this->db();

                // focus comes from the tag argument, else the ?category= URL param
                $cat = trim((string)$this->category);
                if ($cat === '' && isset($_GET['category'])) { $cat = trim((string)$_GET['category']); }

                if ($cat !== '') {   // focus a single category
                    $st = $db->prepare("SELECT name, description,
                        (SELECT COUNT(*) FROM annotations a WHERE a.tag=Categories.name AND a.target LIKE 'page:%') AS n
                        FROM Categories WHERE name=?");
                    $st->execute(array($cat));
                    $c = $st->fetch(PDO::FETCH_ASSOC);
                    if (!$c) { return "<p>No such category: <code>" . self::esc($cat) . "</code>. <a href='?page=tags&tag=CategoryBrowse'>&larr; browse all</a></p>"; }
                    return "<div class='category-browse'>" . $this->section($db, $c['name'], $c['description'], $c['n'])
                         . "<p style='margin-top:.8rem'><a href='?page=tags&tag=CategoryBrowse'>&larr; browse all categories</a></p></div>";
                }

                // full browse: every category, with page counts, ordered by name
                $cats = $db->query("SELECT name, description,
                    (SELECT COUNT(*) FROM annotations a WHERE a.tag=Categories.name AND a.target LIKE 'page:%') AS n
                    FROM Categories ORDER BY name")->fetchAll(PDO::FETCH_ASSOC);

                if (!$cats) { return "<p>No categories yet. Create one at <a href='?page=forms'>the admin forms</a>.</p>"; }

                $pages = 0; foreach ($cats as $c) { $pages += (int)$c['n']; }
                $out = "<div class='category-browse'><p style='color:#555;font-size:.9rem'><strong>"
                     . count($cats) . "</strong> categor" . (count($cats) === 1 ? "y" : "ies")
                     . " &middot; <strong>" . $pages . "</strong> page tag" . ($pages === 1 ? "" : "s") . "</p>";
                foreach ($cats as $c) {
                    $out .= $this->section($db, $c['name'], $c['description'], $c['n']);
                }
                return $out . "</div>";
            } catch (\Throwable $e) {
                return "<div class='cy-form-error'>CategoryBrowse error: " . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</div>";
            }
        }
    }
}
?>
