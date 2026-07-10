-- 0027_front_telemetry.sql -- FRONT-END TELEMETRY BEACON (adapts the json-controls client-tracking
-- idea): every served page carries a <<<TelemetryBeacon>>> (spliced by <<<Style>>>, embedded by every
-- page template) that reports PAGE VIEWS + client JS ERRORS (+ throttled interaction events) to
-- ?route=telemetry.record. On kind='error' the receiver (boot/rest.php -> boot/monitor.php
-- congruency_telemetry_ingest) reuses the v4.118 SERVER fatal pipe: it writes an error_log row
-- (type='js') AND auto-files a de-duped bug (source='front-end') so a CLIENT crash surfaces in
-- ?page=bugs just like a server fatal. This migration provisions the raw stream table + its index +
-- two public routes. Additive; self-contained (CREATE ... IF NOT EXISTS so it applies to a bare db
-- too -- the migration-isolation shadow).

CREATE TABLE IF NOT EXISTS api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);

CREATE TABLE IF NOT EXISTS front_telemetry (
  id     INTEGER PRIMARY KEY,
  ts     INTEGER,
  kind   TEXT,
  route  TEXT,
  detail TEXT,
  ua     TEXT,
  sig    TEXT
);
CREATE INDEX IF NOT EXISTS idx_front_telemetry_kind_ts ON front_telemetry (kind, ts);

-- telemetry.record [POST, public]: the beacon endpoint. boot/rest.php intercepts this route and hands
-- it to congruency_telemetry_ingest (kind='error' -> error_log + de-duped front-end bug via the fatal
-- pipe; kind='pageview'|'event' -> a front_telemetry stream row). The INSERT below is the
-- compile-checked contract (route-sql-compiles / route-params-declared) and the pageview/event write
-- shape; the PHP handler owns the branch and performs the actual write. 'message' is declared for the
-- error branch (carried in the JSON body; it is not a front_telemetry column).
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'telemetry.record', 'POST',
  'INSERT INTO front_telemetry (ts, kind, route, detail) VALUES (strftime(''%s'',''now''), :kind, :route, :detail)',
  'public',
  '{"kind":"str","route":"str","message":"str","detail":"str"}',
  'front-end telemetry beacon: page views / interaction events land a front_telemetry row; client JS errors also log to error_log + auto-file a de-duped front-end bug (boot/monitor.php)'
);

-- telemetry.recent [GET, public]: the tail of the raw beacon stream, newest first.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'telemetry.recent', 'GET',
  'SELECT id, ts, kind, route, detail, ua, sig FROM front_telemetry ORDER BY id DESC LIMIT 100',
  'public',
  '{}',
  'recent front-end telemetry beacons (page views / events / client errors), newest first'
);
