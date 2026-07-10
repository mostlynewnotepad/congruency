-- 0025_shadowforge_page.sql — the "Shadow Forge" page (?page=shadowforge): a read-only reflection of
-- the SHADOW FORGE index (~/bin/config/forge/shadow_forge/shadow_index.db, a SEPARATE database from
-- CONGRUENCY_SQLITE), built by jazz-forge's forge/shadow_forge.py (RFC-0030). It surfaces per-file
-- test coverage (SF-1), spec-citation (SF-3), and the SF-6 DEFICIT backlog: files with no test and/or
-- no spec.
-- Data-driven like every other page: a Document_Templates row holds the page shell (nav via
-- <<<SiteMap>>>) and splices in the <<<ShadowForge>>> invocator; a Documents row 'shadowforge' binds
-- the slug to that template. SiteMap.php adds 'shadowforge' to the nav order (source change, committed
-- alongside). High, fixed id (98) so INSERT OR REPLACE is idempotent and never collides with the
-- seeded templates or the forge(95)/omni(96)/bugs(97) pages. Additive.
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

INSERT OR REPLACE INTO Document_Templates (TemplateID, Content) VALUES (98,
'<!DOCTYPE html>
<html>
<head>
<<<TitleTag>>>
<<<Style>>>
</head>
<body>
<nav><<<SiteMap>>></nav>
<h1>Shadow Forge</h1>
<p>Per-file test/spec coverage over our actively-developed code (RFC-0030) &mdash; and the deficit backlog: where we lack a test or a spec citation.</p>
<<<ShadowForge>>>
</body>
</html>');

INSERT OR REPLACE INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (
  'shadowforge', 98, 'Shadow Forge &middot; Congruency', 'Read-only reflection of the shadow-forge coverage + spec-deficit backlog (RFC-0030)', 98
);
