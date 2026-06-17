"""Local MBTiles server for offline map tiles.

Serves Leaflet assets + map tiles from a local .mbtiles SQLite file.
If no .mbtiles file is found, falls back to proxying OpenStreetMap tiles
(when internet is available).

Usage:
    server = MBTilesServer(mbtiles_dir="data")
    port = server.start()
    # Load http://127.0.0.1:{port}/ in QWebEngineView
"""

from __future__ import annotations

import io
import os
import re
import glob
import sqlite3
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.error import URLError

log = logging.getLogger(__name__)

# ── Leaflet assets (served from local server so map works fully offline) ──

_LEAFLET_VERSION = "1.9.4"
_UNPKG_CSS = f"https://unpkg.com/leaflet@{_LEAFLET_VERSION}/dist/leaflet.css"
_UNPKG_JS = f"https://unpkg.com/leaflet@{_LEAFLET_VERSION}/dist/leaflet.js"

# Cached at module level after first fetch
_cached_css: str | None = None
_cached_js: str | None = None


def _fetch_leaflet_assets() -> tuple[str, str]:
    """Download and cache Leaflet CSS/JS (one-time, on first server start)."""
    global _cached_css, _cached_js
    if _cached_css and _cached_js:
        return _cached_css, _cached_js

    # Try local files first (user can place leaflet.css / leaflet.js next to mbtiles)
    here = os.path.dirname(os.path.abspath(__file__))
    css_path = os.path.join(here, "leaflet.css")
    js_path = os.path.join(here, "leaflet.js")

    if os.path.isfile(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            _cached_css = f.read()
    else:
        try:
            _cached_css = urlopen(_UNPKG_CSS, timeout=10).read().decode("utf-8")
        except Exception:
            _cached_css = "/* Leaflet CSS unavailable */"

    if os.path.isfile(js_path):
        with open(js_path, "r", encoding="utf-8") as f:
            _cached_js = f.read()
    else:
        try:
            _cached_js = urlopen(_UNPKG_JS, timeout=10).read().decode("utf-8")
        except Exception:
            _cached_js = "/* Leaflet JS unavailable */"

    return _cached_css, _cached_js


def _build_map_html(tile_url: str, has_mbtiles: bool) -> str:
    """Build the full Leaflet map HTML with the correct tile URL."""
    css, js = _fetch_leaflet_assets()

    # Escape backticks / dollar signs for embedding in template
    # (Leaflet JS is safe to embed as-is since it doesn't use backtick templates
    # at the top level in a conflicting way, but we use a script tag)

    return f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
{css}
</style>
<script>
{js}
</script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;overflow:hidden;background:#1c1c1e}}
#map{{width:100%;height:100%}}
.leaflet-control-zoom a{{background:#2c2c2e!important;color:#f5f5f7!important;border:1px solid #48484a!important}}
.leaflet-control-zoom a:hover{{background:#3a3a3c!important}}
.leaflet-control-attribution{{display:none!important}}
.leaflet-popup-content-wrapper{{background:rgba(28,28,30,0.94);color:#f5f5f7;border:1px solid rgba(72,72,74,0.6);border-radius:6px;font:600 11px 'SF Pro Display',sans-serif}}
.leaflet-popup-tip{{background:rgba(28,28,30,0.94)}}
#hud{{position:absolute;bottom:14px;left:50%;transform:translateX(-50%);
  background:rgba(28,28,30,0.92);border:1px solid rgba(10,132,255,0.4);
  border-radius:8px;padding:8px 18px;color:#f5f5f7;font:600 13px 'SF Pro Display',sans-serif;
  display:none;pointer-events:none;white-space:nowrap;z-index:1000}}
#hud.show{{display:flex;align-items:center;gap:10px}}
#hud .dist{{color:#0a84ff;font-size:16px}}
#hud .brg{{color:#30d158;font-size:13px}}
#hud .unit{{color:#636366;font-size:11px}}
#hud .hint{{color:#98989d;font-size:10px}}
#clearBtn{{position:absolute;top:10px;right:10px;z-index:1000;
  background:rgba(28,28,30,0.9);border:1px solid rgba(72,72,74,0.6);
  border-radius:6px;padding:6px 14px;color:#98989d;font:600 10px 'SF Pro Display',sans-serif;
  cursor:pointer;letter-spacing:1px;display:none}}
#clearBtn:hover{{background:rgba(45,45,45,0.95);color:#f5f5f7;border-color:#0a84ff}}
#clearBtn.show{{display:block}}
#beamInfo{{position:absolute;bottom:14px;left:14px;z-index:1000;
  background:rgba(28,28,30,0.88);border:1px solid rgba(255,159,10,0.4);
  border-radius:6px;padding:6px 12px;color:#ff9f0a;font:600 11px 'SF Pro Display',sans-serif;
  pointer-events:none;display:none}}
#beamInfo.show{{display:block}}
#offline{{position:absolute;inset:0;display:none;flex-direction:column;
  align-items:center;justify-content:center;color:#636366;
  font:600 14px 'SF Pro Display',sans-serif;background:#1c1c1e;z-index:2000}}
#offline .icon{{font-size:48px;margin-bottom:12px;opacity:0.4}}
#offline .sub{{font-size:11px;color:#48484a;margin-top:6px}}
</style>
</head>
<body>
<div id="map"></div>
<div id="hud"><span class="dist" id="distVal">0</span><span class="unit">m</span><span class="brg" id="brgVal"></span><span class="hint">LClick: measure | RClick: set device | DblClick: finish</span></div>
<button id="clearBtn" onclick="clearAll()">CLEAR</button>
<div id="beamInfo">BEAM <span id="beamAngle">0</span>&deg;</div>
<div id="offline"><div class="icon">&#x1F5FA;</div>Map offline<div class="sub">No tiles available</div></div>
<script>
var map, devicePos=[55.751574,37.573856];
var beamOffset=0, beamLength=3000, currentPan=0;
var markers=[], line=null, bearingLines=[], points=[], totalDist=0;
var devMarker=null, beamLine=null, beamMarker=null, beamCone=null;
var hud=document.getElementById('hud'), distVal=document.getElementById('distVal');
var brgVal=document.getElementById('brgVal');
var clearBtn=document.getElementById('clearBtn');
var beamInfo=document.getElementById('beamInfo'), beamAngleEl=document.getElementById('beamAngle');
var offlineDiv=document.getElementById('offline');
var HAS_LOCAL_TILES = {str(has_mbtiles).lower()};

function haversine(a,b){{
  var R=6371000, dLat=(b[0]-a[0])*Math.PI/180, dLon=(b[1]-a[1])*Math.PI/180;
  var la=a[0]*Math.PI/180, lb=b[0]*Math.PI/180;
  var x=Math.sin(dLat/2)*Math.sin(dLat/2)+Math.cos(la)*Math.cos(lb)*Math.sin(dLon/2)*Math.sin(dLon/2);
  return R*2*Math.atan2(Math.sqrt(x),Math.sqrt(1-x));
}}
function bearing(a,b){{
  var la=a[0]*Math.PI/180,lb=b[0]*Math.PI/180,dL=(b[1]-a[1])*Math.PI/180;
  var y=Math.sin(dL)*Math.cos(lb),x=Math.cos(la)*Math.sin(lb)-Math.sin(la)*Math.cos(lb)*Math.cos(dL);
  return (Math.atan2(y,x)*180/Math.PI+360)%360;
}}
function destPoint(lat,lon,brg,d){{
  var R=6371000,dR=d/R,la=lat*Math.PI/180,lo=lon*Math.PI/180,b=brg*Math.PI/180;
  var la2=Math.asin(Math.sin(la)*Math.cos(dR)+Math.cos(la)*Math.sin(dR)*Math.cos(b));
  var lo2=lo+Math.atan2(Math.sin(b)*Math.sin(dR)*Math.cos(la),Math.cos(dR)-Math.sin(la)*Math.sin(la2));
  return [la2*180/Math.PI,lo2*180/Math.PI];
}}
function fmtDist(m){{return m>=1000?(m/1000).toFixed(2)+' km':m.toFixed(0)+' m'}}

// Device marker
function updateDeviceMarker(){{
  if(!devMarker){{
    devMarker=L.circleMarker(devicePos,{{radius:7,fillColor:'#ff453a',fillOpacity:1,
      color:'#ff453a',weight:2}}).addTo(map);
    devMarker.bindTooltip('Device',{{permanent:false,direction:'top'}});
  }} else devMarker.setLatLng(devicePos);
}}

function updateHud(){{
  if(points.length===0){{hud.classList.remove('show');clearBtn.classList.remove('show');return}}
  var last=points[points.length-1];
  var d=haversine(devicePos,last);
  var b=bearing(devicePos,last).toFixed(0);
  distVal.textContent=totalDist>=1000?(totalDist/1000).toFixed(2):totalDist.toFixed(0);
  brgVal.textContent=' | '+b+'\u00B0 ('+fmtDist(d)+')';
  hud.classList.add('show');clearBtn.classList.add('show');
}}

function clearAll(){{
  markers.forEach(function(m){{map.removeLayer(m)}});
  bearingLines.forEach(function(l){{map.removeLayer(l)}});
  if(line) map.removeLayer(line);
  markers=[];bearingLines=[];points=[];line=null;totalDist=0;
  updateHud();
}}

// Beam visualization
function updateBeam(panDeg){{
  currentPan=panDeg;
  var bng=((panDeg+beamOffset)%360+360)%360;
  var endPt=destPoint(devicePos[0],devicePos[1],bng,beamLength);

  updateDeviceMarker();

  // Beam ray
  if(!beamLine){{
    beamLine=L.polyline([devicePos,endPt],{{color:'#FF9F0A',weight:2,opacity:0.8,
      dashArray:'8,6'}}).addTo(map);
  }} else beamLine.setLatLngs([devicePos,endPt]);

  // Beam cone
  var halfSpread=8;
  var b1=((bng-halfSpread)%360+360)%360;
  var b2=((bng+halfSpread)%360+360)%360;
  var ep1=destPoint(devicePos[0],devicePos[1],b1,beamLength*0.7);
  var ep2=destPoint(devicePos[0],devicePos[1],b2,beamLength*0.7);
  if(!beamCone){{
    beamCone=L.polygon([devicePos,ep1,endPt,ep2],{{
      fillColor:'#FF9F0A',fillOpacity:0.12,stroke:false}}).addTo(map);
  }} else beamCone.setLatLngs([devicePos,ep1,endPt,ep2]);

  // Beam end dot
  if(!beamMarker){{
    beamMarker=L.circleMarker(endPt,{{radius:5,fillColor:'#FF9F0A',fillOpacity:1,
      color:'#FF9F0A',weight:1}}).addTo(map);
  }} else beamMarker.setLatLng(endPt);

  beamAngleEl.textContent=bng.toFixed(0);
  beamInfo.classList.add('show');
}}

// Python -> JS bridge
function pySetPan(deg){{updateBeam(parseFloat(deg))}}
function pySetDevicePos(lat,lng){{
  devicePos=[parseFloat(lat),parseFloat(lng)];
  if(map) map.setView(devicePos, map.getZoom(), {{animate:false}});
  updateBeam(currentPan);
  updateBearingLines();
}}
function pySetBeamOffset(deg){{beamOffset=parseFloat(deg);updateBeam(currentPan)}}
function pySetBeamLength(m){{beamLength=parseFloat(m);updateBeam(currentPan)}}

// Saved config apply on load
function pyApplyConfig(lat,lng,offset,length,pan){{
  devicePos=[parseFloat(lat),parseFloat(lng)];
  beamOffset=parseFloat(offset);
  beamLength=parseFloat(length);
  if(map) map.setView(devicePos, map.getZoom(), {{animate:false}});
  updateBeam(parseFloat(pan));
}}

// Bearing lines: draw from device to each measured point
function updateBearingLines(){{
  bearingLines.forEach(function(l){{map.removeLayer(l)}});
  bearingLines=[];
  points.forEach(function(pt,i){{
    var brg=bearing(devicePos,pt).toFixed(0);
    var dist=haversine(devicePos,pt);
    var bl=L.polyline([devicePos,pt],{{
      color:'#30d158',weight:1.5,opacity:0.6,dashArray:'6,4'
    }}).addTo(map);
    bl.bindPopup('<b>P'+(i+1)+'</b><br>'+brg+'\u00B0 | '+fmtDist(dist));
    bearingLines.push(bl);
  }});
}}

// Init map
try {{
  map=L.map('map',{{center:devicePos,zoom:14,zoomControl:true,
    attributionControl:false}});

  // Primary: local tiles from MBTiles server
  var localLayer=L.tileLayer('{tile_url}',{{
    maxZoom:19, errorTileUrl:'', tms:false
  }}).addTo(map);

  var tilesLoaded=false;
  var localFailed=false;

  localLayer.on('tileerror',function(){{
    if(!tilesLoaded){{
      // If local tiles failed and we don't have mbtiles, show offline
      if(!HAS_LOCAL_TILES) offlineDiv.style.display='flex';
    }}
  }});
  localLayer.on('tileload',function(){{tilesLoaded=true;offlineDiv.style.display='none'}});

  // LEFT CLICK — measure distance
  map.on('click',function(e){{
    var latlng=[e.latlng.lat,e.latlng.lng];
    if(points.length>0){{
      var prev=points[points.length-1];
      totalDist+=haversine(prev,latlng);
    }}
    points.push(latlng);
    var pm=L.circleMarker(latlng,{{radius:5,fillColor:'#0a84ff',fillOpacity:1,
      color:'#0a84ff',weight:1}}).addTo(map);
    markers.push(pm);
    if(line) map.removeLayer(line);
    if(points.length>=2){{
      line=L.polyline(points,{{color:'#0a84ff',weight:2,opacity:1}}).addTo(map);
    }}
    var brg=bearing(devicePos,latlng).toFixed(0);
    var distDev=haversine(devicePos,latlng);
    var bl=L.polyline([devicePos,latlng],{{
      color:'#30d158',weight:1.5,opacity:0.6,dashArray:'6,4'
    }}).addTo(map);
    bl.bindPopup('<b>P'+points.length+'</b><br>'+brg+'\u00B0 | '+fmtDist(distDev));
    bearingLines.push(bl);
    pm.bindTooltip('P'+points.length+' '+brg+'\u00B0 '+fmtDist(distDev),{{
      permanent:false,direction:'top',className:'leaflet-popup-content-wrapper'}});
    updateHud();
  }});

  // RIGHT CLICK — set device position
  map.on('contextmenu',function(e){{
    L.DomEvent.preventDefault(e);
    devicePos=[e.latlng.lat,e.latlng.lng];
    devMarker.setLatLng(devicePos);
    updateBeam(currentPan);
    updateBearingLines();
    updateHud();
  }});

  // Dbl-click to finish
  map.on('dblclick',function(e){{L.DomEvent.stopPropagation(e);updateHud()}});
  map.doubleClickZoom.disable();

  updateBeam(0);
}} catch(ex) {{
  offlineDiv.style.display='flex';
  console.error('Map init failed:',ex);
}}
</script>
</body>
</html>
"""


# ── MBTiles reader ──

class _MBTilesDB:
    """Thread-safe MBTiles reader."""

    def __init__(self, path: str):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    def open(self):
        self._conn = sqlite3.connect(
            self._path,
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=wal")

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_tile(self, z: int, x: int, y: int) -> bytes | None:
        """Return tile PNG bytes for z/x/y, or None."""
        if not self._conn:
            return None
        try:
            cur = self._conn.execute(
                "SELECT tile_data FROM tiles "
                "WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (z, x, y),
            )
            row = cur.fetchone()
            return row[0] if row else None
        except Exception:
            return None


# ── HTTP request handler ──

_TILE_RE = re.compile(r"^/tiles/(\d+)/(\d+)/(\d+)\.png$")
_OSM_PROXY_RE = re.compile(r"^/osm/(\d+)/(\d+)/(\d+)\.png$")


class _TileHandler(BaseHTTPRequestHandler):
    """Serves the map page, Leaflet assets, and tiles."""

    # Set by MBTilesServer before starting
    mbtiles_db: _MBTilesDB | None = None
    map_html: str = ""

    def log_message(self, fmt, *args):
        """Suppress default HTTP access logs."""
        pass

    def _send(self, code: int, content_type: str, data: bytes):
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # Client disconnected — safe to ignore for tile requests

    def do_GET(self):
        path = self.path.split("?")[0]  # strip query string

        # Serve map page
        if path == "/" or path == "/index.html":
            self._send(200, "text/html; charset=utf-8",
                       self.map_html.encode("utf-8"))
            return

        # Serve MBTiles tiles
        m = _TILE_RE.match(path)
        if m and self.mbtiles_db:
            z, x, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            # MBTiles uses TMS y-coordinate (flipped)
            tms_y = (1 << z) - 1 - y
            tile_data = self.mbtiles_db.get_tile(z, x, tms_y)
            if tile_data:
                self._send(200, "image/png", tile_data)
                return
            # Tile not in MBTiles — return 404 so Leaflet shows empty
            try:
                self.send_response(404)
                self.end_headers()
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass
            return

        # Proxy OSM tiles (fallback when no MBTiles)
        m2 = _OSM_PROXY_RE.match(path)
        if m2:
            z, x, y = m2.group(1), m2.group(2), m2.group(3)
            url = f"https://{'abc'[hash((z,x,y)) % 3]}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            try:
                req = Request(url, headers={"User-Agent": "VisOPU/1.0"})
                data = urlopen(req, timeout=5).read()
                self._send(200, "image/png", data)
            except (URLError, OSError, Exception):
                try:
                    self.send_response(502)
                    self.end_headers()
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass
            return

        # Not found
        try:
            self.send_response(404)
            self.end_headers()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass


# ── Public API ──

class MBTilesServer:
    """Local HTTP server for offline map tiles.

    Parameters
    ----------
    mbtiles_dir : str
        Directory to search for *.mbtiles files.
        If a file is found, it is used for local tile serving.
    """

    def __init__(self, mbtiles_dir: str | None = None):
        self._mbtiles_dir = mbtiles_dir
        self._db: _MBTilesDB | None = None
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0
        self._has_mbtiles = False

    @property
    def port(self) -> int:
        return self._port

    @property
    def has_mbtiles(self) -> bool:
        return self._has_mbtiles

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def start(self) -> int:
        """Start the tile server in a daemon thread. Returns the port."""

        # Find MBTiles file
        if self._mbtiles_dir:
            pattern = os.path.join(self._mbtiles_dir, "*.mbtiles")
            files = glob.glob(pattern)
            if files:
                mbt_path = files[0]
                log.info(f"MBTiles found: {mbt_path}")
                self._db = _MBTilesDB(mbt_path)
                self._db.open()
                self._has_mbtiles = True

        # Build the map HTML
        if self._has_mbtiles:
            tile_url = f"http://127.0.0.1:{{port}}/tiles/{{z}}/{{x}}/{{y}}.png"
        else:
            tile_url = f"http://127.0.0.1:{{port}}/osm/{{z}}/{{x}}/{{y}}.png"

        # We need to know the port before building HTML, so use port 0
        # and build HTML after binding
        self._httpd = HTTPServer(("127.0.0.1", 0), _TileHandler)
        self._port = self._httpd.server_address[1]

        # Now build HTML with the actual port
        final_tile_url = tile_url.replace("{port}", str(self._port))
        html = _build_map_html(final_tile_url, self._has_mbtiles)

        _TileHandler.mbtiles_db = self._db
        _TileHandler.map_html = html

        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True, name="MBTilesServer")
        self._thread.start()
        log.info(f"MBTiles server started on port {self._port} "
                 f"({'offline MBTiles' if self._has_mbtiles else 'OSM proxy'})")
        return self._port

    def stop(self):
        """Stop the server."""
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
        if self._db:
            self._db.close()
            self._db = None
