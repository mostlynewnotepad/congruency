-- 0013_journey.sql — the ticket's journey: the ordered record of what happened from goal to finish,
-- blunders AND successes (the "record blunders and successes" ask). crankd auto-journals crank
-- outcomes — a mint is a 'success', a regression refusal / failure is a 'blunder' — so the history
-- writes itself; supersessions and notes can be journaled too. Iteration 10. Additive.

CREATE TABLE IF NOT EXISTS journey (
  id        INTEGER PRIMARY KEY,
  ts        INTEGER,
  ticket_id INTEGER,
  kind      TEXT,          -- 'success' | 'blunder' | 'pivot' | 'note'
  text      TEXT
);
CREATE INDEX IF NOT EXISTS idx_journey_ticket ON journey (ticket_id, id);

-- journey.record [POST, token]: append one journey event to a ticket.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'journey.record', 'POST',
  'INSERT INTO journey (ts, ticket_id, kind, text)
   VALUES (strftime(''%s'',''now''), :ticket_id, :kind, :text)',
  'token',
  '{"ticket_id":"int","kind":"str","text":"str"}',
  'append a journey event (success/blunder/pivot/note) to a ticket''s history'
);

-- journey.list [GET, public]: a ticket's journey in order.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'journey.list', 'GET',
  'SELECT kind, text, ts FROM journey WHERE ticket_id=:ticket_id ORDER BY id',
  'public',
  '{"ticket_id":"int"}',
  'list a ticket''s journey (blunders and successes, in order)'
);
