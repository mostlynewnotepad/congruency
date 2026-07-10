#!/usr/bin/env python3
# tree-injection-shadow.py — the TreeView invocator (?page=tree) browses ONLY repos actually
# registered in the `repos` table (a DB whitelist: name/forge_remote/head_commit come from the row,
# never trusted from ?repo=), and EVERY git argument is escapeshellarg()'d so a malicious ?path= /
# ?blob= cannot inject a shell command or run a non-read-only git subcommand (only ls-tree/show are
# ever run). Two-sided (teeth): the same payload string-interpolated into a RAW git command WITHOUT
# escapeshellarg DOES inject (a second sentinel appears), proving the payload is real and that
# escapeshellarg is exactly what stops it. Isolation: a real bare git repo + a throwaway sqlite DB +
# a PHP harness under a TemporaryDirectory; the live DB and repo are never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "TreeView.php")

checks = []
def check(name, ok):
    checks.append(bool(ok))
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def git(args, env):
    subprocess.run(["git"] + args, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  \033[31m✗ FAIL\033[0m php-not-provisioned")
        return 1

    with tempfile.TemporaryDirectory() as t:
        bare = os.path.join(t, "safe.git")
        work = os.path.join(t, "work")
        os.makedirs(work, exist_ok=True)

        env = dict(os.environ)
        env.update({
            "GIT_AUTHOR_NAME": "shadow", "GIT_AUTHOR_EMAIL": "shadow@local",
            "GIT_COMMITTER_NAME": "shadow", "GIT_COMMITTER_EMAIL": "shadow@local",
        })

        # a REAL bare repo to serve as the registered repo's forge_remote
        git(["init", "--bare", bare], env)
        git(["init", work], env)
        with open(os.path.join(work, "hello.txt"), "w") as fh:
            fh.write("hi")
        git(["-C", work, "add", "hello.txt"], env)
        git(["-C", work, "commit", "-m", "seed"], env)
        git(["-C", work, "push", bare, "HEAD:refs/heads/main"], env)
        sha = subprocess.run(["git", "-C", work, "rev-parse", "HEAD"],
                             capture_output=True, text=True, env=env).stdout.strip()

        # a throwaway sqlite whitelist: one registered repo ('safe')
        db = os.path.join(t, "tree.sqlite")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE repos (name TEXT, forge_remote TEXT, head_commit TEXT)")
        con.execute("INSERT INTO repos (name, forge_remote, head_commit) VALUES (?,?,?)",
                    ("safe", bare, sha))
        con.commit(); con.close()

        SENTINEL = os.path.join(t, "pwned")     # must NOT exist after any escaped attempt
        SENTINEL2 = os.path.join(t, "pwned2")   # WILL exist after the raw (unescaped) control

        # a PHP harness: render the ACTUAL TreeView invocator for four cases, each output fenced by a
        # marker so python can slice it. warnings silenced so they can't pollute a captured body.
        harness = os.path.join(t, "render.php")
        with open(harness, "w") as fh:
            fh.write(textwrap.dedent('''\
                <?php
                error_reporting(E_ERROR | E_PARSE);
                ini_set('display_errors', '0');
                define('CONGRUENCY_SQLITE', %r);
                interface Tag_Interface { public function get_document(); }
                class ArgStub { public function pop() { return null; } }
                require %r;
                $SENT = $argv[1];
                function render($get) {
                    $_GET = $get;
                    $t = new TreeView(new ArgStub());
                    return $t->get_document();
                }
                $cases = array(
                    'A' => array('repo' => 'safe'),
                    'B' => array('repo' => 'evil-unregistered'),
                    'C' => array('repo' => 'safe', 'path' => '; touch ' . $SENT . '; #'),
                    'D' => array('repo' => 'safe', 'blob' => 'HEAD; touch ' . $SENT),
                );
                foreach ($cases as $id => $get) {
                    echo "\n===CASE-" . $id . "-BEGIN===\n";
                    echo render($get);
                    echo "\n===CASE-" . $id . "-END===\n";
                }
            ''') % (db, INVOC))

        proc = subprocess.run([PHP, harness, SENTINEL], capture_output=True, text=True, timeout=60)
        out = proc.stdout

        def block(cid):
            b = "===CASE-%s-BEGIN===" % cid
            e = "===CASE-%s-END===" % cid
            i = out.find(b); j = out.find(e)
            if i < 0 or j < 0:
                return ""
            return out[i + len(b):j]

        A = block('A'); B = block('B')

        # teeth: the SAME payload interpolated into a RAW git command WITHOUT escapeshellarg -> injects
        os.system("git --git-dir=" + bare + " ls-tree HEAD ; touch " + SENTINEL2 + " ; #")

        check("tree whitelist: registered repo renders, unregistered refused",
              ("hello.txt" in A) and ("No such registered repo" in B))
        check("git args escapeshellarg'd: malicious path/blob cannot inject a shell command",
              not os.path.exists(SENTINEL))
        check("shadow has teeth: the raw (unescaped) control DOES inject",
              os.path.exists(SENTINEL2))

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
