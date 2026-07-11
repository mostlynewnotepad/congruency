<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * ForgeView — congruency reflects the LOCAL forge store (~/bin/config/forge/forge.db), a SEPARATE
 * sqlite database from CONGRUENCY_SQLITE. A read-only reflection of forge's own append-only actions
 * journal + content-addressed artifacts registry + bare remotes/archives.
 *
 * Invoked as <<<ForgeView>>> on ?page=forge. Data source: forge.db, resolved from
 * getenv('FORGE_DB') ?: $HOME/bin/config/forge/forge.db, opened through a SECOND PDO handle with
 * `PRAGMA query_only=1` so the reflection can NEVER mutate forge. If the db is absent/unreadable the
 * page degrades gracefully ("forge db not found at <path>"), it never crashes the page.
 *   ?page=forge                 -> summary + recent actions + artifacts
 *   ?page=forge&action=<verb>   -> filter the actions table to one action verb (bound :param)
 *   ?page=forge&name=<artifact> -> filter the artifacts table to one artifact name (bound :param)
 *
 * SECURITY: EVERY value read from forge.db (action/target/detail/meta, artifact names, source refs)
 * is htmlspecialchars()'d before it flows back through execute_all_tags, so a stored <<<Tag>>> or
 * <script> in a forge action detail stays inert (escape-first). Facets are bound, never interpolated.
 */
if (!class_exists("ForgeView")) {
    class ForgeView implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

        private static function forge_path() {
            $p = getenv('FORGE_DB');
            if ($p !== false && $p !== '') { return $p; }
            return getenv('HOME') . '/bin/config/forge/forge.db';
        }

        public function get_document() {
            $path = self::forge_path();
            if (!is_file($path) || !is_readable($path)) {
                return "<p class='cy-form-error'>forge db not found at <code>" . self::esc($path) . "</code></p>";
            }
            try {
                $fdb = new PDO('sqlite:' . $path);
                $fdb->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                $fdb->exec('PRAGMA query_only=1');   // read-only: the reflection can never mutate forge
            } catch (\Throwable $e) {
                return "<p class='cy-form-error'>forge db not readable at <code>" . self::esc($path) . "</code></p>";
            }
            try {
                return $this->summary($fdb) . $this->actions($fdb) . $this->artifacts($fdb);
            } catch (\Throwable $e) {
                return "<div class='cy-form-error'>ForgeView error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        private static function scalar($fdb, $sql) {
            $v = $fdb->query($sql)->fetchColumn();
            return ($v === false || $v === null) ? 0 : $v;
        }

        private static function status_color($s) {
            switch ((string) $s) {
                case 'ok':      return '#2e7d32';
                case 'started': return '#1565c0';
                case 'fail':    return '#c62828';
                case 'skipped': return '#8d6e00';
                default:        return '#555';
            }
        }

        private function summary($fdb) {
            $acts  = self::scalar($fdb, "SELECT COUNT(*) FROM actions");
            $runs  = self::scalar($fdb, "SELECT COUNT(DISTINCT run_id) FROM actions");
            $arts  = self::scalar($fdb, "SELECT COUNT(*) FROM artifacts");
            $names = self::scalar($fdb, "SELECT COUNT(DISTINCT name) FROM artifacts");
            $size  = self::scalar($fdb, "SELECT COALESCE(SUM(size),0) FROM artifacts");

            $out  = "<h2>Summary</h2>\n<ul class='srclist'>\n";
            $out .= "<li><strong>" . self::esc($acts) . "</strong> actions across <strong>" . self::esc($runs) . "</strong> runs</li>\n";
            $out .= "<li><strong>" . self::esc($arts) . "</strong> artifacts (<strong>" . self::esc($names) . "</strong> distinct names), <strong>" . self::esc($size) . "</strong> bytes total</li>\n";

            $byst = $fdb->query("SELECT status, COUNT(*) AS n FROM actions GROUP BY status ORDER BY status")->fetchAll(PDO::FETCH_ASSOC);
            if ($byst) {
                $parts = array();
                foreach ($byst as $r) {
                    $parts[] = "<a href='?page=forge&status=" . self::esc(urlencode($r['status'])) . "'><span style='color:" . self::status_color($r['status']) . "'>" . self::esc($r['status']) . "</span></a>&nbsp;" . self::esc($r['n']);
                }
                $out .= "<li>status: " . implode(" &middot; ", $parts) . "</li>\n";
            }
            $out .= "</ul>\n";

            // the omni corpus / bare archives: archive.register row(s) if present
            $ar = $fdb->query("SELECT id, target, status, substr(detail,1,120) AS detail FROM actions WHERE action='archive.register' ORDER BY id DESC LIMIT 5")->fetchAll(PDO::FETCH_ASSOC);
            if ($ar) {
                $out .= "<p><strong>Archives (archive.register):</strong></p>\n<ul class='srclist'>\n";
                foreach ($ar as $r) {
                    $out .= "<li>&#128230; " . self::esc($r['target']) . " <span style='color:#888;font-size:.85em'>" . self::esc($r['status']) . " &middot; " . self::esc($r['detail']) . "</span></li>\n";
                }
                $out .= "</ul>\n";
            }
            return $out;
        }

        private function actions($fdb) {
            $action = isset($_GET['action']) ? (string) $_GET['action'] : '';
            $sql = "SELECT id, ts, run_id, action, target, status, substr(detail,1,80) AS detail FROM actions";
            $run = isset($_GET['run']) ? (string) $_GET['run'] : '';
            $status = isset($_GET['status']) ? (string) $_GET['status'] : '';
            $where = array();
            $params = array();
            if ($action !== '') { $where[] = "action = :action"; $params[':action'] = $action; }
            if ($run !== '') { $where[] = "run_id = :run"; $params[':run'] = $run; }
            if ($status !== '') { $where[] = "status = :status"; $params[':status'] = $status; }
            if ($where) { $sql .= " WHERE " . implode(" AND ", $where); }
            $sql .= " ORDER BY id DESC LIMIT 40";
            $st = $fdb->prepare($sql);
            $st->execute($params);
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);

            $out = "<h2>Recent actions" . (($action !== '' || $run !== '' || $status !== '') ? " &middot;" . ($action !== '' ? " action " . self::esc($action) : "") . ($run !== '' ? " run " . self::esc($run) : "") . ($status !== '' ? " status " . self::esc($status) : "") . " <a href='?page=forge'>&times;</a>" : "") . "</h2>\n";
            if (!$rows) { return $out . "<p>(no actions)</p>\n"; }
            $out .= "<table class='forge-actions' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= "<tr><th style='text-align:left'>id</th><th style='text-align:left'>ts</th><th style='text-align:left'>run</th><th style='text-align:left'>action</th><th style='text-align:left'>target</th><th style='text-align:left'>status</th><th style='text-align:left'>detail</th></tr>\n";
            foreach ($rows as $r) {
                $out .= "<tr>"
                      . "<td>" . self::esc($r['id']) . "</td>"
                      . "<td>" . self::esc($r['ts']) . "</td>"
                      . "<td><a href='?page=forge&run=" . self::esc(urlencode($r['run_id'])) . "'>" . self::esc($r['run_id']) . "</a></td>"
                      . "<td><a href='?page=forge&action=" . self::esc(urlencode($r['action'])) . "'>" . self::esc($r['action']) . "</a></td>"
                      . "<td>" . self::esc($r['target']) . "</td>"
                      . "<td style='color:" . self::status_color($r['status']) . "'>" . self::esc($r['status']) . "</td>"
                      . "<td>" . self::esc($r['detail']) . "</td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }

        private function artifacts($fdb) {
            $name = isset($_GET['name']) ? (string) $_GET['name'] : '';
            $artkind = isset($_GET['artkind']) ? (string) $_GET['artkind'] : '';
            $sql = "SELECT id, name, version, kind, size, substr(sha256,1,12) AS sha, source_repo, source_commit FROM artifacts";
            $awhere = array();
            $params = array();
            if ($name !== '') { $awhere[] = "name = :name"; $params[':name'] = $name; }
            if ($artkind !== '') { $awhere[] = "kind = :artkind"; $params[':artkind'] = $artkind; }
            if ($awhere) { $sql .= " WHERE " . implode(" AND ", $awhere); }
            $sql .= " ORDER BY id DESC LIMIT 40";
            $st = $fdb->prepare($sql);
            $st->execute($params);
            $rows = $st->fetchAll(PDO::FETCH_ASSOC);

            $out = "<h2>Artifacts" . (($name !== '' || $artkind !== '') ? " &middot;" . ($name !== '' ? " name " . self::esc($name) : "") . ($artkind !== '' ? " kind " . self::esc($artkind) : "") . " <a href='?page=forge'>&times;</a>" : "") . "</h2>\n";
            if (!$rows) { return $out . "<p>(no artifacts)</p>\n"; }
            $out .= "<table class='forge-artifacts' style='border-collapse:collapse;width:100%;font-size:.85rem'>\n";
            $out .= "<tr><th style='text-align:left'>name</th><th style='text-align:left'>version</th><th style='text-align:left'>kind</th><th style='text-align:left'>size</th><th style='text-align:left'>sha256</th><th style='text-align:left'>source</th></tr>\n";
            foreach ($rows as $r) {
                $src = self::esc($r['source_repo']);
                if ($r['source_commit'] !== null && $r['source_commit'] !== '') {
                    $src .= " <span style='color:#888'>@ " . self::esc(substr((string) $r['source_commit'], 0, 12)) . "</span>";
                }
                $out .= "<tr>"
                      . "<td><a href='?page=forge&name=" . self::esc(urlencode($r['name'])) . "'>" . self::esc($r['name']) . "</a></td>"
                      . "<td>" . self::esc($r['version']) . "</td>"
                      . "<td><a href='?page=forge&artkind=" . self::esc(urlencode($r['kind'])) . "'>" . self::esc($r['kind']) . "</a></td>"
                      . "<td>" . self::esc($r['size']) . "</td>"
                      . "<td><code>" . self::esc($r['sha']) . "</code></td>"
                      . "<td>" . $src . "</td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }
    }
}
?>
