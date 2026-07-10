-- 0017_repo_docs.sql — per-repo documentation (docs/ + README), ingested and associated with each
-- repo (feature c). congruency holds the doc bodies; tooling ingests them through the token write
-- route, and they are served read-only through public routes and the <<<RepoDocs>>> browser on
-- ?page=repodocs. Additive.
--
-- Self-contained: CREATE ... IF NOT EXISTS the base CMS tables so this migration applies to a bare
-- db too (a fresh seed / the migration-isolation shadow), not only one that already has them.

CREATE TABLE IF NOT EXISTS repo_docs (
  id   INTEGER PRIMARY KEY,
  ts   INTEGER,
  repo TEXT,
  path TEXT,
  kind TEXT,
  body TEXT
);
CREATE INDEX IF NOT EXISTS idx_repo_docs_repo_path ON repo_docs (repo, path);

-- doc.repos [GET, public]: repos that have docs.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'doc.repos', 'GET',
  'SELECT DISTINCT repo FROM repo_docs ORDER BY repo',
  'public',
  '{}',
  'list repos that have ingested documentation'
);

-- doc.list [GET, public]: a repo's documentation files.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'doc.list', 'GET',
  'SELECT path, kind FROM repo_docs WHERE repo=:repo ORDER BY path',
  'public',
  '{"repo":"str"}',
  'list a repo''s documentation files'
);

-- doc.read [GET, public]: one doc's body.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'doc.read', 'GET',
  'SELECT body, kind FROM repo_docs WHERE repo=:repo AND path=:path',
  'public',
  '{"repo":"str","path":"str"}',
  'read one repo documentation file body'
);

-- doc.record [POST, token]: ingest a repo documentation file.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'doc.record', 'POST',
  'INSERT INTO repo_docs (ts, repo, path, kind, body)
   VALUES (strftime(''%s'',''now''), :repo, :path, :kind, :body)',
  'token',
  '{"repo":"str","path":"str","kind":"str","body":"str"}',
  'ingest a repo documentation file'
);

-- the page: a Document_Templates row (fixed id 92) with the shell + <<<RepoDocs>>>, and a Documents
-- row 'repodocs' binding the slug to that template. High, fixed ids so INSERT OR REPLACE is
-- idempotent and never collides with the seeded templates.
CREATE TABLE IF NOT EXISTS Document_Templates (TemplateID INTEGER PRIMARY KEY, Content TEXT);
CREATE TABLE IF NOT EXISTS Documents (
  DocumentID  TEXT PRIMARY KEY,
  TemplateID  INTEGER,
  Title       TEXT,
  Description TEXT,
  ContentID   INTEGER
);

INSERT OR REPLACE INTO Document_Templates (TemplateID, Content) VALUES (92,
'<!DOCTYPE html>
<html>
<head>
<<<TitleTag>>>
<<<Style>>>
</head>
<body>
<nav><<<SiteMap>>></nav>
<h1>Repo docs</h1>
<p>Per-repo documentation &mdash; each repo''s <code>docs/</code> and README, ingested and associated with the repo. Rendered through the &lt;&lt;&lt;RepoDocs&gt;&gt;&gt; tag.</p>
<<<RepoDocs>>>
</body>
</html>');

INSERT OR REPLACE INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (
  'repodocs', 92, 'Repo docs &middot; Congruency', 'Per-repo documentation browser', 92
);
