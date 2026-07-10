<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * ShadowForge — congruency reflects the SHADOW FORGE index
 * (~/bin/config/forge/shadow_forge/shadow_index.db), a SEPARATE sqlite database from
 * CONGRUENCY_SQLITE, built by jazz-forge's forge/shadow_forge.py (RFC-0030). A read-only reflection
 * of per-file test/spec coverage over our actively-developed code, and the DEFICIT backlog: files
 * that lack a test and/or a spec citation ("learn the deficits within our specifications").
 *
 * Invoked as <<<ShadowForge>>> on ?page=shadowforge. Data source: shadow_index.db, resolved from
 * getenv('SHADOW_FORGE_DB') ?: $HOME/bin/config/forge/shadow_forge/shadow_index.db, opened through a
 * SECOND PDO handle with `PRAGMA query_only=1` so the reflection can NEVER mutate the shadow index.
 * Absent/unreadable -> the page degrades gracefully ("shadow forge not built yet at <path>"), it
 * never crashes the page.
 *   ?page=shadowforge                       -> summary + DEFICIT backlog + spec-cited exemplars
 *   ?page=shadowforge&reason=<r>&repo=<r>    -> filter the deficit backlog (NULL-safe COALESCE guards)
 *   ?page=shadowforge&file=<path>           -> which shadow-docs cover a file (+ the file's spec_refs)
 *
 * SF-1 coverage = distinct covered files / non-shadow files. SF-3 spec-cite = files citing a spec /
 * all files. SF-6 = the deficit count + a per-reason breakdown.
 *
 * SECURITY: EVERY value read from shadow_index.db (paths, repos, reasons, spec_refs) is
 * htmlspecialchars()'d before it flows back through execute_all_tags, so a stored <<<Tag>>> /
 * <script> in a path stays inert (escape-first). Facets are bound, never interpolated. The index is
 * opened read-only, so the page can never mutate the shadow index.
 */
if (!class_exists("ShadowForge")) {
    class ShadowForge implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

        private static function shadow_path() {
            $p = getenv('SHADOW_FORGE_DB');
            if ($p !== false && $p !== '') { return $p; }
            return getenv('HOME') . '/bin/config/forge/shadow_forge/shadow_index.db';
        }

        public function get_document() {
            $path = self::shadow_path();
            if (!is_file($path) || !is_readable($path)) {
                return "<p class='cy-form-error'>shadow forge not built yet at <code>" . self::esc($path) . "</code> &mdash; run forge/shadow_forge.py</p>";
            }
            try {
                $sdb = new PDO('sqlite:' . $path);
                $sdb->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                $sdb->exec('PRAGMA query_only=1');   // read-only: the reflection can never mutate the shadow index
            } catch (\Throwable $e) {
                return "<p class='cy-form-error'>shadow forge not readable at <code>" . self::esc($path) . "</code> &mdash; run forge/shadow_forge.py</p>";
            }
            try {
                if (isset($_GET['file']) && $_GET['file'] !== '') {
                    return $this->summary($sdb) . $this->by_file($sdb, (string) $_GET['file']);
                }
                return $this->summary($sdb) . $this->facet_form($sdb) . $this->deficits($sdb) . $this->spec_cited($sdb);
            } catch (\Throwable $e) {
                return "<div class='cy-form-error'>ShadowForge error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        private static function scalar($sdb, $sql) {
            $v = $sdb->query($sql)->fetchColumn();
            return ($v === false || $v === null) ? 0 : $v;
        }

        private static function pct($num, $den) {
            return ($den > 0) ? round(100 * $num / $den, 1) : 0;
        }

        // SF-1 coverage + SF-3 spec-citation + SF-6 deficit count with a per-reason breakdown.
        private function summary($sdb) {
            $nonshadow = self::scalar($sdb, "SELECT COUNT(*) FROM sf_file WHERE is_shadow=0");
            $covered   = self::scalar($sdb, "SELECT COUNT(DISTINCT covers) FROM sf_shadow");
            $allfiles  = self::scalar($sdb, "SELECT COUNT(*) FROM sf_file");
            $cited     = self::scalar($sdb, "SELECT COUNT(*) FROM sf_file WHERE cites_spec=1");
            $deficits  = self::scalar($sdb, "SELECT COUNT(*) FROM sf_deficit");

            $out  = "<h2>Summary</h2>\n<ul class='srclist'>\n";
            $out .= "<li><strong>SF-1 test coverage:</strong> " . self::esc(self::pct($covered, $nonshadow)) . "% &mdash; <strong>"
                  . self::esc($covered) . "</strong> of <strong>" . self::esc($nonshadow) . "</strong> non-shadow files covered by a shadow-doc</li>\n";
            $out .= "<li><strong>SF-3 spec-citation:</strong> " . self::esc(self::pct($cited, $allfiles)) . "% &mdash; <strong>"
                  . self::esc($cited) . "</strong> of <strong>" . self::esc($allfiles) . "</strong> files cite a spec</li>\n";
            $out .= "<li><strong>SF-6 deficits:</strong> <strong>" . self::esc($deficits) . "</strong> file(s) lacking a test and/or a spec</li>\n";

            $by = $sdb->query("SELECT reason, COUNT(*) AS n FROM sf_deficit GROUP BY reason ORDER BY reason")->fetchAll(PDO::FETCH_ASSOC);
            if ($by) {
                $parts = array();
                foreach ($by as $r) {
                    $parts[] = "<a href='?page=shadowforge&reason=" . self::esc(urlencode($r['reason'])) . "'>" . self::esc($r['reason']) . "</a>&nbsp;" . self::esc($r['n']);
                }
                $out .= "<li>by reason: " . implode(" &middot; ", $parts) . "</li>\n";
            }
            return $out . "</ul>\n";
        }

        // reason + repo facet form; preserves the current selection.
        private function facet_form($sdb) {
            $reason = isset($_GET['reason']) ? (string) $_GET['reason'] : '';
            $repo   = isset($_GET['repo'])   ? (string) $_GET['repo']   : '';
            $out  = "<form method='get' class='shadowforge-facets' style='margin:.5rem 0'>";
            $out .= "<input type='hidden' name='page' value='shadowforge'>";
            $out .= " reason <select name='reason'>";
            foreach (array('', 'no-test', 'no-spec', 'no-test+no-spec') as $r) {
                $sel = ($r === $reason) ? " selected" : "";
                $lbl = ($r === '') ? '(any)' : $r;
                $out .= "<option value='" . self::esc($r) . "'" . $sel . ">" . self::esc($lbl) . "</option>";
            }
            $out .= "</select> repo <select name='repo'>";
            $out .= "<option value=''" . ($repo === '' ? " selected" : "") . ">(any)</option>";
            $repos = $sdb->query("SELECT DISTINCT repo FROM sf_file ORDER BY repo")->fetchAll(PDO::FETCH_COLUMN);
            foreach ($repos as $rp) {
                $sel = ((string) $rp === $repo) ? " selected" : "";
                $out .= "<option value='" . self::esc($rp) . "'" . $sel . ">" . self::esc($rp) . "</option>";
            }
            $out .= "</select> <button type='submit'>filter</button></form>\n";
            return $out;
        }

        // DEFAULT / ?reason / ?repo — the deficit backlog. NULL-safe COALESCE(:x,'')='' optional-facet
        // guards, so an omitted (NULL-bound) facet and an empty-string facet both mean "no filter".
        private function deficits($sdb) {
            $reason = isset($_GET['reason']) ? (string) $_GET['reason'] : '';
            $repo   = isset($_GET['repo'])   ? (string) $_GET['repo']   : '';
            $st = $sdb->prepare(
                "SELECT path, repo, reason, detail FROM sf_deficit
                 WHERE (COALESCE(:reason,'')='' OR reason=:reason) AND (COALESCE(:repo,'')='' OR repo=:repo)
                 ORDER BY reason, repo, path LIMIT 300");
            $st->execute(array(':reason' => $reason, ':repo' => $repo));
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);

            $facet = array();
            if ($reason !== '') { $facet[] = "reason=" . self::esc($reason); }
            if ($repo   !== '') { $facet[] = "repo=" . self::esc($repo); }
            $suffix = $facet ? " &middot; " . implode(" &middot; ", $facet) . " <a href='?page=shadowforge'>&times;</a>" : "";
            $out = "<h2>Deficit backlog" . $suffix . "</h2>\n";
            if (!$rows) { return $out . "<p>(no deficits)</p>\n"; }
            $out .= "<table class='shadowforge-deficits' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= "<tr><th style='text-align:left'>path</th><th style='text-align:left'>repo</th><th style='text-align:left'>reason</th><th style='text-align:left'>detail</th></tr>\n";
            foreach ($rows as $r) {
                $out .= "<tr>"
                      . "<td><a href='?page=shadowforge&file=" . self::esc(urlencode($r['path'])) . "'>" . self::esc($r['path']) . "</a></td>"
                      . "<td><a href='?page=shadowforge&repo=" . self::esc(urlencode($r['repo'])) . "'>" . self::esc($r['repo']) . "</a></td>"
                      . "<td><a href='?page=shadowforge&reason=" . self::esc(urlencode($r['reason'])) . "'>" . self::esc($r['reason']) . "</a></td>"
                      . "<td>" . self::esc($r['detail']) . "</td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }

        // ?file=<path> — which shadow-docs cover this file (+ the file's own spec_refs).
        private function by_file($sdb, $file) {
            $out = "<h2>Shadows covering <code>" . self::esc($file) . "</code> <a href='?page=shadowforge'>&times;</a></h2>\n";
            $fst = $sdb->prepare("SELECT spec_refs FROM sf_file WHERE path=:file LIMIT 1");
            $fst->execute(array(':file' => $file));
            $fref = $fst->fetchColumn();
            if ($fref !== false && $fref !== null && $fref !== '') {
                $out .= "<p>file spec_refs: <code>" . self::esc($fref) . "</code></p>\n";
            }
            $st = $sdb->prepare("SELECT shadow, spec_refs FROM sf_shadow WHERE covers=:file ORDER BY shadow LIMIT 200");
            $st->execute(array(':file' => $file));
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);
            if (!$rows) { return $out . "<p>(no shadow-doc covers this file)</p>\n"; }
            $out .= "<table class='shadowforge-covers' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= "<tr><th style='text-align:left'>shadow</th><th style='text-align:left'>spec_refs</th></tr>\n";
            foreach ($rows as $r) {
                $out .= "<tr><td>" . self::esc($r['shadow']) . "</td><td><code>" . self::esc($r['spec_refs']) . "</code></td></tr>\n";
            }
            return $out . "</table>\n";
        }

        // the exemplars that DO cite a spec.
        private function spec_cited($sdb) {
            $rows = $sdb->query("SELECT path, spec_refs FROM sf_file WHERE cites_spec=1 ORDER BY path LIMIT 40")->fetchAll(PDO::FETCH_ASSOC);
            $out = "<h2>Spec-cited exemplars</h2>\n";
            if (!$rows) { return $out . "<p>(no files cite a spec yet)</p>\n"; }
            $out .= "<table class='shadowforge-cited' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= "<tr><th style='text-align:left'>path</th><th style='text-align:left'>spec_refs</th></tr>\n";
            foreach ($rows as $r) {
                $out .= "<tr>"
                      . "<td><a href='?page=shadowforge&file=" . self::esc(urlencode($r['path'])) . "'>" . self::esc($r['path']) . "</a></td>"
                      . "<td><code>" . self::esc($r['spec_refs']) . "</code></td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }
    }
}
?>
