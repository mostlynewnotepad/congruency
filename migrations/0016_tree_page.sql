-- 0016_tree_page.sql — the "Source tree" page (?page=tree): browse a registered repo's REAL
-- source tree read straight from forge's bare git remote. Data-driven like every other page: a
-- Document_Templates row holds the page shell (nav via <<<SiteMap>>>) and splices in the
-- <<<TreeView>>> invocator; a Documents row 'tree' binds the slug to that template. SiteMap.php
-- adds 'tree' to the nav order (source change, committed alongside). High, fixed id (91) so
-- INSERT OR REPLACE is idempotent and never collides with the seeded templates. Additive.
--
-- Self-contained: guard the base CMS tables with CREATE IF NOT EXISTS so this migration applies
-- to a bare db too (a fresh seed / the migration-isolation shadow), not only one that already has them.

CREATE TABLE IF NOT EXISTS Document_Templates (TemplateID INTEGER PRIMARY KEY, Content TEXT);
CREATE TABLE IF NOT EXISTS Documents (
  DocumentID  TEXT PRIMARY KEY,
  TemplateID  INTEGER,
  Title       TEXT,
  Description TEXT,
  ContentID   INTEGER
);

INSERT OR REPLACE INTO Document_Templates (TemplateID, Content) VALUES (91,
'<!DOCTYPE html>
<html>
<head>
<<<TitleTag>>>
<<<Style>>>
</head>
<body>
<nav><<<SiteMap>>></nav>
<h1>Source tree</h1>
<p>Browse a registered repo''s real source tree, read straight from forge''s bare git remote &mdash; directories drill in, files open in a line-numbered blob view. Rendered through the &lt;&lt;&lt;TreeView&gt;&gt;&gt; tag.</p>
<<<TreeView>>>
</body>
</html>');

INSERT OR REPLACE INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (
  'tree', 91, 'Source tree &middot; Congruency', 'Browse a registered repo''s source from the forge remote', 91
);
