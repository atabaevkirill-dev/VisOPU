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


def _build_map_html(tile_url: str, has_mbtiles: bool) -> str:
    """Build the MapLibre GL JS map with 3D buildings, compass rotation, and interactive beam."""

    return f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;overflow:hidden;background:#0a0a0a}}
#map{{width:100%;height:100%}}
.maplibregl-ctrl-group{{background:rgba(20,20,25,0.85)!important;border:1px solid rgba(80,80,85,0.5)!important;border-radius:8px!important;backdrop-filter:blur(10px)}}
.maplibregl-ctrl-group button{{width:29px!important;height:29px!important}}
.maplibregl-ctrl-group button+button{{border-top:1px solid rgba(80,80,85,0.3)!important}}
.maplibregl-ctrl-attrib{{display:none!important}}
.maplibregl-popup-content{{background:rgba(20,20,25,0.95)!important;color:#f5f5f7!important;border:1px solid rgba(10,132,255,0.4)!important;border-radius:8px!important;font:600 11px 'SF Pro Display',sans-serif!important;padding:8px 12px!important;backdrop-filter:blur(10px)}}
.maplibregl-popup-tip{{border-top-color:rgba(20,20,25,0.95)!important}}

/* Compass */
#compass{{position:absolute;top:14px;left:14px;width:56px;height:56px;z-index:10;cursor:pointer;pointer-events:auto}}
#compass svg{{width:100%;height:100%;filter:drop-shadow(0 2px 8px rgba(0,0,0,0.6))}}
#compass .ring{{fill:none;stroke:rgba(60,60,65,0.7);stroke-width:1.5}}
#compass .n{{fill:#ff453a}}
#compass .s{{fill:#636366}}
#compass .cap{{fill:#2c2c2e;stroke:#48484a;stroke-width:1}}
#compass .lbl{{fill:#98989d;font:700 9px 'SF Pro Display',sans-serif;text-anchor:middle}}

/* HUD */
#hud{{position:absolute;bottom:14px;left:50%;transform:translateX(-50%);
  background:rgba(14,14,16,0.94);border:1px solid rgba(10,132,255,0.4);
  border-radius:10px;padding:8px 20px;color:#f5f5f7;font:600 13px 'SF Pro Display',sans-serif;
  display:none;align-items:center;gap:12px;z-index:10;pointer-events:none;
  backdrop-filter:blur(12px);box-shadow:0 4px 24px rgba(0,0,0,0.5)}}
#hud.show{{display:flex}}
#hud .dist{{color:#0a84ff;font-size:16px;font-weight:700}}
#hud .brg{{color:#30d158;font-size:13px}}
#hud .unit{{color:#636366;font-size:11px}}
#hud .hint{{color:#98989d;font-size:10px}}

/* Beam info */
#beamInfo{{position:absolute;bottom:14px;left:14px;z-index:10;
  background:rgba(14,14,16,0.92);border:1px solid rgba(255,159,10,0.5);
  border-radius:8px;padding:6px 14px;color:#ff9f0a;font:600 12px 'SF Pro Display',sans-serif;
  pointer-events:none;display:none;backdrop-filter:blur(10px);
  box-shadow:0 2px 12px rgba(255,159,10,0.2)}}
#beamInfo.show{{display:block}}
#beamInfo .val{{font-size:16px;font-weight:700}}
#beamInfo .sep{{color:#636366;margin:0 6px}}
#beamInfo .len{{color:#bf5af2}}

/* Clear button */
#clearBtn{{position:absolute;top:14px;right:14px;z-index:10;
  background:rgba(14,14,16,0.92);border:1px solid rgba(80,80,85,0.5);
  border-radius:8px;padding:6px 16px;color:#98989d;font:600 10px 'SF Pro Display',sans-serif;
  cursor:pointer;letter-spacing:1px;display:none;backdrop-filter:blur(10px)}}
#clearBtn:hover{{background:rgba(40,40,45,0.95);color:#f5f5f7;border-color:#0a84ff}}
#clearBtn.show{{display:block}}

/* Mode indicator */
#modeInd{{position:absolute;top:14px;left:50%;transform:translateX(-50%);z-index:10;
  background:rgba(10,132,255,0.2);border:1px solid rgba(10,132,255,0.5);
  border-radius:6px;padding:4px 12px;color:#0a84ff;font:600 10px 'SF Pro Display',sans-serif;
  letter-spacing:1px;display:none;pointer-events:none;backdrop-filter:blur(8px)}}
#modeInd.show{{display:block}}

/* Offline fallback */
#offline{{position:absolute;inset:0;display:none;flex-direction:column;
  align-items:center;justify-content:center;color:#636366;
  font:600 14px 'SF Pro Display',sans-serif;background:#0a0a0a;z-index:20}}
#offline .icon{{font-size:48px;margin-bottom:12px;opacity:0.4}}
#offline .sub{{font-size:11px;color:#48484a;margin-top:6px}}

/* Beam drag cursor */
body.beam-drag{{cursor:grabbing!important}}
body.beam-hover{{cursor:grab!important}}
</style>
</head>
<body>
<div id="map"></div>

<!-- Compass rose -->
<div id="compass" title="Reset rotation">
<svg viewBox="0 0 56 56">
  <circle class="ring" cx="28" cy="28" r="26"/>
  <g id="compassNeedle">
    <polygon class="n" points="28,4 32,28 24,28"/>
    <polygon class="s" points="28,52 32,28 24,28"/>
  </g>
  <circle class="cap" cx="28" cy="28" r="5"/>
  <text class="lbl" x="28" y="16">N</text>
</svg>
</div>

<div id="hud">
  <span class="dist" id="distVal">0</span><span class="unit">m</span>
  <span class="brg" id="brgVal"></span>
  <span class="hint">LClick: measure | Shift+Drag: beam | RClick: device | DblClick: reset</span>
</div>
<button id="clearBtn" onclick="clearAll()">CLEAR</button>
<div id="beamInfo">
  BEAM <span class="val" id="beamAngle">0</span>&deg;
  <span class="sep">|</span>
  <span class="len" id="beamLen">3000</span>m
</div>
<div id="modeInd">BEAM CONTROL</div>
<div id="offline"><div class="icon">&#x1F5FA;</div>Map offline<div class="sub">No tiles available</div></div>

<script>
var map, devicePos=[55.751574,37.573856];
var beamOffset=0, beamLength=3000, currentPan=0, mapBearing=0;
var markers=[], points=[], totalDist=0, line=null, bearingLines=[];
var beamDrag=false, beamDragStart=null, beamOffsetStart=0;
var HAS_LOCAL_TILES={str(has_mbtiles).lower()};

// DOM
var hud=document.getElementById('hud'), distVal=document.getElementById('distVal');
var brgVal=document.getElementById('brgVal'), clearBtn=document.getElementById('clearBtn');
var beamInfo=document.getElementById('beamInfo'), beamAngleEl=document.getElementById('beamAngle');
var beamLenEl=document.getElementById('beamLen'), modeInd=document.getElementById('modeInd');
var compassEl=document.getElementById('compass'), compassNeedle=document.getElementById('compassNeedle');
var offlineDiv=document.getElementById('offline');

// ── Geometry helpers ──
function haversine(a,b){{
  var R=6371000,dLat=(b[0]-a[0])*Math.PI/180,dLon=(b[1]-a[1])*Math.PI/180;
  var la=a[0]*Math.PI/180,lb=b[0]*Math.PI/180;
  var x=Math.sin(dLat/2)**2+Math.cos(la)*Math.cos(lb)*Math.sin(dLon/2)**2;
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
  return [lo2*180/Math.PI,la2*180/Math.PI]; // [lng,lat] for GeoJSON
}}
function fmtDist(m){{return m>=1000?(m/1000).toFixed(2)+' km':m.toFixed(0)+' m'}}

// ── Compass rotation ──
function updateCompass(){{
  mapBearing=map.getBearing();
  compassNeedle.setAttribute('transform','rotate('+(-mapBearing)+',28,28)');
}}
compassEl.addEventListener('click',function(){{
  map.rotateTo(0,{{duration:600,easing:function(t){{return t<0.5?2*t*t:(4-2*t)*t-1}}}});
}});

// ── Beam source (GeoJSON) ──
var beamSource={{
  type:'FeatureCollection',
  features:[
    {{type:'Feature',id:'beamRay',properties:{{type:'ray'}},geometry:{{type:'LineString',coordinates:[[0,0],[0,0]]}}}},
    {{type:'Feature',id:'beamCone',properties:{{type:'cone'}},geometry:{{type:'Polygon',coordinates:[[[0,0],[0,0],[0,0],[0,0],[0,0]]]}}}},
    {{type:'Feature',id:'beamEnd',properties:{{type:'end'}},geometry:{{type:'Point',coordinates:[0,0]}}}},
    {{type:'Feature',id:'devicePt',properties:{{type:'device'}},geometry:{{type:'Point',coordinates:[0,0]}}}}
  ]
}};

function updateBeamSources(panDeg){{
  currentPan=panDeg;
  var bng=((panDeg+beamOffset)%360+360)%360;
  var ep=destPoint(devicePos[0],devicePos[1],bng,beamLength);
  var halfSpread=10;
  var b1=((bng-halfSpread)%360+360)%360;
  var b2=((bng+halfSpread)%360+360)%360;
  var ep1=destPoint(devicePos[0],devicePos[1],b1,beamLength*0.75);
  var ep2=destPoint(devicePos[0],devicePos[1],b2,beamLength*0.75);
  var dev=[devicePos[1],devicePos[0]]; // [lng,lat]
  beamSource.features[0].geometry.coordinates=[dev,ep];
  beamSource.features[1].geometry.coordinates=[[dev,ep1,ep,ep2,dev]];
  beamSource.features[2].geometry.coordinates=ep;
  beamSource.features[3].geometry.coordinates=dev;
  if(map&&map.getSource('beam')){{
    map.getSource('beam').setData(beamSource);
  }}
  beamAngleEl.textContent=bng.toFixed(0);
  beamLenEl.textContent=beamLength.toFixed(0);
  beamInfo.classList.add('show');
}}

// ── Python bridge ──
function pySetPan(deg){{updateBeamSources(parseFloat(deg))}}
function pySetDevicePos(lat,lng){{
  devicePos=[parseFloat(lat),parseFloat(lng)];
  if(map) map.flyTo({{center:[devicePos[1],devicePos[0]],zoom:map.getZoom(),duration:800}});
  updateBeamSources(currentPan);
}}
function pySetBeamOffset(deg){{beamOffset=parseFloat(deg);updateBeamSources(currentPan)}}
function pySetBeamLength(m){{beamLength=parseFloat(m);updateBeamSources(currentPan)}}
function pyApplyConfig(lat,lng,offset,length,pan){{
  devicePos=[parseFloat(lat),parseFloat(lng)];
  beamOffset=parseFloat(offset);beamLength=parseFloat(length);
  if(map) map.setCenter([devicePos[1],devicePos[0]]);
  updateBeamSources(parseFloat(pan));
}}

// ── Measurement ──
function addMeasurePoint(lnglat){{
  var pt=[lnglat.lat,lnglat.lng];
  if(points.length>0){{totalDist+=haversine(points[points.length-1],pt)}}
  points.push(pt);
  // Marker
  var el=document.createElement('div');
  el.style.cssText='width:12px;height:12px;border-radius:50%;background:#0a84ff;border:2px solid #fff;box-shadow:0 0 8px rgba(10,132,255,0.6)';
  var m=new maplibregl.Marker({{element:el}}).setLngLat(lnglat).addTo(map);
  markers.push(m);
  // Line
  if(line) line.remove();
  if(points.length>=2){{
    var coords=points.map(function(p){{return [p[1],p[0]]}});
    line={{remove:function(){{}}}};
    var src={{type:'Feature',geometry:{{type:'LineString',coordinates:coords}}}};
    if(map.getSource('measure'))map.getSource('measure').setData(src);
  }}
  // Bearing line
  var brg=bearing(devicePos,pt).toFixed(0);
  var distDev=haversine(devicePos,pt);
  updateHud();
}}
function clearAll(){{
  markers.forEach(function(m){{m.remove()}});
  markers=[];points=[];totalDist=0;
  if(line){{try{{map.removeLayer('measureLine');map.removeSource('measure')}}catch(e){{}}}}
  line=null;
  hud.classList.remove('show');clearBtn.classList.remove('show');
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

// ── Beam drag control ──
function getBeamEndLngLat(){{
  var bng=((currentPan+beamOffset)%360+360)%360;
  return destPoint(devicePos[0],devicePos[1],bng,beamLength);
}}
function isNearBeamEnd(lnglat){{
  var ep=getBeamEndLngLat();
  return haversine([lnglat.lat,lnglat.lng],[ep[1],ep[0]])<beamLength*0.15;
}}
function isNearBeamLine(lnglat){{
  var bng=((currentPan+beamOffset)%360+360)%360;
  var brgToMouse=bearing(devicePos,[lnglat.lat,lnglat.lng]);
  var distToMouse=haversine(devicePos,[lnglat.lat,lnglat.lng]);
  var angleDiff=Math.abs(((brgToMouse-bng+180)%360)-180);
  return distToMouse<=beamLength*1.1 && angleDiff<15;
}}

// Shift+drag to rotate beam
map.addEventListener&&(document.addEventListener('keydown',function(e){{if(e.key==='Shift')window._shiftDown=true}}));
document.addEventListener('keyup',function(e){{if(e.key==='Shift')window._shiftDown=false}});

// ── Init map ──
try {{
  map=new maplibregl.Map({{
    container:'map',
    style:{{
      version:8,
      name:'VisOPU Dark',
      sources:{{
        'raster-tiles':{{
          type:'raster',
          tiles:['{tile_url}'],
          tileSize:256,
          attribution:''
        }}
      }},
      layers:[
        {{id:'osm-tiles',type:'raster',source:'raster-tiles',paint:{{
          'raster-brightness-max':0.35,
          'raster-saturation':-0.6,
          'raster-contrast':0.1
        }}}}
      ],
      glyphs:'https://demotiles.maplibre.org/font/{{fontstack}}/{{range}}.pbf'
    }},
    center:[devicePos[1],devicePos[0]],
    zoom:14,
    pitch:0,
    bearing:0,
    maxPitch:60,
    attributionControl:false
  }});

  // Controls
  map.addControl(new maplibregl.NavigationControl({{showCompass:false}}), 'top-right');
  map.addControl(new maplibregl.ScaleControl({{maxWidth:120,unit:'metric'}}), 'bottom-right');

  // Rotation/bearing update
  map.on('rotate',updateCompass);
  map.on('pitch',function(){{}});  // pitch allowed

  map.on('load',function(){{
    // ── 3D Buildings (from OSM via Overpass, loaded as source) ──
    // We'll add building extrusion from a static GeoJSON layer
    // For now, add a procedural "building" effect using the map style
    // Add building footprint source (we'll generate some around device)
    map.addSource('beam',{{type:'geojson',data:beamSource}});
    map.addSource('buildings',{{type:'geojson',data:{{type:'FeatureCollection',features:[]}}}});

    // ── 3D Buildings layer ──
    map.addLayer({{
      id:'buildings-3d',
      type:'fill-extrusion',
      source:'buildings',
      paint:{{
        'fill-extrusion-color':['interpolate',['linear'],['get','height'],0,'#1a1a2e',50,'#16213e',100,'#0f3460'],
        'fill-extrusion-height':['get','height'],
        'fill-extrusion-base':0,
        'fill-extrusion-opacity':0.7
      }}
    }});

    // ── Measure line ──
    map.addSource('measure',{{type:'geojson',data:{{type:'Feature',geometry:{{type:'LineString',coordinates:[]}}}}}});
    map.addLayer({{id:'measureLine',type:'line',source:'measure',
      paint:{{'line-color':'#0a84ff','line-width':2.5,'line-dasharray':[2,2]}}}});

    // ── Beam cone (fill) ──
    map.addLayer({{
      id:'beamConeLayer',type:'fill',source:'beam',
      filter:['==',['get','type'],'cone'],
      paint:{{'fill-color':'#ff9f0a','fill-opacity':0.15}}
    }});

    // ── Beam ray (line) ──
    map.addLayer({{
      id:'beamRayLayer',type:'line',source:'beam',
      filter:['==',['get','type'],'ray'],
      paint:{{
        'line-color':'#ff9f0a',
        'line-width':2.5,
        'line-dasharray':[3,2],
        'line-opacity':0.9
      }}
    }});

    // ── Beam end dot ──
    map.addLayer({{
      id:'beamEndLayer',type:'circle',source:'beam',
      filter:['==',['get','type'],'end'],
      paint:{{
        'circle-radius':6,
        'circle-color':'#ff9f0a',
        'circle-stroke-color':'#fff',
        'circle-stroke-width':1.5,
        'circle-opacity':0.9
      }}
    }});

    // ── Device point ──
    map.addLayer({{
      id:'deviceLayer',type:'circle',source:'beam',
      filter:['==',['get','type'],'device'],
      paint:{{
        'circle-radius':8,
        'circle-color':'#ff453a',
        'circle-stroke-color':'#fff',
        'circle-stroke-width':2,
        'circle-opacity':1
      }}
    }});

    // ── Device label ──
    map.addLayer({{
      id:'deviceLabel',type:'symbol',source:'beam',
      filter:['==',['get','type'],'device'],
      layout:{{
        'text-field':'DEVICE',
        'text-offset':[0,-1.8],
        'text-size':10,
        'text-font':['Open Sans Bold']
      }},
      paint:{{'text-color':'#ff453a','text-halo-color':'#0a0a0a','text-halo-width':1}}
    }});

    // ── Load OSM buildings around device ──
    loadBuildings();

    updateBeamSources(0);
    updateCompass();
  }});

  // ── Click: measure or beam drag ──
  var _dragStart=null,_dragOffsetStart=0,_dragLengthStart=0;

  map.on('mousedown',function(e){{
    if(e.originalEvent.shiftKey){{
      // Beam control mode
      _dragStart={{x:e.point.x,y:e.point.y}};
      _dragOffsetStart=beamOffset;
      _dragLengthStart=beamLength;
      beamDrag=true;
      map.getCanvas().style.cursor='grabbing';
      modeInd.classList.add('show');
      e.preventDefault();
    }}
  }});

  map.on('mousemove',function(e){{
    if(beamDrag && _dragStart){{
      var dx=e.point.x-_dragStart.x;
      var dy=e.point.y-_dragStart.y;
      // Horizontal drag = rotate beam (1px = 0.5 degrees)
      beamOffset=_dragOffsetStart+dx*0.5;
      beamOffset=((beamOffset%360)+360)%360;
      // Vertical drag = change length (1px = 5 meters)
      beamLength=Math.max(100,_dragLengthStart-dy*5);
      updateBeamSources(currentPan);
    }} else if(!beamDrag){{
      // Hover effect near beam
      var near=isNearBeamLine([e.lngLat.lat,e.lngLat.lng]);
      map.getCanvas().style.cursor=near?'grab':'';
    }}
  }});

  map.on('mouseup',function(e){{
    if(beamDrag){{
      beamDrag=false;
      _dragStart=null;
      map.getCanvas().style.cursor='';
      modeInd.classList.remove('show');
      // Emit to Python
      window.pyBeamChanged&&window.pyBeamChanged(beamOffset,beamLength);
    }}
  }});

  map.on('click',function(e){{
    if(!e.originalEvent.shiftKey && !beamDrag){{
      addMeasurePoint(e.lngLat);
    }}
  }});

  // Right-click: set device position
  map.on('contextmenu',function(e){{
    e.preventDefault();
    devicePos=[e.lngLat.lat,e.lngLat.lng];
    updateBeamSources(currentPan);
  }});

  // Double-click: reset view
  map.doubleClickZoom.disable();
  map.on('dblclick',function(e){{
    e.preventDefault();
    map.flyTo({{center:[devicePos[1],devicePos[0]],zoom:14,bearing:0,pitch:0,duration:1000}});
  }});

  // Scroll on beam: change length
  map.getCanvas().addEventListener('wheel',function(e){{
    if(e.shiftKey){{
      e.preventDefault();
      beamLength=Math.max(100,beamLength-e.deltaY*2);
      updateBeamSources(currentPan);
    }}
  }},{{passive:false}});

  // ── Load buildings from OSM Overpass ──
  function loadBuildings(){{
    var lat=devicePos[0],lng=devicePos[1];
    var delta=0.008; // ~800m
    var bbox=(lat-delta)+','+(lng-delta)+','+(lat+delta)+','+(lng+delta);
    var query='[out:json][timeout:10];(way["building"]('+bbox+'));out body geom;';
    var url='https://overpass-api.de/api/interpreter?data='+encodeURIComponent(query);
    fetch(url).then(function(r){{return r.json()}}).then(function(data){{
      var features=[];
      (data.elements||[]).forEach(function(el){{
        if(!el.geometry||el.geometry.length<3) return;
        var coords=el.geometry.map(function(g){{return [g.lon,g.lat]}});
        coords.push(coords[0]); // close ring
        var height=parseInt(el.tags&&el.tags['building:levels']||'4')*3;
        if(el.tags&&el.tags.height) height=parseFloat(el.tags.height)||height;
        features.push({{
          type:'Feature',
          properties:{{height:Math.min(height,200),name:el.tags&&el.tags.name||''}},
          geometry:{{type:'Polygon',coordinates:[coords]}}
        }});
      }});
      if(features.length>0 && map.getSource('buildings')){{
        map.getSource('buildings').setData({{type:'FeatureCollection',features:features}});
      }}
    }}).catch(function(e){{console.log('Buildings load failed:',e)}});
  }}

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
