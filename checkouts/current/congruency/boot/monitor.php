<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * boot/monitor.php -- the SYSTEMIC FATAL-ERROR NET. Installed once, as early as possible, by
 * congruency_install_monitor($pdo) from boot/router.php so it covers BOTH the REST path (?route=/?api=)
 * AND the page-render path (?page=). Nothing else in the app watches for uncaught exceptions or fatal
 * errors, so a live OOM (e.g. SemanticSearch.php) would otherwise die silently to the client. This
 * closes that hole: every uncaught Throwable and every fatal error is
 *   (a) written to the error_log table (migrations/0026_error_log.sql), and
 *   (b) auto-filed as a de-duped bug (source=fatal-monitor) into the SAME `bugs` table bug.record
 *       uses, so it surfaces in ?page=bugs.
 *
 * OOM SURVIVAL: at install time we reserve 256KB ($GLOBALS['__oom_reserve']); the shutdown handler
 * FIRST frees it and raises memory_limit, before any work, so a memory-exhaustion fatal can still be
 * recorded.
 *
 * DE-DUP: sig = substr(sha1(type|message|file|line),0,16). One open bug per signature within a 3600s
 * window -- a repeat still logs an error_log row but does NOT file a second bug.
 *
 * The whole monitor is wrapped in try/catch: a logging failure must NEVER itself fatal.
 */
if (!function_exists('congruency_monitor_report')) {

    function congruency_monitor_db($pdo = null) {
        if ($pdo instanceof PDO) { return $pdo; }
        if (defined('CONGRUENCY_SQLITE')) {
            $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);   // resolved the same way boot does
            $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            return $db;
        }
        if (isset($GLOBALS['__monitor_pdo']) && $GLOBALS['__monitor_pdo'] instanceof PDO) {
            return $GLOBALS['__monitor_pdo'];
        }
        return null;
    }

    function congruency_monitor_route() {
        foreach (array('route', 'page', 'api') as $k) {
            if (isset($_GET[$k]) && $_GET[$k] !== '') { return $k . '=' . (string) $_GET[$k]; }
        }
        return '';
    }

    // report ONE fatal: log an error_log row (always) + auto-file a de-duped bug. NEVER throws.
    function congruency_monitor_report($type, $message, $file, $line, $route = null, $pdo = null, $dedup = true) {
        try {
            $db = congruency_monitor_db($pdo);
            if (!($db instanceof PDO)) { return; }
            if ($route === null) { $route = congruency_monitor_route(); }
            $type    = (int) $type;
            $message = (string) $message;
            $file    = (string) $file;
            $line    = (int) $line;
            $route   = (string) $route;
            $ts      = time();
            $sig     = substr(sha1($type . '|' . $message . '|' . $file . '|' . $line), 0, 16);

            // (a) ALWAYS record the error_log row.
            $st = $db->prepare('INSERT INTO error_log (ts, type, message, file, line, route, sig)
                                VALUES (:ts, :type, :message, :file, :line, :route, :sig)');
            $st->execute(array(':ts' => $ts, ':type' => $type, ':message' => $message,
                               ':file' => $file, ':line' => $line, ':route' => $route, ':sig' => $sig));

            // (b) DE-DUP: one open bug per signature within the window. A prior error_log row with the
            //     same sig means the bug is already filed -> log-only (skip the bug insert).
            if ($dedup) {
                $seen = $db->prepare('SELECT COUNT(*) FROM error_log WHERE sig = :sig AND ts >= :since');
                $seen->execute(array(':sig' => $sig, ':since' => $ts - 3600));
                if ((int) $seen->fetchColumn() > 1) { return; }
            }

            // (b) AUTO-FILE a bug, SAME columns bug.record uses, so it appears in ?page=bugs.
            $GLOBALS['__monitor_seq'] = (isset($GLOBALS['__monitor_seq']) ? $GLOBALS['__monitor_seq'] : 0) + 1;
            $short = (strlen($message) > 77) ? (substr($message, 0, 77) . '...') : $message;
            $title = 'fatal: ' . $short . ' @ ' . $file . ':' . $line;
            $bodytxt = 'type=' . $type . ' route=' . $route . ' | ' . $message . ' @ ' . $file . ':' . $line;
            $bug = $db->prepare('INSERT OR REPLACE INTO bugs
                (bug_id, source, title, severity, location, repro, success, fanout, repos, status, pattern, meta)
                VALUES (:bug_id, :source, :title, :severity, :location, :repro, :success, :fanout, :repos, :status, :pattern, :meta)');
            $bug->execute(array(
                ':bug_id'   => $sig . '-' . $GLOBALS['__monitor_seq'],
                ':source'   => 'fatal-monitor',
                ':title'    => $title,
                ':severity' => 'high',
                ':location' => $file . ':' . $line,
                ':repro'    => '',
                ':success'  => '',
                ':fanout'   => 0,
                ':repos'    => 0,
                ':status'   => 'open',
                ':pattern'  => 'fatal',
                ':meta'     => $bodytxt,
            ));
        } catch (\Throwable $e) {
            // a logging failure must never itself fatal -- swallow it.
        }
    }

    // shutdown: catch fatals (incl. OOM). Free the reserve + raise the limit FIRST, before any work.
    function congruency_monitor_shutdown() {
        unset($GLOBALS['__oom_reserve']);
        @ini_set('memory_limit', '512M');
        try {
            $e = error_get_last();
            $mask = E_ERROR | E_PARSE | E_CORE_ERROR | E_COMPILE_ERROR | E_USER_ERROR | E_RECOVERABLE_ERROR;
            if ($e && ($e['type'] & $mask)) {
                congruency_monitor_report($e['type'], $e['message'], $e['file'], $e['line']);
            }
        } catch (\Throwable $x) {
            // never fatal from the shutdown handler.
        }
    }

    // uncaught exceptions anywhere in the app.
    function congruency_monitor_exception($ex) {
        try {
            congruency_monitor_report(E_ERROR, get_class($ex) . ': ' . $ex->getMessage(), $ex->getFile(), $ex->getLine());
        } catch (\Throwable $x) {
            // swallow.
        }
    }

    // install once: reserve OOM headroom, register the shutdown + exception handlers. $pdo optional.
    function congruency_install_monitor($pdo = null) {
        if (!empty($GLOBALS['__monitor_installed'])) { return; }
        $GLOBALS['__monitor_installed'] = true;
        if ($pdo instanceof PDO) { $GLOBALS['__monitor_pdo'] = $pdo; }
        $GLOBALS['__oom_reserve'] = str_repeat('x', 262144);   // 256KB, freed first in the shutdown handler
        register_shutdown_function('congruency_monitor_shutdown');
        set_exception_handler('congruency_monitor_exception');
    }
}
