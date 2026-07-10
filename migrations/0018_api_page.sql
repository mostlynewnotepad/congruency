-- 0018_api_page.sql — the "API reference" page (?page=api): a standardized, browsable reference for
-- the data-driven API surface. Every row of api_routes (name, method, sql, auth, params, meta) is
-- rendered with its method, declared params and a response shape DERIVED from its SQL, plus the
-- generic ?api=<table> CRUD layer and the admin denylist. Data-driven like every other page: a
-- Document_Templates row holds the shell (nav via <<<SiteMap>>>) and splices in the <<<ApiReference>>>
-- invocator; a Documents row 'api' binds the slug. SiteMap.php adds 'api' to the nav order (source
-- change, committed alongside). High, fixed id (93) so INSERT OR REPLACE is idempotent and never
-- collides with the seeded templates. Additive.
--
-- Self-contained: CREATE ... IF NOT EXISTS the base CMS tables so this migration applies to a bare
-- db too (a fresh seed / the migration-isolation shadow), not only one that already has them.

CREATE TABLE IF NOT EXISTS Document_Templates (TemplateID INTEGER PRIMARY KEY, Content TEXT);
CREATE TABLE IF NOT EXISTS Documents (
  DocumentID  TEXT PRIMARY KEY,
  TemplateID  INTEGER,
  Title       TEXT,
  Description TEXT,
  ContentID   INTEGER
);

INSERT OR REPLACE INTO Document_Templates (TemplateID, Content) VALUES (93,
'<!DOCTYPE html>
<html>
<head>
<<<TitleTag>>>
<<<Style>>>
</head>
<body>
<nav><<<SiteMap>>></nav>
<h1>API reference</h1>
<p>The documented, standardized API &mdash; every named route in <code>api_routes</code> with its method, declared params and a response shape derived from its SQL, plus the generic <code>?api=&lt;table&gt;</code> CRUD layer and the admin denylist. Rendered through the &lt;&lt;&lt;ApiReference&gt;&gt;&gt; tag.</p>
<<<ApiReference>>>
</body>
</html>');

INSERT OR REPLACE INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (
  'api', 93, 'API reference &middot; Congruency', 'Standardized reference for the data-driven API surface', 93
);
