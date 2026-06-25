import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import shared

# Start AIS in background on first load
shared.start_aisstream()

st.set_page_config(page_title="Movement Summarizer", page_icon="🛰️",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
  html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
  .stApp { background: #0a0e1a; color: #c8d6e5; }
  [data-testid="stSidebar"] { background: #0d1220 !important; border-right: 1px solid #1e2d45; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 🛰️ Movement Summarizer")
st.markdown("### Maritime & Aviation Intelligence — Western Hemisphere Transit Corridor")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    <div style="background:#111827;border:1px solid #1e2d45;border-radius:10px;padding:24px;">
      <div style="font-size:32px;margin-bottom:10px;">✈</div>
      <div style="font-size:18px;font-weight:700;color:#f59e0b;margin-bottom:8px;">OpenSky — Live Aircraft</div>
      <div style="font-size:13px;color:#6b8aad;line-height:1.7;">
        Fetch current aircraft positions across the WHTC corridor.<br>
        Pulls full flight paths since takeoff.<br>
        Click any aircraft for an AI movement brief.
      </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Open Aircraft Tracker →", use_container_width=True, key="go_opensky"):
        st.switch_page("pages/1_✈_OpenSky.py")

with col2:
    n_ships = shared.ais_status["ship_count"]
    collecting = shared.ais_status["collecting"]
    status_color = "#22c55e" if collecting else "#ef4444"
    status_text  = f"LIVE · {n_ships} ships" if collecting else "DISCONNECTED"
    st.markdown(f"""
    <div style="background:#111827;border:1px solid #1e2d45;border-radius:10px;padding:24px;">
      <div style="font-size:32px;margin-bottom:10px;">⚓</div>
      <div style="font-size:18px;font-weight:700;color:#0ea5e9;margin-bottom:8px;">AISStream — Live Ships</div>
      <div style="font-size:13px;color:#6b8aad;line-height:1.7;">
        Real-time AIS position pings streamed over WebSocket.<br>
        Ships populate automatically as broadcasts are received.<br>
        Live terminal feed of every incoming ping.
      </div>
      <div style="margin-top:12px;font-family:'JetBrains Mono',monospace;font-size:11px;
           color:{status_color};">⬤ AIS {status_text}</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Open Ship Tracker →", use_container_width=True, key="go_ais"):
        st.switch_page("pages/2_⚓_AISStream.py")