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
 *   PROGRESS — 'X of Y' where X is the latest reported steps_remaining
 *              (newest ticket_events row that HAS a steps_remaining value) and
 *              Y = COUNT(*) of ticket_lifecycles for the ticket's kind at
 *              version 1 (the enumerable steps to the goal); '—' if either is unknown,
 *   WORKS   — count of ticket_works (the UID'd manifest),
 *   LESSONS — count of ticket_events WHERE event='lesson' (harvested at settle).
 * A ticket with an unreleased stop aimed at it is marked STOPPED (see stops(),
 * which mirrors the ticket.stops route in 0030_pair_loop_routes.sql). Rows are
 * ordered ACTIVE first, then OPEN/REQUESTED, then everything else; newest id
 * first within each group; DONE/CLOSED rows are rendered muted.
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
 * models BugReport.php, but reads live rows. Do not remove an esc() call.
 */
if (!class_exists("TicketList")) {
    class TicketList implements Tag_Interface {

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
            // ACTIVE (group 0) leads, then OPEN/REQUESTED (1), then everything else (2).
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

            // PROGRESS X: the LATEST reported steps_remaining per ticket. A row without a
            // steps_remaining (e.g. an auto-journaled status change or a lesson) reports no
            // countdown, so we take the newest row that HAS one. Rows arrive oldest-first,
            // so the last one written per ticket is the latest.
            $stepsX = array();
            foreach (self::safe($db,
                "SELECT ticket_id, steps_remaining FROM ticket_events "
              . "WHERE steps_remaining IS NOT NULL ORDER BY ticket_id, ts, id") as $s) {
                $stepsX[(int)$s['ticket_id']] = (int)$s['steps_remaining'];
            }

            // PROGRESS Y: the enumerable lifecycle length per kind (version 1) — the
            // steps-until-goal that steps_remaining counts down.
            $stepsY = array();
            foreach (self::safe($db,
                "SELECT kind, COUNT(*) AS n FROM ticket_lifecycles "
              . "WHERE version=1 GROUP BY kind") as $y) {
                $stepsY[(string)$y['kind']] = (int)$y['n'];
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
            $out .= "</style>\n";

            // Header counts (all static/derived integers — safe, but the summary strings
            // below embed only ints we compute here, never raw DB text).
            $total   = count($rows);
            $active  = 0; $openish = 0; $doneish = 0; $stoppedCount = 0;

            // Precompute per-row derived values and the STOPPED flag (needs the ancestor walk).
            $view = array();
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

                $view[] = array('r' => $r, 'id' => $id, 'stopped' => $stopped, 'st' => $st);
            }

            $out .= "<p style='font-size:.85rem;color:#555'><strong>" . self::esc($total)
                  . "</strong> tickets &middot; <strong>" . self::esc($active)
                  . "</strong> active &middot; <strong>" . self::esc($openish)
                  . "</strong> open/requested &middot; <strong>" . self::esc($doneish)
                  . "</strong> done/other &middot; <strong>" . self::esc($stoppedCount)
                  . "</strong> stopped</p>\n";

            $out .= "<table class='tkl'>\n<thead><tr>"
                  . "<th>#</th><th>KIND</th><th>STATUS</th><th>TITLE</th>"
                  . "<th>CREW</th><th>PROGRESS</th><th class='num'>WORKS</th><th class='num'>LESSONS</th>"
                  . "</tr></thead>\n<tbody>\n";

            foreach ($view as $v) {
                $r  = $v['r'];
                $id = $v['id'];
                $st = $v['st'];

                // kind → '(unkinded)' when NULL/empty on a legacy row.
                $kindRaw = isset($r['kind']) ? (string)$r['kind'] : '';
                $kind = ($kindRaw === '') ? '(unkinded)' : $kindRaw;

                // CREW → 'role,role,...' or '—'.
                $crewList = isset($crew[$id]) ? $crew[$id] : array();
                $crewStr = $crewList ? implode(',', $crewList) : '—';

                // PROGRESS → 'X of Y' only when BOTH are known.
                $hasX = array_key_exists($id, $stepsX);
                $yKey = ($kindRaw === '') ? null : $kindRaw;
                $hasY = ($yKey !== null && isset($stepsY[$yKey]) && $stepsY[$yKey] > 0);
                if ($hasX && $hasY) {
                    $progress = self::esc($stepsX[$id]) . " of " . self::esc($stepsY[$yKey]);
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
                $out .= "<tr" . $muted . ">";
                $out .= "<td class='id'>#" . self::esc($id) . "</td>";
                $out .= "<td class='kind'>" . self::esc($kind) . "</td>";
                $out .= "<td><span class='st' style='background:" . $stColour . "'>"
                      . self::esc($r['status']) . "</span>"
                      . ($v['stopped'] ? "<span class='stopped'>Stopped</span>" : "") . "</td>";
                $out .= "<td>" . self::esc($r['title']) . "</td>";
                $out .= "<td class='crew'>" . self::esc($crewStr) . "</td>";
                $out .= "<td class='num'>" . $progress . "</td>";
                $out .= "<td class='num'>" . self::esc($worksN) . "</td>";
                $out .= "<td class='num'>" . self::esc($lessonsN) . "</td>";
                $out .= "</tr>\n";
            }
            $out .= "</tbody>\n</table>\n";
            return $out;
        }
    }
}
?>
