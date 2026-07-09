-- 0005_crank_jobs.sql — content-addressed crank jobs. A job (component + policy + brief + goal) is
-- stored by the sha256 of its CANONICAL spec, so the same job always addresses to the same hash.
-- crank_launch refers to a job by hash and records a run anchor stamped to the agent, so every
-- autonomous run is provenance-linked to the immutable job it ran. Additive.

CREATE TABLE IF NOT EXISTS crank_jobs (
  hash TEXT PRIMARY KEY,   -- sha256 of the canonical spec JSON
  ts   REAL,
  spec TEXT                -- the canonical job JSON (immutable; the hash addresses it)
);

-- job.put [POST]: store a job by its hash (idempotent — same content, same hash).
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'job.put', 'POST',
  'INSERT OR REPLACE INTO crank_jobs (hash, ts, spec) VALUES (:hash, strftime(''%s'',''now''), :spec)',
  'token',
  '{"hash":"str","spec":"str"}',
  'store a content-addressed crank job (hash = sha256 of the canonical spec)'
);

-- job.get [GET, public]: fetch a job's spec by hash.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'job.get', 'GET',
  'SELECT hash, ts, spec FROM crank_jobs WHERE hash=:hash',
  'public',
  '{"hash":"str"}',
  'fetch a content-addressed crank job by hash'
);
