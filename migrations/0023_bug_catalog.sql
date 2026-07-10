-- 0023_bug_catalog.sql — ?page=bugs, a first-class BUG CATALOG that REPURPOSES congruency's own
-- bug-report schema (tooling/congruencey-bugs/bugs.json: id,title,severity,file,repro,success) and
-- unifies TWO sources under one table: 'congruency' — the curated + reproduced bugs (each with a
-- runnable repro path) — and 'corpus' — corpus-wide "consistent bug" pattern findings (an
-- anti-pattern id + a consistency metric: fanout occurrences across N repos). Mechanism only; the
-- data is ingested after deploy through bug.record. Mirrors ?page=forge / ?page=omni: a data table +
-- api_routes + a Document_Templates/Documents pair splicing in the <<<BugCatalog>>> invocator.
-- Additive.
--
-- Self-contained: CREATE ... IF NOT EXISTS the base tables so this migration applies to a bare db too
-- (a fresh seed / the migration-isolation shadow), not only one that already has them.

CREATE TABLE IF NOT EXISTS api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);

CREATE TABLE IF NOT EXISTS bugs (
  bug_id   TEXT,
  source   TEXT,
  title    TEXT,
  severity TEXT,
  location TEXT,
  repro    TEXT,
  success  TEXT,
  fanout   INTEGER DEFAULT 0,
  repos    INTEGER DEFAULT 0,
  status   TEXT DEFAULT 'open',
  pattern  TEXT,
  meta     TEXT,
  PRIMARY KEY (source, bug_id)
);

-- bug.record [POST, token]: UPSERT one bug keyed (source, bug_id). 'source' is 'congruency' for the
-- curated catalog or 'corpus' for the pattern lens; fanout/repos carry the corpus consistency metric;
-- pattern is the anti-pattern id.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'bug.record', 'POST',
  'INSERT OR REPLACE INTO bugs (bug_id, source, title, severity, location, repro, success, fanout, repos, status, pattern, meta)
   VALUES (:bug_id, :source, :title, :severity, :location, :repro, :success, :fanout, :repos, :status, :pattern, :meta)',
  'token',
  '{"bug_id":"str","source":"str","title":"str","severity":"str","location":"str","repro":"str","success":"str","fanout":"int","repos":"int","status":"str","pattern":"str","meta":"str"}',
  'upsert one bug (congruency curated repro or corpus consistent-bug pattern), keyed (source, bug_id)'
);

-- bug.list [GET, public]: the catalog, facetable by source + severity (empty facet = all), severity-ordered.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'bug.list', 'GET',
  'SELECT * FROM bugs WHERE (:source='''' OR source=:source) AND (:severity='''' OR severity=:severity)
   ORDER BY CASE severity WHEN ''critical'' THEN 0 WHEN ''high'' THEN 1 WHEN ''medium'' THEN 2 ELSE 3 END, source, bug_id LIMIT 300',
  'public',
  '{"source":"str","severity":"str"}',
  'list bugs, optionally scoped by source and/or severity, ordered by severity'
);

-- bug.stats [GET, public]: counts grouped by severity and by source (one result set, discriminated by 'facet').
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'bug.stats', 'GET',
  'SELECT ''severity'' AS facet, severity AS value, COUNT(*) AS n FROM bugs GROUP BY severity
   UNION ALL
   SELECT ''source'' AS facet, source AS value, COUNT(*) AS n FROM bugs GROUP BY source
   ORDER BY facet, value',
  'public',
  '{}',
  'bug counts grouped by severity and by source'
);

-- the page: a Document_Templates row (fixed id 97) with the shell + <<<BugCatalog>>>, and a Documents
-- row 'bugs' binding the slug. High, fixed id so INSERT OR REPLACE is idempotent.
CREATE TABLE IF NOT EXISTS Document_Templates (TemplateID INTEGER PRIMARY KEY, Content TEXT);
CREATE TABLE IF NOT EXISTS Documents (
  DocumentID  TEXT PRIMARY KEY,
  TemplateID  INTEGER,
  Title       TEXT,
  Description TEXT,
  ContentID   INTEGER
);

INSERT OR REPLACE INTO Document_Templates (TemplateID, Content) VALUES (97,
'<!DOCTYPE html>
<html>
<head>
<<<TitleTag>>>
<<<Style>>>
</head>
<body>
<nav><<<SiteMap>>></nav>
<h1>Bug Catalog</h1>
<p>Congruency&rsquo;s curated bugs (with runnable repros) plus corpus-wide consistent-bug patterns &mdash; one schema, two sources.</p>
<<<BugCatalog>>>
</body>
</html>');

INSERT OR REPLACE INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (
  'bugs', 97, 'Bug Catalog &middot; Congruency', 'Unified bug catalog &mdash; congruency repros + corpus consistent-bug patterns', 97
);
