-- 0030_pair_loop_routes.sql — two routes the pair-loop harness needs to stay on the governed
-- REST surface (no direct db writes from the harness):
--
--   ticket.kind — classify a ticket after ticket.create (which predates the kind column).
--     SET-ONCE is already enforced by tg_tickets_immutable_identity (re-kinding a kinded
--     ticket aborts); this route only supplies the sanctioned write path.
--   ticket.stops — the stop-state the loop checks BEFORE acting (the brake): counts 'stops'
--     edges aimed at the ticket OR ANY ANCESTOR (walking 'spawned' edges up), excluding stop
--     tickets that have themselves been released by a 'starts' edge (a start is aimed at the
--     stop ticket it releases). active_stops > 0 => the ticket authorizes nothing right now.
--
-- Forward-only, ADDITIVE (INSERT OR REPLACE only).

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.kind', 'POST',
  'UPDATE tickets SET kind = :kind, updated = strftime(''%s'',''now'') WHERE id = :id AND kind IS NULL',
  'token', '{"kind":"str","id":"int"}',
  'classify a ticket (set-once: the identity trigger refuses re-kinding; must exist in ticket_kinds)'
);

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.stops', 'GET',
  'SELECT COUNT(*) AS active_stops FROM ticket_edges st WHERE st.kind = ''stops'' AND st.child_id IN (WITH RECURSIVE anc(id) AS (SELECT :ticket_id UNION SELECT e.parent_id FROM ticket_edges e JOIN anc ON e.child_id = anc.id AND e.kind = ''spawned'') SELECT id FROM anc) AND NOT EXISTS (SELECT 1 FROM ticket_edges rel WHERE rel.kind = ''starts'' AND rel.child_id = st.parent_id)',
  'public', '{"ticket_id":"int"}',
  'active (unreleased) stop tickets aimed at this ticket or any ancestor — >0 means HALT'
);
