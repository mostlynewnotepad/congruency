#!/usr/bin/env python3
# memgraph-edge-facet-shadow.py -- the MemGraph invocator gains an EDGE-KIND facet
# (?page=memgraph&edge=<kind>) that lists every edge of one kind, bound as :edge. Invariants:
#   (filter) ?edge=<kind> returns ONLY edges of that kind -- teeth: a contains-only dst renders under
#     ?edge=contains but must be hidden under ?edge=similar_to (a non-filtering renderer leaks it).
#   (escape-first) EVERY graph value rendered stays htmlspecialchars()'d, so a stored <<<Tag>>> /
#     <script> in a node id on an edge is inert.
#   (read-only) the reflection opens mem_graph.db with PRAGMA query_only=1 and only SELECTs, so the
#     node+edge row count is UNCHANGED after a faceted render.
# Isolation: a throwaway mem_graph.db + PHP harness under a TemporaryDirectory (MEM_GRAPH_DB pointed
# at it); the live graph, the live congruency db, and the repo are never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "MemGraph.php")

harness_tpl = """<?php
error_reporting(E_ERROR | E_PARSE);
ini_set('display_errors', '0');
interface Tag_Interface { public function get_document(); }
class ArgStub { public function pop() { return null; } }
require '__INVOC__';
$_GET = __GET__;
$t = new MemGraph(new ArgStub());
echo $t->get_document();
"""

checks = []
def check(name, ok):
    checks.append(bool(ok))
    mark = "\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m"
    print("  " + mark + " " + name)


def row_count(db):
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM node").fetchone()[0]
    n += con.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
    con.close()
    return n


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  \033[31m✗ FAIL\033[0m php-not-provisioned")
        return 1

    with tempfile.TemporaryDirectory() as t:
        mdb = os.path.join(t, "mem_graph.db")
        con = sqlite3.connect(mdb)
        con.execute("CREATE TABLE node (id TEXT PRIMARY KEY, kind TEXT, label TEXT, attrs TEXT, ts TEXT)")
        con.execute("CREATE TABLE edge (src TEXT, dst TEXT, kind TEXT, weight REAL, ts TEXT, attrs TEXT)")
        con.execute("CREATE TABLE drift (path TEXT, pingpong_raw REAL, temporal_wobble REAL, fork_spread REAL)")
        con.execute("CREATE TABLE meta (built_at TEXT, n_nodes INTEGER, n_edges INTEGER, sources TEXT)")
        evil = "<<<Evil>>><script>alert(1)</script>"
        for nid in (evil, "repo/other.py", "repo/app.py", "uniq-contains-dst", "spec/rfc-0031"):
            con.execute("INSERT INTO node (id, kind, label, attrs, ts) VALUES (?,?,?,?,?)",
                        (nid, "file", nid, "{}", "2026-07-01T00:00:00"))
        con.execute("INSERT INTO edge (src, dst, kind, weight, ts, attrs) VALUES (?,?,?,?,?,?)",
                    (evil, "repo/other.py", "similar_to", 0.97, "2026-07-04T00:00:00", "{}"))
        con.execute("INSERT INTO edge (src, dst, kind, weight, ts, attrs) VALUES (?,?,?,?,?,?)",
                    ("repo/app.py", "uniq-contains-dst", "contains", 1.0, "2026-07-05T00:00:00", "{}"))
        con.execute("INSERT INTO edge (src, dst, kind, weight, ts, attrs) VALUES (?,?,?,?,?,?)",
                    ("spec/rfc-0031", "repo/app.py", "shadow_of", 1.0, "2026-07-06T00:00:00", "{}"))
        con.execute("INSERT INTO meta (built_at, n_nodes, n_edges, sources) VALUES (?,?,?,?)",
                    ("2026-07-06T12:00:00", 5, 3, "omni,forge,mem"))
        con.commit(); con.close()

        before = row_count(mdb)

        env = dict(os.environ)
        env["MEM_GRAPH_DB"] = mdb

        def render(getarr):
            hp = os.path.join(t, "render.php")
            phpsrc = harness_tpl.replace("__INVOC__", INVOC).replace("__GET__", getarr)
            with open(hp, "w") as fh:
                fh.write(phpsrc)
            return subprocess.run([PHP, hp], capture_output=True, text=True, timeout=60, env=env).stdout

        out_sim = render("array('edge' => 'similar_to')")
        out_con = render("array('edge' => 'contains')")

        after = row_count(mdb)

        check("edge facet filters edges to the bound kind (similar_to shows repo/other.py, hides the contains-only dst)",
              ("repo/other.py" in out_sim) and ("uniq-contains-dst" not in out_sim))
        check("shadow has teeth: the contains-only dst renders under ?edge=contains (so its absence above is filtering)",
              "uniq-contains-dst" in out_con)
        check("memory-graph edge data is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out_sim) and ("<<<Evil>>>" not in out_sim)
              and ("&lt;script&gt;" in out_sim) and ("<script>" not in out_sim))
        check("the edge facet never writes to the graph (read-only)",
              before == after)

    ok = all(checks)
    print("")
    print(("PASS" if ok else "FAIL") + "  (" + str(sum(checks)) + "/" + str(len(checks)) + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
