<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * TicketList — a congruency component (tag/invocator).
 *
 * Implements Tag_Interface, so the tag engine instantiates it whenever a
 * document's content contains <<<TicketList>>> and splices in get_document()
 * (see Tag_Wrapper::get_tag_wrapper / execute_all_tags). Renders the project
 * ticket table from the unified congruency DB (CONGRUENCY_SQLITE) — the same
 * file the CMS, telemetry and gate all share.
 *
 * It reflects the ticket-AUTHORIZATION model added in migrations 0029-0032
 * (0029_ticket_authorization.sql, 0030_pair_loop_routes.sql). A ticket now
 * AUTHORIZES an agent (or an adversarial pair) to act; it carries a kind with a
 * versioned, enumerable lifecycle; it is a manifest of UID'd works; and it can
 * be halted by a STOP ticket aimed at it via a 'stops' edge. Each row surfaces:
 *   id, kind (or '(unkinded)' when tickets.kind IS NULL),
 *   status, title,
 *   CREW    — the distinct roles authorized on it (ticket_agents.role; '—' if none),
 *   PROGRESS — 'D of Y' where D is the number of lifecycle steps DONE and
 *              Y = COUNT(*) of ticket_lifecycles for the ticket's kind at
 *              version 1 (the enumerable steps to the goal). steps_remaining is a
 *              COUNT-DOWN to the goal (0029_ticket_authorization.sql:81), so the
 *              latest reported value R (newest ticket_events row that HAS a
 *              steps_remaining) is steps LEFT, not steps done — a DONE ticket
 *              reports R=0. We therefore show forward progress D = Y - R (clamped
 *              to 0..Y), so a finished ticket reads 'Y of Y' (all done), never
 *              '0 of Y' (which reads as nothing done). '—' if either R or Y is
 *              unknown,
 *   WORKS   — count of ticket_works (the UID'd manifest),
 *   LESSONS — count of ticket_events WHERE event='lesson' (harvested at settle).
 * A ticket with an unreleased stop aimed at it is marked STOPPED (see stops(),
 * which mirrors the ticket.stops route in 0030_pair_loop_routes.sql). Rows are
 * ordered ACTIVE first, then OPEN/REQUESTED, then everything else; newest id
 * first within each group; DONE/CLOSED rows are rendered muted.
 *
 * ── GROUPING (near-identical floods collapse) ────────────────────────────────
 * Machine-filed tickets arrive in FLOODS of near-identical rows — 25 "Docs may be
 * stale: <path>" rows (#112-#142, filed by doc_watch) and the per-crank prediction
 * runs ("PREDICTION #25 crank1..crank10"). Thirty near-identical rows bury the work
 * that matters, so such a flood collapses into ONE group header row carrying the
 * count; the members are still there, one click away, with every column intact.
 *
 * A ticket's group is decided by its SIGNATURE, computed mechanically from the
 * title by sigKey():
 *   1. take the part before the FIRST ':' (the stable stem the filer templated;
 *      the part after it is the per-instance variable — a path, an element name).
 *      A title with no ':' uses the whole title;
 *   2. lowercase it and collapse whitespace runs to one space;
 *   3. replace every run of digits with '#', EXCEPT a run already introduced by a
 *      '#' — because '#25' is a TICKET REFERENCE (this view renders ids the same
 *      way), i.e. part of the family's identity, while a bare '1' in 'crank1' is
 *      the varying index. So 'PREDICTION #25 crank1' and '...crank10' share the
 *      signature 'prediction #25 crank#', while the #44 and #45 crank runs stay
 *      distinct families of their own.
 * Two guards keep grouping from hiding anything it shouldn't:
 *   GROUP_MIN (3)      — fewer than three members is not a flood; those rows stay
 *                        individual. A group header for two rows saves nothing.
 *   MIN_SIG_WORDS (2)  — a ONE-word signature is a category, not a description.
 *                        'Research:', 'Build:', 'Test:', 'Spec:' and 'RFC:' prefix
 *                        dozens of UNRELATED frontier tickets; grouping on a stem
 *                        that thin would collapse exactly the work a reader came
 *                        for. Such rows are never grouped, whatever their count.
 * Grouping is scoped to the status band (ACTIVE / OPEN-REQUESTED / other), so a
 * group never mixes an ACTIVE ticket into a flood of CLOSED ones, and the group
 * sits at the position of its FIRST (newest-id) member — the established row order
 * above is preserved exactly, with a flood's rows folded into one line.
 *
 * ── DRILL-DOWN (click a row, walk the provenance graph) ──────────────────────
 * Clicking a ticket's TITLE expands that ticket in place: the edges recorded in
 * ticket_edges (0012_ticket_edges.sql) plus its append-only journal
 * (ticket_events; the same rows, in the same ts,id order, that the ticket.journal
 * route serves — 0029_ticket_authorization.sql). The expansion shows
 *   PROVENANCE — the incoming edges (what spawned / superseded / stopped this),
 *   TREE       — the outgoing edges below it, walked recursively, and
 *   JOURNAL    — every appended event: ts, agent, event, status, steps, note.
 * Every referenced ticket is itself a row in this list, so the graph is navigable
 * without leaving the page. Expansion is native <details>/<summary>: no
 * JavaScript, no request, no state — a closed page and an open one read the same
 * rows. All edge/journal rows are fetched in ONE bulk SELECT each and bucketed in
 * PHP (mirroring how CREW/WORKS/LESSONS above are loaded) — never a query per row.
 *
 * NB (graph guard): ticket_edges is a DAG, NOT a tree — #189 and #188 both spawn
 * #190, and #176 has two parents — so a naive walk would re-render shared subtrees
 * (exponentially) and would not terminate at all should an edge ever close a
 * cycle. treeHtml() therefore carries a $seen set across the WHOLE walk of one
 * ticket: a node is expanded the first time it appears and marked '(shown above)'
 * on any later appearance. That alone bounds the walk (each ticket at most once)
 * and terminates on a cycle; MAX_TREE_DEPTH is a second, independent stop.
 *
 * READ-ONLY: every statement is a SELECT and the connection is pinned with
 * `PRAGMA query_only = TRUE`, so this tag can make no write and no schema change
 * (the ticket forbids both). Missing authorization tables (e.g. a checkout where
 * 0029+ has not run) degrade to '—'/0 per column or a friendly message — never a
 * fatal. The base `tickets` table pre-dates 0029, so it is always expected.
 *
 * NB (recursion guard): ticket titles may themselves contain <<<Tag>>> syntax
 * (e.g. this very ticket, "render ... a <<<TicketList>>> ..."), so EVERY value
 * is passed through htmlspecialchars() before it is emitted — otherwise
 * execute_all_tags would re-parse the output and recurse the tag engine. This
 * models BugReport.php, but reads live rows. Do not remove an esc() call. The
 * drill-down widens this surface — journal notes and edge-linked titles are DB
 * text too — so they are escaped on exactly the same rule.
 */
if (!class_exists("TicketList")) {
    class TicketList implements Tag_Interface {

        // A flood is three or more near-identical tickets; fewer stay individual rows.
        const GROUP_MIN = 3;
        // A one-word signature ('Research', 'Build', 'Test') is a category, not a
        // description — never group on one, however many tickets share it.
        const MIN_SIG_WORDS = 2;
        // Second, independent stop for the edge walk (the $seen set is the first).
        const MAX_TREE_DEPTH = 8;

        private $arguments;

        public function __construct($arguments) {
            // arguments may be null when rendered standalone (e.g. by TagList: new TicketList(null))
            $this->arguments = $arguments;
        }

        private static function esc($s) {
            return htmlspecialchars((string)$s, ENT_QUOTES);
        }

        // A read-only PDO handle. `query_only` blocks any write on this connection,
        // so a stray non-SELECT would raise rather than mutate the shared DB.
        private function db() {
            $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
            $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            $db->exec('PRAGMA query_only = TRUE');
            return $db;
        }

        // Run a SELECT and return its rows; if the table is absent (a checkout
        // where 0029+ never ran) degrade to an empty set rather than a fatal.
        private static function safe($db, $sql) {
            try {
                return $db->query($sql)->fetchAll(PDO::FETCH_ASSOC);
            } catch (\Throwable $e) {
                return array();
            }
        }

        // The stem a flood is templated from: the part before the first ':' (or the
        // whole title when it has none), with whitespace runs collapsed. Shared by
        // sigKey (the grouping key) and sigLabel (what the reader sees), so the two
        // can never disagree about what the group is.
        private static function sigStem($title) {
            $s = trim((string)$title);
            $i = strpos($s, ':');
            if ($i !== false && $i > 0) { $s = substr($s, 0, $i); }
            return trim(preg_replace('/\s+/', ' ', $s));
        }

        // The grouping key: the stem, lowercased, with each varying digit-run folded
        // to '#'. The lookbehind (?<![#\d]) keeps a '#25' ticket reference intact —
        // it skips a digit introduced by '#', and skips digits inside a run already
        // being folded, so '#25' stays '#25' rather than becoming '#2#'.
        private static function sigKey($title) {
            return preg_replace('/(?<![#\d])\d+/', '#', strtolower(self::sigStem($title)));
        }

        // What the group header shows: the same stem in its original case, with the
        // varying digit-runs shown as '…' ('PREDICTION #25 crank…') so the reader can
        // see WHICH part varies across the members.
        private static function sigLabel($title) {
            return preg_replace('/(?<![#\d])\d+/', '…', self::sigStem($title));
        }

        // Groupable only if the signature carries at least MIN_SIG_WORDS words.
        private static function groupable($sigKey) {
            return count(preg_split('/\s+/', $sigKey, -1, PREG_SPLIT_NO_EMPTY)) >= self::MIN_SIG_WORDS;
        }

        // The status band a row sorts into — must mirror the ORDER BY CASE in the
        // ticket SELECT below (ACTIVE 0, OPEN/REQUESTED 1, everything else 2).
        private static function band($st) {
            if ($st === 'ACTIVE') { return 0; }
            if ($st === 'OPEN' || $st === 'REQUESTED') { return 1; }
            return 2;
        }

        // Epoch seconds -> a readable stamp; '—' when the row carries no usable ts.
        private static function stamp($ts) {
            $t = (int)$ts;
            return ($t > 0) ? gmdate('Y-m-d H:i', $t) : '—';
        }

        // One node label in the edge walk: '#id title [STATUS]', every part escaped.
        // $meta may not know the id at all (an edge may name a ticket that no longer
        // resolves) — say so plainly rather than rendering a bare number.
        private static function nodeHtml($id, $meta) {
            $out = "<span class='tid'>#" . self::esc($id) . "</span> ";
            if (!isset($meta[$id])) {
                return $out . "<span class='tnote'>(no such ticket row)</span>";
            }
            $m = $meta[$id];
            return $out . self::esc($m['title'])
                 . " <span class='tst'>" . self::esc($m['status']) . "</span>";
        }

        // The outgoing edge walk below $id, as nested lists. $seen is carried across
        // the WHOLE walk BY REFERENCE (see the graph-guard note in the header): the
        // edges are a DAG, so a node already rendered is marked and not re-expanded.
        // That bounds the walk to one visit per ticket and terminates on a cycle;
        // MAX_TREE_DEPTH is the second, independent stop.
        private static function treeHtml($id, $depth, &$seen, $kids, $meta) {
            if (!isset($kids[$id])) { return ''; }
            if ($depth >= self::MAX_TREE_DEPTH) {
                return "<ul class='tree'><li><span class='tnote'>… depth cap ("
                     . self::esc(self::MAX_TREE_DEPTH) . ") reached; open this ticket's own row to go deeper</span></li></ul>";
            }
            $out = "<ul class='tree'>";
            foreach ($kids[$id] as $e) {
                $cid = $e['child'];
                $out .= "<li><span class='ek ek-" . self::esc($e['kind']) . "'>"
                      . self::esc($e['kind']) . "</span> " . self::nodeHtml($cid, $meta);
                if (isset($seen[$cid])) {
                    $out .= " <span class='tnote'>↑ shown above</span>";
                } else {
                    $seen[$cid] = true;
                    $out .= self::treeHtml($cid, $depth + 1, $seen, $kids, $meta);
                }
                $out .= "</li>";
            }
            return $out . "</ul>";
        }

        // The whole expansion for one ticket: PROVENANCE (incoming edges), TREE
        // (outgoing edges, walked) and JOURNAL (the append-only events).
        private static function expansionHtml($id, $kids, $parents, $journal, $meta) {
            $out = "<div class='exp'>";

            // PROVENANCE — the incoming edges: what spawned/superseded/stopped this.
            $out .= "<div class='exph'>PROVENANCE</div>";
            if (isset($parents[$id])) {
                $out .= "<ul class='tree'>";
                foreach ($parents[$id] as $e) {
                    $out .= "<li><span class='ek ek-" . self::esc($e['kind']) . "'>"
                          . self::esc($e['kind']) . "</span> " . self::nodeHtml($e['parent'], $meta)
                          . " <span class='tnote'>→ this ticket</span></li>";
                }
                $out .= "</ul>";
            } else {
                $out .= "<p class='tnote'>no incoming edges — this ticket is a root.</p>";
            }

            // TREE — the outgoing edges below it.
            $out .= "<div class='exph'>TREE</div>";
            if (isset($kids[$id])) {
                $seen = array($id => true);
                $out .= self::treeHtml($id, 0, $seen, $kids, $meta);
            } else {
                $out .= "<p class='tnote'>no outgoing edges — this ticket spawned nothing.</p>";
            }

            // JOURNAL — every appended event, oldest first (the ticket.journal order).
            $out .= "<div class='exph'>JOURNAL</div>";
            if (isset($journal[$id])) {
                $out .= "<table class='jr'><thead><tr><th>WHEN</th><th>AGENT</th><th>EVENT</th>"
                      . "<th>STATUS</th><th class='num'>STEPS LEFT</th><th>NOTE</th></tr></thead><tbody>";
                foreach ($journal[$id] as $j) {
                    $agent = ($j['agent_id'] === null || $j['agent_id'] === '')
                           ? '(mechanical)' : $j['agent_id'];
                    $steps = ($j['steps_remaining'] === null) ? '—' : (int)$j['steps_remaining'];
                    $note  = ($j['note'] === null || $j['note'] === '') ? '—' : $j['note'];
                    $out .= "<tr><td class='jts'>" . self::esc(self::stamp($j['ts'])) . "</td>"
                          . "<td class='jag'>" . self::esc($agent) . "</td>"
                          . "<td class='jev'>" . self::esc($j['event']) . "</td>"
                          . "<td>" . self::esc(($j['status'] === null || $j['status'] === '') ? '—' : $j['status']) . "</td>"
                          . "<td class='num'>" . self::esc($steps) . "</td>"
                          . "<td class='jnote'>" . self::esc($note) . "</td></tr>";
                }
                $out .= "</tbody></table>";
            } else {
                $out .= "<p class='tnote'>no journal entries — nothing has been appended to this ticket.</p>";
            }

            return $out . "</div>";
        }

        public function get_document() {
            if (!defined('CONGRUENCY_SQLITE')) {
                return "<p style='color:#b00020'>TicketList: CONGRUENCY_SQLITE is not defined.</p>";
            }
            try {
                $db = $this->db();
            } catch (\Throwable $e) {
                return "<p style='color:#b00020'>TicketList: could not open the database ("
                     . self::esc($e->getMessage()) . ").</p>";
            }

            // The base ticket rows — ordered by authorization state, then newest id first.
            // ACTIVE (band 0) leads, then OPEN/REQUESTED (1), then everything else (2).
            // The tickets table pre-dates 0029; if even it is unreadable, that is fatal
            // to this view, so surface a friendly message (never a PHP fatal).
            try {
                $ticketSql =
                    "SELECT id, kind, status, title FROM tickets "
                  . "ORDER BY CASE WHEN upper(status)='ACTIVE' THEN 0 "
                  . "WHEN upper(status) IN ('OPEN','REQUESTED') THEN 1 ELSE 2 END, id DESC";
                $rows = $db->query($ticketSql)->fetchAll(PDO::FETCH_ASSOC);
            } catch (\Throwable $e) {
                return "<p style='color:#b00020'>TicketList: could not read tickets ("
                     . self::esc($e->getMessage()) . ").</p>";
            }
            if (!$rows) {
                return "<p style='color:#555'>TicketList: no tickets yet.</p>";
            }

            // ── the authorization overlays (each degrades to empty if its table is absent) ──

            // CREW: distinct roles per ticket, in assignment order (ts, then role for a
            // stable tiebreak when a pair is authorized in one write). Deduped in PHP so
            // the first appearance of each role wins — e.g. 'coder,tester,scribe'.
            $crew = array();
            foreach (self::safe($db,
                "SELECT ticket_id, role FROM ticket_agents ORDER BY ticket_id, ts, role") as $a) {
                $tid = (int)$a['ticket_id'];
                if (!isset($crew[$tid])) { $crew[$tid] = array(); }
                if (!in_array($a['role'], $crew[$tid], true)) { $crew[$tid][] = $a['role']; }
            }

            // WORKS: size of the UID'd manifest per ticket.
            $works = array();
            foreach (self::safe($db,
                "SELECT ticket_id, COUNT(*) AS n FROM ticket_works GROUP BY ticket_id") as $w) {
                $works[(int)$w['ticket_id']] = (int)$w['n'];
            }

            // LESSONS: harvested 'lesson' events per ticket.
            $lessons = array();
            foreach (self::safe($db,
                "SELECT ticket_id, COUNT(*) AS n FROM ticket_events "
              . "WHERE event='lesson' GROUP BY ticket_id") as $l) {
                $lessons[(int)$l['ticket_id']] = (int)$l['n'];
            }

            // PROGRESS (remaining): the LATEST reported steps_remaining per ticket — the
            // steps LEFT until the goal (a COUNT-DOWN; a DONE ticket reports 0). A row
            // without a steps_remaining (e.g. an auto-journaled status change or a lesson)
            // reports no countdown, so we take the newest row that HAS one. Rows arrive
            // oldest-first, so the last one written per ticket is the latest. We convert
            // this to steps-DONE at render time (Y - remaining) so the column reads forward.
            $stepsRemaining = array();
            foreach (self::safe($db,
                "SELECT ticket_id, steps_remaining FROM ticket_events "
              . "WHERE steps_remaining IS NOT NULL ORDER BY ticket_id, ts, id") as $s) {
                $stepsRemaining[(int)$s['ticket_id']] = (int)$s['steps_remaining'];
            }

            // PROGRESS Y: the enumerable lifecycle length per kind (version 1) — the
            // steps-until-goal that steps_remaining counts down.
            $stepsY = array();
            foreach (self::safe($db,
                "SELECT kind, COUNT(*) AS n FROM ticket_lifecycles "
              . "WHERE version=1 GROUP BY kind") as $y) {
                $stepsY[(string)$y['kind']] = (int)$y['n'];
            }

            // ── the drill-down overlays: one bulk SELECT each, bucketed in PHP ──

            // EDGES: both directions, from the single ticket_edges scan (0012). kids
            // drives the downward walk; parents is the incoming provenance list.
            $kids = array(); $parents = array();
            foreach (self::safe($db,
                "SELECT parent_id, child_id, kind FROM ticket_edges "
              . "ORDER BY parent_id, kind, child_id") as $e) {
                $p = (int)$e['parent_id']; $c = (int)$e['child_id'];
                $k = (string)$e['kind'];
                if (!isset($kids[$p]))    { $kids[$p]    = array(); }
                if (!isset($parents[$c])) { $parents[$c] = array(); }
                $kids[$p][]    = array('child' => $c,  'kind' => $k);
                $parents[$c][] = array('parent' => $p, 'kind' => $k);
            }

            // JOURNAL: every event for every ticket, in the ticket.journal order
            // (ts, id — oldest first), bucketed per ticket.
            $journal = array();
            foreach (self::safe($db,
                "SELECT ticket_id, ts, agent_id, event, status, note, steps_remaining "
              . "FROM ticket_events ORDER BY ticket_id, ts, id") as $j) {
                $tid = (int)$j['ticket_id'];
                if (!isset($journal[$tid])) { $journal[$tid] = array(); }
                $journal[$tid][] = $j;
            }

            // STOPPED: mirror the ticket.stops route (0030_pair_loop_routes.sql). A ticket
            // is halted when a 'stops' edge is aimed at IT or any ancestor (walking 'spawned'
            // edges upward), UNLESS the stop ticket has itself been released by a 'starts'
            // edge aimed back at it. Build the two sets, then walk ancestors in PHP.
            $stopTargets = array();   // child_id of every UNRELEASED stop edge
            foreach (self::safe($db,
                "SELECT DISTINCT st.child_id FROM ticket_edges st WHERE st.kind='stops' "
              . "AND NOT EXISTS (SELECT 1 FROM ticket_edges rel "
              . "WHERE rel.kind='starts' AND rel.child_id = st.parent_id)") as $e) {
                $stopTargets[(int)$e['child_id']] = true;
            }
            $spawnParent = array();   // child_id -> [parent_id, ...] over 'spawned' edges
            foreach (self::safe($db,
                "SELECT parent_id, child_id FROM ticket_edges WHERE kind='spawned'") as $e) {
                $c = (int)$e['child_id'];
                if (!isset($spawnParent[$c])) { $spawnParent[$c] = array(); }
                $spawnParent[$c][] = (int)$e['parent_id'];
            }

            $out  = "<style>";
            $out .= ".tkl{width:100%;border-collapse:collapse;font-size:.82rem}";
            $out .= ".tkl th{text-align:left;border-bottom:2px solid #d8d2c4;padding:.35rem .5rem;color:#555;font-weight:600;white-space:nowrap}";
            $out .= ".tkl td{border-bottom:1px solid #eee4d0;padding:.35rem .5rem;vertical-align:top}";
            $out .= ".tkl .id{font:600 .78rem/1 monospace;color:#555;white-space:nowrap}";
            $out .= ".tkl .kind{font:.72rem/1 monospace;color:#8a5a1a;white-space:nowrap}";
            $out .= ".tkl .st{font:600 .62rem/1.6 sans-serif;text-transform:uppercase;color:#fff;padding:.05rem .4rem;border-radius:3px}";
            $out .= ".tkl .crew{font:.72rem/1.3 monospace;color:#3a5a3a}";
            $out .= ".tkl .num{text-align:right;font-variant-numeric:tabular-nums;color:#555;white-space:nowrap}";
            $out .= ".tkl .stopped{font:700 .6rem/1.6 sans-serif;text-transform:uppercase;color:#fff;background:#b00020;padding:.05rem .4rem;border-radius:3px;margin-left:.4rem}";
            $out .= ".tkl tr.muted td{color:#aaa;background:#faf8f2}";
            $out .= ".tkl tr.muted .kind,.tkl tr.muted .crew,.tkl tr.muted .num{color:#aaa}";
            // drill-down: the title cell is a <details>; the summary IS the title.
            $out .= ".tkl summary{cursor:pointer;list-style:none}";
            $out .= ".tkl summary::-webkit-details-marker{display:none}";
            $out .= ".tkl summary::before{content:'▸ ';color:#8a5a1a;font-size:.7rem}";
            $out .= ".tkl details[open]>summary::before{content:'▾ '}";
            $out .= ".tkl summary:hover{background:#fdf8ec}";
            $out .= ".exp{margin:.5rem 0 .3rem;padding:.5rem .6rem;background:#fbf9f3;border-left:3px solid #d8d2c4}";
            $out .= ".exph{font:700 .6rem/1.8 sans-serif;letter-spacing:.08em;color:#8a5a1a;text-transform:uppercase}";
            $out .= ".tree{margin:.1rem 0 .4rem;padding-left:1rem;list-style:none}";
            $out .= ".tree li{padding:.1rem 0;border-left:1px dotted #d8d2c4;padding-left:.5rem}";
            $out .= ".tid{font:600 .74rem/1 monospace;color:#555}";
            $out .= ".tst{font:.62rem/1 sans-serif;color:#888;text-transform:uppercase}";
            $out .= ".tnote{font:italic .7rem/1.4 sans-serif;color:#999}";
            $out .= ".ek{font:600 .58rem/1.6 sans-serif;text-transform:uppercase;color:#fff;background:#888;padding:.02rem .3rem;border-radius:3px}";
            $out .= ".ek-spawned{background:#3a6a8a}.ek-supersedes{background:#8a5a1a}.ek-stops{background:#b00020}.ek-starts{background:#1a7a3a}";
            $out .= ".jr{width:100%;border-collapse:collapse;font-size:.7rem;margin:.1rem 0 .2rem}";
            $out .= ".jr th{text-align:left;border-bottom:1px solid #d8d2c4;padding:.15rem .35rem;color:#777;font-weight:600;white-space:nowrap}";
            $out .= ".jr td{border-bottom:1px solid #f0ead8;padding:.15rem .35rem;vertical-align:top}";
            $out .= ".jr .jts,.jr .jag,.jr .jev{font:.68rem/1.3 monospace;color:#555;white-space:nowrap}";
            $out .= ".jr .jnote{color:#444}";
            $out .= ".jr .num{text-align:right;font-variant-numeric:tabular-nums;color:#555}";
            // grouping: the flood header row, and the member table nested inside it.
            $out .= ".tkl tr.grp>td{background:#f6f2e6;border-bottom:1px solid #d8d2c4}";
            $out .= ".gsig{font:600 .8rem/1.4 sans-serif;color:#3a3a3a}";
            $out .= ".gcount{font:700 .62rem/1.6 sans-serif;text-transform:uppercase;color:#fff;background:#8a5a1a;padding:.05rem .4rem;border-radius:3px;margin-left:.4rem}";
            $out .= ".gmeta{font:.7rem/1.4 sans-serif;color:#777;margin-left:.4rem}";
            $out .= ".tkl table.sub{margin:.4rem 0 .2rem;background:#fff}";
            $out .= "</style>\n";

            // Header counts (all static/derived integers — safe, but the summary strings
            // below embed only ints we compute here, never raw DB text).
            $total   = count($rows);
            $active  = 0; $openish = 0; $doneish = 0; $stoppedCount = 0;

            // Precompute per-row derived values and the STOPPED flag (needs the ancestor
            // walk), plus each row's grouping signature and status band.
            $view = array();
            $meta = array();   // id -> status/title, for labelling nodes in the edge walk
            $sigCount = array();
            foreach ($rows as $r) {
                $id = (int)$r['id'];

                // STOPPED: this id or any spawned-ancestor is an unreleased stop target.
                $stopped = false;
                $seen = array();
                $stack = array($id);
                while ($stack) {
                    $cur = array_pop($stack);
                    if (isset($seen[$cur])) { continue; }
                    $seen[$cur] = true;
                    if (isset($stopTargets[$cur])) { $stopped = true; break; }
                    if (isset($spawnParent[$cur])) {
                        foreach ($spawnParent[$cur] as $p) { $stack[] = $p; }
                    }
                }

                $st = strtoupper((string)$r['status']);
                if ($st === 'ACTIVE') { $active++; }
                elseif ($st === 'OPEN' || $st === 'REQUESTED') { $openish++; }
                else { $doneish++; }
                if ($stopped) { $stoppedCount++; }

                $meta[$id] = array('status' => (string)$r['status'], 'title' => (string)$r['title']);

                // The grouping key is scoped to the status band, so a flood of CLOSED
                // rows can never swallow an ACTIVE ticket that shares its wording.
                $sig = self::sigKey($r['title']);
                $key = self::band($st) . "\x00" . $sig;
                if (self::groupable($sig)) {
                    $sigCount[$key] = isset($sigCount[$key]) ? $sigCount[$key] + 1 : 1;
                }

                $view[] = array('r' => $r, 'id' => $id, 'stopped' => $stopped,
                                'st' => $st, 'key' => $key, 'sig' => $sig);
            }

            // Fold each flood into ONE slot at the position of its FIRST (newest-id)
            // member; every other row keeps its own slot. Walking $view in order means
            // the established ACTIVE-first / newest-first order is preserved exactly.
            $slots = array();       // ordered: each is a single row or a group of rows
            $slotOfKey = array();   // group key -> index into $slots
            foreach ($view as $v) {
                $key = $v['key'];
                $isGroup = isset($sigCount[$key]) && $sigCount[$key] >= self::GROUP_MIN;
                if (!$isGroup) {
                    $slots[] = array('type' => 'row', 'v' => $v);
                    continue;
                }
                if (!isset($slotOfKey[$key])) {
                    $slotOfKey[$key] = count($slots);
                    $slots[] = array('type' => 'group',
                                     'label' => self::sigLabel($v['r']['title']),
                                     'members' => array());
                }
                $slots[$slotOfKey[$key]]['members'][] = $v;
            }

            $groupCount = count($slotOfKey);
            $groupedRows = 0;
            foreach ($slotOfKey as $i) { $groupedRows += count($slots[$i]['members']); }

            $out .= "<p style='font-size:.85rem;color:#555'><strong>" . self::esc($total)
                  . "</strong> tickets &middot; <strong>" . self::esc($active)
                  . "</strong> active &middot; <strong>" . self::esc($openish)
                  . "</strong> open/requested &middot; <strong>" . self::esc($doneish)
                  . "</strong> done/other &middot; <strong>" . self::esc($stoppedCount)
                  . "</strong> stopped</p>\n";
            $out .= "<p style='font-size:.75rem;color:#777'>"
                  . self::esc($groupedRows) . " near-identical tickets are folded into "
                  . self::esc($groupCount) . " group"  . ($groupCount === 1 ? "" : "s")
                  . " &middot; click a group to list its members, or any ticket's title to expand"
                  . " its provenance tree and journal.</p>\n";

            $head = "<thead><tr>"
                  . "<th>#</th><th>KIND</th><th>STATUS</th><th>TITLE</th>"
                  . "<th>CREW</th><th>PROGRESS</th><th class='num'>WORKS</th><th class='num'>LESSONS</th>"
                  . "</tr></thead>\n";
            $out .= "<table class='tkl'>\n" . $head . "<tbody>\n";

            foreach ($slots as $slot) {
                if ($slot['type'] === 'row') {
                    $out .= $this->rowHtml($slot['v'], $crew, $stepsRemaining, $stepsY,
                                           $works, $lessons, $kids, $parents, $journal, $meta);
                    continue;
                }

                // ── a group header: one row for the whole flood, members one click away ──
                $members = $slot['members'];
                $n = count($members);

                // The id range and the status mix, so the header answers what the folded
                // rows would have: which tickets, and what state they are in.
                $ids = array();
                $byStatus = array();
                $muteAll = true;
                foreach ($members as $m) {
                    $ids[] = $m['id'];
                    $s = (string)$m['r']['status'];
                    $byStatus[$s] = isset($byStatus[$s]) ? $byStatus[$s] + 1 : 1;
                    if ($m['st'] !== 'DONE' && $m['st'] !== 'CLOSED') { $muteAll = false; }
                }
                $mix = array();
                foreach ($byStatus as $s => $c) { $mix[] = $s . "\u{00d7}" . $c; }
                $range = ($n > 1) ? ("#" . min($ids) . "–#" . max($ids)) : ("#" . $ids[0]);

                $out .= "<tr class='grp" . ($muteAll ? " muted" : "") . "'><td colspan='8'>";
                $out .= "<details><summary>";
                $out .= "<span class='gsig'>" . self::esc($slot['label']) . "</span>";
                $out .= "<span class='gcount'>" . self::esc($n) . " similar</span>";
                $out .= "<span class='gmeta'>" . self::esc($range) . " &middot; "
                      . self::esc(implode(', ', $mix)) . "</span>";
                $out .= "</summary>";
                $out .= "<table class='tkl sub'>\n" . $head . "<tbody>\n";
                foreach ($members as $m) {
                    $out .= $this->rowHtml($m, $crew, $stepsRemaining, $stepsY,
                                           $works, $lessons, $kids, $parents, $journal, $meta);
                }
                $out .= "</tbody>\n</table>";
                $out .= "</details></td></tr>\n";
            }

            $out .= "</tbody>\n</table>\n";
            return $out;
        }

        // One ticket row, with the existing columns. Used for both an ungrouped row and
        // a group member, so a folded ticket loses nothing but its top-level slot. The
        // TITLE cell carries the drill-down <details>.
        private function rowHtml($v, $crew, $stepsRemaining, $stepsY, $works, $lessons,
                                 $kids, $parents, $journal, $meta) {
            $r  = $v['r'];
            $id = $v['id'];
            $st = $v['st'];

            // kind → '(unkinded)' when NULL/empty on a legacy row.
            $kindRaw = isset($r['kind']) ? (string)$r['kind'] : '';
            $kind = ($kindRaw === '') ? '(unkinded)' : $kindRaw;

            // CREW → 'role,role,...' or '—'.
            $crewList = isset($crew[$id]) ? $crew[$id] : array();
            $crewStr = $crewList ? implode(',', $crewList) : '—';

            // PROGRESS → 'D of Y' (steps DONE of total) only when BOTH are known.
            // steps_remaining counts DOWN to the goal, so DONE = Y - remaining. A
            // finished ticket (remaining 0) reads 'Y of Y', never a backwards '0 of Y'.
            // Clamp to 0..Y so an over/under-reported remaining can't produce a
            // nonsensical 'D of Y' (e.g. negative, or D > Y).
            $hasR = array_key_exists($id, $stepsRemaining);
            $yKey = ($kindRaw === '') ? null : $kindRaw;
            $hasY = ($yKey !== null && isset($stepsY[$yKey]) && $stepsY[$yKey] > 0);
            if ($hasR && $hasY) {
                $total_steps = $stepsY[$yKey];
                $done = $total_steps - $stepsRemaining[$id];
                if ($done < 0) { $done = 0; }
                if ($done > $total_steps) { $done = $total_steps; }
                $progress = self::esc($done) . " of " . self::esc($total_steps);
            } else {
                $progress = '—';
            }

            $worksN   = isset($works[$id])   ? $works[$id]   : 0;
            $lessonsN = isset($lessons[$id]) ? $lessons[$id] : 0;

            // DONE/CLOSED render muted.
            $muted = ($st === 'DONE' || $st === 'CLOSED') ? " class='muted'" : "";
            $stColour = ($st === 'ACTIVE') ? '#1a7a3a'
                      : (($st === 'OPEN' || $st === 'REQUESTED') ? '#b5651d' : '#888');

            // Every dynamic value below is passed through esc() (recursion guard).
            $out  = "<tr" . $muted . ">";
            $out .= "<td class='id'>#" . self::esc($id) . "</td>";
            $out .= "<td class='kind'>" . self::esc($kind) . "</td>";
            $out .= "<td><span class='st' style='background:" . $stColour . "'>"
                  . self::esc($r['status']) . "</span>"
                  . ($v['stopped'] ? "<span class='stopped'>Stopped</span>" : "") . "</td>";
            $out .= "<td><details><summary>" . self::esc($r['title']) . "</summary>"
                  . self::expansionHtml($id, $kids, $parents, $journal, $meta)
                  . "</details></td>";
            $out .= "<td class='crew'>" . self::esc($crewStr) . "</td>";
            $out .= "<td class='num'>" . $progress . "</td>";
            $out .= "<td class='num'>" . self::esc($worksN) . "</td>";
            $out .= "<td class='num'>" . self::esc($lessonsN) . "</td>";
            $out .= "</tr>\n";
            return $out;
        }
    }
}
?>
