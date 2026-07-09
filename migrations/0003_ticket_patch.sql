-- 0003_ticket_patch.sql — the crank's actual change rides on the ticket as a confined python patch.
--
-- So that approval BINDS the exact change: the agent files the patch, the wallet signature covers the
-- content digest (which now includes the patch), and crankd applies the patch under the audit-veto
-- (confined to the repo — no shell-out / out-of-repo writes) BEFORE minting. Additive; the
-- schema_migrations guard runs the ALTER once.

ALTER TABLE tickets ADD COLUMN patch TEXT;   -- the python patch crankd applies (confined) before mint

-- ticket.create now carries the patch; status REQUESTED (approval is a separate wallet signature).
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.create', 'POST',
  'INSERT INTO tickets (ts, updated, component, title, severity, status, body, patch) VALUES (strftime(''%s'',''now''), strftime(''%s'',''now''), :component, :title, :severity, ''REQUESTED'', :body, :patch)',
  'token',
  '{"component":"str","title":"str","severity":"str","body":"str","patch":"str"}',
  'file a crank ticket with its change (patch); status REQUESTED, approval is a separate wallet signature'
);

-- ticket.approval returns the patch too, so crankd can bind approval to it and apply it.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.approval', 'GET',
  'SELECT id, component, title, body, patch, status, approval_sig FROM tickets WHERE component=:component ORDER BY id DESC LIMIT 1',
  'public',
  '{"component":"str"}',
  'the latest ticket for a component (content + patch + approval_sig) for crankd to verify + apply'
);
