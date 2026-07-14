-- 0031_harvest_routes.sql — harvest: memory as an AUTHORIZED ARTIFACT, not private context.
--
-- The rule ("an agent may remember only what it has filed"): when a pair-loop ticket settles, the
-- harness distills what happened — adversary findings that forced rework, and what resolved them —
-- into a LESSON event on the ticket's journal. lessons.recent reads them across tickets; the
-- pair_loop --compile-playbook mode files a documentation ticket embedding those lessons and runs
-- the SAME adversarial pair over it, so the playbook future workers read at birth is itself an
-- audited, permanent-UID work. Nothing is remembered that was not filed, reviewed, and recorded.
--
-- Forward-only, ADDITIVE (INSERT OR REPLACE only). ticket_events is already append-only (0029
-- triggers) — lessons inherit the same immutability.

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.lesson', 'POST',
  'INSERT INTO ticket_events (ts, ticket_id, agent_id, event, note) VALUES (strftime(''%s'',''now''), :ticket_id, :agent_id, ''lesson'', :note)',
  'token', '{"ticket_id":"int","agent_id":"str","note":"str"}',
  'harvest a settled ticket: append the distilled lesson (attributed; append-only like all events)'
);

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'lessons.recent', 'GET',
  'SELECT ticket_id, ts, agent_id, note FROM ticket_events WHERE event = ''lesson'' ORDER BY ts DESC, id DESC LIMIT COALESCE(:n, -1)',
  'public', '{"n":"int"}',
  'harvested lessons across all tickets, newest first (LIMIT :n; omit n for all) — playbook input'
);
