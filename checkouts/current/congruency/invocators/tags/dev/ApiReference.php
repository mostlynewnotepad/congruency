<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * ApiReference — the standardized, data-driven API reference (?page=api).
 *
 * Invoked as <<<ApiReference>>>. Renders EVERY row of `api_routes` (the named-route
 * contract: name, method, sql, auth, params, meta) as a browsable reference, grouped
 * by route-name prefix. For each route the response SHAPE is DERIVED from its SQL:
 *   SELECT ... FROM ...  -> {"route":"…","rows":[ <the SELECTed columns> ]}
 *   anything else        -> {"route":"…","affected":<n>,"rowid":<id>}
 * mirroring boot/rest.php's dispatch. Also documents the generic ?api=<table> CRUD
 * layer and the admin DENYLIST (tables kept off the public REST surface).
 *
 * SECURITY: a route's sql / meta / params are DATA — htmlspecialchars()'d escape-first
 * before flowing back through execute_all_tags, so a stored <<<Tag>>> stays inert.
 */
if (!class_exists("ApiReference")) {
    class ApiReference implements Tag_Interface {

        private $arguments;
        public function __construct($arguments) { $this->arguments = $arguments; }
        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

        // admin-only tables kept off the public REST surface (mirrors boot/rest.php's denylist).
        private static $denylist = array('code_blobs', 'code_refs', 'doc_blobs', 'doc_refs',
                                          'Login_Password', 'User_Group_Mappings', 'Group_Privileges', 'api_keys');

        public function get_document() {
            try {
                if (!defined('CONGRUENCY_SQLITE')) { return "<p>ApiReference: no DB.</p>"; }
                $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
                $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                if (!$db->query("SELECT name FROM sqlite_master WHERE type='table' AND name='api_routes'")->fetch()) {
                    return "<p>No <code>api_routes</code> table yet.</p>";
                }
                $rows = $db->query("SELECT name, method, sql, auth, params, meta FROM api_routes ORDER BY name")->fetchAll(PDO::FETCH_ASSOC);
                return $this->intro($rows) . $this->groups($rows) . $this->crudSection();
            } catch (\Throwable $e) {
                return "<div class='cy-form-error'>ApiReference error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        private function intro($rows) {
            $n = count($rows);
            return "<p>The data-driven API surface &mdash; <strong>" . (int) $n . "</strong> named routes, each a row in "
                 . "<code>api_routes</code>. Call one as <code>?route=&lt;name&gt;</code>: it runs that row's parameterized "
                 . "SQL with your declared <code>:params</code> bound. A <code>SELECT</code> route replies "
                 . "<code>{&quot;route&quot;:&hellip;,&quot;rows&quot;:[&hellip;]}</code>; a write route replies "
                 . "<code>{&quot;route&quot;:&hellip;,&quot;affected&quot;:n,&quot;rowid&quot;:id}</code>. "
                 . "<code>auth</code> is <em>public</em> for reads, <em>token</em>/<em>admin</em> for writes.</p>\n";
        }

        private static function groupOf($name) {
            $p = '';
            if (preg_match('/^[a-zA-Z]+/', (string) $name, $m)) { $p = strtolower($m[0]); }
            $tickets = array('ticket' => 1, 'mandate' => 1, 'guarantee' => 1, 'binding' => 1);
            $prov    = array('run' => 1, 'journey' => 1, 'artifact' => 1, 'edge' => 1, 'children' => 1, 'policy' => 1, 'agent' => 1);
            $repos   = array('repo' => 1, 'source' => 1, 'doc' => 1);
            if (isset($tickets[$p])) { return 'Tickets'; }
            if (isset($prov[$p]))    { return 'Provenance'; }
            if (isset($repos[$p]))   { return 'Repos & Docs'; }
            return 'Process / Other';
        }

        private function groups($rows) {
            $order = array('Tickets', 'Provenance', 'Repos & Docs', 'Process / Other');
            $buckets = array();
            foreach ($order as $g) { $buckets[$g] = array(); }
            foreach ($rows as $r) { $buckets[self::groupOf($r['name'])][] = $r; }
            $out = "";
            foreach ($order as $g) {
                if (!$buckets[$g]) { continue; }
                $out .= "<h2>" . self::esc($g) . "</h2>\n" . $this->table($buckets[$g]);
            }
            return $out;
        }

        private function table($rows) {
            $out = "<table class='api-ref' border='1' cellspacing='0' cellpadding='4'>\n"
                 . "<thead><tr><th>route</th><th>method</th><th>auth</th><th>params</th><th>response shape</th><th>meta</th></tr></thead>\n<tbody>\n";
            foreach ($rows as $r) {
                $shape  = self::deriveShape((string) $r['name'], (string) $r['sql']);
                $params = trim((string) $r['params']) === '' ? '{}' : (string) $r['params'];
                $out .= "<tr>"
                      . "<td><code>" . self::esc($r['name']) . "</code></td>"
                      . "<td>" . self::esc($r['method']) . "</td>"
                      . "<td>" . self::esc($r['auth']) . "</td>"
                      . "<td><code>" . self::esc($params) . "</code></td>"
                      . "<td><code>" . self::esc($shape) . "</code></td>"
                      . "<td>" . self::esc($r['meta']) . "</td>"
                      . "</tr>\n";
            }
            return $out . "</tbody>\n</table>\n";
        }

        // Derive the response shape from the route SQL, mirroring boot/rest.php:
        //   SELECT ... -> {"route":"…","rows":[ <columns parsed from SELECT … FROM> ]}
        //   else       -> {"route":"…","affected":<n>,"rowid":<id>}
        private static function deriveShape($name, $sql) {
            if (stripos(ltrim($sql), 'select') === 0) {
                $q = array();
                foreach (self::selectCols($sql) as $c) { $q[] = '"' . $c . '"'; }
                return '{"route":"' . $name . '","rows":[' . implode(', ', $q) . ']}';
            }
            return '{"route":"' . $name . '","affected":<n>,"rowid":<id>}';
        }

        // Parse the output column names from a SELECT: the top-level comma list between SELECT and FROM,
        // taking each item's AS-alias or trailing identifier.
        private static function selectCols($sql) {
            $s = trim((string) $sql);
            if (preg_match('/^select\s+(distinct\s+)?/i', $s, $m)) { $s = substr($s, strlen($m[0])); }
            $depth = 0; $len = strlen($s); $fromPos = -1;
            for ($i = 0; $i < $len; $i++) {
                $ch = $s[$i];
                if ($ch === '(') { $depth++; }
                elseif ($ch === ')') { $depth--; }
                elseif ($depth === 0 && strcasecmp(substr($s, $i, 4), 'from') === 0) {
                    $before = ($i === 0) ? ' ' : $s[$i - 1];
                    $after  = ($i + 4 < $len) ? $s[$i + 4] : ' ';
                    if (!ctype_alnum($before) && $before !== '_' && !ctype_alnum($after) && $after !== '_') { $fromPos = $i; break; }
                }
            }
            $colPart = ($fromPos >= 0) ? substr($s, 0, $fromPos) : $s;
            $names = array();
            foreach (self::splitTop($colPart) as $c) {
                $c = trim($c);
                if ($c === '') { continue; }
                if (preg_match('/\s+as\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*$/i', $c, $m)) { $names[] = $m[1]; }
                elseif ($c !== '*' && preg_match('/([a-zA-Z_][a-zA-Z0-9_]*)\s*$/', $c, $m)) { $names[] = $m[1]; }
                else { $names[] = $c; }
            }
            return $names;
        }

        // Split on top-level commas (parens-aware) so column expressions like func(a, b) stay intact.
        private static function splitTop($s) {
            $out = array(); $buf = ''; $depth = 0; $len = strlen($s);
            for ($i = 0; $i < $len; $i++) {
                $ch = $s[$i];
                if ($ch === '(') { $depth++; $buf .= $ch; }
                elseif ($ch === ')') { $depth--; $buf .= $ch; }
                elseif ($ch === ',' && $depth === 0) { $out[] = $buf; $buf = ''; }
                else { $buf .= $ch; }
            }
            if (trim($buf) !== '') { $out[] = $buf; }
            return $out;
        }

        private function crudSection() {
            $out  = "<h2>Generic <code>?api=&lt;table&gt;</code> CRUD</h2>\n";
            $out .= "<p>Beyond the named routes, every non-denylisted table is reachable through a generic CRUD layer "
                  . "(the fast internal path). Table and column names are validated against the schema; reads are public, "
                  . "writes need a token / admin session:</p>\n";
            $out .= "<table class='api-ref' border='1' cellspacing='0' cellpadding='4'>\n"
                  . "<thead><tr><th>call</th><th>does</th></tr></thead>\n<tbody>\n";
            $crud = array(
                array('GET ?api=tables', 'list the reachable tables'),
                array('GET ?api=<table>[&<col>=<v>&order=<c>.<dir>&limit=&p=&per=]', 'filtered / paginated rows'),
                array('GET ?api=<table>&id=<pk>', 'a single row by primary key'),
                array('POST ?api=<table>', 'create a row from the JSON body (real columns only)'),
                array('PUT|PATCH ?api=<table>&id=<pk>', 'update a row by primary key'),
                array('DELETE ?api=<table>&id=<pk>', 'delete a single row by primary key'),
            );
            foreach ($crud as $c) {
                $out .= "<tr><td><code>" . self::esc($c[0]) . "</code></td><td>" . self::esc($c[1]) . "</td></tr>\n";
            }
            $out .= "</tbody>\n</table>\n";
            $out .= "<h3>Admin denylist &mdash; not in REST</h3>\n";
            $out .= "<p>These tables &mdash; the self-hosting archive plus the auth / key tables &mdash; are "
                  . "<strong>admin-only</strong> and never reachable through <code>?api=</code> or generic writes:</p>\n<ul class='denylist'>\n";
            foreach (self::$denylist as $t) {
                $out .= "<li><code>" . self::esc($t) . "</code> &mdash; admin-only, not in REST</li>\n";
            }
            return $out . "</ul>\n";
        }
    }
}
?>
