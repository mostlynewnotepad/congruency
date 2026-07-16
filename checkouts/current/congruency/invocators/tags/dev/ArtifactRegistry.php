<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * ArtifactRegistry — the artifact registry, made VIEWABLE and INTERACTIVE. Invoked as
 * <<<ArtifactRegistry>>> on ?page=artifacts. Reading the registry should not require a shell:
 * this tag is the door, `sqlite3` is not.
 *
 * ── THE DATA ─────────────────────────────────────────────────────────────────────────────────
 * `ticket_artifacts` (id, ts, ticket_id, name, version, forge_sha, kind) — the TICKET-SIDE
 * artifact registry: congruency holds the metadata/provenance, forge holds the blob
 * (migrations/0014_ticket_artifacts.sql:7-16). Rows arrive ONLY through the governed
 * `artifact.record` route (0014_ticket_artifacts.sql:19-26); ticket #455 (the VM registry —
 * `tools/vm_registry.py --record`, which tags every VM image kind='forge-vm', vm_registry.py:265)
 * and ticket #457 (the mint hook) are what call it. This tag DISPLAYS the registry and nothing
 * else: it never registers, never repairs, never writes.
 *
 * ONE DIFFERENCE FROM ITS SIBLINGS: ForgeView/OmniExplorer/ShadowForge open a SECOND PDO to a
 * separate database (forge.db / omni_index.db). `ticket_artifacts` lives in the PRIMARY congruency
 * database, so this tag uses the ordinary CONGRUENCY_SQLITE handle, exactly as TicketList.php does.
 * READ-ONLY all the same: every statement in this file is a SELECT, and the connection is pinned
 * with `PRAGMA query_only = TRUE` (TicketList.php:133-138), so a stray non-SELECT would raise
 * rather than mutate the shared db. This file contains no write statement of any kind — grep it
 * for the three write verbs and the count is zero, comments included.
 *
 * ── KIND IS THE TAG. THREE VIEWS, EACH A LINK AWAY FROM THE OTHERS ───────────────────────────
 *   ?page=artifacts             the INDEX. One row per kind with its count (the tags), every kind
 *                               a link to its filtered view; plus the most recent artifacts
 *                               overall (ts DESC), each linking to its detail.
 *   ?page=artifacts&kind=<k>    the ITEMS of that tag: name, version, short forge_sha, ts, minting
 *                               ticket. Every row links to the detail; the ticket id links to that
 *                               ticket (?page=graphs&ticket=<id>, as GraphNode.php:152 does).
 *                               A kind nothing is registered under says so and links back.
 *   ?page=artifacts&sha=<sha>   ONE artifact, the interactive leaf: its identity (name, kind,
 *                               version, the FULL forge_sha), EVERY LOCATION the same forge_sha was
 *                               registered at, the minting ticket(s), and first/last seen. An
 *                               unregistered sha says "not registered" and links back.
 * `sha` wins over `kind` when both are present — the leaf is the more specific view.
 *
 * WHY A LOCATION IS A ROW: the registry is content-addressed, so the SAME BYTES registered twice
 * are ONE artifact with SEVERAL locations — that is the entire point of content addressing. In
 * this table a location IS a row: a (ticket_id, name, version, kind, ts) tuple that registered
 * that sha. The leaf therefore lists every row sharing the sha, and reports identity as a SET:
 * the same blob may legitimately be registered under two names, and the page shows both rather
 * than silently picking one.
 *
 * ── WHY THE SHA IS SHOWN IN FULL: IT IS A LIVE HANDLE, NOT DECORATION ────────────────────────
 * `forge_sha` is a sha256 content address (0014_ticket_artifacts.sql:13), and it is exactly what
 * the universal resolver (#193, DONE) takes as input:
 *     python3 tools/resolver.py <forge_sha>
 * A 64-hex identifier classifies as kind 'sha256' (resolver.py:369-370) and fans out to the probes
 * ['content-sha256', 'forge-artifacts', 'git-object-db'] (resolver.py:388); the 'forge-artifacts'
 * probe answers it with `SELECT filename FROM artifacts WHERE lower(sha256) = ?` (resolver.py:
 * 551-553). So the page and the resolver are two doors on the same content address: this page
 * shows every ticket-side location the blob was registered at, the resolver shows every place the
 * blob itself lives. Copy the sha off this page straight into that command — that is why it is
 * rendered in full, and never truncated on the leaf.
 *
 * NB, so no reader is misled about which table the resolver reads: the 'forge-artifacts' probe
 * reads FORGE's own db (`forge.db`, table `artifacts`, keyed on sha256), NOT this
 * `ticket_artifacts` table — resolver.py contains no reference to `ticket_artifacts` at all, a
 * gap tools/vm_registry.py:102-109 documents as well. The two doors agree because both key on the
 * same sha256 content address, not because either reads the other. For `ticket_artifacts` this
 * page is the only door — which is the point of the ticket that built it.
 *
 * ── SECURITY (the posture ForgeView/OmniExplorer/TreeView already hold) ──────────────────────
 * ESCAPE-FIRST: EVERY value out of the db (name, kind, version, sha, ts, ticket id) is passed
 * through esc() BEFORE it flows back through execute_all_tags, so a stored <<<Tag>>> or <script>
 * in an artifact name stays INERT — the tag engine re-parses this output, so an unescaped value
 * would be re-executed. Do not remove an esc() call.
 * BOUND FACETS: the ?kind= and ?sha= facets come from $_GET and are BOUND (:kind, :sha), never
 * interpolated into SQL. Values placed into links are urlencode()'d and then esc()'d, so a value
 * carrying '&' or '"' can escape neither the query string nor the attribute. The only values ever
 * concatenated into SQL text are this class's own integer LIMIT constants — never a request value.
 * DEGRADE, NEVER CRASH: a missing CONGRUENCY_SQLITE, an unopenable db, an absent table (a checkout
 * where 0014 never ran) and an empty table each render a plain message; any other throwable is
 * caught and shown as one line. This tag never takes the page down.
 *
 * ── EMPTY IS A FIRST-CLASS STATE ─────────────────────────────────────────────────────────────
 * The registry may hold zero rows (it did when this tag was written; #455 has since registered
 * its VM images). An empty table renders a clear "no artifacts registered yet" that names
 * #455/#457 as what fills it — never an error, never a blank page — and the page lights up
 * automatically as rows arrive, with no change here.
 *
 * ── HOW IT REACHES ?page=artifacts ───────────────────────────────────────────────────────────
 * This file is the RENDERER only. As with every other page, a Document_Templates row holds the
 * page shell and a Documents row binds the slug to it (the shape of migrations/0021_forge_page.sql
 * for ?page=forge); the template is what splices in <<<ArtifactRegistry>>>, and SiteMap.php picks
 * a page up from the Documents table on its own. That binding is data, not this tag, and is not
 * this ticket's deliverable.
 */
if (!class_exists("ArtifactRegistry")) {
    class ArtifactRegistry implements Tag_Interface {

        /* Row caps. These are class constants, never request values — they are the ONLY things
           this file concatenates into SQL text. Whenever a cap actually hides rows, the view
           says so out loud (a silent truncation would read as "that is all there is"). */
        const RECENT_LIMIT = 20;    // most-recent artifacts on the index
        const ITEM_LIMIT   = 200;   // items listed for one kind
        const LOC_LIMIT    = 200;   // locations listed for one sha

        const SHORT_SHA = 12;                 // short form, as ForgeView.php:150 renders one
        const UNKINDED  = '(unkinded)';       // label for a row whose kind is NULL or ''
        const NO_SHA    = '(no forge_sha)';   // label for a row with no content address

        private $arguments;

        // arguments may be null when rendered standalone (e.g. by TagList: new ArtifactRegistry(null))
        public function __construct($arguments) { $this->arguments = $arguments; }

        private static function esc($s) { return htmlspecialchars((string) $s, ENT_QUOTES); }

        /* A read-only PDO handle on the PRIMARY congruency db. `query_only` blocks every write on
           this connection, so this tag cannot mutate the registry it displays even by mistake. */
        private function db() {
            $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
            $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            $db->exec('PRAGMA query_only = TRUE');
            return $db;
        }

        // ── query helpers (every facet BOUND; nothing from $_GET is ever interpolated) ────────

        private static function rows($db, $sql, $params = array()) {
            $st = $db->prepare($sql);
            $st->execute($params);
            return $st->fetchAll(PDO::FETCH_ASSOC);
        }

        private static function scalar($db, $sql, $params = array()) {
            $st = $db->prepare($sql);
            $st->execute($params);
            $v = $st->fetchColumn();
            return ($v === false || $v === null) ? 0 : $v;
        }

        /* Is the registry table present at all? A checkout where 0014 never ran has no
           `ticket_artifacts`, which is a DIFFERENT state from "registered nothing yet" — the
           reader is told which one they are looking at rather than left guessing. */
        private static function hasTable($db) {
            try {
                $st = $db->prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n LIMIT 1");
                $st->execute(array(':n' => 'ticket_artifacts'));
                return $st->fetchColumn() !== false;
            } catch (\Throwable $e) {
                return false;
            }
        }

        // ── presentation helpers ─────────────────────────────────────────────────────────────

        /* One URL into this page. Each facet value is urlencode()'d (it cannot break out of the
           query string) and then esc()'d (it cannot break out of the attribute); '&amp;' separates
           the facets, as GraphNode.php:152 does. The keys are this class's own literals. */
        private static function url($facets = array()) {
            $u = "?page=artifacts";
            foreach ($facets as $k => $v) {
                $u .= "&amp;" . $k . "=" . self::esc(urlencode((string) $v));
            }
            return $u;
        }

        /* A link to the ticket that minted a registration — the per-ticket graph page, the same
           target GraphNode.php:152 uses. A row with no ticket_id says so rather than linking to #0. */
        private static function ticketLink($id) {
            if ($id === null || $id === '') { return "<span class='areg-dim'>(no ticket)</span>"; }
            $n = (int) $id;
            return "<a href='?page=graphs&amp;ticket=" . self::esc($n) . "'>#" . self::esc($n) . "</a>";
        }

        // ticket_artifacts.ts is epoch seconds (0014_ticket_artifacts.sql:22 writes strftime('%s','now')).
        private static function stamp($ts) {
            $t = (int) $ts;
            return ($t > 0) ? (gmdate('Y-m-d H:i', $t) . ' UTC') : '—';
        }

        private static function kindLabel($k) { return ($k === '') ? self::UNKINDED : $k; }

        private static function shortSha($sha) {
            $s = (string) $sha;
            if ($s === '') { return self::NO_SHA; }
            return (strlen($s) > self::SHORT_SHA) ? substr($s, 0, self::SHORT_SHA) : $s;
        }

        private static function orDash($v) {
            $s = ($v === null) ? '' : (string) $v;
            return ($s === '') ? '—' : $s;
        }

        /* The distinct values of one column across every location, in first-seen order. Identity is
           a SET, not a single value: the same bytes may be registered under two names, and the leaf
           shows both rather than silently picking one. Values are escaped by the caller. */
        private static function distinctVals($locs, $col, $blank) {
            $seen = array(); $out = array();
            foreach ($locs as $r) {
                $v = ($r[$col] === null) ? '' : (string) $r[$col];
                if ($v === '') { $v = $blank; }
                if (!isset($seen[$v])) { $seen[$v] = true; $out[] = $v; }
            }
            return $out;
        }

        /* Escape each value THEN join with the separator — escaping the joined string would turn
           the separator into a literal entity on the page (the trap TreeView.php:271-274 names). */
        private static function escJoin($vals, $sep, $wrap = '') {
            $out = array();
            foreach ($vals as $v) {
                $out[] = ($wrap === '') ? self::esc($v) : ("<" . $wrap . ">" . self::esc($v) . "</" . $wrap . ">");
            }
            return implode($sep, $out);
        }

        private function css() {
            $out  = "<style>";
            $out .= ".areg{width:100%;border-collapse:collapse;font-size:.82rem;margin:.2rem 0 .8rem}";
            $out .= ".areg th{text-align:left;border-bottom:2px solid #d8d2c4;padding:.35rem .5rem;color:#555;font-weight:600;white-space:nowrap}";
            $out .= ".areg td{border-bottom:1px solid #eee4d0;padding:.35rem .5rem;vertical-align:top}";
            $out .= ".areg .num{text-align:right;font-variant-numeric:tabular-nums;color:#555;white-space:nowrap}";
            $out .= ".areg .mono,.areg-id .mono{font:.75rem/1.3 monospace}";
            $out .= ".areg .kind{font:.72rem/1 monospace;color:#8a5a1a;white-space:nowrap}";
            $out .= ".areg .ts{color:#777;white-space:nowrap}";
            $out .= ".areg-crumb{font-size:.9rem;margin:.2rem 0 .5rem}";
            $out .= ".areg-head{font-size:.85rem;color:#555;margin:.2rem 0 .6rem}";
            $out .= ".areg-note{font-size:.75rem;color:#777;margin:.2rem 0 .6rem}";
            $out .= ".areg-dim{color:#999;font-style:italic}";
            $out .= ".areg-h{font:700 .62rem/1.8 sans-serif;letter-spacing:.08em;color:#8a5a1a;text-transform:uppercase;margin-top:.6rem}";
            $out .= ".areg-id{margin:.3rem 0 .6rem;padding:.5rem .7rem;background:#fbf9f3;border-left:3px solid #d8d2c4}";
            $out .= ".areg-id dl{margin:0;display:grid;grid-template-columns:max-content 1fr;gap:.2rem .8rem}";
            $out .= ".areg-id dt{font:700 .62rem/1.6 sans-serif;letter-spacing:.06em;color:#8a5a1a;text-transform:uppercase}";
            $out .= ".areg-id dd{margin:0;font-size:.84rem}";
            $out .= ".areg-sha{font:.8rem/1.4 monospace;color:#333;word-break:break-all;background:#f4f1e8;border:1px solid #d8d2c4;padding:.15rem .3rem;border-radius:3px}";
            $out .= ".areg-empty{padding:.6rem .8rem;background:#fbf9f3;border-left:3px solid #d8d2c4;font-size:.86rem}";
            $out .= ".areg-empty p{margin:.3rem 0}";
            $out .= "</style>\n";
            return $out;
        }

        // ── the tag entry point ──────────────────────────────────────────────────────────────

        public function get_document() {
            if (!defined('CONGRUENCY_SQLITE')) {
                return "<p class='cy-form-error'>ArtifactRegistry: CONGRUENCY_SQLITE is not defined.</p>";
            }
            try {
                $db = $this->db();
            } catch (\Throwable $e) {
                return "<p class='cy-form-error'>ArtifactRegistry: could not open the database ("
                     . self::esc($e->getMessage()) . ").</p>";
            }
            try {
                if (!self::hasTable($db)) {
                    return $this->css() . "<div class='areg-empty'><p><strong>No artifact registry in this checkout.</strong></p>"
                         . "<p>The <code>ticket_artifacts</code> table does not exist here, so there is nothing to read. "
                         . "It is created by <code>migrations/0014_ticket_artifacts.sql</code>, which has not run against "
                         . "this database.</p></div>";
                }

                /* Route on the PRESENCE of the facet, not on its emptiness: '?page=artifacts&kind='
                   sets $_GET['kind'] to the empty string, which is how the (unkinded) group — rows
                   whose kind is NULL or '' — is reachable as a link like any other kind. A facet
                   that is absent entirely means "no filter". Same rule for sha.
                   Both facets are BOUND below (:kind / :sha); neither is ever interpolated. */
                $hasSha  = array_key_exists('sha', $_GET);
                $hasKind = array_key_exists('kind', $_GET);

                if ($hasSha)  { return $this->css() . $this->detail($db, (string) $_GET['sha']); }
                if ($hasKind) { return $this->css() . $this->items($db, (string) $_GET['kind']); }
                return $this->css() . $this->index($db);
            } catch (\Throwable $e) {
                return "<div class='cy-form-error'>ArtifactRegistry error: " . self::esc($e->getMessage()) . "</div>";
            }
        }

        // ── view 1: the index — one row per kind (the tags), plus the most recent artifacts ──

        private function index($db) {
            $total = (int) self::scalar($db, "SELECT COUNT(*) FROM ticket_artifacts");
            if ($total === 0) { return $this->emptyNotice(); }

            $blobs   = (int) self::scalar($db, "SELECT COUNT(DISTINCT lower(COALESCE(forge_sha,''))) FROM ticket_artifacts");
            $tickets = (int) self::scalar($db, "SELECT COUNT(DISTINCT ticket_id) FROM ticket_artifacts WHERE ticket_id IS NOT NULL");

            // GROUP BY kind — the tag and its count. COALESCE folds a NULL kind together with an
            // empty one: both mean "carries no tag", and both drill in through '&kind='.
            $kinds = self::rows($db,
                "SELECT COALESCE(kind,'') AS k, COUNT(*) AS n, "
              . "COUNT(DISTINCT lower(COALESCE(forge_sha,''))) AS d, MAX(ts) AS newest "
              . "FROM ticket_artifacts GROUP BY COALESCE(kind,'') ORDER BY n DESC, k");

            $out  = "<p class='areg-head'><strong>" . self::esc($total) . "</strong> registration"
                  . ($total === 1 ? "" : "s") . " &middot; <strong>" . self::esc($blobs)
                  . "</strong> distinct artifact" . ($blobs === 1 ? "" : "s") . " by content sha &middot; <strong>"
                  . self::esc(count($kinds)) . "</strong> kind" . (count($kinds) === 1 ? "" : "s")
                  . " &middot; minted by <strong>" . self::esc($tickets) . "</strong> ticket"
                  . ($tickets === 1 ? "" : "s") . "</p>\n";
            $out .= "<p class='areg-note'>Kind is the tag. Click a kind to list its artifacts, or any "
                  . "artifact to open its detail &mdash; every location that content sha was registered at, "
                  . "and the full sha the resolver takes.</p>\n";

            $out .= "<div class='areg-h'>Kinds</div>\n";
            $out .= "<table class='areg'>\n<tr><th>KIND</th><th class='num'>ARTIFACTS</th>"
                  . "<th class='num'>DISTINCT SHAS</th><th>NEWEST</th></tr>\n";
            foreach ($kinds as $r) {
                $k = (string) $r['k'];
                $out .= "<tr>"
                      . "<td class='kind'><a href='" . self::url(array('kind' => $k)) . "'>"
                      . self::esc(self::kindLabel($k)) . "</a></td>"
                      . "<td class='num'>" . self::esc($r['n']) . "</td>"
                      . "<td class='num'>" . self::esc($r['d']) . "</td>"
                      . "<td class='ts'>" . self::esc(self::stamp($r['newest'])) . "</td>"
                      . "</tr>\n";
            }
            $out .= "</table>\n";

            // The most recent artifacts overall, newest first; each links to its detail.
            // LIMIT takes a class constant, never a request value.
            $recent = self::rows($db,
                "SELECT id, ts, ticket_id, name, version, forge_sha, COALESCE(kind,'') AS k "
              . "FROM ticket_artifacts ORDER BY ts DESC, id DESC LIMIT " . (int) self::RECENT_LIMIT);

            $out .= "<div class='areg-h'>Most recent</div>\n";
            $shown = count($recent);
            $out .= "<p class='areg-note'>" . ($total > $shown
                    ? ("the " . self::esc($shown) . " most recent of " . self::esc($total) . " registrations &mdash; open a kind above for the rest")
                    : ("all " . self::esc($total) . " registration" . ($total === 1 ? "" : "s"))) . "</p>\n";
            $out .= $this->itemTable($recent, true);
            return $out;
        }

        /* The empty registry — a real state, not an error. Names exactly what fills it. */
        private function emptyNotice() {
            return "<div class='areg-empty'>"
                 . "<p><strong>No artifacts registered yet.</strong></p>"
                 . "<p>The registry table (<code>ticket_artifacts</code>, created by "
                 . "<code>migrations/0014_ticket_artifacts.sql</code>) exists and holds zero rows: nothing has "
                 . "registered an artifact against a ticket yet. This is the registry's real state, not a "
                 . "lookup error.</p>"
                 . "<p>Rows arrive through the governed <code>artifact.record</code> route "
                 . "(<code>0014_ticket_artifacts.sql:19-26</code>). Two tickets call it: <strong>#455</strong>, the "
                 . "VM registry (<code>tools/vm_registry.py --record</code>, which registers every VM image tagged "
                 . "<code>kind='forge-vm'</code>), and <strong>#457</strong>, the mint hook. This page lights up "
                 . "automatically as they register &mdash; it needs no change to show them.</p>"
                 . "</div>";
        }

        // ── view 2: the items of one kind ────────────────────────────────────────────────────

        private function items($db, $kind) {
            // BOUND :kind — never interpolated. COALESCE matches a NULL kind against '' so the
            // (unkinded) group is reachable through the same facet as every other kind.
            $p = array(':kind' => $kind);
            $total = (int) self::scalar($db,
                "SELECT COUNT(*) FROM ticket_artifacts WHERE COALESCE(kind,'') = :kind", $p);

            $out = "<p class='areg-crumb'><a href='" . self::url() . "'>artifacts</a> &rsaquo; "
                 . "kind " . self::esc(self::kindLabel($kind)) . "</p>\n";

            if ($total === 0) {
                // An unknown kind is a plain answer, never an error: nothing is registered under it.
                return $out . "<div class='areg-empty'><p><strong>No artifacts of kind "
                     . self::esc(self::kindLabel($kind)) . ".</strong></p>"
                     . "<p>Nothing has been registered under that tag. Kinds are not a fixed list &mdash; a kind "
                     . "exists exactly when some artifact carries it, so this one either was never used or was "
                     . "mistyped.</p><p><a href='" . self::url() . "'>&larr; all kinds</a></p></div>";
            }

            $rows = self::rows($db,
                "SELECT id, ts, ticket_id, name, version, forge_sha, COALESCE(kind,'') AS k "
              . "FROM ticket_artifacts WHERE COALESCE(kind,'') = :kind "
              . "ORDER BY ts DESC, id DESC LIMIT " . (int) self::ITEM_LIMIT, $p);

            $blobs = (int) self::scalar($db,
                "SELECT COUNT(DISTINCT lower(COALESCE(forge_sha,''))) FROM ticket_artifacts "
              . "WHERE COALESCE(kind,'') = :kind", $p);

            $shown = count($rows);
            $out .= "<p class='areg-head'>kind <strong>" . self::esc(self::kindLabel($kind)) . "</strong> &middot; <strong>"
                  . self::esc($total) . "</strong> registration" . ($total === 1 ? "" : "s") . " &middot; <strong>"
                  . self::esc($blobs) . "</strong> distinct artifact" . ($blobs === 1 ? "" : "s") . " by content sha</p>\n";
            if ($total > $shown) {
                $out .= "<p class='areg-note'>showing the " . self::esc($shown) . " most recent of "
                      . self::esc($total) . " &mdash; " . self::esc($total - $shown) . " older registration"
                      . (($total - $shown) === 1 ? " is" : "s are") . " not listed on this page.</p>\n";
            }
            $out .= $this->itemTable($rows, false);
            return $out . "<p class='areg-crumb'><a href='" . self::url() . "'>&larr; all kinds</a></p>\n";
        }

        /* One artifact table. Used by BOTH the index's recent list and the per-kind list, so a row
           reads the same wherever it appears and every row links to its detail. $withKind adds the
           KIND column (redundant when the whole table is one kind). */
        private function itemTable($rows, $withKind) {
            if (!$rows) { return "<p class='areg-dim'>(no artifacts)</p>\n"; }
            $out  = "<table class='areg'>\n<tr><th>NAME</th><th>VERSION</th>"
                  . ($withKind ? "<th>KIND</th>" : "")
                  . "<th>FORGE SHA</th><th>REGISTERED</th><th>MINTED BY</th></tr>\n";
            foreach ($rows as $r) {
                $sha  = ($r['forge_sha'] === null) ? '' : (string) $r['forge_sha'];
                $href = self::url(array('sha' => $sha));
                // EVERY value below comes out of the db and is esc()'d before it is emitted.
                $out .= "<tr>"
                      . "<td><a href='" . $href . "'>" . self::esc(self::orDash($r['name'])) . "</a></td>"
                      . "<td class='mono'>" . self::esc(self::orDash($r['version'])) . "</td>";
                if ($withKind) {
                    $out .= "<td class='kind'><a href='" . self::url(array('kind' => (string) $r['k'])) . "'>"
                          . self::esc(self::kindLabel((string) $r['k'])) . "</a></td>";
                }
                $out .= "<td class='mono'><a href='" . $href . "'>" . self::esc(self::shortSha($sha)) . "</a></td>"
                      . "<td class='ts'>" . self::esc(self::stamp($r['ts'])) . "</td>"
                      . "<td>" . self::ticketLink($r['ticket_id']) . "</td>"
                      . "</tr>\n";
            }
            return $out . "</table>\n";
        }

        // ── view 3: the leaf — ONE artifact, every location it was registered at ─────────────

        private function detail($db, $sha) {
            // BOUND :sha — never interpolated. Matched case-insensitively on the same rule the
            // resolver's forge-artifacts probe uses (`lower(sha256) = ?`, resolver.py:552), so a
            // sha pasted in either case finds its artifact. The STORED value is what is displayed.
            $p = array(':sha' => $sha);
            $locs = self::rows($db,
                "SELECT id, ts, ticket_id, name, version, forge_sha, COALESCE(kind,'') AS k "
              . "FROM ticket_artifacts WHERE lower(COALESCE(forge_sha,'')) = lower(:sha) "
              . "ORDER BY ts, id", $p);

            $out = "<p class='areg-crumb'><a href='" . self::url() . "'>artifacts</a> &rsaquo; "
                 . "sha " . self::esc(self::shortSha($sha)) . "</p>\n";

            if (!$locs) {
                // An unknown sha is a plain answer, never an error.
                return $out . "<div class='areg-empty'><p><strong>Not registered.</strong></p>"
                     . "<p>No artifact in this registry carries the content sha <code class='areg-sha'>"
                     . self::esc(($sha === '') ? self::NO_SHA : $sha) . "</code>. Nothing has recorded that blob "
                     . "against a ticket &mdash; which does not mean the blob does not exist, only that "
                     . "<code>ticket_artifacts</code> has never seen it.</p>"
                     . "<p><a href='" . self::url() . "'>&larr; all kinds</a></p></div>";
            }

            // Identity, over EVERY location (not just the page shown below). The same bytes may be
            // registered under more than one name/version/kind, so each is reported as a set.
            $stored  = (string) (($locs[0]['forge_sha'] === null) ? '' : $locs[0]['forge_sha']);
            $names   = self::distinctVals($locs, 'name',    '(unnamed)');
            $vers    = self::distinctVals($locs, 'version', '(no version)');
            $kindSet = self::distinctVals($locs, 'k',       self::UNKINDED);

            $tickets = array();   // distinct minting tickets, in first-seen order
            $firstTs = null; $lastTs = null;
            foreach ($locs as $r) {
                $t = $r['ticket_id'];
                $key = ($t === null || $t === '') ? '' : (string) (int) $t;
                if (!array_key_exists($key, $tickets)) { $tickets[$key] = $t; }
                $ts = (int) $r['ts'];
                if ($ts > 0 && ($firstTs === null || $ts < $firstTs)) { $firstTs = $ts; }
                if ($ts > 0 && ($lastTs === null || $ts > $lastTs))   { $lastTs = $ts; }
            }
            $tlinks = array();
            foreach ($tickets as $t) { $tlinks[] = self::ticketLink($t); }

            // Kind is the tag: link each of this artifact's kinds back to its filtered view.
            $klinks = array();
            foreach ($kindSet as $k) {
                $facet = ($k === self::UNKINDED) ? '' : $k;
                $klinks[] = "<a href='" . self::url(array('kind' => $facet)) . "'>" . self::esc($k) . "</a>";
            }

            $n = count($locs);
            $out .= "<div class='areg-id'>\n<dl>\n";
            $out .= "<dt>Name</dt><dd>" . self::escJoin($names, " &middot; ") . "</dd>\n";
            $out .= "<dt>Kind</dt><dd class='kind'>" . implode(" &middot; ", $klinks) . "</dd>\n";
            $out .= "<dt>Version</dt><dd class='mono'>" . self::escJoin($vers, " &middot; ") . "</dd>\n";
            $out .= "<dt>Forge sha</dt><dd><code class='areg-sha'>"
                  . self::esc(($stored === '') ? self::NO_SHA : $stored) . "</code></dd>\n";
            $out .= "<dt>Locations</dt><dd>" . self::esc($n) . " registration" . ($n === 1 ? "" : "s")
                  . " &middot; minted by " . implode(" &middot; ", $tlinks) . "</dd>\n";
            $out .= "<dt>First seen</dt><dd class='ts'>" . self::esc(self::stamp($firstTs))
                  . ($lastTs !== null && $lastTs !== $firstTs
                     ? ("  &middot; last seen " . self::esc(self::stamp($lastTs))) : "") . "</dd>\n";
            $out .= "</dl>\n</div>\n";

            // The sha is a live handle: this is the command it is the input to.
            if ($stored !== '') {
                $out .= "<p class='areg-note'>This sha is the content address of the blob itself, so it is shown in "
                      . "full: it is what the universal resolver takes as input &mdash; "
                      . "<code>python3 tools/resolver.py " . self::esc($stored) . "</code> &mdash; which probes "
                      . "<code>forge-artifacts</code> and returns every place those bytes live. The registry below "
                      . "lists every place they were registered.</p>\n";
            } else {
                $out .= "<p class='areg-note'>These rows carry no <code>forge_sha</code>, so they name no content "
                      . "address: there is no blob to resolve and no bytes to point at. That is a defect in whatever "
                      . "registered them, shown here rather than hidden.</p>\n";
            }

            // EVERY LOCATION the same sha was registered at — the whole point of content addressing:
            // the same bytes in two places are ONE artifact with several locations.
            $out .= "<div class='areg-h'>Every location this sha is registered at</div>\n";
            $shown = $locs;
            if (count($locs) > self::LOC_LIMIT) {
                $shown = array_slice($locs, 0, self::LOC_LIMIT);
                $out .= "<p class='areg-note'>showing the " . self::esc(self::LOC_LIMIT) . " oldest of "
                      . self::esc(count($locs)) . " locations.</p>\n";
            }
            $out .= "<table class='areg'>\n<tr><th class='num'>#</th><th>MINTING TICKET</th><th>NAME</th>"
                  . "<th>VERSION</th><th>KIND</th><th>REGISTERED</th></tr>\n";
            foreach ($shown as $r) {
                $out .= "<tr>"
                      . "<td class='num'>" . self::esc($r['id']) . "</td>"
                      . "<td>" . self::ticketLink($r['ticket_id']) . "</td>"
                      . "<td>" . self::esc(self::orDash($r['name'])) . "</td>"
                      . "<td class='mono'>" . self::esc(self::orDash($r['version'])) . "</td>"
                      . "<td class='kind'><a href='" . self::url(array('kind' => (string) $r['k'])) . "'>"
                      . self::esc(self::kindLabel((string) $r['k'])) . "</a></td>"
                      . "<td class='ts'>" . self::esc(self::stamp($r['ts'])) . "</td>"
                      . "</tr>\n";
            }
            $out .= "</table>\n";
            if ($n === 1) {
                $out .= "<p class='areg-note'>These bytes are registered at exactly one location. Were the same sha "
                      . "registered again &mdash; under another ticket, name or version &mdash; it would appear here as a "
                      . "second location of this one artifact, not as a second artifact.</p>\n";
            }
            return $out . "<p class='areg-crumb'><a href='" . self::url() . "'>&larr; all kinds</a></p>\n";
        }
    }
}
?>
