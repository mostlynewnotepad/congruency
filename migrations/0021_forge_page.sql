-- 0021_forge_page.sql — the "Forge" page (?page=forge): a read-only reflection of forge's OWN
-- sqlite (~/bin/config/forge/forge.db, a SEPARATE database from CONGRUENCY_SQLITE) — its
-- append-only actions journal + content-addressed artifacts registry + bare remotes/archives.
-- Data-driven like every other page: a Document_Templates row holds the page shell (nav via
-- <<<SiteMap>>>) and splices in the <<<ForgeView>>> invocator; a Documents row 'forge' binds the
-- slug to that template. SiteMap.php adds 'forge' to the nav order (source change, committed
-- alongside). High, fixed id (95) so INSERT OR REPLACE is idempotent and never collides with the
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

INSERT OR REPLACE INTO Document_Templates (TemplateID, Content) VALUES (95,
'<!DOCTYPE html>
<html>
<head>
<<<TitleTag>>>
<<<Style>>>
</head>
<body>
<nav><<<SiteMap>>></nav>
<h1>Forge</h1>
<p>Reflection of the local forge store (~/bin/config/forge/forge.db) &mdash; the action-log + artifact registry.</p>
<<<ForgeView>>>
</body>
</html>');

INSERT OR REPLACE INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (
  'forge', 95, 'Forge &middot; Congruency', 'Read-only reflection of the forge action-log + artifact registry', 95
);
