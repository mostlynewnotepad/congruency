-- 0011_guarantee_held.sql — the contract a component must not erode. guarantee.held returns every
-- guarantee label the component has ever recorded (across all its tickets). crankd fetches this before
-- a mint and refuses the crank if the candidate run would DROP any held guarantee — turning the corpus
-- from a record into an enforcer (regression-gating). Iteration 8. Route only; additive.

INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (
  'guarantee.held', 'GET',
  'SELECT DISTINCT g.guarantee FROM guarantees g JOIN tickets t ON t.id = g.ticket_id
   WHERE t.component = :component',
  'public',
  '{"component":"str"}',
  'every guarantee label a component has recorded — the contract crankd will not let a crank erode'
);
