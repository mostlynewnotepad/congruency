-- 0033_assign_idempotent.sql — ticket.assign is IDEMPOTENT (INSERT OR IGNORE).
-- A crashed/resumed pair run re-assigns the same (ticket, agent, role); the PK made that a PDO
-- 500 that killed the whole run. OR IGNORE keeps the authorization append-only semantics intact:
-- an existing assignment is never modified (the no-update/no-delete triggers still hold) — the
-- re-assign simply becomes a no-op instead of a crash. Additive.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'ticket.assign', 'POST',
  'INSERT OR IGNORE INTO ticket_agents (ts, ticket_id, agent_id, role) VALUES (strftime(''%s'',''now''), :ticket_id, :agent_id, :role)',
  'token', '{"ticket_id":"int","agent_id":"str","role":"str"}',
  'authorize a REGISTERED agent on a ticket in a role (idempotent: re-assign is a no-op, never an error)'
);
