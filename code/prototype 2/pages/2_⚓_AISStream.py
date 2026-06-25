import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import folium
from streamlit_folium import st_folium
from datetime import datetime, timezone
import time
import shared

# Ensure AIS is running
shared.start_aisstream()

st.set_page_config(page_title="AISStream — Ships", page_icon="⚓",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
  html,body,[class*="css"]{ font-family:'Space Grotesk',sans-serif; }
  .stApp { background:#0a0e1a; color:#c8d6e5; }
  [data-testid="stSidebar"]{ background:#0d1220 !important; border-right:1px solid #1e2d45; }
  .stat-card{ background:#111827; border:1px solid #1e2d45; border-radius:8px; padding:14px; margin-bottom:8px; }
  .stat-label{ font-size:10px; color:#4a6580; text-transform:uppercase; letter-spacing:1.5px; margin-bottom:3px; }
  .stat-value{ font-size:20px; font-weight:700; color:#38bdf8; font-family:'JetBrains Mono',monospace; }
  .stat-unit{ font-size:11px; color:#4a6580; margin-left:3px; }
  .brief-box{ background:#0d1a2a; border:1px solid #1e3a5a; border-left:3px solid #38bdf8; border-radius:0 8px 8px 0; padding:16px 18px; font-size:13px; line-height:1.7; color:#c8d6e5; margin-top:10px; }
  .section-label{ font-size:10px; color:#38bdf8; text-transform:uppercase; letter-spacing:2px; margin-bottom:6px; font-weight:600; }
  .status-bar{ background:#111827; border:1px solid #1e2d45; border-radius:6px; padding:7px 12px; font-size:11px; color:#4a6580; font-family:'JetBrains Mono',monospace; margin-bottom:10px; }
  .live-dot{ display:inline-block; width:7px; height:7px; background:#22c55e; border-radius:50%; animation:pulse 1.5s infinite; margin-right:5px; }
  @keyframes pulse{ 0%,100%{opacity:1} 50%{opacity:0.4} }
  hr{ border-color:#1e2d45 !important; }
  .track-point{ display:flex; align-items:center; gap:8px; padding:5px 0; border-bottom:1px solid #1a2535; font-size:11px; font-family:'JetBrains Mono',monospace; color:#6b8aad; }
  .track-point:last-child{ border-bottom:none; }
  .track-dot{ width:5px; height:5px; border-radius:50%; flex-shrink:0; }
  .terminal{ background:#060d14; border:1px solid #1e3a5a; border-radius:6px; padding:12px 14px;
             font-family:'JetBrains Mono',monospace; font-size:11px; color:#4ade80;
             max-height:260px; overflow-y:auto; line-height:1.6; }
  div[data-testid="stButton"] button{
    background:#0c1929 !important; border:1px solid #1e3a5a !important;
    color:#6b8aad !important; font-family:'JetBrains Mono',monospace !important;
    font-size:11px !important; border-radius:5px !important; text-align:left !important;
  }
  div[data-testid="stButton"] button:hover{
    background:#0f2033 !important; border-color:#2d5f80 !important; color:#a8c4d8 !important;
  }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {"ais_selected": None, "ais_briefs": {}, "ais_auto_refresh": True}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Map builder ───────────────────────────────────────────────────────────────
def build_map(vessels, selected_id=None):
    if vessels:
        lats = [v["lat"] for v in vessels.values()]
        lons = [v["lon"] for v in vessels.values()]
        center = [sum(lats)/len(lats), sum(lons)/len(lons)]
    else:
        center = [20.0, -77.5]

    m = folium.Map(location=center, zoom_start=4,
                   tiles="CartoDB dark_matter", prefer_canvas=True)

    # WHTC boundary — drawn as non-interactive GeoJson so clicks pass through
    import json as _json
    whtc_geojson = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [shared.WHTC_BBOX["lon_min"], shared.WHTC_BBOX["lat_min"]],
                [shared.WHTC_BBOX["lon_max"], shared.WHTC_BBOX["lat_min"]],
                [shared.WHTC_BBOX["lon_max"], shared.WHTC_BBOX["lat_max"]],
                [shared.WHTC_BBOX["lon_min"], shared.WHTC_BBOX["lat_max"]],
                [shared.WHTC_BBOX["lon_min"], shared.WHTC_BBOX["lat_min"]],
            ]]
        },
        "properties": {}
    }
    folium.GeoJson(
        whtc_geojson,
        style_function=lambda _: {
            "color": "#1e4d6b", "weight": 1.5,
            "fillColor": "#0a2035", "fillOpacity": 0.15,
            "dashArray": "6 4",
        },
        highlight_function=None,
        interactive=False,
    ).add_to(m)

    # Ship paths — non-interactive PolyLines
    for vid, v in vessels.items():
        is_sel = vid == selected_id
        color  = "#38bdf8" if is_sel else "#0ea5e9"
        track  = v.get("track", [])
        if len(track) >= 2:
            folium.PolyLine(
                [(p[0], p[1]) for p in track],
                color=color,
                weight=2.5 if is_sel else 1.5,
                opacity=0.9 if is_sel else 0.55,
                interactive=False,   # path never intercepts clicks
            ).add_to(m)

    # Ship markers — only these respond to clicks
    for vid, v in vessels.items():
        is_sel = vid == selected_id
        color  = "#38bdf8" if is_sel else "#0ea5e9"
        size   = 20 if is_sel else 14
        border = "2px solid #38bdf8" if is_sel else "1px solid #0ea5e9"
        bg     = "rgba(56,189,248,0.15)" if is_sel else "rgba(0,0,0,0.75)"
        track  = v.get("track", [])
        name   = v.get("name", vid)
        dest   = v.get("destination", "Unknown")

        popup_html = (
            f"<div style='font-family:monospace;font-size:12px;color:#1e293b;min-width:170px'>"
            f"<b style='color:#0c4a6e'>{name}</b><br>"
            f"MMSI: {v.get('mmsi','?')} | dest: {dest}<br>"
            f"Spd: {v['speed']} kn | Hdg: {v['course']}<br>"
            f"Pings: {len(track)}</div>"
        )
        folium.Marker(
            location=[v["lat"], v["lon"]],
            icon=folium.DivIcon(
                html=(f'<div style="font-size:{size}px;border:{border};border-radius:50%;'
                      f'background:{bg};width:{size+10}px;height:{size+10}px;'
                      f'display:flex;align-items:center;justify-content:center;">&#9875;</div>'),
                icon_size=(size+10, size+10),
                icon_anchor=((size+10)//2, (size+10)//2),
            ),
            popup=folium.Popup(popup_html, max_width=220),
            tooltip=f"{name} | {v['speed']} kn | {len(track)} pings",
        ).add_to(m)
    return m

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚓ AISStream Ships")
    collecting = shared.ais_status["collecting"]
    n_ships    = shared.ais_status["ship_count"]
    dot_color  = "#22c55e" if collecting else "#ef4444"
    status_txt = f"LIVE · {n_ships} ships" if collecting else "DISCONNECTED"
    st.markdown(
        f'<div style="background:#0c1929;border:1px solid #1e3a5a;border-left:3px solid {dot_color};'
        f'border-radius:0 6px 6px 0;padding:8px 12px;margin-bottom:12px;">'
        f'<div style="font-size:11px;color:{dot_color};font-family:JetBrains Mono,monospace;">'
        f'⬤ AIS {status_txt}</div></div>',
        unsafe_allow_html=True
    )

    auto = st.checkbox("Auto-refresh map (5s)", value=st.session_state.ais_auto_refresh, key="ais_auto_cb")
    st.session_state.ais_auto_refresh = auto

    if st.button("🔄 Refresh Now", use_container_width=True):
        st.rerun()

    st.markdown("---")
    st.markdown("""
    <div style="background:#0c1929;border:1px solid #1e3a5a;border-left:3px solid #38bdf8;
         border-radius:0 6px 6px 0;padding:10px 12px;">
      <div style="font-size:11px;font-weight:600;color:#7dd3fc;margin-bottom:4px;">WHTC CORRIDOR</div>
      <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#4a8ab5;line-height:1.8">
        5°N–35°N · 100°W–55°W<br>
        Gulf of Mexico<br>Caribbean Sea<br>
        Florida Straits<br>Windward Passage
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if st.session_state.ais_auto_refresh and collecting:
    import threading as _t
    def _rerun():
        time.sleep(5)
        st.rerun()
    _t.Thread(target=_rerun, daemon=True).start()

# ── Layout ────────────────────────────────────────────────────────────────────
st.markdown("## ⚓ Live Ship Tracker — AISStream")

vessels = dict(shared.ais_ships)   # snapshot of live data

map_col, right_col = st.columns([3, 2], gap="medium")

with map_col:
    n = len(vessels)
    st.markdown(
        f'<div class="status-bar"><span class="live-dot"></span>'
        f'{n} ships · {"streaming" if collecting else "disconnected"}</div>',
        unsafe_allow_html=True
    )
    if not vessels:
        st.markdown(
            '<div class="brief-box" style="color:#2d4a6a;font-style:italic;">'
            'Waiting for AIS pings… Ships will appear as position reports are received.<br><br>'
            'Check the terminal below for incoming data.</div>',
            unsafe_allow_html=True
        )
    else:
        m = build_map(vessels, st.session_state.ais_selected)
        map_data = st_folium(m, height=440, use_container_width=True,
                             returned_objects=["last_object_clicked_tooltip"])
        if map_data and map_data.get("last_object_clicked_tooltip"):
            tip = map_data["last_object_clicked_tooltip"]
            for vid, v in vessels.items():
                if v.get("name", vid) in tip and st.session_state.ais_selected != vid:
                    st.session_state.ais_selected = vid
                    st.rerun()

    # ── AIS Terminal ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-label" style="margin-top:14px;">AIS Terminal Feed</div>',
                unsafe_allow_html=True)
    log_lines = list(shared.ais_log)[-40:]   # last 40 lines
    if log_lines:
        lines_html = "<br>".join(
            (f'<span style="color:#fbbf24">{l}</span>' if "[NEW]" in l
             else f'<span style="color:#6ee7b7">{l}</span>' if "[UPD]" in l
             else f'<span style="color:#ef4444">{l}</span>' if "ERROR" in l or "DISCONN" in l
             else f'<span style="color:#4ade80">{l}</span>')
            for l in log_lines
        )
        st.markdown(f'<div class="terminal">{lines_html}</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="terminal" style="color:#1e4d3a;">Waiting for AIS data…<br>'
            'Check your AISSTREAM_API_KEY in .env</div>',
            unsafe_allow_html=True
        )

with right_col:
    # ── Detail panel ─────────────────────────────────────────────────────────
    if st.session_state.ais_selected and st.session_state.ais_selected in vessels:
        sel   = vessels[st.session_state.ais_selected]
        stats = shared.compute_track_stats(sel)
        vid   = st.session_state.ais_selected

        st.markdown(
            f'<div style="background:#0c1929;border:1px solid #38bdf8;border-radius:8px;'
            f'padding:12px 14px;margin-bottom:12px;">'
            f'<div style="font-size:10px;color:#38bdf8;text-transform:uppercase;letter-spacing:2px;font-weight:600;margin-bottom:2px;">Selected</div>'
            f'<div style="font-size:16px;font-weight:700;color:#e0f2fe;">⚓ {sel.get("name","?")}</div>'
            f'<div style="font-size:11px;color:#4a6580;font-family:JetBrains Mono,monospace;margin-top:3px;">'
            f'MMSI: {sel.get("mmsi","?")} · Flag: {sel.get("flag","?")}</div>'
            f'</div>', unsafe_allow_html=True)

        c1,c2,c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="stat-card"><div class="stat-label">Speed</div>'
                        f'<div class="stat-value">{sel["speed"]}<span class="stat-unit">kn</span></div></div>',
                        unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="stat-card"><div class="stat-label">Course</div>'
                        f'<div class="stat-value">{sel["course"]}<span class="stat-unit">°</span></div></div>',
                        unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="stat-card"><div class="stat-label">Destination</div>'
                        f'<div class="stat-value" style="font-size:13px">{sel.get("destination","?")[:10]}</div></div>',
                        unsafe_allow_html=True)

        if stats:
            s1,s2 = st.columns(2)
            with s1:
                st.markdown(f'<div class="stat-card"><div class="stat-label">Distance</div>'
                            f'<div class="stat-value">{stats["total_distance_km"]}<span class="stat-unit">km</span></div></div>',
                            unsafe_allow_html=True)
            with s2:
                st.markdown(f'<div class="stat-card"><div class="stat-label">Pings</div>'
                            f'<div class="stat-value">{len(sel.get("track",[]))}</div></div>',
                            unsafe_allow_html=True)

        st.markdown('<div class="section-label" style="margin-top:4px;">AI Movement Brief</div>', unsafe_allow_html=True)
        existing = st.session_state.ais_briefs.get(vid)
        b1,b2 = st.columns([2,1])
        with b1:
            if st.button("⚡ Generate Brief", key="ais_gen", use_container_width=True):
                if not shared.GEMINI_API_KEY:
                    st.error("GEMINI_API_KEY not set in .env")
                else:
                    with st.spinner("Generating brief…"):
                        st.session_state.ais_briefs[vid] = shared.fetch_brief(sel, stats)
                    st.rerun()
        with b2:
            if existing and st.button("✕ Clear", key="ais_clr", use_container_width=True):
                del st.session_state.ais_briefs[vid]
                st.rerun()

        if existing:
            st.markdown(f'<div class="brief-box">{existing}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="brief-box" style="color:#2d4a6a;font-style:italic;">Click Generate Brief for an AI analyst summary.</div>', unsafe_allow_html=True)

        if sel.get("track") and len(sel["track"]) > 1:
            with st.expander(f"Ping History — {len(sel['track'])} pings", expanded=False):
                html = ""
                pts = sel["track"][-12:]
                for i, pt in enumerate(pts):
                    ts_str = datetime.fromtimestamp(pt[2], tz=timezone.utc).strftime("%H:%M:%S")
                    alpha  = 0.35 + 0.65*(i/max(len(pts)-1,1))
                    c      = f"rgba(56,189,248,{alpha:.2f})"
                    html  += (f'<div class="track-point">'
                              f'<div class="track-dot" style="background:{c}"></div>'
                              f'<span style="color:#38bdf8;min-width:70px">{ts_str} UTC</span>'
                              f'<span>{pt[0]:.3f}°, {pt[1]:.3f}°</span>'
                              f'<span style="margin-left:auto">{pt[3]:.1f} kn</span></div>')
                st.markdown(html, unsafe_allow_html=True)
        st.markdown("---")
    else:
        st.markdown('<div class="brief-box" style="color:#2d4a6a;font-style:italic;margin-bottom:12px;">Select a ship from the list or click one on the map.</div>', unsafe_allow_html=True)

    # ── Ship list ─────────────────────────────────────────────────────────────
    st.markdown('<div style="font-size:11px;font-weight:600;color:#0ea5e9;letter-spacing:1px;margin-bottom:6px;">⚓ SHIPS</div>', unsafe_allow_html=True)
    if vessels:
        # Sort by most recently seen
        sorted_ships = sorted(vessels.items(), key=lambda x: x[1].get("timestamp", 0), reverse=True)
        for vid, v in sorted_ships:
            is_sel = vid == st.session_state.ais_selected
            n_pts  = len(v.get("track", []))
            prefix = "● " if is_sel else "  "
            ts_ago = int(time.time() - v.get("timestamp", time.time()))
            label  = f"{prefix}{v['name']}  {v['speed']}kn  {n_pts}pings  {ts_ago}s ago"
            if is_sel:
                st.markdown(
                    '<div style="background:#0c2d4a;border:2px solid #38bdf8;border-radius:5px;margin-bottom:2px;padding:1px;">',
                    unsafe_allow_html=True
                )
            if st.button(label, key=f"ais_{vid}", use_container_width=True):
                st.session_state.ais_selected = vid
                st.rerun()
            if is_sel:
                st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="font-size:11px;color:#2d4a6a;font-style:italic;">No ships received yet.</div>', unsafe_allow_html=True)