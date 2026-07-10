#!/usr/bin/env python3
# front-telemetry-shadow.py -- proves the FRONT-END TELEMETRY BEACON: every served page carries a
# <<<TelemetryBeacon>>> (spliced by <<<Style>>>) that reports PAGE VIEWS + client JS ERRORS (+ throttled
# interaction events) to ?route=telemetry.record, and that a client JS error reuses the v4.118 SERVER
# fatal pipe -- it logs to error_log (type='js') AND auto-files a de-duped bug (source='front-end')
# visible in ?page=bugs, htmlspecialchars-escaped. Drives boot/monitor.php's congruency_telemetry_ingest
# directly on a tempfile-isolated db (setup.do_migrate applies the REAL migrations so front_telemetry +
# error_log + bugs exist), mirroring fatal-monitor-shadow. Isolation: TemporaryDirectory; the live
# db/repo are never touched. Stdlib-only.
import os
import sys
import tempfile
import sqlite3
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
MON = os.path.join(REPO, "checkouts", "current", "congruency", "boot", "monitor.php")
BUGCAT = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "BugCatalog.php")
BEACON = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "TelemetryBeacon.php")

sys.path.insert(0, REPO)
import setup  # noqa: E402

checks = []
def check(name, ok):
    checks.append(bool(ok))
    print("  %s %s" % ("✓" if ok else "✗ FAIL", name))


def build_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);"
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT, tool TEXT, intent TEXT, note TEXT);")
    con.commit(); con.close()
    setup.do_migrate(db_path=path)


def route_sql(con, name):
    row = con.execute("SELECT sql FROM api_routes WHERE name=?", (name,)).fetchone()
    return row[0] if row else None


MSG = "TypeError: undefined is not a function <<<Evil>>><script>alert(1)</script> at forge"
DRIVER = '''<?php
error_reporting(E_ERROR | E_PARSE);
ini_set('display_errors', '0');
define('CONGRUENCY_SQLITE', %r);
require %r;
congruency_install_monitor();
$kind = $argv[1]; $route = $argv[2]; $msg = $argv[3]; $detail = $argv[4];
$dedup = ($argv[5] === '1'); $n = (int)$argv[6];
for ($i = 0; $i < $n; $i++) {
    congruency_telemetry_ingest($kind, $route, $msg, $detail, null, $dedup);
}
echo "done";
'''


def run_driver(db, kind, route, msg, detail, dedup, n):
    drv = os.path.join(os.path.dirname(db), "drive.php")
    with open(drv, "w") as fh:
        fh.write(DRIVER % (db, MON))
    return subprocess.run([PHP, drv, kind, route, msg, detail, dedup, str(n)],
                          capture_output=True, text=True, timeout=60)


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  ✗ FAIL php-not-provisioned"); return 1
    if not os.path.isfile(MON):
        print("  ✗ FAIL monitor-not-found"); return 1
    if not os.path.isfile(BEACON):
        print("  ✗ FAIL beacon-invocator-not-found"); return 1

    with tempfile.TemporaryDirectory() as t:
        # --- page view: a beacon lands a front_telemetry row (kind=pageview) ---
        dbpv = os.path.join(t, "pv.sqlite"); build_db(dbpv)
        run_driver(dbpv, "pageview", "?page=forge", "", "", "1", 1)
        con = sqlite3.connect(dbpv)
        pv = con.execute("SELECT COUNT(*) FROM front_telemetry WHERE kind='pageview'").fetchone()[0]
        con.close()
        check("a front-end page-view beacon lands a front_telemetry row (kind=pageview)", pv >= 1)

        # --- client JS error: error_log(type=js) + de-duped auto-filed front-end bug (repeat != dup) ---
        dberr = os.path.join(t, "err.sqlite"); build_db(dberr)
        run_driver(dberr, "error", "?page=search", MSG, "app.js:10:5", "1", 2)
        con = sqlite3.connect(dberr); con.row_factory = sqlite3.Row
        elog_js = con.execute("SELECT * FROM error_log WHERE type='js'").fetchall()
        logged = any("<<<Evil>>>" in (r["message"] or "") for r in elog_js)
        bug_rows = con.execute("SELECT * FROM bugs WHERE source='front-end'").fetchall()
        lst = route_sql(con, "bug.list")
        listed = con.execute(lst, {"source": "", "severity": ""}).fetchall()
        listed_fe = [r for r in listed if r["source"] == "front-end"]
        con.close()
        check("a client JS error auto-files a de-duped front-end bug",
              logged and len(elog_js) == 2 and len(bug_rows) == 1 and len(listed_fe) == 1)

        # --- render ?page=bugs (BugCatalog): the auto-filed front-end bug is htmlspecialchars-escaped ---
        harness = os.path.join(t, "render.php")
        with open(harness, "w") as fh:
            fh.write('''<?php
error_reporting(E_ERROR | E_PARSE);
ini_set('display_errors', '0');
interface Tag_Interface { public function get_document(); }
class ArgStub { public function pop() { return null; } }
define('CONGRUENCY_SQLITE', %r);
require %r;
$_GET = array();
$t = new BugCatalog(new ArgStub());
echo $t->get_document();
''' % (dberr, BUGCAT))
        out = subprocess.run([PHP, harness], capture_output=True, text=True, timeout=60).stdout
        escaped = ("<<<Evil>>>" not in out) and ("<script>alert" not in out) \
            and ("&lt;script&gt;" in out) and ("front-end" in out)
        check("telemetry-derived output is htmlspecialchars-escaped", escaped)

        # --- the beacon invocator actually emits the tracking <script> ---
        bharness = os.path.join(t, "beacon.php")
        with open(bharness, "w") as fh:
            fh.write('''<?php
error_reporting(E_ERROR | E_PARSE);
ini_set('display_errors', '0');
interface Tag_Interface { public function get_document(); }
require %r;
$t = new TelemetryBeacon(null);
echo $t->get_document();
''' % (BEACON,))
        bout = subprocess.run([PHP, bharness], capture_output=True, text=True, timeout=60).stdout
        emits = ("<script>" in bout) and ("sendBeacon" in bout) and ("telemetry.record" in bout) \
            and ("addEventListener('error'" in bout) and ("unhandledrejection" in bout)
        check("the TelemetryBeacon invocator emits a self-contained <script> that beacons page views + JS errors to telemetry.record", emits)

        # --- TEETH: de-dup DISABLED files a duplicate front-end bug (the de-dup assertion bites) ---
        dbt = os.path.join(t, "teeth.sqlite"); build_db(dbt)
        run_driver(dbt, "error", "?page=search", MSG, "app.js:10:5", "0", 2)
        con2 = sqlite3.connect(dbt)
        dup = con2.execute("SELECT COUNT(*) FROM bugs WHERE source='front-end'").fetchone()[0]
        con2.close()
        check("shadow has teeth: with de-dup disabled a repeated client error DOES file a duplicate bug", dup == 2)

    ok = all(checks)
    print("")
    print("%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
