"""
Shared constants, helpers, and AIS background thread.
Imported by both pages so state lives in st.session_state.
"""
import os, json, math, time, threading
from datetime import datetime, timezone
import requests, websocket
from dotenv import load_dotenv

load_dotenv()
OPENSKY_CLIENT_ID     = os.environ.get("OPENSKY_CLIENT_ID", "")
OPENSKY_CLIENT_SECRET = os.environ.get("OPENSKY_CLIENT_SECRET", "")
AISSTREAM_API_KEY     = os.environ.get("AISSTREAM_API_KEY", "")
GEMINI_API_KEY        = os.environ.get("GEMINI_API_KEY", "")

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

# ── Shared mutable state (module-level so thread can write to it) ─────────────
ais_ships   = {}   # {vid: vessel_dict}  — written by thread, read by page
ais_log     = []   # list of log strings for display
ais_status  = {"collecting": False, "started": False, "ship_count": 0}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
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

# ── AISStream background thread ───────────────────────────────────────────────
def start_aisstream():
    if ais_status["started"]:
        return
    if not AISSTREAM_API_KEY:
        msg = "[AIS] ERROR: AISSTREAM_API_KEY not set in .env"
        print(msg)
        ais_log.append(msg)
        return

    ais_status["started"]    = True
    ais_status["collecting"] = True
    print("[AIS] Starting WebSocket connection to aisstream.io …")
    ais_log.append("[AIS] Connecting to aisstream.io …")

    def run():
        subscribe = {
            "APIKey": AISSTREAM_API_KEY,
            "BoundingBoxes": [[[WHTC_LIST[0], WHTC_LIST[1]],
                                [WHTC_LIST[2], WHTC_LIST[3]]]],
            "FilterMessageTypes": ["PositionReport"],
        }

        def on_open(ws):
            msg = "[AIS] WebSocket opened - subscribing to WHTC bounding box"
            print(msg)
            ais_log.append(msg)
            ws.send(json.dumps(subscribe))

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
                dest = meta.get("Destination", "").strip() or "Unknown"
                ts   = time.time()
                ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S")

                existing = ais_ships.get(vid, {})
                track    = list(existing.get("track", []))
                is_new   = vid not in ais_ships
                track.append((lat, lon, ts, spd))
                if len(track) > 200:
                    track = track[-200:]

                ais_ships[vid] = {
                    "id": vid, "type": "ship", "name": name,
                    "lat": lat, "lon": lon, "speed": spd, "course": cog,
                    "mmsi": mmsi, "flag": meta.get("flag", "?"),
                    "destination": dest, "timestamp": ts, "track": track,
                }
                ais_status["ship_count"] = len(ais_ships)

                tag   = "NEW" if is_new else "UPD"
                log_line = (f"[AIS] {ts_str} UTC  [{tag}]  {name:<20}  "
                            f"MMSI:{mmsi}  {lat:.3f},{lon:.3f}  "
                            f"{spd:.1f}kn  hdg:{cog:.0f}deg  -> {dest}")
                try:
                    print(log_line)
                except UnicodeEncodeError:
                    print(log_line.encode('ascii', errors='replace').decode('ascii'))
                ais_log.append(log_line)
                if len(ais_log) > 500:
                    ais_log.pop(0)

            except Exception as e:
                err = f"[AIS] parse error: {e}"
                print(err)
                ais_log.append(err)

        def on_error(ws, error):
            msg = f"[AIS] ERROR: {error}"
            print(msg)
            ais_log.append(msg)
            ais_status["collecting"] = False
            ais_status["started"]    = False

        def on_close(ws, code, reason):
            msg = f"[AIS] Connection closed — code:{code} reason:{reason}"
            print(msg)
            ais_log.append(msg)
            ais_status["collecting"] = False
            ais_status["started"]    = False

        try:
            websocket.WebSocketApp(
                "wss://stream.aisstream.io/v0/stream",
                on_open=on_open, on_message=on_message,
                on_error=on_error, on_close=on_close,
            ).run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            msg = f"[AIS] WebSocket exception: {e}"
            print(msg)
            ais_log.append(msg)
            ais_status["collecting"] = False
            ais_status["started"]    = False

    threading.Thread(target=run, daemon=True).start()

# ── OpenSky ───────────────────────────────────────────────────────────────────
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
        try:
            return {"Authorization": f"Bearer {_get_opensky_token()}"}
        except Exception:
            pass
    return {}

def fetch_flight_track(icao24, headers):
    try:
        r = requests.get(
            "https://opensky-network.org/api/tracks/all",
            params={"icao24": icao24, "time": 0},
            headers=headers, timeout=10,
        )
        if r.status_code != 200:
            return []
        path = r.json().get("path", [])
        return [(pt[1], pt[2], pt[0], 0.0)
                for pt in path if pt[1] is not None and pt[2] is not None]
    except Exception:
        return []

def fetch_opensky():
    try:
        headers = _opensky_headers()
        params  = {"lamin": WHTC_LIST[0], "lomin": WHTC_LIST[1],
                   "lamax": WHTC_LIST[2], "lomax": WHTC_LIST[3]}
        r = requests.get("https://opensky-network.org/api/states/all",
                         params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            return {}
        vessels = {}
        for s in (r.json().get("states") or [])[:40]:
            if s[5] is None or s[6] is None:
                continue
            icao = s[0]
            vid  = f"plane_{icao}"
            spd  = round((s[9] or 0) * 1.944, 1)
            ts   = s[3] or time.time()
            name = (s[1] or icao).strip() or icao
            track = fetch_flight_track(icao, headers)
            if track:
                last = track[-1]
                track[-1] = (last[0], last[1], last[2], spd)
            else:
                track = [(s[6], s[5], ts, spd)]
            vessels[vid] = {
                "id": vid, "type": "plane", "name": name, "callsign": name,
                "icao24": icao, "lat": s[6], "lon": s[5],
                "altitude": s[7] or 0, "speed": spd,
                "course": round(s[10] or 0, 1),
                "vertical_rate": s[11] or 0,
                "origin_country": s[2], "timestamp": ts, "track": track,
            }
        return vessels
    except Exception as e:
        return {}

# ── Gemini brief ──────────────────────────────────────────────────────────────
def build_prompt(vessel, stats):
    v     = vessel
    vtype = "ship" if v["type"] == "ship" else "aircraft"
    name  = v.get("name", v.get("callsign", "Unknown"))
    su    = "kn" if v["type"] == "ship" else "kt"
    track_desc = "".join(
        f"  {i}. {datetime.fromtimestamp(pt[2], tz=timezone.utc).strftime('%H:%M:%S UTC')} "
        f"— lat {pt[0]:.3f}, lon {pt[1]:.3f}, speed {pt[3]:.1f} {su}\n"
        for i, pt in enumerate(v.get("track", []), 1)
    )
    extras = (
        f"Flag: {v.get('flag','?')} | MMSI: {v.get('mmsi','?')} | Destination: {v.get('destination','Unknown')}"
        if v["type"] == "ship" else
        f"ICAO24: {v.get('icao24','?')} | Country: {v.get('origin_country','?')} | "
        f"Altitude: {v.get('altitude',0):,} m | Vertical rate: {v.get('vertical_rate',0):.1f} m/s"
    )
    return (
        f"You are an intelligence analyst writing a movement brief for an operations room.\n\n"
        f"VESSEL TYPE: {vtype.upper()}\nIDENTIFIER: {name}\n{extras}\n"
        f"CURRENT POSITION: {v['lat']:.4f}°, {v['lon']:.4f}°\n"
        f"CURRENT SPEED: {v['speed']} {su} | COURSE: {v['course']}°\n"
        f"DATA WINDOW: {stats.get('duration_minutes',0):.0f} min | "
        f"DISTANCE: {stats.get('total_distance_km',0)} km | "
        f"AVG SPEED: {stats.get('avg_speed',0)} {su}\n"
        f"TRACK HISTORY:\n{track_desc}\n"
        f"Write a concise plain-language movement brief (3-5 sentences) for an ops briefing. "
        f"Cover where it went and when, speed changes or stops (speed < 1 = stopped), "
        f"current status and trajectory, anything operationally noteworthy. "
        f"Single paragraph, no headers, no bullets. Professional tone. "
        f"Compass directions and times."
    )

def fetch_brief(vessel, stats):
    if not GEMINI_API_KEY:
        return "⚠ GEMINI_API_KEY not set in .env"
    try:
        from google import genai
        client   = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=build_prompt(vessel, stats))
        return response.text.strip()
    except Exception as e:
        return f"⚠ Brief generation failed: {e}"