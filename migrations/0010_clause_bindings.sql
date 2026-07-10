-- 0010_clause_bindings.sql — the binding affordance. Guarantees are harvested at CRANK time, but the
-- author knows which shadow assertion satisfies which mandate clause at FILE time (it wrote both). So
-- the agent DECLARES bindings when filing (clause_seq <- guarantee label); crankd APPLIES them during
-- auto-harvest, setting guarantees.clause_seq. This closes the automated coverage loop: declare once,
-- coverage computes itself. Iteration 6 of the ticket-class build. Additive.

CREATE TABLE IF NOT EXISTS clause_bindings (
  id              INTEGER PRIMARY KEY,
  ts              INTEGER,
  ticket_id       INTEGER,
  clause_seq      INTEGER,       -- the mandate clause this label satisfies
  guarantee_label TEXT,          -- the shadow ✓ label (exact) the author declares as satisfying it
  digest          TEXT           -- sha256(ticket_id|clause_seq|label)
);
CREATE INDEX IF NOT EXISTS idx_clause_bindings_ticket ON clause_bindings (ticket_id);

-- binding.record [POST, token]: declare one guarantee-label -> clause binding for a ticket.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'binding.record', 'POST',
  'INSERT INTO clause_bindings (ts, ticket_id, clause_seq, guarantee_label, digest)
   VALUES (strftime(''%s'',''now''), :ticket_id, :clause_seq, :guarantee_label, :digest)',
  'token',
  '{"ticket_id":"int","clause_seq":"int","guarantee_label":"str","digest":"str"}',
  'declare that a shadow guarantee label satisfies a mandate clause (applied by crankd at harvest)'
);

-- binding.list [GET, public]: a ticket's declared label->clause bindings (crankd reads this at harvest).
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'binding.list', 'GET',
  'SELECT clause_seq, guarantee_label FROM clause_bindings WHERE ticket_id=:ticket_id',
  'public',
  '{"ticket_id":"int"}',
  'list a ticket''s declared guarantee-label -> clause bindings'
);
