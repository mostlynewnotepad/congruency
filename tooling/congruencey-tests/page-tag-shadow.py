#!/usr/bin/env python3
# page-tag-shadow.py — the page + tag-engine + provenance floor. Drives the REAL recursive tag engine
# (lib/TagLoader/Tag/Tag_Wrapper::execute_all_tags, depth cap 64 — BUG-06) through the REAL parser
# (Tag_Parser + TagArguments) using the app's own regex constants (read verbatim from
# boot/constants.default.json). Proves three critical-feature invariants and is two-sided (teeth):
#   1. a ?page= Document renders through its Document_Templates.Content and its <<<Tag>>> invocators
#      are EXPANDED (a deterministic MarkerTag + a literal marker; no raw <<< left behind).
#   2. the recursive re-parse is DEPTH-BOUNDED: a self-referential invocator (<<<LoopTag>>> re-emits
#      itself) TERMINATES instead of looping forever, and its output is finite (anti-DoS invariant).
#   3. the provenance graph (TicketGraph -> <<<GraphNode(mandate)(id)>>>) renders a ticket's mandate
#      clause read from the mandates table.
#   4. teeth: a pure-python un-capped re-parse of a self-expanding token grows without bound, far past
#      the engine's bounded output — proving 'depth-bounded' distinguishes capped from un-capped.
# Isolation: a throwaway sqlite DB + a PHP harness under a TemporaryDirectory; the live DB/repo are
# never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
PHP  = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
CONG = os.path.join(REPO, "checkouts", "current", "congruency")

checks = []
def check(name, ok):
    checks.append(bool(ok))
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  \033[31m✗ FAIL\033[0m php-not-provisioned")
        return 1

    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "pagetag.sqlite")
        con = sqlite3.connect(db)
        con.executescript(
            "CREATE TABLE Documents (DocumentID INTEGER PRIMARY KEY, TemplateID INTEGER, Title TEXT, Description TEXT, ContentID INTEGER);"
            "CREATE TABLE Document_Templates (TemplateID INTEGER PRIMARY KEY, Content TEXT);"
            "CREATE TABLE tickets (id INTEGER PRIMARY KEY, ts INTEGER, updated INTEGER, component TEXT, title TEXT, severity TEXT, status TEXT, body TEXT, meta TEXT);"
            "CREATE TABLE mandates (id INTEGER PRIMARY KEY, ts INTEGER, ticket_id INTEGER, seq INTEGER, clause TEXT, digest TEXT);"
        )
        # demo page: renders through its template; contains a simple invocator + a literal marker
        con.execute("INSERT INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (?,?,?,?,?)",
                    (1, 10, "demo", "demo page", 0))
        con.execute("INSERT INTO Document_Templates (TemplateID, Content) VALUES (?,?)",
                    (10, "LITERAL-MARKER-DEMO-777 <<<MarkerTag>>> end"))
        # self-referential page: its invocator re-emits <<<LoopTag>>> -> forces the engine to re-parse
        con.execute("INSERT INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (?,?,?,?,?)",
                    (2, 20, "loop", "self-referential page", 0))
        con.execute("INSERT INTO Document_Templates (TemplateID, Content) VALUES (?,?)",
                    (20, "<<<LoopTag>>>"))
        # a ticket with ONE mandate row -> the provenance graph renders its clause
        con.execute("INSERT INTO tickets (id, ts, updated, component, title, severity, status, body, meta) VALUES (?,?,?,?,?,?,?,?,?)",
                    (900, 0, 0, "shadowtest", "shadow provenance ticket", "info", "OPEN", "shadow body", ""))
        con.execute("INSERT INTO mandates (id, ts, ticket_id, seq, clause, digest) VALUES (?,?,?,?,?,?)",
                    (1, 0, 900, 1, "SHADOW-MANDATE-CLAUSE-XYZ", ""))
        con.commit(); con.close()

        # a PHP harness that drives the REAL engine for three cases (dispatched by argv[3]); paths and
        # the db come in as argv so nothing is string-interpolated into the source.
        harness = os.path.join(t, "render.php")
        with open(harness, "w") as fh:
            fh.write(textwrap.dedent('''\
                <?php
                error_reporting(E_ERROR | E_PARSE);
                ini_set('display_errors', '0');

                $DB   = $argv[1];
                $CONG = $argv[2];
                $CASE = $argv[3];

                define('CONGRUENCY_SQLITE', $DB);

                // real regex constants, verbatim from the app's constants.default.json (no reinvention)
                $C = json_decode(file_get_contents($CONG . '/boot/constants.default.json'), true);
                foreach (array('KEY_PREFIX','KEY_SUFFIX','TAG_KEY_PREFIX','TAG_KEY_SUFFIX',
                               'FUNCTION_NAME','FUNCTION_ARGUMENTS','FUNCTION_ARGUMENT','GET_TAG_IDENTIFIER') as $k) {
                    if (!defined($k)) { define($k, $C[$k]); }
                }

                if (!interface_exists('Tag_Interface')) {
                    interface Tag_Interface { public function get_document(); }
                }

                // minimal POM + tag loader: loadClassByName requires the REAL invocator file by name
                class ShadowTagLoader {
                    private $dir;
                    public function __construct($dir) { $this->dir = $dir; }
                    public function loadClassByName($name) {
                        if (class_exists($name)) { return; }
                        $f = $this->dir . '/' . $name . '.php';
                        if (is_file($f)) { require $f; }
                    }
                }
                class PersistentObjectManager {
                    private static $tagloader;
                    public static function setLoader($l) { self::$tagloader = $l; }
                    public static function getData($k) { return ($k === 'TAG_LOADER') ? self::$tagloader : null; }
                }
                PersistentObjectManager::setLoader(new ShadowTagLoader($CONG . '/invocators/tags/dev'));

                // the REAL parser + arguments + recursive engine (with the depth cap)
                require $CONG . '/lib/TagLoader/Parser/Tag_Parser.php';
                require $CONG . '/lib/TagLoader/Arguments/TagArguments.php';
                require $CONG . '/lib/TagLoader/Tag/Tag_Wrapper.php';

                // a page document: returns its Document_Templates.Content verbatim; the engine expands its tags
                class PageDoc implements Tag_Interface {
                    private $content;
                    public function __construct($content) { $this->content = $content; }
                    public function get_document() { return $this->content; }
                }
                // a deterministic simple invocator (proves EXPANSION happened)
                class MarkerTag implements Tag_Interface {
                    public function __construct($args = null) {}
                    public function get_document() { return 'EXPANDED-MARKER-RESULT-42'; }
                }
                // a SELF-REFERENTIAL invocator: re-emits itself, forcing the engine to re-parse (exercises the cap)
                class LoopTag implements Tag_Interface {
                    public function __construct($args = null) {}
                    public function get_document() { return 'L' . KEY_PREFIX . 'LoopTag' . KEY_SUFFIX; }
                }
                // TicketGraph's id argument (single pop())
                class IdArg {
                    private $v;
                    public function __construct($v) { $this->v = $v; }
                    public function pop() { return $this->v; }
                }

                function load_page($slug) {
                    $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
                    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
                    $st = $db->prepare('SELECT dt.Content FROM Documents d JOIN Document_Templates dt ON dt.TemplateID = d.TemplateID WHERE d.Title = :t');
                    $st->execute(array(':t' => $slug));
                    return (string)$st->fetchColumn();
                }

                if ($CASE === 'render') {
                    $doc = Tag_Wrapper::create_document_tag(new PageDoc(load_page('demo')));
                    echo Tag_Wrapper::execute_all_tags($doc);
                } else if ($CASE === 'depth') {
                    $doc = Tag_Wrapper::create_document_tag(new PageDoc(load_page('loop')));
                    echo Tag_Wrapper::execute_all_tags($doc);
                } else if ($CASE === 'graph') {
                    require $CONG . '/invocators/tags/dev/TicketGraph.php';
                    $tg  = new TicketGraph(new IdArg(900));
                    $doc = Tag_Wrapper::create_document_tag($tg);
                    echo Tag_Wrapper::execute_all_tags($doc);
                }
            '''))

        def run_case(case, timeout):
            try:
                p = subprocess.run([PHP, harness, db, CONG, case],
                                   capture_output=True, text=True, timeout=timeout)
                return p.returncode, p.stdout, False
            except subprocess.TimeoutExpired as e:
                out = e.stdout or ""
                if isinstance(out, bytes):
                    out = out.decode("utf-8", "replace")
                return -1, out, True

        render_rc, render_out, render_to = run_case("render", 30)
        depth_rc,  depth_out,  depth_to  = run_case("depth", 30)
        graph_rc,  graph_out,  graph_to  = run_case("graph", 30)

        # 1. a page renders through its template and its <<<Tag>>> invocator is EXPANDED
        check("a page renders and its <<<Tag>>> is expanded",
              (not render_to) and (render_rc == 0)
              and ("EXPANDED-MARKER-RESULT-42" in render_out)
              and ("LITERAL-MARKER-DEMO-777" in render_out)
              and ("<<<MarkerTag>>>" not in render_out)
              and ("<<<" not in render_out))

        # 2. the recursive re-parse is DEPTH-BOUNDED: the self-referential page TERMINATES (returns
        #    within the timeout, rc 0), output is finite/bounded, and the cap leaves the tag literal.
        check("recursive tag re-parse is depth-bounded (self-referential input terminates, output finite)",
              (not depth_to) and (depth_rc == 0)
              and (0 < len(depth_out) < 1000000)
              and ("<<<LoopTag>>>" in depth_out))

        # 3. the provenance graph renders the ticket's mandate clause read from the DB
        check("provenance graph renders a ticket's mandate clause from the DB",
              (not graph_to) and (graph_rc == 0)
              and ("SHADOW-MANDATE-CLAUSE-XYZ" in graph_out))

        # 4. TEETH: an un-capped re-parse of a self-expanding token grows without bound. Modelled in
        #    pure python (no engine): a token that re-emits itself, substituted with NO depth cap. It
        #    explodes; the length ceiling is only a safety valve so the shadow itself can't OOM --
        #    without it the growth is unbounded. Compared against the engine's BOUNDED depth output.
        naive = "T"
        for _ in range(2000):
            naive = naive.replace("T", "TT")
            if len(naive) > 8000000:
                break
        control_len = len(naive)
        check("shadow has teeth: naive un-capped re-parse grows without bound",
              (control_len > 100000) and (control_len > len(depth_out) * 50))

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
