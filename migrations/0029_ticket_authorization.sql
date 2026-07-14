-- 0029_ticket_authorization.sql — THE TICKET IS AN AUTHORIZATION (the spec, made schema).
--
-- Spec (2026-07-13, Steven): a ticket AUTHORIZES — it requires an agent (or adversarial pair) to act.
-- It has a kind-specific lifecycle with enumerable steps ("steps until the goal"). It is a descriptive
-- MANIFEST of related works: every item it authorizes gets a permanent, unchangeable UID. Tickets
-- track and SPAWN other tickets (RFC -> spec -> implementations + audits -> patches/refactors): a
-- recursive graph. Control is made of the same material: a STOP ticket can be aimed at any ticket
-- (stop + spawn + supersedes-edge = graft); a stop facilitates a later START. Progress metadata
-- (reports, dates, steps-remaining) is APPENDED by an attributed agent, never edited.
--
-- Logical consequences, enforced here IN SQL (a rule in a docstring has already failed to bind):
--   current state is DERIVED (events + edges), never edited in place;
--   DELETE and identity-UPDATE on core tables are REFUSED by triggers;
--   only REGISTERED agents can be authorized (the agents registry is a precondition);
--   a pair-kind ticket cannot reach DONE without two distinct agents in two distinct roles.
--
-- Forward-only + ADDITIVE (CREATE IF NOT EXISTS / INSERT OR REPLACE; the one ALTER runs exactly once
-- under the schema_migrations guard). Composes with: 0001 agents registry, 0002 wallet approval,
-- 0004 standing policies, 0012 ticket_edges (edge kinds used here: 'spawned', 'stops', 'starts',
-- 'supersedes' — TEXT, additive). Existing flows are untouched: process_status / ticket.approve
-- update only status/updated/approval_sig, which stay mutable; guards bind to the NEW lifecycle
-- statuses (ACTIVE, DONE) that no current flow uses.

-- ── the kind: pattern + roles (pair = adversarial network; solo = the adversary IS the work) ──────
ALTER TABLE tickets ADD COLUMN kind TEXT;   -- NULL on legacy rows; set once, then immutable

CREATE TABLE IF NOT EXISTS ticket_kinds (
  kind           TEXT PRIMARY KEY,
  pattern        TEXT NOT NULL,      -- 'pair' | 'solo'
  worker_role    TEXT NOT NULL,
  adversary_role TEXT,               -- NULL for solo kinds
  purpose        TEXT
);
INSERT OR REPLACE INTO ticket_kinds (kind, pattern, worker_role, adversary_role, purpose) VALUES
  ('build',             'pair', 'coder',      'tester',              'produce working code; the tester adversarially proves/disproves it'),
  ('bug',               'pair', 'coder',      'tester',              'fix a defect; the tester proves the fix and hunts regressions'),
  ('documentation',     'pair', 'writer',     'readability-auditor', 'document produced work; the auditor adversarially reads for clarity'),
  ('design',            'solo', 'designer',   NULL,                  'shape an approach before a spec exists'),
  ('spec',              'solo', 'spec-author', NULL,                 'the artifact that authorizes building — we just need a spec to start'),
  ('bet',               'pair', 'claimant',   'adjudicator',         'a speculative claim, adversarially adjudicated'),
  ('test',              'solo', 'tester',     NULL,                  'prove/disprove functions already produced — the adversary IS the work'),
  ('rfc-investigation', 'solo', 'researcher', NULL,                  'research toward a spec; may spawn implementations and audits'),
  ('audit',             'solo', 'auditor',    NULL,                  'examine delivered work; may spawn patch/refactor tickets'),
  ('stop',              'solo', 'stopper',    NULL,                  'aimed at ANY ticket via a ''stops'' edge; halts it; facilitates a start'),
  ('start',             'solo', 'starter',    NULL,                  'aimed at a stop ticket via a ''starts'' edge; resumes the stopped work');

-- ── the lifecycle as DATA (versioned, so refining it never rewrites in-flight history) ────────────
CREATE TABLE IF NOT EXISTS ticket_lifecycles (
  kind    TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  seq     INTEGER NOT NULL,
  step    TEXT NOT NULL,
  PRIMARY KEY (kind, version, seq)
);
INSERT OR REPLACE INTO ticket_lifecycles (kind, version, seq, step) VALUES
  ('build',1,1,'filed'),('build',1,2,'authorized'),('build',1,3,'paired'),('build',1,4,'implementing'),
  ('build',1,5,'adversary-review'),('build',1,6,'revising'),('build',1,7,'verified'),('build',1,8,'done'),
  ('bug',1,1,'filed'),('bug',1,2,'authorized'),('bug',1,3,'paired'),('bug',1,4,'fixing'),
  ('bug',1,5,'adversary-review'),('bug',1,6,'verified'),('bug',1,7,'done'),
  ('documentation',1,1,'filed'),('documentation',1,2,'authorized'),('documentation',1,3,'paired'),
  ('documentation',1,4,'drafting'),('documentation',1,5,'readability-review'),('documentation',1,6,'revised'),('documentation',1,7,'done'),
  ('design',1,1,'filed'),('design',1,2,'authorized'),('design',1,3,'designing'),('design',1,4,'reviewed'),('design',1,5,'done'),
  ('spec',1,1,'filed'),('spec',1,2,'authorized'),('spec',1,3,'drafting'),('spec',1,4,'adopted'),
  ('bet',1,1,'filed'),('bet',1,2,'authorized'),('bet',1,3,'claimed'),('bet',1,4,'adjudicated'),('bet',1,5,'settled'),
  ('test',1,1,'filed'),('test',1,2,'authorized'),('test',1,3,'proving'),('test',1,4,'verdict'),('test',1,5,'done'),
  ('rfc-investigation',1,1,'filed'),('rfc-investigation',1,2,'authorized'),('rfc-investigation',1,3,'researching'),
  ('rfc-investigation',1,4,'spec-drafted'),('rfc-investigation',1,5,'spawned'),('rfc-investigation',1,6,'done'),
  ('audit',1,1,'filed'),('audit',1,2,'authorized'),('audit',1,3,'examining'),('audit',1,4,'findings-filed'),('audit',1,5,'done'),
  ('stop',1,1,'filed'),('stop',1,2,'authorized'),('stop',1,3,'applied'),
  ('start',1,1,'filed'),('start',1,2,'authorized'),('start',1,3,'applied');

-- ── the journal: progress reports, dates, steps-until-goal — APPENDED, attributed, never edited ──
CREATE TABLE IF NOT EXISTS ticket_events (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,   -- MECHANICAL; callers never set it
  ts              REAL NOT NULL,
  ticket_id       INTEGER NOT NULL,
  agent_id        TEXT,                -- who reports (NULL only for trigger auto-journal)
  event           TEXT NOT NULL,       -- 'status' | 'progress' | 'assigned' | 'work' | ...
  status          TEXT,
  note            TEXT,
  steps_remaining INTEGER              -- countdown to the goal (parent progress = rollup over children)
);
CREATE INDEX IF NOT EXISTS idx_ticket_events_ticket ON ticket_events (ticket_id);

-- ── the manifest: every item the ticket authorized, under a PERMANENT mechanical UID ──────────────
CREATE TABLE IF NOT EXISTS ticket_works (
  uid       INTEGER PRIMARY KEY AUTOINCREMENT,   -- MECHANICAL; permanent; never reissued
  ts        REAL NOT NULL,
  ticket_id INTEGER NOT NULL,
  kind      TEXT,                                -- 'code' | 'doc' | 'spec' | 'patch' | 'crank' | ...
  ref       TEXT,                                -- where the item lives (path, route, version-tag)
  note      TEXT
);
CREATE INDEX IF NOT EXISTS idx_ticket_works_ticket ON ticket_works (ticket_id);

-- ── the authorization edge: ticket -> registered agent, in a role ─────────────────────────────────
CREATE TABLE IF NOT EXISTS ticket_agents (
  ts        REAL NOT NULL,
  ticket_id INTEGER NOT NULL,
  agent_id  TEXT NOT NULL,
  role      TEXT NOT NULL,     -- worker_role / adversary_role from ticket_kinds; 'scribe' also valid
  PRIMARY KEY (ticket_id, agent_id, role)
);

-- ── governance triggers: the rules live in the DB, not in a docstring ─────────────────────────────
CREATE TRIGGER IF NOT EXISTS tg_tickets_no_delete BEFORE DELETE ON tickets
BEGIN
  SELECT RAISE(ABORT, 'tickets are never deleted: aim a stop ticket at it (kind=stop + a ''stops'' edge)');
END;

CREATE TRIGGER IF NOT EXISTS tg_tickets_immutable_identity BEFORE UPDATE ON tickets
WHEN OLD.id IS NOT NEW.id OR OLD.ts IS NOT NEW.ts OR OLD.title IS NOT NEW.title
  OR OLD.body IS NOT NEW.body OR OLD.component IS NOT NEW.component
  OR (OLD.kind IS NOT NULL AND NEW.kind IS NOT OLD.kind)
BEGIN
  SELECT RAISE(ABORT, 'ticket identity (id, ts, title, body, component, kind) is permanent: append events, or stop+spawn (graft) a successor');
END;

CREATE TRIGGER IF NOT EXISTS tg_tickets_journal_status AFTER UPDATE OF status ON tickets
WHEN NEW.status IS NOT OLD.status
BEGIN
  INSERT INTO ticket_events (ts, ticket_id, event, status, note)
  VALUES (strftime('%s','now'), NEW.id, 'status', NEW.status, 'auto-journaled: status was ' || COALESCE(OLD.status,'(none)'));
END;

CREATE TRIGGER IF NOT EXISTS tg_tickets_active_needs_agent BEFORE UPDATE OF status ON tickets
WHEN upper(NEW.status) = 'ACTIVE'
 AND NOT EXISTS (SELECT 1 FROM ticket_agents WHERE ticket_id = NEW.id)
BEGIN
  SELECT RAISE(ABORT, 'a ticket authorizes an agent: assign one (ticket.assign) before it can go ACTIVE');
END;

CREATE TRIGGER IF NOT EXISTS tg_tickets_pair_completion BEFORE UPDATE OF status ON tickets
WHEN upper(NEW.status) = 'DONE'
 AND (SELECT pattern FROM ticket_kinds WHERE kind = NEW.kind) = 'pair'
 AND ((SELECT COUNT(DISTINCT role)     FROM ticket_agents WHERE ticket_id = NEW.id) < 2
   OR (SELECT COUNT(DISTINCT agent_id) FROM ticket_agents WHERE ticket_id = NEW.id) < 2)
BEGIN
  SELECT RAISE(ABORT, 'a pair ticket is an adversarial network: DONE requires two DISTINCT agents in two DISTINCT roles');
END;

CREATE TRIGGER IF NOT EXISTS tg_ticket_events_no_update BEFORE UPDATE ON ticket_events
BEGIN SELECT RAISE(ABORT, 'the journal is append-only: progress is appended, never edited'); END;
CREATE TRIGGER IF NOT EXISTS tg_ticket_events_no_delete BEFORE DELETE ON ticket_events
BEGIN SELECT RAISE(ABORT, 'the journal is append-only: history is never erased'); END;

CREATE TRIGGER IF NOT EXISTS tg_ticket_works_no_update BEFORE UPDATE ON ticket_works
BEGIN SELECT RAISE(ABORT, 'a work UID is a permanent, unchangeable part of the ticket'); END;
CREATE TRIGGER IF NOT EXISTS tg_ticket_works_no_delete BEFORE DELETE ON ticket_works
BEGIN SELECT RAISE(ABORT, 'the manifest only grows: supersede via a graft, never erase'); END;

CREATE TRIGGER IF NOT EXISTS tg_ticket_agents_registered BEFORE INSERT ON ticket_agents
WHEN NOT EXISTS (SELECT 1 FROM agents WHERE agent_id = NEW.agent_id)
BEGIN
  SELECT RAISE(ABORT, 'unregistered agent: a ticket authorizes only REGISTERED agents (agent.register first)');
END;
CREATE TRIGGER IF NOT EXISTS tg_ticket_agents_no_update BEFORE UPDATE ON ticket_agents
BEGIN SELECT RAISE(ABORT, 'an authorization is a fact: append a new assignment, never edit one'); END;
CREATE TRIGGER IF NOT EXISTS tg_ticket_agents_no_delete BEFORE DELETE ON ticket_agents
BEGIN SELECT RAISE(ABORT, 'an authorization is history: aim a stop ticket at the work instead'); END;

-- ── routes (data-driven; omitted params bind NULL) ────────────────────────────────────────────────
-- agent.roster: FIX the documented ''omit n for all'' contract (NULL LIMIT was a datatype mismatch).
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'agent.roster', 'GET',
  'SELECT agent_id, parent, status, ts, substr(prompt,1,160) AS prompt FROM agents ORDER BY ts DESC LIMIT COALESCE(:n,-1)',
  'public', '{"n":"int"}',
  'registered agents, newest first (LIMIT :n; omit n for all)'
);

-- agent.prompt: the FULL prompt an agent was born with (roster shows a 160-char preview only).
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'agent.prompt', 'GET',
  'SELECT agent_id, parent, tools, status, ts, prompt FROM agents WHERE agent_id = :agent_id',
  'public', '{"agent_id":"str"}',
  'one agent''s full birth prompt + registration record'
);

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.assign', 'POST',
  'INSERT INTO ticket_agents (ts, ticket_id, agent_id, role) VALUES (strftime(''%s'',''now''), :ticket_id, :agent_id, :role)',
  'token', '{"ticket_id":"int","agent_id":"str","role":"str"}',
  'authorize a REGISTERED agent on a ticket in a role (worker/adversary per ticket_kinds; scribe)'
);

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.crew', 'GET',
  'SELECT ta.ts, ta.agent_id, ta.role, a.status FROM ticket_agents ta LEFT JOIN agents a ON a.agent_id = ta.agent_id WHERE ta.ticket_id = :ticket_id ORDER BY ta.ts',
  'public', '{"ticket_id":"int"}',
  'the agents authorized on a ticket, with roles'
);

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.progress', 'POST',
  'INSERT INTO ticket_events (ts, ticket_id, agent_id, event, note, steps_remaining) VALUES (strftime(''%s'',''now''), :ticket_id, :agent_id, ''progress'', :note, :steps_remaining)',
  'token', '{"ticket_id":"int","agent_id":"str","note":"str","steps_remaining":"int"}',
  'append an attributed progress report (+ steps until the goal); the journal never edits'
);

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.journal', 'GET',
  'SELECT ts, agent_id, event, status, note, steps_remaining FROM ticket_events WHERE ticket_id = :ticket_id ORDER BY ts, id',
  'public', '{"ticket_id":"int"}',
  'the full append-only journal for a ticket (status changes + progress reports)'
);

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'work.record', 'POST',
  'INSERT INTO ticket_works (ts, ticket_id, kind, ref, note) VALUES (strftime(''%s'',''now''), :ticket_id, :kind, :ref, :note)',
  'token', '{"ticket_id":"int","kind":"str","ref":"str","note":"str"}',
  'mint a PERMANENT work UID into a ticket''s manifest (returns nothing; read ticket.manifest)'
);

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.manifest', 'GET',
  'SELECT uid, ts, kind, ref, note FROM ticket_works WHERE ticket_id = :ticket_id ORDER BY uid',
  'public', '{"ticket_id":"int"}',
  'the ticket as a descriptive manifest: every UID''d item it authorized'
);

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'kind.roster', 'GET',
  'SELECT kind, pattern, worker_role, adversary_role, purpose FROM ticket_kinds ORDER BY kind',
  'public', '{}',
  'the ticket kinds: pair (adversarial network) vs solo, with role names'
);

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'lifecycle.steps', 'GET',
  'SELECT seq, step FROM ticket_lifecycles WHERE kind = :kind AND version = COALESCE(:version, 1) ORDER BY seq',
  'public', '{"kind":"str","version":"int"}',
  'the enumerable lifecycle steps for a kind (versioned; steps-remaining counts down these)'
);
