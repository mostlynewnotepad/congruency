-- 0004_policies.sql — STANDING SCOPE APPROVAL: a wallet-signed policy authorizes an agent to crank a
-- component autonomously within bounds (max_version, expiry), replacing per-crank sign-off. crankd
-- verifies the signature + bounds before running; the audit-veto still confines every patch, so the
-- blast radius stays bounded even inside the policy. Additive.

CREATE TABLE IF NOT EXISTS crank_policies (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          REAL,
  component   TEXT,
  max_version TEXT,       -- crank allowed while the component's current_version < max_version
  expires     INTEGER,    -- unix seconds; 0 = no expiry
  sig         TEXT        -- hex ed25519 signature over the policy digest (wallet 'crank-approver')
);

-- policy.create [POST]: the human files a wallet-signed standing policy.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'policy.create', 'POST',
  'INSERT INTO crank_policies (ts, component, max_version, expires, sig) VALUES (strftime(''%s'',''now''), :component, :max_version, :expires, :sig)',
  'token',
  '{"component":"str","max_version":"str","expires":"int","sig":"str"}',
  'file a wallet-signed standing crank policy for a component (scope: max_version, expiry)'
);

-- policy.active [GET, public]: crankd reads the newest policy for a component to verify + bound.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'policy.active', 'GET',
  'SELECT id, component, max_version, expires, sig FROM crank_policies WHERE component=:component ORDER BY id DESC LIMIT 1',
  'public',
  '{"component":"str"}',
  'the newest standing policy for a component (for crankd to verify + apply bounds)'
);
