-- 0006_crank_runs.sql — durable crank run history. Today crankd captures the shadow-gate output but
-- returns only a 5-line tail; the full record of a run's pass/fail lives only in the per-run screen
-- log. This table persists each crank's FULL shadow output, content-addressed by its sha256, linked
-- to the minted version + the authorizing ticket. It is the source the guarantee corpus (phase 2)
-- harvests from. Additive — no existing table or route changes.

CREATE TABLE IF NOT EXISTS crank_runs (
  id            INTEGER PRIMARY KEY,
  ts            INTEGER,
  component     TEXT,
  version       TEXT,          -- the version this run minted (from install.json after --mint)
  ticket_id     INTEGER,       -- provenance: the authorizing ticket
  authorized_by TEXT,          -- 'ticket-signature' | 'policy'
  ok            INTEGER,       -- 1 = shadows green + minted
  shadow_output TEXT,          -- the FULL gate stdout (not the tail)
  digest        TEXT           -- sha256(shadow_output) — content address of the output blob
);
CREATE INDEX IF NOT EXISTS idx_crank_runs_component ON crank_runs (component, id DESC);
CREATE INDEX IF NOT EXISTS idx_crank_runs_digest ON crank_runs (digest);

-- run.record [POST, token]: persist one crank run (crankd calls this after a green mint).
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'run.record', 'POST',
  'INSERT INTO crank_runs (ts, component, version, ticket_id, authorized_by, ok, shadow_output, digest)
   VALUES (strftime(''%s'',''now''), :component, :version, :ticket_id, :authorized_by, :ok, :shadow_output, :digest)',
  'token',
  '{"component":"str","version":"str","ticket_id":"int","authorized_by":"str","ok":"int","shadow_output":"str","digest":"str"}',
  'persist a crank run with its full shadow output (content-addressed by sha256(shadow_output))'
);

-- run.get [GET, public]: fetch run(s) whose output content-addresses to a digest.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'run.get', 'GET',
  'SELECT id, ts, component, version, ticket_id, authorized_by, ok, shadow_output, digest
   FROM crank_runs WHERE digest=:digest ORDER BY id DESC',
  'public',
  '{"digest":"str"}',
  'fetch crank run(s) by the content address of their shadow output'
);

-- run.recent [GET, public]: the component''s recent runs (metadata only — omits the output blob).
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'run.recent', 'GET',
  'SELECT id, ts, version, ticket_id, authorized_by, ok, digest
   FROM crank_runs WHERE component=:component ORDER BY id DESC LIMIT :n',
  'public',
  '{"component":"str","n":"int"}',
  'list a component''s recent crank runs (metadata; use run.get for the full output)'
);
