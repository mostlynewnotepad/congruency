-- 0032_dispatch_routes.sql — the dispatch queue: what dispatch-01 reads before deciding.
-- One public route; the dispatcher's decisions all execute through existing governed routes
-- (ticket.kind, ticket.progress, ticket.create, edge.record) and pair_loop itself. Additive.

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.queue', 'GET',
  'SELECT id, kind, status, component, title, body FROM tickets WHERE upper(status) IN (''OPEN'', ''REQUESTED'') ORDER BY id',
  'public', '{}',
  'the dispatch queue: open/requested tickets, oldest first (brake state checked per-ticket via ticket.stops)'
);
