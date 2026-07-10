<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * rest.php — the flexible REST interface over the unified DB (CONGRUENCY_SQLITE). Dispatched by
 * boot/router.php on ?api= / ?route= AFTER the session/POM/ClassLoader boot (so it can check the login).
 * Three layers:
 *
 *  (1) Generic table CRUD (the fast internal path) — every table minus an admin denylist:
 *      GET  ?api=tables                                             -> { "tables": [ ... ] }
 *      GET  ?api=<table>[&<col>=<v>&order=<c>.<dir>&limit=&p=&per=]  -> filtered / paginated rows
 *      GET  ?api=<table>&id=<pk>                                    -> a single row
 *      POST/PUT/PATCH/DELETE ?api=<table>[&id=]                     -> create / update / delete
 *  (2) Data-driven NAMED ROUTES (the stable contract) — endpoints are rows in `api_routes`:
 *      ?route=<name>  -> runs that row's parameterized SQL with bound :params (add an endpoint = a row).
 *  (3) Token auth — writes / token-routes accept an API key (X-Api-Key header or ?key=, in `api_keys`)
 *      OR the admin session. READS stay public.
 *
 * Table/column names are validated against sqlite_master / table_info (allowlist); route SQL is admin-
 * authored + trusted, consumer :params are always bound (prepared) — no injection.
 */

require_once __DIR__ . '/vault.php';   // optional Vault-validated authorization (graceful when unconfigured)

/* authorization: admin session OR a valid API key (X-Api-Key header / ?key=, looked up in api_keys). */
function congruency_rest_apikey($db) {
    $key = isset($_SERVER['HTTP_X_API_KEY']) ? (string) $_SERVER['HTTP_X_API_KEY'] : (string) ($_GET['key'] ?? '');
    if ($key === '') { return false; }
    if (!$db->query("SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys'")->fetch()) { return false; }
    $st = $db->prepare("SELECT label, scope FROM api_keys WHERE key = ?");
    $st->execute(array($key));
    $row = $st->fetch(PDO::FETCH_ASSOC);
    return $row ? $row : false;
}
function congruency_rest_authorized($db) {
    // OVERRIDE SECURITY FLAG (interim): with CONGRUENCY_AUTH_OVERRIDE set, every request is treated
    // as authenticated — the app "starts authenticated". This is a runtime-overridable default on the
    // config object (boot/constants.default.json), landed because the permission system isn't built
    // yet and a stale api-key would otherwise make clients panic. Flip to false (or override via
    // install.json/$CONGRUENCY_CONFIG) to re-enable the key/session checks. SECURITY-TODO: replace
    // with the wallet-backed, role-based authenticator (deferred crank).
    if (defined('CONGRUENCY_AUTH_OVERRIDE') && CONGRUENCY_AUTH_OVERRIDE) { return true; }
    if (class_exists('UserPrivilegeSet') && UserPrivilegeSet::logged_in()) { return true; }
    if (congruency_rest_apikey($db) !== false) { return true; }
    // Vault-validated: when Vault is configured, the App checks the presented token against its authorization
    // secret in Vault — so the shared secret lives in Vault, not at rest in the CMS DB. Off/unreachable -> skip.
    if (function_exists('congruency_vault_authorizes')) {
        $presented = isset($_SERVER['HTTP_X_API_KEY']) ? (string) $_SERVER['HTTP_X_API_KEY'] : (string) ($_GET['key'] ?? '');
        if ($presented !== '' && congruency_vault_authorizes($presented)) { return true; }
    }
    return false;
}

/* data-driven named route: run one row of api_routes with bound :params. The route's SQL is admin-authored
 * (writes are gated), so it is trusted; only declared :params that the SQL actually uses are bound. */
function congruency_rest_route($db, $route, $method) {
    if (!$db->query("SELECT name FROM sqlite_master WHERE type='table' AND name='api_routes'")->fetch()) {
        http_response_code(404); echo json_encode(array('error' => 'no api_routes table')) . "\n"; return true;
    }
    $rs = $db->prepare("SELECT method, sql, auth, params FROM api_routes WHERE name = ?");
    $rs->execute(array($route));
    $def = $rs->fetch(PDO::FETCH_ASSOC);
    if (!$def) { http_response_code(404); echo json_encode(array('error' => 'unknown route', 'route' => $route)) . "\n"; return true; }

    $allowed = array_map('trim', explode(',', strtoupper((string) $def['method'] ?: 'GET')));
    if (!in_array($method, $allowed, true)) {
        http_response_code(405); echo json_encode(array('error' => 'method not allowed', 'route' => $route, 'allowed' => $allowed)) . "\n"; return true;
    }
    $auth = strtolower(trim((string) ($def['auth'] ?? 'public')));
    if ($auth === 'admin' && !(class_exists('UserPrivilegeSet') && UserPrivilegeSet::logged_in())) {
        http_response_code(401); echo json_encode(array('error' => 'admin login required', 'route' => $route)) . "\n"; return true;
    }
    if ($auth === 'token' && !congruency_rest_authorized($db)) {
        http_response_code(401); echo json_encode(array('error' => 'API key or admin login required', 'route' => $route)) . "\n"; return true;
    }

    $input = $_GET;
    if (in_array($method, array('POST', 'PUT', 'PATCH', 'DELETE'), true)) {
        $body = json_decode((string) file_get_contents('php://input'), true);
        if (is_array($body)) { $input = array_merge($input, $body); }
    }

    // Front-end telemetry receiver: telemetry.record carries a kind (error|pageview|event) a single
    // SQL row can't branch on -- a client 'error' must ALSO log to error_log and auto-file a de-duped
    // front-end bug (reusing boot/monitor.php's fatal pipe). Handle it in PHP and short-circuit; the
    // route's INSERT SQL stays the compile-checked contract (route-sql-compiles / route-params-declared).
    if ($route === 'telemetry.record' && function_exists('congruency_telemetry_record')) {
        return congruency_telemetry_record($db, $input);
    }
    $decl = json_decode(((string) ($def['params'] ?? '')) ?: '{}', true);
    if (!is_array($decl)) { $decl = array(); }

    $st = $db->prepare((string) $def['sql']);
    foreach ($decl as $pname => $ptype) {
        if (strpos((string) $def['sql'], ':' . $pname) === false) { continue; }   // only bind params the SQL uses
        $val = array_key_exists($pname, $input) ? $input[$pname] : null;
        if ($val !== null) {
            $t = strtolower((string) $ptype);
            if ($t === 'int') { $val = (int) $val; }
            elseif ($t === 'float' || $t === 'real') { $val = (float) $val; }
            else { $val = (string) $val; }
        }
        $st->bindValue(':' . $pname, $val);
    }
    $st->execute();

    if (stripos(ltrim((string) $def['sql']), 'select') === 0) {
        echo json_encode(array('route' => $route, 'rows' => $st->fetchAll(PDO::FETCH_ASSOC)),
                         JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    } else {
        echo json_encode(array('route' => $route, 'affected' => $st->rowCount(), 'rowid' => $db->lastInsertId()),
                         JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    }
    return true;
}

/* Front-end telemetry receiver behind ?route=telemetry.record (POST, public). Reads the JSON body
 * fields congruency_rest_route already merged into $input and hands them to boot/monitor.php's
 * telemetry ingest, which branches on kind: a client 'error' ALSO logs to error_log and auto-files a
 * de-duped front-end bug (reusing the v4.118 fatal pipe), while pageview/event just land a
 * front_telemetry stream row. Emits a small JSON ack. Never throws (the ingest swallows its own
 * failures) so a beacon can't fatal a page. */
function congruency_telemetry_record($db, $input) {
    $kind    = isset($input['kind'])    ? (string) $input['kind']    : 'pageview';
    $route   = isset($input['route'])   ? (string) $input['route']   : '';
    $message = isset($input['message']) ? (string) $input['message'] : '';
    $detail  = isset($input['detail'])  ? (string) $input['detail']  : '';
    if (function_exists('congruency_telemetry_ingest')) {
        congruency_telemetry_ingest($kind, $route, $message, $detail, $db, true);
    }
    echo json_encode(array('route' => 'telemetry.record', 'ok' => true, 'kind' => $kind),
                     JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    return true;
}

function congruency_rest_dispatch() {
    if (ob_get_level()) { ob_clean(); }                 // drop buffered boot whitespace so JSON headers/body are clean
    header('Content-Type: application/json');
    header('Access-Control-Allow-Origin: *');
    $out = null;
    try {
        if (!defined('CONGRUENCY_SQLITE')) { throw new Exception('CONGRUENCY_SQLITE not defined'); }
        $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
        $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

        $tables = array();
        foreach ($db->query("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name") as $r) {
            $tables[$r['name']] = 1;
        }
        // admin-only: the self-hosting archive + the auth tables + the API keys stay off the public REST surface
        foreach (array('code_blobs', 'code_refs', 'doc_blobs', 'doc_refs',
                       'Login_Password', 'User_Group_Mappings', 'Group_Privileges', 'api_keys') as $__deny) { unset($tables[$__deny]); }

        $api = (string)($_GET['api'] ?? '');
        $route = (string)($_GET['route'] ?? '');
        $method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');

        // (2) Data-driven named routes: ?route=<name> runs an api_routes row (with its own auth).
        if ($route !== '') { return congruency_rest_route($db, $route, $method); }

        // (3) Writes require authorization: the admin session OR a valid API key (X-Api-Key / ?key=). Reads public.
        if (in_array($method, array('POST', 'PUT', 'PATCH', 'DELETE'), true) && !congruency_rest_authorized($db)) {
            http_response_code(401);
            echo json_encode(array('error' => 'authorization required for writes', 'method' => $method,
                                   'hint' => 'send X-Api-Key: <key> (or ?key=), or log in via the Login form')) . "\n";
            return true;
        }

        if ($method === 'POST' && isset($tables[$api])) {
            // CREATE: insert a row from the JSON body; only real columns are used (rest ignored).
            $data = json_decode((string)file_get_contents('php://input'), true);
            if (!is_array($data)) { http_response_code(400); echo json_encode(array('error' => 'body must be a JSON object')); return true; }
            $cols = array();
            foreach ($db->query("PRAGMA table_info(\"$api\")") as $c) { $cols[$c['name']] = 1; }
            $use = array();
            foreach ($data as $k => $v) { if (isset($cols[$k])) { $use[$k] = $v; } }
            if (!$use) { http_response_code(400); echo json_encode(array('error' => 'no valid columns for ' . $api, 'columns' => array_keys($cols))); return true; }
            $names = array_keys($use);
            $sql = "INSERT INTO \"$api\" (" . implode(',', array_map(function ($n) { return "\"$n\""; }, $names)) . ") "
                 . "VALUES (" . implode(',', array_map(function ($n) { return ":$n"; }, $names)) . ")";
            $st = $db->prepare($sql);
            foreach ($use as $k => $v) { $st->bindValue(":$k", $v); }
            $st->execute();
            http_response_code(201);
            echo json_encode(array('created' => true, 'table' => $api, 'rowid' => $db->lastInsertId(), 'used' => $use),
                             JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
            return true;
        }

        if (($method === 'PUT' || $method === 'PATCH') && isset($tables[$api])) {
            // UPDATE by primary key: ?id=<pk>, JSON body of column=>value (real columns only).
            $pk = null;
            foreach ($db->query("PRAGMA table_info(\"$api\")") as $c) { if ($c['pk']) { $pk = $c['name']; } }
            if ($pk === null || !isset($_GET['id'])) { http_response_code(400); echo json_encode(array('error' => 'update needs a single-column pk and ?id=')); return true; }
            $data = json_decode((string)file_get_contents('php://input'), true);
            if (!is_array($data)) { http_response_code(400); echo json_encode(array('error' => 'body must be a JSON object')); return true; }
            $cols = array();
            foreach ($db->query("PRAGMA table_info(\"$api\")") as $c) { $cols[$c['name']] = 1; }
            $use = array();
            foreach ($data as $k => $v) { if (isset($cols[$k]) && $k !== $pk) { $use[$k] = $v; } }
            if (!$use) { http_response_code(400); echo json_encode(array('error' => 'no valid columns to update')); return true; }
            $set = implode(', ', array_map(function ($n) { return "\"$n\" = :$n"; }, array_keys($use)));
            $st = $db->prepare("UPDATE \"$api\" SET $set WHERE \"$pk\" = :__id");
            foreach ($use as $k => $v) { $st->bindValue(":$k", $v); }
            $st->bindValue(":__id", $_GET['id']);
            $st->execute();
            echo json_encode(array('updated' => $st->rowCount(), 'table' => $api, 'pk' => $pk, 'id' => $_GET['id'], 'set' => $use),
                             JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
            return true;
        }

        if ($method === 'DELETE' && isset($tables[$api])) {
            // DELETE a single row by primary key (?id=). No bulk deletes.
            $pk = null;
            foreach ($db->query("PRAGMA table_info(\"$api\")") as $c) { if ($c['pk']) { $pk = $c['name']; } }
            if ($pk === null || !isset($_GET['id'])) { http_response_code(400); echo json_encode(array('error' => 'delete needs a single-column pk and ?id=')); return true; }
            $st = $db->prepare("DELETE FROM \"$api\" WHERE \"$pk\" = ?");
            $st->execute(array($_GET['id']));
            echo json_encode(array('deleted' => $st->rowCount(), 'table' => $api, 'pk' => $pk, 'id' => $_GET['id'])) . "\n";
            return true;
        }

        if ($api === '' || $api === 'tables') {
            $out = array('tables' => array_keys($tables));
        } elseif (isset($tables[$api])) {
            // primary-key column (for ?id=)
            $pk = null;
            foreach ($db->query("PRAGMA table_info(\"$api\")") as $c) { if ($c['pk']) { $pk = $c['name']; break; } }

            if (isset($_GET['id']) && $pk !== null) {
                $st = $db->prepare("SELECT * FROM \"$api\" WHERE \"$pk\" = ?");
                $st->execute(array($_GET['id']));
                $row = $st->fetch(PDO::FETCH_ASSOC);
                if ($row === false) { http_response_code(404); $out = array('error' => 'not found', 'table' => $api, 'id' => $_GET['id']); }
                else { $out = array('table' => $api, 'pk' => $pk, 'row' => $row); }
            } else {
                // filter by any real column named in the query string; order=<col>.<dir>; limit / p / per
                $cols = array();
                foreach ($db->query("PRAGMA table_info(\"$api\")") as $c) { $cols[$c['name']] = 1; }
                $reserved = array('api' => 1, 'route' => 1, 'key' => 1, 'p' => 1, 'per' => 1, 'id' => 1, 'order' => 1, 'limit' => 1);
                $where = array(); $bind = array();
                foreach ($_GET as $k => $v) {
                    if (isset($cols[$k]) && !isset($reserved[$k])) { $where[] = "\"$k\" = :f_$k"; $bind[":f_$k"] = $v; }
                }
                $wsql = $where ? (' WHERE ' . implode(' AND ', $where)) : '';
                $order = '';
                if (isset($_GET['order'])) {
                    $op = explode('.', (string)$_GET['order']);
                    $ocol = $op[0]; $odir = (isset($op[1]) && strtolower($op[1]) === 'desc') ? 'DESC' : 'ASC';
                    if (isset($cols[$ocol])) { $order = " ORDER BY \"$ocol\" $odir"; }
                }
                $per = isset($_GET['per']) ? max(1, min(500, (int)$_GET['per']))
                     : (isset($_GET['limit']) ? max(1, min(500, (int)$_GET['limit'])) : 50);
                $pg  = isset($_GET['p'])   ? max(1, (int)$_GET['p']) : 1;
                $off = ($pg - 1) * $per;
                $ct = $db->prepare("SELECT COUNT(*) FROM \"$api\"" . $wsql);
                $ct->execute($bind);
                $total = (int)$ct->fetchColumn();
                $q = $db->prepare("SELECT * FROM \"$api\"" . $wsql . $order . " LIMIT $per OFFSET $off");
                $q->execute($bind);
                $rows = $q->fetchAll(PDO::FETCH_ASSOC);
                $out = array('table' => $api, 'pk' => $pk, 'total' => $total, 'page' => $pg, 'per' => $per,
                             'pages' => (int)ceil($total / max(1, $per)), 'filter' => array_keys($bind), 'rows' => $rows);
            }
        } else {
            http_response_code(404);
            $out = array('error' => 'unknown table', 'table' => $api, 'tables' => array_keys($tables));
        }
    } catch (\Throwable $e) {
        http_response_code(500);
        $out = array('error' => $e->getMessage());
    }
    echo json_encode($out, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    return true;
}
