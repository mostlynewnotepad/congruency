-- 0002_ticket_approval.sql — ticket approval by WALLET SIGNATURE (the external, unforgeable gate).
--
-- A crank agent may FILE a ticket (ticket.create -> status REQUESTED) but must NOT be able to APPROVE
-- it. Approval is a wallet signature over the ticket's CONTENT digest, written by the human via
-- ticket.approve and verified by crankd against the wallet pubkey before a crank runs. The agent has no
-- wallet, so it cannot forge the signature -- even though, under the interim auth override, it could
-- call the write route. Forward-only + ADDITIVE (CREATE IF NOT EXISTS / ALTER ADD / INSERT OR REPLACE);
-- the schema_migrations guard runs the ALTER exactly once, so it is safe on the live db and re-runs.

-- defensive: guarantee tickets exists (fresh install / shadow db both reach here) WITHOUT approval_sig,
-- so the ALTER below always adds it exactly once.
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL, updated REAL, component TEXT, title TEXT, severity TEXT, status TEXT, body TEXT, meta TEXT
);

ALTER TABLE tickets ADD COLUMN approval_sig TEXT;   -- hex ed25519 signature over the content digest

-- ticket.create [POST]: the agent files a request. status REQUESTED; NOT yet approved.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.create', 'POST',
  'INSERT INTO tickets (ts, updated, component, title, severity, status, body) VALUES (strftime(''%s'',''now''), strftime(''%s'',''now''), :component, :title, :severity, ''REQUESTED'', :body)',
  'token',
  '{"component":"str","title":"str","severity":"str","body":"str"}',
  'file a crank ticket (status REQUESTED); approval is a separate wallet signature'
);

-- ticket.approve [POST]: the human attaches a wallet signature over the ticket content digest.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.approve', 'POST',
  'UPDATE tickets SET approval_sig=:approval_sig, updated=strftime(''%s'',''now'') WHERE id=:id',
  'token',
  '{"id":"int","approval_sig":"str"}',
  'attach a wallet signature over the ticket content digest -- the external approval the agent cannot forge'
);

-- ticket.approval [GET, public]: crankd reads a component's latest ticket (content + approval_sig) so
-- it can recompute the digest and verify the signature before running a crank.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.approval', 'GET',
  'SELECT id, component, title, body, status, approval_sig FROM tickets WHERE component=:component ORDER BY id DESC LIMIT 1',
  'public',
  '{"component":"str"}',
  'the latest ticket for a component (content + wallet approval_sig) for crankd to verify'
);
