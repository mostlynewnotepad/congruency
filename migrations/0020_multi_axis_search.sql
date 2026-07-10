-- 0020_multi_axis_search.sql — multi-axis search: a KEYWORD (full-text) axis over repo_docs plus
-- repo/type facets, combinable with the existing semantic axis on ?page=search. The rewritten
-- <<<SemanticSearch>>> invocator drives all axes; these routes expose the keyword axis + facet values
-- over the data layer. Additive; robust LIKE (no FTS5 dependency).
--
-- Self-contained: CREATE ... IF NOT EXISTS the base tables so this migration applies to a bare db too
-- (a fresh seed / the migration-isolation shadow), not only one that already has them.

CREATE TABLE IF NOT EXISTS api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);
CREATE TABLE IF NOT EXISTS repo_docs (
  id   INTEGER PRIMARY KEY,
  ts   INTEGER,
  repo TEXT,
  path TEXT,
  kind TEXT,
  body TEXT
);
CREATE INDEX IF NOT EXISTS idx_repo_docs_repo_path ON repo_docs (repo, path);

-- search.text [GET, public]: the KEYWORD (full-text) axis over repo_docs via LIKE (robust; no FTS5).
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'search.text', 'GET',
  'SELECT repo, path, substr(body,1,240) AS snippet FROM repo_docs
   WHERE body LIKE ''%''||:q||''%'' AND (:repo='''' OR repo=:repo) ORDER BY repo, path LIMIT 40',
  'public',
  '{"q":"str","repo":"str"}',
  'keyword (full-text) search over the documentation corpus, optionally repo-scoped'
);

-- search.facets [GET, public]: the distinct repo + kind facet values (one result set, discriminated
-- by a 'facet' column) that populate the multi-axis search form's selects.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'search.facets', 'GET',
  'SELECT ''repo'' AS facet, repo AS value FROM (SELECT DISTINCT repo FROM repo_docs)
   UNION ALL
   SELECT ''kind'' AS facet, kind AS value FROM (SELECT DISTINCT kind FROM repo_docs)
   ORDER BY facet, value',
  'public',
  '{}',
  'distinct repo + kind facet values for the multi-axis search form'
);
