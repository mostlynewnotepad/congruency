-- 0014_ticket_artifacts.sql — the artifacts slot: durable outputs a crank produced, stored in FORGE
-- (the content-addressed registry) and referenced here by (name:version, sha). This connects the
-- ticket-class explorer to forge — congruency holds the metadata/provenance, forge holds the blob.
-- crankd publishes each crank's run-evidence (shadow_output) to forge and records the reference.
-- Iteration 11. Additive.

CREATE TABLE IF NOT EXISTS ticket_artifacts (
  id        INTEGER PRIMARY KEY,
  ts        INTEGER,
  ticket_id INTEGER,
  name      TEXT,          -- forge artifact name (e.g. workstation-run)
  version   TEXT,          -- forge artifact version (the crank version)
  forge_sha TEXT,          -- sha256 content address of the blob in forge
  kind      TEXT           -- 'run-output' (later: image, seed, ...)
);
CREATE INDEX IF NOT EXISTS idx_ticket_artifacts_ticket ON ticket_artifacts (ticket_id);

-- artifact.record [POST, token]: reference a forge artifact a crank produced.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'artifact.record', 'POST',
  'INSERT INTO ticket_artifacts (ts, ticket_id, name, version, forge_sha, kind)
   VALUES (strftime(''%s'',''now''), :ticket_id, :name, :version, :forge_sha, :kind)',
  'token',
  '{"ticket_id":"int","name":"str","version":"str","forge_sha":"str","kind":"str"}',
  'reference a forge artifact (name:version + sha) a crank produced, against its ticket'
);

-- artifact.list [GET, public]: a ticket's forge artifacts.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'artifact.list', 'GET',
  'SELECT name, version, forge_sha, kind FROM ticket_artifacts WHERE ticket_id=:ticket_id ORDER BY id',
  'public',
  '{"ticket_id":"int"}',
  'list the forge artifacts a ticket produced'
);
