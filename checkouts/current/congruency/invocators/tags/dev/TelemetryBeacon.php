<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * TelemetryBeacon -- <<<TelemetryBeacon>>>. Emitted ONCE per served page (spliced by <<<Style>>>,
 * which every page template embeds in its <head>) so every page carries the front-end telemetry
 * beacon. Returns a small SELF-CONTAINED inline <script> (no external deps, no server data
 * interpolated -- a NOWDOC literal, so it is escape-safe by construction) that:
 *   - reports a PAGE VIEW on DOMContentLoaded,
 *   - reports any client JS ERROR (window 'error' + 'unhandledrejection') as kind='error', which the
 *     telemetry.record receiver routes into the SERVER fatal pipe (error_log + auto-filed front-end
 *     bug), so a browser crash surfaces in ?page=bugs like a server fatal,
 *   - reports a THROTTLED interaction EVENT on click (ignores repeats within 500ms),
 * all via navigator.sendBeacon('/?route=telemetry.record', JSON) with a fetch(keepalive) fallback.
 */
if (!class_exists("TelemetryBeacon")) {
    class TelemetryBeacon implements Tag_Interface {
        public function __construct($arguments = null) {}
        public function get_document() {
            return <<<'BEACON'
<script>
(function(){
  var EP='/?route=telemetry.record';
  function beacon(p){
    try{
      var b=JSON.stringify(p);
      if(navigator&&typeof navigator.sendBeacon==='function'){navigator.sendBeacon(EP,b);}
      else{fetch(EP,{method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:b});}
    }catch(err){}
  }
  function route(){return location.search||location.pathname;}
  document.addEventListener('DOMContentLoaded',function(){beacon({kind:'pageview',route:route()});});
  window.addEventListener('error',function(e){
    beacon({kind:'error',message:(e&&e.message)?String(e.message):'error',route:route(),detail:((e&&e.filename)||'')+':'+((e&&e.lineno)||0)+':'+((e&&e.colno)||0)});
  });
  window.addEventListener('unhandledrejection',function(e){
    beacon({kind:'error',message:'unhandledrejection: '+String(e&&e.reason),route:route(),detail:''});
  });
  var last=0;
  document.addEventListener('click',function(e){
    var now=(new Date()).getTime();
    if(now-last<500){return;}
    last=now;
    var el=e.target||{};
    var tag=(el.tagName||'').toLowerCase();
    var id=el.id?('#'+el.id):'';
    beacon({kind:'event',route:route(),detail:'click:'+tag+id});
  },true);
})();
</script>
BEACON;
        }
    }
}
?>
