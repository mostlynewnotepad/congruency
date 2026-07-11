-- 0028_memgraph_page.sql — the "Memory Graph" page (?page=memgraph): a read-only reflection of the
-- RFC-0031 memory-and-spec property graph (~/bin/config/forge/mem_graph.db, a SEPARATE database from
-- CONGRUENCY_SQLITE), built by jazz-forge's forge/mem_graph.py. It unifies the omni corpus,
-- spec-drift, the memory timeline, the shadow-forge, and semantic near-duplicates into one
-- node/edge property graph (+ a lifted drift metric + a freshness meta stamp).
-- Data-driven like every other page: a Document_Templates row holds the page shell (nav via
-- <<<SiteMap>>>) and splices in the <<<MemGraph>>> invocator; a Documents row 'memgraph' binds the
-- slug to that template. SiteMap.php adds 'memgraph' to the nav order (source change, committed
-- alongside). High, fixed id (99) so INSERT OR REPLACE is idempotent and never collides with the
-- seeded templates or the forge(95)/omni(96)/bugs(97)/shadowforge(98) pages. Additive.
--
-- Self-contained: guard the base CMS tables with CREATE IF NOT EXISTS so this migration applies to a
-- bare db too (a fresh seed / the migration-isolation shadow), not only one that already has them.

CREATE TABLE IF NOT EXISTS Document_Templates (TemplateID INTEGER PRIMARY KEY, Content TEXT);
CREATE TABLE IF NOT EXISTS Documents (
  DocumentID  TEXT PRIMARY KEY,
  TemplateID  INTEGER,
  Title       TEXT,
  Description TEXT,
  ContentID   INTEGER
);

INSERT OR REPLACE INTO Document_Templates (TemplateID, Content) VALUES (99,
'<!DOCTYPE html>
<html>
<head>
<<<TitleTag>>>
<<<Style>>>
</head>
<body>
<nav><<<SiteMap>>></nav>
<h1>Memory Graph</h1>
<p>RFC-0031 property graph over the omni corpus, spec-drift, the memory timeline, the shadow-forge, and semantic near-dupes (~/bin/config/forge/mem_graph.db).</p>
<<<MemGraph>>>
</body>
</html>');

INSERT OR REPLACE INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (
  'memgraph', 99, 'Memory Graph &middot; Congruency', 'Read-only reflection of the RFC-0031 memory-and-spec graph &mdash; nodes/edges, drift, near-dupes', 99
);
