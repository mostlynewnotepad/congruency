<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * Style — the ONE site stylesheet. Every page template embeds <<<Style>>> in its <head> (like
 * <<<TitleTag>>>), so the entire look lives in a single place: change it here, every page changes.
 * Full-width by design — no max-width, just comfortable side margins, so the content uses the whole screen.
 * The nav styling (including the all-caps top-level links) lives here too.
 */
if (!class_exists("Style")) {
    class Style implements Tag_Interface {
        public function __construct($arguments) {}
        public function get_document() {
            return "<style>"
                 . "body{font-family:Georgia,serif;margin:1.5rem 2.5rem;line-height:1.6;color:#222;background:#f7f4ee}"
                 . "a{color:#8a5a1a}"
                 . "h1,h2{font-weight:normal}"
                 . "code{background:#eae5d8;padding:1px 4px}"
                 . "pre{background:#f4f1e8;border:1px solid #d8d2c4;padding:.6rem;overflow:auto}"
                 . "nav{margin:0 0 1.5rem;padding-bottom:.75rem;border-bottom:1px solid #ccc;text-transform:uppercase;letter-spacing:.04em}"
                 . "table{border-collapse:collapse}"
                 . "th,td{text-align:left}"
                 . ".prose{max-width:70ch}"   // reading pages opt in via class='prose' — a comfortable measure; data/code pages stay full-width
                 . "</style>"
                 . "<<<TelemetryBeacon>>>";
        }
    }
}
?>
