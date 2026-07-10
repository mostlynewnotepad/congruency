-- 0026_error_log.sql -- the SYSTEMIC FATAL-ERROR LOG behind boot/monitor.php. monitor.php catches
-- every uncaught exception / fatal error, writes a row HERE, and auto-files a de-duped bug into the
-- `bugs` table (0023) so it surfaces in ?page=bugs. This migration provisions the log table + an
-- index on (sig, ts) for the de-dup lookup, plus two public read routes so the log is inspectable:
-- error.recent (the tail) and error.stats (counts grouped by signature). Additive; self-contained
-- (CREATE ... IF NOT EXISTS so it applies to a bare db -- the migration-isolation shadow -- too).

CREATE TABLE IF NOT EXISTS api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);

CREATE TABLE IF NOT EXISTS error_log (
  id      INTEGER PRIMARY KEY,
  ts      INTEGER,
  type    INTEGER,
  message TEXT,
  file    TEXT,
  line    INTEGER,
  route   TEXT,
  sig     TEXT
);
CREATE INDEX IF NOT EXISTS idx_error_log_sig_ts ON error_log (sig, ts);

-- error.recent [GET, public]: the tail of the fatal log, newest first.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'error.recent', 'GET',
  'SELECT id, ts, type, message, file, line, route, sig FROM error_log ORDER BY id DESC LIMIT 100',
  'public',
  '{}',
  'recent fatal-monitor error_log rows, newest first'
);

-- error.stats [GET, public]: counts grouped by signature (how many times each fatal has recurred).
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'error.stats', 'GET',
  'SELECT sig, COUNT(*) AS n, MAX(ts) AS last_ts, MAX(message) AS message FROM error_log GROUP BY sig ORDER BY n DESC, last_ts DESC LIMIT 100',
  'public',
  '{}',
  'fatal counts grouped by signature'
);
