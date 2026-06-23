import os
import streamlit as st
import json
import time
import math
import threading
from datetime import datetime, timezone
import requests
import websocket
import folium
from streamlit_folium import st_folium
from google import genai
from dotenv import load_dotenv

# ── Env ───────────────────────────────────────────────────────────────────────
load_dotenv()
OPENSKY_CLIENT_ID     = os.environ.get("OPENSKY_CLIENT_ID", "")
OPENSKY_CLIENT_SECRET = os.environ.get("OPENSKY_CLIENT_SECRET", "")
AISSTREAM_API_KEY     = os.environ.get("AISSTREAM_API_KEY", "")
GEMINI_API_KEY        = os.environ.get("GEMINI_API_KEY", "")

# ── WHTC bounding box ─────────────────────────────────────────────────────────
WHTC_BBOX = {"lat_min": 5.0, "lon_min": -100.0, "lat_max": 35.0, "lon_max": -55.0}
WHTC_LIST = [5.0, -100.0, 35.0, -55.0]
WHTC_ZONES = {
    "Gulf of Mexico":   dict(lat_min=18.0, lon_min=-98.0, lat_max=30.5, lon_max=-80.5),
    "Caribbean Sea":    dict(lat_min= 9.0, lon_min=-85.0, lat_max=22.0, lon_max=-60.0),
    "Florida Straits":  dict(lat_min=23.5, lon_min=-82.0, lat_max=26.5, lon_max=-79.0),
    "Windward Passage": dict(lat_min=19.5, lon_min=-75.0, lat_max=21.0, lon_max=-73.0),
    "Mona Passage":     dict(lat_min=17.8, lon_min=-68.5, lat_max=19.0, lon_max=-67.0),
    "Yucatan Channel":  dict(lat_min=20.5, lon_min=-88.0, lat_max=22.5, lon_max=-85.5),
}

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Movement Summarizer", page_icon="🛰️",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
  html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
  .stApp { background: #0a0e1a; color: #c8d6e5; }
  [data-testid="stSidebar"] { background: #0d1220 !important; border-right: 1px solid #1e2d45; }
  .brand-header { display:flex; align-items:center; gap:12px; padding:0 0 20px 0; border-bottom:1px solid #1e2d45; margin-bottom:20px; }
  .brand-icon { font-size:28px; }
  .brand-title { font-size:20px; font-weight:700; color:#e8f4fd; letter-spacing:-0.3px; }
  .brand-sub { font-size:11px; color:#4a6580; text-transform:uppercase; letter-spacing:1.5px; }
  .stat-card { background:#111827; border:1px solid #1e2d45; border-radius:8px; padding:16px; margin-bottom:10px; }
  .stat-label { font-size:10px; color:#4a6580; text-transform:uppercase; letter-spacing:1.5px; margin-bottom:4px; }
  .stat-value { font-size:22px; font-weight:700; color:#38bdf8; font-family:'JetBrains Mono',monospace; }
  .stat-unit { font-size:11px; color:#4a6580; margin-left:4px; }
  .brief-box { background:#0d1a2a; border:1px solid #1e3a5a; border-left:3px solid #38bdf8; border-radius:0 8px 8px 0; padding:18px 20px; font-size:14px; line-height:1.7; color:#c8d6e5; margin-top:12px; }
  .section-label { font-size:10px; color:#38bdf8; text-transform:uppercase; letter-spacing:2px; margin-bottom:8px; font-weight:600; }
  .live-dot { display:inline-block; width:8px; height:8px; background:#22c55e; border-radius:50%; animation:pulse 1.5s infinite; margin-right:6px; }
  @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.5;transform:scale(0.8)} }
  .status-bar { background:#111827; border:1px solid #1e2d45; border-radius:6px; padding:8px 12px; font-size:11px; color:#4a6580; font-family:'JetBrains Mono',monospace; margin-bottom:12px; }
  hr { border-color:#1e2d45 !important; }
  .track-point { display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid #1a2535; font-size:11px; font-family:'JetBrains Mono',monospace; color:#6b8aad; }
  .track-point:last-child { border-bottom:none; }
  .track-dot { width:6px; height:6px; border-radius:50%; flex-shrink:0; }

  /* Vessel list buttons */
  div[data-testid="stButton"] button {
    background: #0c1929 !important;
    border: 1px solid #1e3a5a !important;
    color: #6b8aad !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    font-weight: 400 !important;
    border-radius: 5px !important;
    text-align: left !important;
    transition: all 0.15s !important;
  }
  div[data-testid="stButton"] button:hover {
    background: #0f2033 !important;
    border-color: #2d5f80 !important;
    color: #a8c4d8 !important;
  }
  /* Selected vessel button — bright blue outline */
  div[data-testid="stButton"].selected-vessel button {
    background: #0c2d4a !important;
    border: 2px solid #38bdf8 !important;
    color: #e0f2fe !important;
    font-weight: 600 !important;
  }
  /* Action buttons (generate brief, refresh) */
  div[data-testid="stButton"].action-btn button {
    background: #0c4a6e !important;
    border: 1px solid #0ea5e9 !important;
    color: #7dd3fc !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 13px !important;
    font-weight: 500 !important;
  }
  div[data-testid="stButton"].action-btn button:hover {
    background: #0369a1 !important;
    color: #e0f2fe !important;
  }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
def init_state():
    for k, v in {
        "vessels": {},
        "selected_id": None,
        "briefs": {},
        "last_refresh": None,
        "ais_collecting": False,
        "ais_end_time": None,
        "ais_ship_count": 0,
        "ais_started": False,
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ── Helpers ───────────────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def compute_track_stats(vessel):
    track = vessel.get("track", [])
    if len(track) < 2:
        return {}
    dist   = sum(haversine(track[i][0], track[i][1], track[i+1][0], track[i+1][1])
                 for i in range(len(track)-1))
    speeds = [p[3] for p in track if p[3] is not None and p[3] >= 0]
    dur    = track[-1][2] - track[0][2]
    return {
        "total_distance_km": round(dist, 1),
        "avg_speed":  round(sum(speeds)/len(speeds), 1) if speeds else 0,
        "max_speed":  round(max(speeds), 1) if speeds else 0,
        "duration_minutes": round(dur / 60, 0),
    }

# ── OpenSky OAuth2 token ──────────────────────────────────────────────────────
def _get_opensky_token():
    r = requests.post(
        "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
        data={"grant_type": "client_credentials",
              "client_id": OPENSKY_CLIENT_ID,
              "client_secret": OPENSKY_CLIENT_SECRET},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]

def _opensky_headers():
    if OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET:
        return {"Authorization": f"Bearer {_get_opensky_token()}"}
    return {}

# ── Fetch flight track from OpenSky (/tracks/all) ────────────────────────────
def fetch_flight_track(icao24, headers):
    """Return list of (lat, lon, timestamp, speed_kt) for this flight since takeoff."""
    try:
        now  = int(time.time())
        # OpenSky track endpoint — time=0 means most recent flight
        r = requests.get(
            "https://opensky-network.org/api/tracks/all",
            params={"icao24": icao24, "time": 0},
            headers=headers,
            timeout=10,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        path = data.get("path", [])   # [[time, lat, lon, alt, heading, on_ground], ...]
        if not path:
            return []
        track = []
        for pt in path:
            if pt[1] is None or pt[2] is None:
                continue
            ts  = pt[0]
            lat = pt[1]
            lon = pt[2]
            # speed not in track endpoint — we'll store 0, filled from states later
            track.append((lat, lon, ts, 0.0))
        return track
    except Exception:
        return []

# ── Fetch all aircraft in WHTC + their flight paths ──────────────────────────
def fetch_opensky():
    try:
        headers = _opensky_headers()
        params  = {
            "lamin": WHTC_LIST[0], "lomin": WHTC_LIST[1],
            "lamax": WHTC_LIST[2], "lomax": WHTC_LIST[3],
        }
        r = requests.get("https://opensky-network.org/api/states/all",
                         params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            return {}

        states   = (r.json().get("states") or [])[:40]
        vessels  = {}

        for s in states:
            if s[5] is None or s[6] is None:
                continue
            icao = s[0]
            vid  = f"plane_{icao}"
            spd  = round((s[9] or 0) * 1.944, 1)   # m/s → kt
            ts   = s[3] or time.time()
            name = (s[1] or icao).strip() or icao

            # Fetch full flight track for this aircraft
            track = fetch_flight_track(icao, headers)

            # If track came back, update the last point's speed with current speed
            if track:
                last = track[-1]
                track[-1] = (last[0], last[1], last[2], spd)
            else:
                # Fallback: single point at current position
                track = [(s[6], s[5], ts, spd)]

            vessels[vid] = {
                "id": vid, "type": "plane",
                "name": name,
                "callsign": name,
                "icao24": icao,
                "lat": s[6], "lon": s[5],
                "altitude": s[7] or 0,
                "speed": spd,
                "course": round(s[10] or 0, 1),
                "vertical_rate": s[11] or 0,
                "origin_country": s[2],
                "timestamp": ts,
                "track": track,
            }
        return vessels
    except Exception as e:
        st.warning(f"OpenSky error: {e}")
        return {}

# ── AISStream — background WebSocket, runs indefinitely until stopped ─────────
def start_aisstream():
    """Start AIS collection in a daemon thread. Runs until app exits or key missing."""
    if st.session_state.ais_started:
        return   # already running
    if not AISSTREAM_API_KEY:
        return

    st.session_state.ais_collecting = True
    st.session_state.ais_started    = True

    def run():
        subscribe = {
            "APIKey": AISSTREAM_API_KEY,
            "BoundingBoxes": [[[WHTC_LIST[0], WHTC_LIST[1]],
                                [WHTC_LIST[2], WHTC_LIST[3]]]],
            "FilterMessageTypes": ["PositionReport"],
        }

        def on_message(ws, message):
            try:
                msg  = json.loads(message)
                meta = msg.get("MetaData", {})
                pos  = msg.get("Message", {}).get("PositionReport", {})
                if not pos:
                    return
                mmsi = str(meta.get("MMSI", ""))
                vid  = f"ship_{mmsi}"
                lat, lon = pos.get("Latitude", 0), pos.get("Longitude", 0)
                spd, cog = pos.get("Sog", 0), pos.get("Cog", 0)
                name = meta.get("ShipName", mmsi).strip() or mmsi
                ts   = time.time()

                existing = st.session_state.vessels.get(vid, {})
                track    = list(existing.get("track", []))
                track.append((lat, lon, ts, spd))
                if len(track) > 200:
                    track = track[-200:]

                st.session_state.vessels[vid] = {
                    "id": vid, "type": "ship", "name": name,
                    "lat": lat, "lon": lon, "speed": spd, "course": cog,
                    "mmsi": mmsi, "flag": meta.get("flag", "?"),
                    "destination": meta.get("Destination", "Unknown"),
                    "timestamp": ts, "track": track,
                }
                st.session_state.ais_ship_count = sum(
                    1 for v in st.session_state.vessels.values() if v["type"] == "ship"
                )
            except Exception:
                pass

        def on_error(ws, error):
            st.session_state.ais_collecting = False
            st.session_state.ais_started    = False

        def on_close(ws, *args):
            st.session_state.ais_collecting = False
            st.session_state.ais_started    = False

        def on_open(ws):
            ws.send(json.dumps(subscribe))

        try:
            websocket.WebSocketApp(
                "wss://stream.aisstream.io/v0/stream",
                on_message=on_message, on_error=on_error,
                on_close=on_close, on_open=on_open,
            ).run_forever()
        except Exception:
            st.session_state.ais_collecting = False
            st.session_state.ais_started    = False

    threading.Thread(target=run, daemon=True).start()

# ── Gemini brief ──────────────────────────────────────────────────────────────
def build_prompt(vessel, stats):
    v     = vessel
    vtype = "ship" if v["type"] == "ship" else "aircraft"
    name  = v.get("name", v.get("callsign", "Unknown"))
    su    = "kn" if v["type"] == "ship" else "kt"
    track_desc = ""
    for i, pt in enumerate(v.get("track", []), 1):
        ts_str = datetime.fromtimestamp(pt[2], tz=timezone.utc).strftime("%H:%M:%S UTC")
        track_desc += f"  {i}. {ts_str} — lat {pt[0]:.3f}, lon {pt[1]:.3f}, speed {pt[3]:.1f} {su}\n"
    extras = (
        f"Flag: {v.get('flag','?')} | MMSI: {v.get('mmsi','?')} | Destination: {v.get('destination','Unknown')}"
        if v["type"] == "ship" else
        f"ICAO24: {v.get('icao24','?')} | Country: {v.get('origin_country','?')} | "
        f"Altitude: {v.get('altitude',0):,} m | Vertical rate: {v.get('vertical_rate',0):.1f} m/s"
    )
    return f"""You are an intelligence analyst writing a movement brief for an operations room.

VESSEL TYPE: {vtype.upper()}
IDENTIFIER: {name}
{extras}
CURRENT POSITION: {v['lat']:.4f}°, {v['lon']:.4f}°
CURRENT SPEED: {v['speed']} {su} | COURSE: {v['course']}°
DATA WINDOW: {stats.get('duration_minutes',0):.0f} min | DISTANCE: {stats.get('total_distance_km',0)} km | AVG SPEED: {stats.get('avg_speed',0)} {su}
TRACK HISTORY:
{track_desc}
Write a concise plain-language movement brief (3-5 sentences) for an ops briefing. Cover where it went and when, any speed changes or stops (speed < 1 = stopped), current status and trajectory, anything operationally noteworthy. Single paragraph, no headers, no bullets. Professional tone. Be specific — compass directions and times."""

def fetch_brief(vessel, stats):
    if not GEMINI_API_KEY:
        return "⚠ GEMINI_API_KEY not set in .env"
    try:
        client   = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=build_prompt(vessel, stats),
        )
        return response.text.strip()
    except Exception as e:
        return f"⚠ Brief generation failed: {e}"

# ── Map ───────────────────────────────────────────────────────────────────────
def build_map(vessels, selected_id=None):
    if vessels:
        lats   = [v["lat"] for v in vessels.values()]
        lons   = [v["lon"] for v in vessels.values()]
        center = [sum(lats)/len(lats), sum(lons)/len(lons)]
        zoom   = 4
    else:
        center, zoom = [20.0, -77.5], 4

    m = folium.Map(location=center, zoom_start=zoom,
                   tiles="CartoDB dark_matter", prefer_canvas=True)

    # WHTC boundary
    folium.Rectangle(
        bounds=[[WHTC_BBOX["lat_min"], WHTC_BBOX["lon_min"]],
                [WHTC_BBOX["lat_max"], WHTC_BBOX["lon_max"]]],
        color="#1e4d6b", weight=1.5, fill=True,
        fill_color="#0a2035", fill_opacity=0.18, dash_array="6 4",
        tooltip="Western Hemisphere Transit Corridor  |  5°N–35°N · 100°W–55°W"
    ).add_to(m)

    zone_color = {
        "Gulf of Mexico": "#0369a1", "Caribbean Sea": "#0c4a6e",
        "Florida Straits": "#075985", "Windward Passage": "#0e4d6e",
        "Mona Passage": "#0e4d6e", "Yucatan Channel": "#0e4d6e",
    }
    for zname, zb in WHTC_ZONES.items():
        folium.Rectangle(
            bounds=[[zb["lat_min"], zb["lon_min"]], [zb["lat_max"], zb["lon_max"]]],
            color=zone_color.get(zname, "#1e4d6b"), weight=1,
            fill=False, opacity=0.45, tooltip=zname,
        ).add_to(m)
        folium.Marker(
            location=[zb["lat_max"] - 0.3, zb["lon_min"] + 0.4],
            icon=folium.DivIcon(
                html=f'<div style="font-size:9px;color:#1e6a9e;white-space:nowrap;'
                     f'font-family:JetBrains Mono,monospace;letter-spacing:0.5px;'
                     f'text-shadow:0 0 4px #000,0 0 8px #000;pointer-events:none;">'
                     f'{zname.upper()}</div>',
                icon_size=(180, 14), icon_anchor=(0, 14),
            )
        ).add_to(m)

    folium.Marker(
        location=[34.2, -99.0],
        icon=folium.DivIcon(
            html='<div style="font-size:10px;color:#38bdf8;white-space:nowrap;'
                 'font-family:JetBrains Mono,monospace;letter-spacing:1px;font-weight:600;'
                 'text-shadow:0 0 6px #000,0 0 12px #000;pointer-events:none;">◈ WHTC</div>',
            icon_size=(100, 16), icon_anchor=(0, 16),
        )
    ).add_to(m)

    # Vessels + flight/ship paths
    for vid, v in vessels.items():
        is_ship = v["type"] == "ship"
        is_sel  = vid == selected_id
        color   = "#0ea5e9" if is_ship else "#f59e0b"
        sel_col = "#38bdf8" if is_ship else "#fcd34d"
        icon_ch = "⚓" if is_ship else "✈"
        size    = 20 if is_sel else 14
        border  = f"2px solid {sel_col}" if is_sel else f"1px solid {color}"
        bg      = "rgba(56,189,248,0.15)" if is_sel else "rgba(0,0,0,0.7)"

        track = v.get("track", [])
        if len(track) >= 2:
            # Draw full path as a solid line
            coords = [(p[0], p[1]) for p in track]
            folium.PolyLine(
                coords,
                color=sel_col if is_sel else color,
                weight=2.5 if is_sel else 1.5,
                opacity=0.9 if is_sel else 0.5,
            ).add_to(m)
            # Mark takeoff / departure point with a small dot
            folium.CircleMarker(
                location=coords[0],
                radius=4,
                color=color, fill=True, fill_color=color, fill_opacity=0.8,
                tooltip=f"{'Departure' if not is_ship else 'First ping'} — {datetime.fromtimestamp(track[0][2], tz=timezone.utc).strftime('%H:%M UTC')}",
            ).add_to(m)

        su = "kn" if is_ship else "kt"
        alt_line = f"<br>Alt: {v.get('altitude',0):,.0f} m" if not is_ship else ""
        dest_line = f"<br>→ {v.get('destination','?')}" if is_ship else ""
        popup_html = (
            f"<div style='font-family:monospace;font-size:12px;color:#1e293b;min-width:180px'>"
            f"<b style='color:#0c4a6e;font-size:13px'>{v.get('name', vid)}</b><br>"
            f"{'MMSI: '+v.get('mmsi','?') if is_ship else 'ICAO: '+v.get('icao24','?')}<br>"
            f"Spd: {v['speed']} {su} | Hdg: {v['course']}°{alt_line}{dest_line}<br>"
            f"Track pts: {len(track)}<br>"
            f"<small style='color:#64748b'>Select from list for full brief →</small></div>"
        )

        folium.Marker(
            location=[v["lat"], v["lon"]],
            icon=folium.DivIcon(
                html=f'<div style="font-size:{size}px;border:{border};border-radius:50%;'
                     f'background:{bg};width:{size+10}px;height:{size+10}px;'
                     f'display:flex;align-items:center;justify-content:center;cursor:pointer;">'
                     f'{icon_ch}</div>',
                icon_size=(size+10, size+10), icon_anchor=((size+10)//2, (size+10)//2),
            ),
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"{v.get('name', vid)} | {v['speed']} {su} | {len(track)} pts",
        ).add_to(m)

    return m

# ── Start AIS in background immediately on app load ───────────────────────────
start_aisstream()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="brand-header">
      <div class="brand-icon">🛰️</div>
      <div>
        <div class="brand-title">Movement Summarizer</div>
        <div class="brand-sub">Maritime & Aviation Intel</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-label">Data</div>', unsafe_allow_html=True)
    st.selectbox("", ["OpenSky (Live)"], label_visibility="collapsed", key="datasource_sel")

    # AIS live status
    if st.session_state.ais_collecting:
        n_ships = st.session_state.ais_ship_count
        st.markdown(
            f'<div style="background:#0c1929;border:1px solid #1e3a5a;border-left:3px solid #22c55e;'
            f'border-radius:0 6px 6px 0;padding:8px 12px;margin-top:8px;">'
            f'<div style="font-size:10px;color:#86efac;font-family:JetBrains Mono,monospace;">'
            f'<span style="display:inline-block;width:6px;height:6px;background:#22c55e;border-radius:50%;'
            f'margin-right:5px;animation:pulse 1.5s infinite;"></span>'
            f'AIS LIVE · {n_ships} ships</div></div>',
            unsafe_allow_html=True
        )
    elif AISSTREAM_API_KEY:
        st.markdown(
            '<div style="background:#0c1929;border:1px solid #2d1a1a;border-left:3px solid #ef4444;'
            'border-radius:0 6px 6px 0;padding:8px 12px;margin-top:8px;">'
            '<div style="font-size:10px;color:#fca5a5;font-family:JetBrains Mono,monospace;">'
            'AIS DISCONNECTED</div></div>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # Coverage zone
    st.markdown('<div class="section-label">🌐 Coverage Zone</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="background:#0c1929;border:1px solid #1e3a5a;border-left:3px solid #38bdf8;
         border-radius:0 6px 6px 0;padding:10px 12px;margin-bottom:10px;">
      <div style="font-size:12px;font-weight:600;color:#7dd3fc;margin-bottom:6px;">WESTERN HEMISPHERE TRANSIT CORRIDOR</div>
      <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#4a8ab5;line-height:1.8">
        Lat 5.0°N → 35.0°N<br>Lon 100.0°W → 55.0°W<br>
        <span style="color:#2d5f80">─────────────────────</span><br>
        Gulf of Mexico · Caribbean Sea<br>
        Florida Straits · Windward Passage<br>
        Mona Passage · Yucatan Channel
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    if st.button("🔄  Fetch / Refresh OpenSky", use_container_width=True, key="fetch_btn_sidebar"):
        st.session_state["do_fetch"] = True

    if st.session_state.last_refresh:
        elapsed = int(time.time() - st.session_state.last_refresh)
        n_total = len(st.session_state.vessels)
        st.markdown(
            f'<div class="status-bar">Last fetch: {elapsed}s ago · {n_total} vessels loaded</div>',
            unsafe_allow_html=True
        )

# ── OpenSky fetch on button press ────────────────────────────────────────────
if st.session_state.get("do_fetch"):
    st.session_state["do_fetch"] = False
    with st.spinner("Fetching live aircraft + flight tracks from OpenSky…"):
        sky = fetch_opensky()
        if sky:
            st.session_state.vessels.update(sky)
        st.session_state.last_refresh = time.time()
    st.rerun()

# Schedule a rerun in 5s while AIS is collecting — use st.empty placeholder
# so we never block the render with sleep()
if st.session_state.ais_collecting:
    import threading as _t
    def _deferred_rerun():
        time.sleep(5)
        st.rerun()
    _t.Thread(target=_deferred_rerun, daemon=True).start()

# ── Main layout ───────────────────────────────────────────────────────────────
left_col, right_col = st.columns([3, 2], gap="medium")

with left_col:
    n_ships  = sum(1 for v in st.session_state.vessels.values() if v["type"] == "ship")
    n_planes = sum(1 for v in st.session_state.vessels.values() if v["type"] == "plane")
    ais_note = (' · <span style="color:#86efac">⬤ AIS live</span>'
                if st.session_state.ais_collecting else "")
    st.markdown(
        f'<div class="status-bar"><span class="live-dot"></span>'
        f'{n_ships} ships ⚓ · {n_planes} aircraft ✈{ais_note}</div>',
        unsafe_allow_html=True
    )

    if not st.session_state.vessels:
        st.markdown(
            '<div class="brief-box" style="color:#2d4a6a;font-style:italic;margin-top:20px;">'
            'Ships from AISStream will appear automatically as pings arrive.<br><br>'
            'Hit <b style="color:#38bdf8">Fetch / Refresh OpenSky</b> in the sidebar to load aircraft.'
            '</div>', unsafe_allow_html=True
        )
    else:
        m = build_map(st.session_state.vessels, st.session_state.selected_id)
        map_data = st_folium(m, height=520, use_container_width=True,
                             returned_objects=["last_object_clicked_tooltip"])

        if map_data and map_data.get("last_object_clicked_tooltip"):
            tip = map_data["last_object_clicked_tooltip"]
            for vid, v in st.session_state.vessels.items():
                name = v.get("name", v.get("callsign", vid))
                if name in tip and st.session_state.selected_id != vid:
                    st.session_state.selected_id = vid
                    st.rerun()

with right_col:

    # ── Detail panel FIRST — above the list ──────────────────────────────────
    if st.session_state.selected_id and st.session_state.selected_id in st.session_state.vessels:
        sel     = st.session_state.vessels[st.session_state.selected_id]
        stats   = compute_track_stats(sel)
        is_ship = sel["type"] == "ship"
        su      = "kn" if is_ship else "kt"

        st.markdown(
            f'<div style="background:#0c1929;border:1px solid #38bdf8;border-radius:8px;'
            f'padding:12px 14px;margin-bottom:12px;">'
            f'<div style="font-size:10px;color:#38bdf8;text-transform:uppercase;letter-spacing:2px;'
            f'font-weight:600;margin-bottom:2px;">Selected</div>'
            f'<div style="font-size:16px;font-weight:700;color:#e0f2fe;">'
            f'{"⚓" if is_ship else "✈"} {sel.get("name","?")}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="stat-card"><div class="stat-label">Speed</div>'
                        f'<div class="stat-value">{sel["speed"]}<span class="stat-unit">{su}</span></div></div>',
                        unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="stat-card"><div class="stat-label">Course</div>'
                        f'<div class="stat-value">{sel["course"]}<span class="stat-unit">°</span></div></div>',
                        unsafe_allow_html=True)
        with c3:
            if is_ship:
                st.markdown(f'<div class="stat-card"><div class="stat-label">Destination</div>'
                            f'<div class="stat-value" style="font-size:14px">{sel.get("destination","?")[:9]}</div></div>',
                            unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="stat-card"><div class="stat-label">Altitude</div>'
                            f'<div class="stat-value">{sel.get("altitude",0):,.0f}<span class="stat-unit">m</span></div></div>',
                            unsafe_allow_html=True)

        if stats:
            s1, s2 = st.columns(2)
            with s1:
                st.markdown(f'<div class="stat-card"><div class="stat-label">Distance</div>'
                            f'<div class="stat-value">{stats["total_distance_km"]}<span class="stat-unit">km</span></div></div>',
                            unsafe_allow_html=True)
            with s2:
                st.markdown(f'<div class="stat-card"><div class="stat-label">Track Window</div>'
                            f'<div class="stat-value">{int(stats["duration_minutes"])}<span class="stat-unit">min</span></div></div>',
                            unsafe_allow_html=True)

        st.markdown('<div class="section-label" style="margin-top:4px;">AI Movement Brief</div>',
                    unsafe_allow_html=True)

        vid            = st.session_state.selected_id
        existing_brief = st.session_state.briefs.get(vid)

        cb1, cb2 = st.columns([2, 1])
        with cb1:
            gen_btn = st.button("⚡ Generate Brief", key="gen_brief", use_container_width=True)
        with cb2:
            if existing_brief and st.button("✕ Clear", key="clear_brief", use_container_width=True):
                del st.session_state.briefs[vid]
                st.rerun()

        if gen_btn:
            if not GEMINI_API_KEY:
                st.error("GEMINI_API_KEY not set in .env")
            else:
                with st.spinner("Generating brief via Gemini 3.5 Flash…"):
                    st.session_state.briefs[vid] = fetch_brief(sel, stats)
                    st.rerun()

        if existing_brief:
            st.markdown(f'<div class="brief-box">{existing_brief}</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="brief-box" style="color:#2d4a6a;font-style:italic;">'
                'Click Generate Brief for an AI analyst summary of this vessel\'s movement.</div>',
                unsafe_allow_html=True
            )

        if sel.get("track") and len(sel["track"]) > 1:
            with st.expander(f"Track Log — {len(sel['track'])} points", expanded=False):
                track_html = ""
                pts = sel["track"][-12:]
                for i, pt in enumerate(pts):
                    ts_str = datetime.fromtimestamp(pt[2], tz=timezone.utc).strftime("%H:%M:%S")
                    alpha  = 0.35 + 0.65 * (i / max(len(pts) - 1, 1))
                    color  = f"rgba(56,189,248,{alpha:.2f})"
                    track_html += (
                        f'<div class="track-point">'
                        f'<div class="track-dot" style="background:{color}"></div>'
                        f'<span style="color:#38bdf8;min-width:70px">{ts_str} UTC</span>'
                        f'<span>{pt[0]:.3f}°, {pt[1]:.3f}°</span>'
                        f'<span style="margin-left:auto">{pt[3]:.1f} {su}</span>'
                        f'</div>'
                    )
                st.markdown(track_html, unsafe_allow_html=True)

        st.markdown("---")
    else:
        st.markdown(
            '<div class="brief-box" style="color:#2d4a6a;font-style:italic;margin-bottom:12px;">'
            'Select a vessel from the list below or click one on the map to view movement data.</div>',
            unsafe_allow_html=True
        )

    # ── Vessel list BELOW the detail panel ───────────────────────────────────
    ships  = {k: v for k, v in st.session_state.vessels.items() if v["type"] == "ship"}
    planes = {k: v for k, v in st.session_state.vessels.items() if v["type"] == "plane"}

    if planes:
        st.markdown('<div style="font-size:11px;font-weight:600;color:#f59e0b;letter-spacing:1px;margin-bottom:6px;">✈ AIRCRAFT</div>',
                    unsafe_allow_html=True)
        for vid, v in planes.items():
            is_sel  = vid == st.session_state.selected_id
            n_pts   = len(v.get("track", []))
            label   = f"{'● ' if is_sel else '  '}{v['name']}  {v['speed']} kt  {n_pts}pts"
            # Inject a wrapper div with a class so CSS can target selected state
            if is_sel:
                st.markdown('<div class="selected-vessel">', unsafe_allow_html=True)
            if st.button(label, key=f"btn_{vid}", use_container_width=True):
                st.session_state.selected_id = vid
                st.rerun()
            if is_sel:
                st.markdown('</div>', unsafe_allow_html=True)

    if ships:
        st.markdown('<div style="font-size:11px;font-weight:600;color:#0ea5e9;letter-spacing:1px;margin-top:10px;margin-bottom:6px;">⚓ SHIPS</div>',
                    unsafe_allow_html=True)
        for vid, v in ships.items():
            is_sel = vid == st.session_state.selected_id
            n_pts  = len(v.get("track", []))
            label  = f"{'● ' if is_sel else '  '}{v['name']}  {v['speed']} kn  {n_pts}pts"
            if is_sel:
                st.markdown('<div class="selected-vessel">', unsafe_allow_html=True)
            if st.button(label, key=f"btn_{vid}", use_container_width=True):
                st.session_state.selected_id = vid
                st.rerun()
            if is_sel:
                st.markdown('</div>', unsafe_allow_html=True)

    if not ships and not planes:
        st.markdown(
            '<div style="font-size:11px;color:#2d4a6a;font-style:italic;padding:8px 0;">No vessels loaded yet.</div>',
            unsafe_allow_html=True
        )