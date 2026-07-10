#!/usr/bin/env python3
# fatal-monitor-shadow.py -- proves boot/monitor.php (the systemic fatal-error net) catches a fatal,
# LOGS it to error_log, and AUTO-FILES a de-duped bug visible in ?page=bugs -- WITHOUT any live
# services and WITHOUT actually OOMing. It drives a tiny php harness that includes monitor.php,
# installs it on a tempfile-isolated congruency db (setup.do_migrate applies the REAL migrations so
# error_log + bugs exist), then calls the report() path directly with a SYNTHETIC fatal whose message
# carries a live '<<<Evil>>><script>' payload, and asserts:
#   (log+file) one report writes an error_log row with the message AND auto-files a bugs row
#              (source=fatal-monitor), visible through the real bug.list route.
#   (de-dup)   calling report twice with the SAME fatal writes a SECOND error_log row but does NOT
#              file a second bug (one signature => one open bug).
#   (render)   ?page=bugs (BugCatalog) shows the auto-filed bug htmlspecialchars-escaped -- the raw
#              <<<Evil>>> / <script> never reaches the client (escape-first, mirrors the bug catalog).
#   (teeth)    a variant with de-dup DISABLED files a duplicate bug -- proving the de-dup assertion bites.
# Isolation: a TemporaryDirectory holds the db(s); the live db/repo are never touched. Stdlib-only.
import os
import sys
import tempfile
import sqlite3
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
MON = os.path.join(REPO, "checkouts", "current", "congruency", "boot", "monitor.php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "BugCatalog.php")

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


MSG = "OOM: Allowed memory size exhausted <<<Evil>>><script>alert(1)</script> in SemanticSearch"
DRIVER = '''<?php
error_reporting(E_ERROR | E_PARSE);
ini_set('display_errors', '0');
define('CONGRUENCY_SQLITE', %r);
require %r;
congruency_install_monitor();
$msg = %r;
$dedup = (isset($argv[1]) && $argv[1] === 'nodedup') ? false : true;
$n = isset($argv[2]) ? (int)$argv[2] : 1;
for ($i = 0; $i < $n; $i++) {
    congruency_monitor_report(E_ERROR, $msg, 'lib/Modules/SemanticSearch.php', 512, 'page=search', null, $dedup);
}
echo "done\\n";
'''


def run_driver(db, mode, n):
    drv = os.path.join(os.path.dirname(db), "drive_%s.php" % mode)
    with open(drv, "w") as fh:
        fh.write(DRIVER % (db, MON, MSG))
    return subprocess.run([PHP, drv, mode, str(n)], capture_output=True, text=True, timeout=60)


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  ✗ FAIL php-not-provisioned"); return 1
    if not os.path.isfile(MON):
        print("  ✗ FAIL monitor-not-found"); return 1
    if not os.path.isfile(INVOC):
        print("  ✗ FAIL BugCatalog-invocator-not-found"); return 1

    with tempfile.TemporaryDirectory() as t:
        # --- de-dup ON: two identical fatals -> 2 error_log rows, 1 auto-filed bug ---
        db = os.path.join(t, "main.sqlite"); build_db(db)
        run_driver(db, "dedup", 2)
        con = sqlite3.connect(db); con.row_factory = sqlite3.Row

        elog = con.execute("SELECT * FROM error_log ORDER BY id").fetchall()
        logged = any("<<<Evil>>>" in (row["message"] or "") for row in elog)
        bug_rows = con.execute("SELECT * FROM bugs WHERE source='fatal-monitor'").fetchall()
        lst = route_sql(con, "bug.list")
        listed = con.execute(lst, {"source": "", "severity": ""}).fetchall()
        listed_fatal = [row for row in listed if row["source"] == "fatal-monitor"]
        con.close()

        check("a synthetic fatal is logged to error_log AND auto-files a bug",
              logged and len(bug_rows) == 1 and len(listed_fatal) == 1)
        check("a repeated fatal signature does not file a duplicate bug",
              len(elog) == 2 and len(bug_rows) == 1)

        # --- render ?page=bugs (BugCatalog): the auto-filed bug is htmlspecialchars-escaped ---
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
''' % (db, INVOC))
        out = subprocess.run([PHP, harness], capture_output=True, text=True, timeout=60).stdout
        shows = "fatal-monitor" in out
        escaped = ("<<<Evil>>>" not in out) and ("<script>" not in out) and ("&lt;script&gt;" in out)
        check("?page=bugs renders the auto-filed bug htmlspecialchars-escaped (no raw <<< or <script>)",
              shows and escaped)

        # --- TEETH: de-dup DISABLED files a duplicate bug (the assertion bites) ---
        db2 = os.path.join(t, "teeth.sqlite"); build_db(db2)
        run_driver(db2, "nodedup", 2)
        con2 = sqlite3.connect(db2)
        dup = con2.execute("SELECT COUNT(*) FROM bugs WHERE source='fatal-monitor'").fetchone()[0]
        con2.close()
        check("shadow has teeth: with de-dup disabled a repeated fatal DOES file a duplicate bug",
              dup == 2)

    ok = all(checks)
    print("")
    print("%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
