-- 0019_vector_store.sql — the native vector-store: semantic search over the documentation corpus
-- (repo_docs). An `embeddings` table holds L2-normalized chunk vectors (JSON float arrays), ingested
-- through a token write route; ?page=search embeds a query via the local Ollama nomic-embed-text
-- endpoint and cosine-ranks the stored vectors through the <<<SemanticSearch>>> tag. Additive.
--
-- Self-contained: CREATE ... IF NOT EXISTS the base CMS tables so this migration applies to a bare
-- db too (a fresh seed / the migration-isolation shadow), not only one that already has them.

CREATE TABLE IF NOT EXISTS embeddings (
  id        INTEGER PRIMARY KEY,
  ts        INTEGER,
  repo      TEXT,
  path      TEXT,
  chunk_seq INTEGER,
  section   TEXT,
  text      TEXT,
  dim       INTEGER,
  model     TEXT,
  vector    TEXT
);
CREATE INDEX IF NOT EXISTS idx_embeddings_repo_path ON embeddings (repo, path);

-- search.record [POST, token]: ingest one L2-normalized doc-chunk embedding.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'search.record', 'POST',
  'INSERT INTO embeddings (ts, repo, path, chunk_seq, section, text, dim, model, vector)
   VALUES (strftime(''%s'',''now''), :repo, :path, :chunk_seq, :section, :text, :dim, :model, :vector)',
  'token',
  '{"repo":"str","path":"str","chunk_seq":"int","section":"str","text":"str","dim":"int","model":"str","vector":"str"}',
  'ingest one L2-normalized doc-chunk embedding into the vector store'
);

-- search.stats [GET, public]: vector-store coverage (chunk + doc counts) per embedding model.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'search.stats', 'GET',
  'SELECT model, COUNT(*) AS chunks, COUNT(DISTINCT repo||''/''||path) AS docs FROM embeddings GROUP BY model',
  'public',
  '{}',
  'vector-store coverage: chunk + doc counts per embedding model'
);

-- the page: a Document_Templates row (fixed id 94) with the shell + <<<SemanticSearch>>>, and a
-- Documents row 'search' binding the slug. High, fixed ids so INSERT OR REPLACE is idempotent and
-- never collides with the seeded templates.
CREATE TABLE IF NOT EXISTS Document_Templates (TemplateID INTEGER PRIMARY KEY, Content TEXT);
CREATE TABLE IF NOT EXISTS Documents (
  DocumentID  TEXT PRIMARY KEY,
  TemplateID  INTEGER,
  Title       TEXT,
  Description TEXT,
  ContentID   INTEGER
);

INSERT OR REPLACE INTO Document_Templates (TemplateID, Content) VALUES (94,
'<!DOCTYPE html>
<html>
<head>
<<<TitleTag>>>
<<<Style>>>
</head>
<body>
<nav><<<SiteMap>>></nav>
<h1>Semantic search</h1>
<p>Search the documentation corpus by <em>meaning</em> &mdash; the query is embedded with the local <code>nomic-embed-text</code> model and cosine-ranked against the stored chunk vectors in <code>embeddings</code>. Rendered through the &lt;&lt;&lt;SemanticSearch&gt;&gt;&gt; tag.</p>
<<<SemanticSearch>>>
</body>
</html>');

INSERT OR REPLACE INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (
  'search', 94, 'Semantic search &middot; Congruency', 'Semantic search over the documentation corpus', 94
);
