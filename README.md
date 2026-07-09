# congruencey — the ratchet

Steven Peterson's 2006 PHP CMS ("congruency"), resurrected on PHP 8 and folded into a
ratchet-managed package. **One branch, `main`**, carries everything: the installer
(`setup.py`) at the root **and** the CMS source + tooling under `checkouts/current/`. A crank is
a **commit + `version-*` tag**, not a branch. Each crank is one self-contained tree — installer +
source + database + configuration object — so there is no separate `state` branch. **The crank
state and the crank tool both live in the base**: the database rides in each version commit as
`database.tar.xz`, and the minter is `checkouts/current/congruency/tools/mint_crank.py` (below).

> Home: `origin` = `git@gitlab.com:testmonkeyalpha-group/jazz-forge/congruency.git`
> (`upstream` = the original `github.com:dudezilla/rebase`).

Layout under `checkouts/current/`:

| path | holds |
|---|---|
| `congruency/` | the CMS app + its tooling (`tools/`, `fixes/`, `versioning/`, `boot/`, `lib/`, …) |
| `state/` | the crank's database, shipped compressed as `database.tar.xz` (extracted to `congruency.sqlite` on install) |

## Lifecycle (dev / test)
```
git clone <repo> && cd rebase
python3 setup.py install     # checkout newest version + provision php + install db (+ verify)
python3 setup.py up          # bring the CMS up  -> http://0.0.0.0:8899
python3 setup.py down        # take the CMS down
python3 setup.py uninstall   # tear the tree back to the minted crank (purge runtime)
```
No hand-typed version or flags: **`install.json` is the configuration object** — it stamps the
release version and carries the lifecycle params (host/port/no_verify). It is emitted by
instrumentation at mint time and committed into each version tag, so the verbs are
config-object-driven (an orchestrator drives the lifecycle via that one object). `install` per step
records telemetry and files a Variant-A bug report on any unexpected outcome:
1. **checkout** the tag `version-X` (detached — materializes the crank);
2. **provision php** — `checkouts/current/congruency/tools/provision_php.py` (static PHP 8; idempotent);
3. **shadow gate** — run the `shadows` named in `install.json` (pure-python regression suites; a non-zero exit aborts the install);
4. **install state** — extract the `database.tar.xz` that rides in the version commit → `checkouts/current/state/congruency.sqlite`. **The install REMEMBERS an existing db**: when `preserve_db` is set (default) and a live `congruency.sqlite` is already present, the seed tarball is NOT extracted over it (so `install` is as non-destructive as `up`); a fresh install still seeds. State is never listed for `uninstall` purge;
5. **migrate** — apply forward-only, additive SQL from `migrations/*.sql` to the state db (idempotent, tracked in `schema_migrations`); runs on every install, so the live db is upgraded in place and a fresh seed need not carry the newest schema;
6. **verify** — `tooling/congruencey-tests/verify` (stand-up + bug-catalog + branch-coverage).

The DB-remembering install (`preserve_db`), the migration runner (`migrate`), and the shadow gate
(`shadows`) are all fields on the `install.json` configuration object. **Agent provenance** rides
in the migrations: an `agents` registry plus data-driven routes `agent.register` (POST, record a
spawn's prompt + tools), `agent.trail` (GET, replay every tool+intent an agent id recorded), and
`agent.roster` (GET) — so you can follow the rabbit trail from a prompt to the actions it caused.

Overrides (the configuration object always wins by default):
```
python3 setup.py install path/to/install.json
python3 setup.py install --version 4.081 [--no-verify] [--return-to-main]
python3 setup.py up --port 9000
python3 setup.py emit-config      # instrumentation: write ./install.json for the newest version
```
`uninstall` is a **tolerated anomaly** point: if bringing it up dirtied the tree, it files a bug
report and force-recovers the tree to the minted crank.

## Docker
```
docker build -t congruency .          # install runs at build: provisions php + installs db + verify
docker run -p 8899:8899 congruency    # serves in the foreground on :8899
```
The server is **not bundled** — the build provisions a static PHP 8 (needs network at build time).
It's **config-object-driven**: the port comes from `install.json`, not the Dockerfile
(`docker run … python3 setup.py up --foreground --port 9000` to override). `.git` and the in-crank
`database.tar.xz` must be in the build context (`.dockerignore` keeps only runtime artifacts out).

## How work happens (minting a crank)
The crank tool lives in the base — `checkouts/current/congruency/tools/mint_crank.py` — and mints
in two modes:
```
# patch mode: one Python patch IS the change (precondition: on main, tracked-clean, php provisioned)
python3 checkouts/current/congruency/tools/mint_crank.py --patch P.py --name x

# capture mode: mint a docs/config crank from the CURRENT working tree (no patch to run)
python3 checkouts/current/congruency/tools/mint_crank.py --no-patch --keep-state [--no-verify] -m "…"
```
Each crank is captured **in place** (commit + `version-*` tag). Before the commit, mint produces
the crank's state and re-emits its `install.json`, so the version commit carries **both** the
`database.tar.xz` and the install config. Mint steps: precondition → (inject+run patch, patch mode)
→ state → **shadow gate** → capture → verify.

- **`--keep-state`** reuses the existing in-tree `database.tar.xz` (skip `make_state` — for changes
  that don't touch state, and on hosts without the `source_db`/php `make_state` needs). Otherwise
  `make_state.py` snapshots the unified database named by `STATE.json` `source_db`, falling back to
  the installed db (never re-fabricating a stub).
- **Shadow gate** runs the pure-python `shadows` from `install.json` — the Mac-native regression
  gate, so a crank is gated even where the full PHP `verify` suite can't run. `--no-verify` (or an
  unprovisioned php) skips only the PHP suite, never the shadow gate.
- **install.json is carried forward**: mint re-stamps the version but preserves the durable fields
  (`preserve_db`, `migrate`, `shadows`) from the previous config object — the object is the source
  of truth, so a mint can't silently regress them.

## Telemetry & bugs
Every step emits to `jazz_telemetry` when available; any unexpected outcome writes a Variant-A bug
report to the registry's `bug_reports` sink (`logs/bug_reports.jsonl`) and opens a mechanical-id
ticket. Best-effort — never blocks.

## More docs
`VERSION-NOTES.md` (per-crank notes) · `DEPENDENCIES.md` (runtime deps +
process changes) · `checkouts/current/congruency/ARCHITECTURE.md` (the 2006 CMS internals).
