-- 0022_omni_page.sql — the "Omni-git Explorer" page (?page=omni): a read-only reflection of the
-- omni-git INDEX (~/bin/config/forge/omni_index.db, a SEPARATE database from CONGRUENCY_SQLITE),
-- built by jazz-forge's omni_index.py. It answers "each file maps to one or more repositories at
-- different times": the occ table holds one row per (blob,path) OCCURRENCE across every snapshot, so
-- a single path fans out to many (repo,ts) pairs.
-- Data-driven like every other page: a Document_Templates row holds the page shell (nav via
-- <<<SiteMap>>>) and splices in the <<<OmniExplorer>>> invocator; a Documents row 'omni' binds the
-- slug to that template. SiteMap.php adds 'omni' to the nav order (source change, committed
-- alongside). High, fixed id (96) so INSERT OR REPLACE is idempotent and never collides with the
-- seeded templates. Additive.
--
-- Self-contained: guard the base CMS tables with CREATE IF NOT EXISTS so this migration applies to
-- a bare db too (a fresh seed / the migration-isolation shadow), not only one that already has them.

CREATE TABLE IF NOT EXISTS Document_Templates (TemplateID INTEGER PRIMARY KEY, Content TEXT);
CREATE TABLE IF NOT EXISTS Documents (
  DocumentID  TEXT PRIMARY KEY,
  TemplateID  INTEGER,
  Title       TEXT,
  Description TEXT,
  ContentID   INTEGER
);

INSERT OR REPLACE INTO Document_Templates (TemplateID, Content) VALUES (96,
'<!DOCTYPE html>
<html>
<head>
<<<TitleTag>>>
<<<Style>>>
</head>
<body>
<nav><<<SiteMap>>></nav>
<h1>Omni-git Explorer</h1>
<p>Every file across every snapshot (~/bin/config/forge/omni_index.db) &mdash; a file maps to one or more repos at different times.</p>
<<<OmniExplorer>>>
</body>
</html>');

INSERT OR REPLACE INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (
  'omni', 96, 'Omni-git Explorer &middot; Congruency', 'Read-only reflection of the omni-git index &mdash; file to repos at different times', 96
);
