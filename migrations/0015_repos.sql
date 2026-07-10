-- 0015_repos.sql — the repo dimension: source-in-forge. Tracks repos and their source commits so
-- congruency can reference the source a crank came from. congruency holds the metadata/provenance;
-- forge holds the blobs. Additive.

CREATE TABLE IF NOT EXISTS repos (
  name         TEXT PRIMARY KEY,
  forge_remote TEXT,
  head_commit  TEXT,
  ts           INTEGER
);

CREATE TABLE IF NOT EXISTS source_commits (
  id           INTEGER PRIMARY KEY,
  ts           INTEGER,
  repo         TEXT,
  commit_sha   TEXT,
  is_current   INTEGER DEFAULT 0,
  forge_remote TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_commits_repo_current ON source_commits (repo, is_current);

-- repo.list [GET, public]: the registered repos.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'repo.list', 'GET',
  'SELECT name, forge_remote, head_commit FROM repos ORDER BY name',
  'public',
  '{}',
  'list the registered repos'
);

-- source.commits [GET, public]: a repo's source commits, newest first.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'source.commits', 'GET',
  'SELECT commit_sha, ts, is_current, forge_remote FROM source_commits WHERE repo=:repo ORDER BY id DESC',
  'public',
  '{"repo":"str"}',
  'list a repo''s source commits, newest first'
);

-- source.record [POST, token]: record a source commit for a repo.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'source.record', 'POST',
  'INSERT INTO source_commits (ts, repo, commit_sha, is_current, forge_remote)
   VALUES (strftime(''%s'',''now''), :repo, :commit_sha, :is_current, :forge_remote)',
  'token',
  '{"repo":"str","commit_sha":"str","is_current":"int","forge_remote":"str"}',
  'record a source commit for a repo'
);
