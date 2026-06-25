import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import folium
from streamlit_folium import st_folium
from datetime import datetime, timezone
import time
import shared

st.set_page_config(page_title="OpenSky — Aircraft", page_icon="✈",
                   layout="wide", initial_sidebar_state="expanded")

# ── CSS ───────────────────────────────────────────────────────────────────────
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
  @keyframes pulse{ 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.5;transform:scale(0.8)} }
  hr{ border-color:#1e2d45 !important; }
  .track-point{ display:flex; align-items:center; gap:8px; padding:5px 0; border-bottom:1px solid #1a2535; font-size:11px; font-family:'JetBrains Mono',monospace; color:#6b8aad; }
  .track-point:last-child{ border-bottom:none; }
  .track-dot{ width:5px; height:5px; border-radius:50%; flex-shrink:0; }
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
for k, v in {"sky_vessels": {}, "sky_selected": None, "sky_briefs": {},
             "sky_last_fetch": None}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Map builder ───────────────────────────────────────────────────────────────
def build_map(vessels, selected_id=None):
    if vessels:
        lats = [v["lat"] for v in vessels.values()]
        lons = [v["lon"] for v in vessels.values()]
        center = [sum(lats)/len(lats), sum(lons)/len(lons)]
        zoom = 4
    else:
        center, zoom = [20.0, -77.5], 4

    m = folium.Map(location=center, zoom_start=zoom,
                   tiles="CartoDB dark_matter", prefer_canvas=True)

    folium.Rectangle(
        bounds=[[shared.WHTC_BBOX["lat_min"], shared.WHTC_BBOX["lon_min"]],
                [shared.WHTC_BBOX["lat_max"], shared.WHTC_BBOX["lon_max"]]],
        color="#1e4d6b", weight=1.5, fill=True,
        fill_color="#0a2035", fill_opacity=0.15, dash_array="6 4",
        tooltip="WHTC  |  5°N–35°N · 100°W–55°W"
    ).add_to(m)

    zone_color = {"Gulf of Mexico":"#0369a1","Caribbean Sea":"#0c4a6e",
                  "Florida Straits":"#075985","Windward Passage":"#0e4d6e",
                  "Mona Passage":"#0e4d6e","Yucatan Channel":"#0e4d6e"}
    for zname, zb in shared.WHTC_ZONES.items():
        folium.Rectangle(
            bounds=[[zb["lat_min"],zb["lon_min"]],[zb["lat_max"],zb["lon_max"]]],
            color=zone_color.get(zname,"#1e4d6b"), weight=1, fill=False, opacity=0.4,
            tooltip=zname,
        ).add_to(m)
        folium.Marker(
            location=[zb["lat_max"]-0.3, zb["lon_min"]+0.4],
            icon=folium.DivIcon(
                html=f'<div style="font-size:9px;color:#1e6a9e;white-space:nowrap;'
                     f'font-family:JetBrains Mono,monospace;text-shadow:0 0 4px #000;pointer-events:none;">'
                     f'{zname.upper()}</div>',
                icon_size=(180,14), icon_anchor=(0,14))
        ).add_to(m)

    for vid, v in vessels.items():
        is_sel = vid == selected_id
        color  = "#fcd34d" if is_sel else "#f59e0b"
        size   = 20 if is_sel else 14
        border = f"2px solid #fcd34d" if is_sel else "1px solid #f59e0b"
        bg     = "rgba(251,191,36,0.15)" if is_sel else "rgba(0,0,0,0.75)"

        track = v.get("track", [])
        if len(track) >= 2:
            folium.PolyLine(
                [(p[0],p[1]) for p in track],
                color=color, weight=2.5 if is_sel else 1.5,
                opacity=0.9 if is_sel else 0.5,
            ).add_to(m)
            folium.CircleMarker(
                location=(track[0][0], track[0][1]),
                radius=4, color="#f59e0b", fill=True,
                fill_color="#f59e0b", fill_opacity=0.9,
                tooltip=f"Takeoff — {datetime.fromtimestamp(track[0][2],tz=timezone.utc).strftime('%H:%M UTC')}",
            ).add_to(m)

        alt_line = f"<br>Alt: {v.get('altitude',0):,.0f} m"
        popup_html = (
            f"<div style='font-family:monospace;font-size:12px;color:#1e293b;min-width:170px'>"
            f"<b style='color:#92400e'>{v.get('name',vid)}</b><br>"
            f"ICAO: {v.get('icao24','?')}{alt_line}<br>"
            f"Spd: {v['speed']} kt | Hdg: {v['course']}°<br>"
            f"Track: {len(track)} pts</div>"
        )
        folium.Marker(
            location=[v["lat"], v["lon"]],
            icon=folium.DivIcon(
                html=f'<div style="font-size:{size}px;border:{border};border-radius:50%;'
                     f'background:{bg};width:{size+10}px;height:{size+10}px;'
                     f'display:flex;align-items:center;justify-content:center;">✈</div>',
                icon_size=(size+10,size+10), icon_anchor=((size+10)//2,(size+10)//2)),
            popup=folium.Popup(popup_html, max_width=230),
            tooltip=f"{v.get('name',vid)} | {v['speed']} kt | {len(track)} pts",
        ).add_to(m)
    return m

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ✈ OpenSky Aircraft")
    st.markdown('<div style="font-size:10px;color:#4a6580;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:12px;">WHTC · Live Positions</div>', unsafe_allow_html=True)

    if st.button("🔄 Fetch / Refresh Aircraft", use_container_width=True):
        st.session_state["sky_do_fetch"] = True

    if st.session_state.sky_last_fetch:
        elapsed = int(time.time() - st.session_state.sky_last_fetch)
        n = len(st.session_state.sky_vessels)
        st.markdown(f'<div class="status-bar">Last fetch: {elapsed}s ago · {n} aircraft</div>',
                    unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
    <div style="background:#0c1929;border:1px solid #1e3a5a;border-left:3px solid #f59e0b;
         border-radius:0 6px 6px 0;padding:10px 12px;">
      <div style="font-size:11px;font-weight:600;color:#fcd34d;margin-bottom:6px;">WHTC CORRIDOR</div>
      <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#4a8ab5;line-height:1.8">
        5°N–35°N · 100°W–55°W<br>
        Gulf of Mexico<br>Caribbean Sea<br>
        Florida Straits<br>Windward Passage
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── Fetch ─────────────────────────────────────────────────────────────────────
if st.session_state.get("sky_do_fetch"):
    st.session_state["sky_do_fetch"] = False
    with st.spinner("Fetching aircraft + flight tracks from OpenSky…"):
        sky = shared.fetch_opensky()
        if sky:
            st.session_state.sky_vessels.update(sky)
        st.session_state.sky_last_fetch = time.time()
    st.rerun()

# ── Layout ────────────────────────────────────────────────────────────────────
st.markdown("## ✈ Live Aircraft — WHTC")

left_col, right_col = st.columns([3, 2], gap="medium")

with left_col:
    n = len(st.session_state.sky_vessels)
    st.markdown(f'<div class="status-bar"><span class="live-dot"></span>{n} aircraft tracked</div>',
                unsafe_allow_html=True)

    if not st.session_state.sky_vessels:
        st.markdown(
            '<div class="brief-box" style="color:#2d4a6a;font-style:italic;">'
            'Press <b style="color:#f59e0b">Fetch / Refresh Aircraft</b> in the sidebar to load live positions and flight paths.</div>',
            unsafe_allow_html=True)
    else:
        m = build_map(st.session_state.sky_vessels, st.session_state.sky_selected)
        map_data = st_folium(m, height=520, use_container_width=True,
                             returned_objects=["last_object_clicked_tooltip"])
        if map_data and map_data.get("last_object_clicked_tooltip"):
            tip = map_data["last_object_clicked_tooltip"]
            for vid, v in st.session_state.sky_vessels.items():
                if v.get("name", vid) in tip and st.session_state.sky_selected != vid:
                    st.session_state.sky_selected = vid
                    st.rerun()

with right_col:
    # ── Detail panel first ────────────────────────────────────────────────────
    if st.session_state.sky_selected and st.session_state.sky_selected in st.session_state.sky_vessels:
        sel   = st.session_state.sky_vessels[st.session_state.sky_selected]
        stats = shared.compute_track_stats(sel)
        vid   = st.session_state.sky_selected

        st.markdown(
            f'<div style="background:#0c1929;border:1px solid #f59e0b;border-radius:8px;'
            f'padding:12px 14px;margin-bottom:12px;">'
            f'<div style="font-size:10px;color:#f59e0b;text-transform:uppercase;letter-spacing:2px;font-weight:600;margin-bottom:2px;">Selected</div>'
            f'<div style="font-size:16px;font-weight:700;color:#fef3c7;">✈ {sel.get("name","?")}</div>'
            f'</div>', unsafe_allow_html=True)

        c1,c2,c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="stat-card"><div class="stat-label">Speed</div>'
                        f'<div class="stat-value">{sel["speed"]}<span class="stat-unit">kt</span></div></div>',
                        unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="stat-card"><div class="stat-label">Course</div>'
                        f'<div class="stat-value">{sel["course"]}<span class="stat-unit">°</span></div></div>',
                        unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="stat-card"><div class="stat-label">Altitude</div>'
                        f'<div class="stat-value">{sel.get("altitude",0):,.0f}<span class="stat-unit">m</span></div></div>',
                        unsafe_allow_html=True)

        if stats:
            s1,s2 = st.columns(2)
            with s1:
                st.markdown(f'<div class="stat-card"><div class="stat-label">Distance</div>'
                            f'<div class="stat-value">{stats["total_distance_km"]}<span class="stat-unit">km</span></div></div>',
                            unsafe_allow_html=True)
            with s2:
                st.markdown(f'<div class="stat-card"><div class="stat-label">Flight Time</div>'
                            f'<div class="stat-value">{int(stats["duration_minutes"])}<span class="stat-unit">min</span></div></div>',
                            unsafe_allow_html=True)

        st.markdown('<div class="section-label" style="margin-top:4px;">AI Movement Brief</div>', unsafe_allow_html=True)
        existing = st.session_state.sky_briefs.get(vid)
        b1,b2 = st.columns([2,1])
        with b1:
            if st.button("⚡ Generate Brief", key="sky_gen", use_container_width=True):
                if not shared.GEMINI_API_KEY:
                    st.error("GEMINI_API_KEY not set in .env")
                else:
                    with st.spinner("Generating brief…"):
                        st.session_state.sky_briefs[vid] = shared.fetch_brief(sel, stats)
                    st.rerun()
        with b2:
            if existing and st.button("✕ Clear", key="sky_clr", use_container_width=True):
                del st.session_state.sky_briefs[vid]
                st.rerun()

        if existing:
            st.markdown(f'<div class="brief-box">{existing}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="brief-box" style="color:#2d4a6a;font-style:italic;">Click Generate Brief for an AI analyst summary.</div>', unsafe_allow_html=True)

        if sel.get("track") and len(sel["track"]) > 1:
            with st.expander(f"Flight Path — {len(sel['track'])} points", expanded=False):
                html = ""
                pts = sel["track"][-12:]
                for i, pt in enumerate(pts):
                    ts_str = datetime.fromtimestamp(pt[2], tz=timezone.utc).strftime("%H:%M:%S")
                    alpha  = 0.35 + 0.65*(i/max(len(pts)-1,1))
                    c      = f"rgba(251,191,36,{alpha:.2f})"
                    html  += (f'<div class="track-point">'
                              f'<div class="track-dot" style="background:{c}"></div>'
                              f'<span style="color:#fbbf24;min-width:70px">{ts_str} UTC</span>'
                              f'<span>{pt[0]:.3f}°, {pt[1]:.3f}°</span>'
                              f'<span style="margin-left:auto">{pt[3]:.1f} kt</span></div>')
                st.markdown(html, unsafe_allow_html=True)
        st.markdown("---")
    else:
        st.markdown('<div class="brief-box" style="color:#2d4a6a;font-style:italic;margin-bottom:12px;">Select an aircraft from the list or click one on the map.</div>', unsafe_allow_html=True)

    # ── Aircraft list ─────────────────────────────────────────────────────────
    st.markdown('<div style="font-size:11px;font-weight:600;color:#f59e0b;letter-spacing:1px;margin-bottom:6px;">✈ AIRCRAFT</div>', unsafe_allow_html=True)
    if st.session_state.sky_vessels:
        for vid, v in st.session_state.sky_vessels.items():
            is_sel = vid == st.session_state.sky_selected
            n_pts  = len(v.get("track", []))
            prefix = "● " if is_sel else "  "
            label  = f"{prefix}{v['name']}  {v['speed']} kt  {n_pts}pts"
            style  = "background:#0c2d4a;border:2px solid #f59e0b;color:#fef3c7;" if is_sel else ""
            if style:
                st.markdown(f'<style>div[data-testid="stButton"]:has(button[kind="secondary"]) button {{ {style} }}</style>', unsafe_allow_html=True)
            if st.button(label, key=f"sky_{vid}", use_container_width=True):
                st.session_state.sky_selected = vid
                st.rerun()
    else:
        st.markdown('<div style="font-size:11px;color:#2d4a6a;font-style:italic;">No aircraft loaded.</div>', unsafe_allow_html=True)
