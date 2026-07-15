# Go Write-Route Equivalence: agent.register (#236) & doc.record (#242)

## Summary / Verdict

| Route | Ticket | JSON reply byte-equal? | DB row equal? | Real engine bug? | Satisfied by generic engine? |
|-------|--------|------------------------|---------------|------------------|------------------------------|
| `agent.register` | #236 | YES | YES (except `ts`) | NO | YES |
| `doc.record` | #242 | YES | YES (except `ts`) | NO | YES |

Both write routes are handled correctly by the generic data-driven Go engine (`RunRoute`
in `congruency-go/db.go`). JSON replies are byte-for-byte identical to rest.php, and the
resulting DB rows are column-for-column identical except for the `ts` column, which is an
expected per-call divergence (see below). No per-route Go code is needed; no engine bug found.

## Route definitions (from `api_routes`)

- **agent.register** — method POST, auth `token`, params `{agent_id, parent, prompt, tools}`
  SQL: `INSERT OR REPLACE INTO agents (agent_id,parent,prompt,tools,status,ts) VALUES (:agent_id,:parent,:prompt,:tools,'active',strftime('%s','now'))`
  Writes table `agents` (PK `agent_id`). `status` is the literal `'active'`; `ts` is server clock.
- **doc.record** — method POST, auth `token`, params `{repo, path, kind, body}`
  SQL: `INSERT INTO repo_docs (ts, repo, path, kind, body) VALUES (strftime('%s','now'), :repo, :path, :kind, :body)`
  Writes table `repo_docs` (PK `id` INTEGER autoincrement); `ts` is server clock.

## Method (exactly what was done)

DB isolation — the two engines never wrote to the same file:
1. Copied the live server DB
   (`checkouts/current/state/congruency.sqlite`) to two scratchpad copies: `eqA_236.sqlite`
   and `eqA_242.sqlite`. The Go engine wrote only to these copies.
2. Ran the write through the Go engine against each copy:
   `go run db.go -db <copy> -route <name> -method POST -authorized -input '<json>'`.
   Captured the JSON reply and then `SELECT`ed the produced row from the copy.
3. Ran the identical write through **rest.php** by POSTing to the live server
   (`http://127.0.0.1:8899/rest.php?route=<name>`, header `X-Api-Key`). rest.php writes to the
   live `state/congruency.sqlite`. Captured the JSON reply, then `SELECT`ed the produced row
   from the live DB.
4. Diffed (a) the JSON reply strings and (b) the produced rows.
5. **Cleanup:** deleted the live test rows (`agents.agent_id='equiv-test-236'`,
   `repo_docs.path='equiv-test-242'`) and verified counts returned to originals
   (agents 112, repo_docs 452). No test data left in the live DB.

Test inputs:
- agent.register: `{"agent_id":"equiv-test-236","parent":"p236","prompt":"prompt236","tools":"tools236"}`
- doc.record:    `{"repo":"equiv-test-242-repo","path":"equiv-test-242","kind":"k242","body":"body242"}`

## Per-route results

### agent.register (#236)

JSON reply — **byte-identical**:
```
Go  : {"route":"agent.register","affected":1,"rowid":"129"}
PHP : {"route":"agent.register","affected":1,"rowid":"129"}
```
(same field order, same pretty-print indentation, `rowid` a quoted string in both.)

DB row (`agents`):
```
Go  : rowid=129 agent_id=equiv-test-236 parent=p236 prompt=prompt236 tools=tools236 status=active ts=1784114706
PHP : rowid=129 agent_id=equiv-test-236 parent=p236 prompt=prompt236 tools=tools236 status=active ts=1784114736
```
All columns identical incl. the literal `status='active'`; only `ts` differs (30s = wall-clock
gap between the two runs). Same rowid because both DBs started from the same source state.

### doc.record (#242)

JSON reply — **byte-identical**:
```
Go  : {"route":"doc.record","affected":1,"rowid":"453"}
PHP : {"route":"doc.record","affected":1,"rowid":"453"}
```

DB row (`repo_docs`):
```
Go  : id=453 repo=equiv-test-242-repo path=equiv-test-242 kind=k242 body=body242 ts=1784114706
PHP : id=453 repo=equiv-test-242-repo path=equiv-test-242 kind=k242 body=body242 ts=1784114736
```
All columns identical; only `ts` differs (same 30s wall-clock gap). Same autoincrement `id=453`
because both DBs shared the same next-id from the common source copy.

## Expected divergences (NOT engine bugs)

- **`ts` column** — both routes set `ts = strftime('%s','now')`, evaluated by SQLite at write
  time in each engine. The two writes happened ~30s apart, so the values differ by 30. This is a
  per-call clock value, identical logic in both engines. Expected.
- **rowid / autoincrement id** — matched here (129 / 453) only because Go wrote to a copy that
  shared the live DB's next-id. In independent sequences these would legitimately differ; not an
  engine concern.

## Real engine bug found

None. The generic Go write path (`INSERT`, `INSERT OR REPLACE`, quoted-string `rowid`, `affected`
count, pretty-printed JSON) matches rest.php exactly.

## Recommendation

Tickets **#236 (agent.register)** and **#242 (doc.record)** are fully satisfied by the generic
data-driven engine — no per-route Go code required. Both write routes produce byte-identical JSON
replies and byte-identical DB mutations (modulo the expected per-call `ts` clock value). The two
remaining WRITE port units can be closed as engine-equivalent.
