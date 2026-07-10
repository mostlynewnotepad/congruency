-- 0009_guarantees.sql — the guarantee corpus. A guarantee is a green shadow assertion (a ✓ label)
-- harvested from a crank run's shadow_output, ATTRIBUTED to the ticket whose change introduced that
-- shadow (by section), and BOUND to a mandate clause it satisfies. This closes the thought-1 loop:
-- a clause with >=1 bound guarantee is verified; a clause with none is an UNVERIFIED gap. Content-
-- addressed by sha256(ticket|shadow|guarantee). Iteration 4 of the ticket-class build. Additive.

CREATE TABLE IF NOT EXISTS guarantees (
  id         INTEGER PRIMARY KEY,
  ts         INTEGER,
  ticket_id  INTEGER,       -- the ticket whose change this guarantee belongs to (section attribution)
  version    TEXT,          -- the version whose run asserted it
  shadow     TEXT,          -- tests/down-shadow.py — the shadow section it came from
  guarantee  TEXT,          -- the ✓ label (the falsifiable assertion that held)
  clause_seq INTEGER,       -- the mandate clause (mandates.seq) it binds to; NULL = unbound
  digest     TEXT           -- sha256(ticket_id|shadow|guarantee) — content address / identity
);
CREATE INDEX IF NOT EXISTS idx_guarantees_ticket ON guarantees (ticket_id);

-- guarantee.record [POST, token]: record one harvested, clause-bound guarantee.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'guarantee.record', 'POST',
  'INSERT INTO guarantees (ts, ticket_id, version, shadow, guarantee, clause_seq, digest)
   VALUES (strftime(''%s'',''now''), :ticket_id, :version, :shadow, :guarantee, :clause_seq, :digest)',
  'token',
  '{"ticket_id":"int","version":"str","shadow":"str","guarantee":"str","clause_seq":"int","digest":"str"}',
  'record one harvested shadow guarantee, attributed to a ticket and bound to a mandate clause'
);

-- guarantee.list [GET, public]: a ticket's guarantees, in record order.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'guarantee.list', 'GET',
  'SELECT version, shadow, guarantee, clause_seq FROM guarantees WHERE ticket_id=:ticket_id ORDER BY id',
  'public',
  '{"ticket_id":"int"}',
  'list a ticket''s harvested guarantees and the clauses they bind to'
);
