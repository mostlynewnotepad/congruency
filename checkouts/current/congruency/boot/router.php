<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/* New-tree router for `php -S`. Self-contained bootstrap for checkouts/current,
   pathed entirely off __DIR__ (relocatable). Telemetry stripped — standup only. */
$BOOT = __DIR__;                                        // checkouts/current/boot

error_reporting(E_ALL & ~E_DEPRECATED);
ini_set('display_errors', '1');
ini_set('session.save_path', sys_get_temp_dir());
ini_set('sendmail_path', '/bin/true');                 // Orderer::sendEmail() -> no MTA, no-op

ob_start();  // buffer output so ?api= can emit clean JSON + status headers after the POM/session boot
             // (included files trail whitespace after their closing php tag, which would otherwise send output)

require $BOOT . '/shim.php';                            // mysql_* -> PDO/sqlite
require $BOOT . '/configure.php';                       // install.json + defaults -> ALL constants
require $BOOT . '/monitor.php';                         // fatal-error net (catch uncaught/ fatal -> log + auto-file a bug)
congruency_install_monitor();                           // register shutdown + exception handlers early -- covers ?route= AND ?page=

set_include_path($BOOT . PATH_SEPARATOR . get_include_path());  // shadow the app's illegal AutoLoader.php
require(CLASS_LOADER_HEADER);
session_start();

if (isset($_GET['fresh'])) { unset($_SESSION['POM']); }

$LOADER = getClassLoader();                             // PHP 8: SPL autoload, not __autoLoad()
spl_autoload_register(function ($class) use ($LOADER) { $LOADER->loadClassByName($class); });

PersistentObjectManager::getPOM();
include(BIN . "Initialize_POM.php");

// REST: ?api=... -> generic JSON over every table. Dispatched here (after the session/POM/ClassLoader boot)
// so writes can require the admin login via UserPrivilegeSet::logged_in(); reads stay public. Short-circuits
// the CMS front controller.
require $BOOT . '/rest.php';
if (isset($_GET['api']) || isset($_GET['route'])) { congruency_rest_dispatch(); exit; }

Controller::control();

try { PersistentObjectManager::pack($_SESSION['POM']); }
catch (\Throwable $e) { error_log("[POM pack skipped: " . $e->getMessage() . "]"); }
