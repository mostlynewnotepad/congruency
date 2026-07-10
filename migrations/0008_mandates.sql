-- 0008_mandates.sql — the first ticket-class containment table: a ticket's MANDATE, the ordered set
-- of falsifiable clauses its change must satisfy. This is the keystone the guarantee corpus will bind
-- to (a guarantee satisfies a clause; a clause with no guarantee is an UNVERIFIED gap). Iteration 2 of
-- the ticket-class build: store + render the clauses. Authoring mandates at ticket-filing time is a
-- later increment; for now clauses are recorded via mandate.record. Additive.

CREATE TABLE IF NOT EXISTS mandates (
  id        INTEGER PRIMARY KEY,
  ts        INTEGER,
  ticket_id INTEGER,
  seq       INTEGER,        -- clause order within the mandate
  clause    TEXT,           -- one falsifiable clause the change must satisfy
  digest    TEXT            -- sha256(ticket_id|seq|clause) — content address / clause identity
);
CREATE INDEX IF NOT EXISTS idx_mandates_ticket ON mandates (ticket_id, seq);

-- mandate.record [POST, token]: file one clause of a ticket's mandate.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'mandate.record', 'POST',
  'INSERT INTO mandates (ts, ticket_id, seq, clause, digest)
   VALUES (strftime(''%s'',''now''), :ticket_id, :seq, :clause, :digest)',
  'token',
  '{"ticket_id":"int","seq":"int","clause":"str","digest":"str"}',
  'record one falsifiable clause of a ticket''s mandate'
);

-- mandate.list [GET, public]: a ticket''s mandate clauses, in order.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'mandate.list', 'GET',
  'SELECT seq, clause, digest FROM mandates WHERE ticket_id=:ticket_id ORDER BY seq',
  'public',
  '{"ticket_id":"int"}',
  'list a ticket''s mandate clauses in order'
);
