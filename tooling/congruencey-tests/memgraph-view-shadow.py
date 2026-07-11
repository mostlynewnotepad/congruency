#!/usr/bin/env python3
# memgraph-view-shadow.py — the MemGraph invocator (?page=memgraph) reflects the RFC-0031
# memory-and-spec graph (~/bin/config/forge/mem_graph.db, a SEPARATE db from CONGRUENCY_SQLITE)
# read-only: node(id,kind,label,attrs,ts) + edge(src,dst,kind,weight,ts,attrs) unify the omni corpus,
# spec-drift, the memory timeline, the shadow-forge, and semantic near-dupes. Invariants:
#   (node lookup) ?node=<id> renders the node's outgoing (dst) + incoming (src) edges -- teeth via a
#     node with one outgoing + one incoming edge: both endpoints must show.
#   (escape-first) EVERY graph value rendered is htmlspecialchars()'d, so a stored <<<Tag>>> /
#     <script> in a node id stays inert -- teeth: a non-escaping renderer leaks the raw <<<.
#   (read-only) the reflection opens mem_graph.db with PRAGMA query_only=1 and only SELECTs, so the
#     node+edge row count is UNCHANGED after a render -- the page can never mutate the graph.
# Isolation: a throwaway mem_graph.db + PHP harnesses under a TemporaryDirectory (MEM_GRAPH_DB pointed
# at it); the live graph, the live congruency db, and the repo are never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
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

raw_tpl = """<?php
$db = new PDO('sqlite:' . '__MDB__');
$row = $db->query("SELECT id FROM node WHERE id LIKE '%Evil%' LIMIT 1")->fetch(PDO::FETCH_ASSOC);
echo $row['id'];
"""

checks = []
def check(name, ok):
    checks.append(bool(ok))
    mark = "✓" if ok else "✗ FAIL"
    print("  " + mark + " " + name)


def row_count(db):
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM node").fetchone()[0]
    n += con.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
    con.close()
    return n


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  ✗ FAIL php-not-provisioned")
        return 1

    with tempfile.TemporaryDirectory() as t:
        mdb = os.path.join(t, "mem_graph.db")
        con = sqlite3.connect(mdb)
        con.execute("CREATE TABLE node (id TEXT PRIMARY KEY, kind TEXT, label TEXT, attrs TEXT, ts TEXT)")
        con.execute("CREATE TABLE edge (src TEXT, dst TEXT, kind TEXT, weight REAL, ts TEXT, attrs TEXT)")
        con.execute("CREATE TABLE drift (path TEXT, pingpong_raw REAL, temporal_wobble REAL, fork_spread REAL)")
        con.execute("CREATE TABLE meta (built_at TEXT, n_nodes INTEGER, n_edges INTEGER, sources TEXT)")
        # a node id carrying a live <<<Tag>>> / <script> -> must be ESCAPED when rendered
        evil = "<<<Evil>>><script>alert(1)</script>"
        con.execute("INSERT INTO node (id, kind, label, attrs, ts) VALUES (?,?,?,?,?)",
                    (evil, "mem", "evil-node", "{}", "2026-07-01T00:00:00"))
        con.execute("INSERT INTO node (id, kind, label, attrs, ts) VALUES (?,?,?,?,?)",
                    ("repo/app.py", "file", "app.py", "{}", "2026-07-02T00:00:00"))
        con.execute("INSERT INTO node (id, kind, label, attrs, ts) VALUES (?,?,?,?,?)",
                    ("spec/rfc-0031", "spec", "RFC-0031", "{}", "2026-07-03T00:00:00"))
        # outgoing from evil -> repo/app.py ; incoming to evil <- spec/rfc-0031
        con.execute("INSERT INTO edge (src, dst, kind, weight, ts, attrs) VALUES (?,?,?,?,?,?)",
                    (evil, "repo/app.py", "contains", 1.0, "2026-07-04T00:00:00", "{}"))
        con.execute("INSERT INTO edge (src, dst, kind, weight, ts, attrs) VALUES (?,?,?,?,?,?)",
                    ("spec/rfc-0031", evil, "shadow_of", 1.0, "2026-07-05T00:00:00", "{}"))
        # a cross-repo near-duplicate (similar_to) edge
        con.execute("INSERT INTO edge (src, dst, kind, weight, ts, attrs) VALUES (?,?,?,?,?,?)",
                    ("repo/app.py", "repo/other.py", "similar_to", 0.9731, "2026-07-06T00:00:00", "{}"))
        con.execute("INSERT INTO drift (path, pingpong_raw, temporal_wobble, fork_spread) VALUES (?,?,?,?)",
                    ("repo/app.py", 12.5, None, 3.0))
        con.execute("INSERT INTO meta (built_at, n_nodes, n_edges, sources) VALUES (?,?,?,?)",
                    ("2026-07-06T12:00:00", 3, 3, "omni,forge,mem"))
        con.commit(); con.close()

        before = row_count(mdb)

        env = dict(os.environ)
        env["MEM_GRAPH_DB"] = mdb

        def render(getarr):
            hp = os.path.join(t, "render.php")
            src = harness_tpl.replace("__INVOC__", INVOC).replace("__GET__", getarr)
            with open(hp, "w") as fh:
                fh.write(src)
            return subprocess.run([PHP, hp], capture_output=True, text=True, timeout=60, env=env).stdout

        out_node = render("array('node' => '<<<Evil>>><script>alert(1)</script>')")
        out_over = render("array()")

        after = row_count(mdb)

        check("node lookup renders the node's outgoing + incoming edges",
              ("repo/app.py" in out_node) and ("spec/rfc-0031" in out_node))
        check("near-duplicate similar_to layer surfaces on the overview",
              "repo/other.py" in out_over)
        check("memory-graph data is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out_node) and ("<<<Evil>>>" not in out_node)
              and ("&lt;script&gt;" in out_node) and ("<script>" not in out_node))
        check("the memory-graph reflection never writes to the graph (read-only)",
              before == after)

        # teeth: a non-escaping renderer echoes the RAW node id, leaking the live <<<Tag>>> --
        # the shadow must catch such a renderer (two-sided arena discipline).
        bp = os.path.join(t, "raw.php")
        with open(bp, "w") as fh:
            fh.write(raw_tpl.replace("__MDB__", mdb))
        badout = subprocess.run([PHP, bp], capture_output=True, text=True, timeout=60).stdout

        check("shadow has teeth: a non-escaping renderer leaks the raw <<<",
              "<<<Evil>>>" in badout)

    ok = all(checks)
    print("")
    print(("PASS" if ok else "FAIL") + "  (" + str(sum(checks)) + "/" + str(len(checks)) + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
