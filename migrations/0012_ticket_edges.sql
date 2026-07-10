-- 0012_ticket_edges.sql — the ticket tree. A ticket-class aggregate OWNS child tickets (a true tree);
-- the first real edges are supersessions (a superseding ticket owns the predecessor it replaced, e.g.
-- #186 supersedes #185). This table records parent->child edges so the provenance graph can BRANCH
-- instead of being flat. Iteration 9. Additive.

CREATE TABLE IF NOT EXISTS ticket_edges (
  id        INTEGER PRIMARY KEY,
  ts        INTEGER,
  parent_id INTEGER,
  child_id  INTEGER,
  kind      TEXT           -- 'supersedes' (later: 'subticket', ...)
);
CREATE INDEX IF NOT EXISTS idx_ticket_edges_parent ON ticket_edges (parent_id);

-- edge.record [POST, token]: record one parent->child ticket edge.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'edge.record', 'POST',
  'INSERT INTO ticket_edges (ts, parent_id, child_id, kind)
   VALUES (strftime(''%s'',''now''), :parent_id, :child_id, :kind)',
  'token',
  '{"parent_id":"int","child_id":"int","kind":"str"}',
  'record a parent->child ticket edge (the owned tree)'
);

-- children.list [GET, public]: a ticket's children, joined to their ticket rows for display.
INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'children.list', 'GET',
  'SELECT e.child_id, e.kind, t.title, t.status, t.component
   FROM ticket_edges e JOIN tickets t ON t.id = e.child_id
   WHERE e.parent_id = :parent_id ORDER BY e.child_id DESC',
  'public',
  '{"parent_id":"int"}',
  'list a ticket''s child tickets (the owned tree)'
);
