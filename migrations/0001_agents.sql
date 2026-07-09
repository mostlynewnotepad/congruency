-- 0001_agents.sql — agent provenance: register a spawn (id + prompt + tools), then follow the
-- rabbit trail from that agent id to every tool/intent it recorded. Forward-only and ADDITIVE
-- (CREATE IF NOT EXISTS / INSERT OR REPLACE) so it never wipes data — safe on the live db.
--
-- The tool/intent events already land in `memories` keyed on `session` (= the agent id, indexed).
-- This adds the missing registry (`agents`) and the data-driven REST routes to write + read it.

CREATE TABLE IF NOT EXISTS agents (
  agent_id TEXT PRIMARY KEY,   -- the spawn number / agent id (== memories.session)
  parent   TEXT,               -- the agent that spawned this one (provenance chain)
  prompt   TEXT,               -- the prompt() the agent was born with
  tools    TEXT,               -- the tools() it was granted (JSON array / csv)
  status   TEXT,               -- active | done | ...
  ts       INTEGER             -- unix seconds at registration
);
CREATE INDEX IF NOT EXISTS idx_agents_ts ON agents(ts);

-- agent.register [POST, token]: record a spawn with its prompt() + tools() at birth.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'agent.register', 'POST',
  'INSERT OR REPLACE INTO agents (agent_id,parent,prompt,tools,status,ts) VALUES (:agent_id,:parent,:prompt,:tools,''active'',strftime(''%s'',''now''))',
  'token',
  '{"agent_id":"str","parent":"str","prompt":"str","tools":"str"}',
  'record an agent spawn: id + parent + prompt() + tools()'
);

-- agent.trail [GET, public]: pass an agent id -> see every tool/intent it propagated, in order.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'agent.trail', 'GET',
  'SELECT m.ts, m.tool, m.intent, m.note FROM memories m WHERE m.session=:agent_id ORDER BY m.ts',
  'public',
  '{"agent_id":"str"}',
  'the propagation trail for an agent id (tool + intent events, in order)'
);

-- agent.roster [GET, public]: the registered agents, newest first.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'agent.roster', 'GET',
  'SELECT agent_id, parent, status, ts, substr(prompt,1,160) AS prompt FROM agents ORDER BY ts DESC LIMIT :n',
  'public',
  '{"n":"int"}',
  'registered agents, newest first (LIMIT :n; omit n for all)'
);
