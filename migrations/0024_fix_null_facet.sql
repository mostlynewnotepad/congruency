-- 0024_fix_null_facet.sql -- fix the sql-null-vs-empty optional-facet bug. boot/rest.php binds a
-- declared route :param as NULL when the request OMITS it (congruency_rest_route:
-- `$val = array_key_exists($pname,$input) ? $input[$pname] : null;`). The optional-facet guard
-- `(:x='' OR col=:x)` then evaluates to NULL and the WHERE filters out EVERY row, so search.text and
-- bug.list returned ZERO rows unless the caller passed an explicit empty string. Rewrite every
-- optional-facet guard to `COALESCE(:x,'')=''` so a NULL (omitted) facet and an empty-string facet
-- both mean "no filter". Only the guard predicates change; columns/ORDER BY/LIMIT are preserved
-- verbatim. Idempotent (UPDATE to a fixed value); self-contained (CREATE IF NOT EXISTS api_routes).

CREATE TABLE IF NOT EXISTS api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);

-- search.text: (:repo='' OR repo=:repo) -> (COALESCE(:repo,'')='' OR repo=:repo)
UPDATE api_routes SET sql =
  'SELECT repo, path, substr(body,1,240) AS snippet FROM repo_docs
   WHERE body LIKE ''%''||:q||''%'' AND (COALESCE(:repo,'''')='''' OR repo=:repo) ORDER BY repo, path LIMIT 40'
  WHERE name='search.text';

-- bug.list: both facet guards -> COALESCE(:x,'')='' form
UPDATE api_routes SET sql =
  'SELECT * FROM bugs WHERE (COALESCE(:source,'''')='''' OR source=:source) AND (COALESCE(:severity,'''')='''' OR severity=:severity)
   ORDER BY CASE severity WHEN ''critical'' THEN 0 WHEN ''high'' THEN 1 WHEN ''medium'' THEN 2 ELSE 3 END, source, bug_id LIMIT 300'
  WHERE name='bug.list';
