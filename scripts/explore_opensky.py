"""
check_opensky.py
----------------
Fetches a small live snapshot from OpenSky Network and pretty-prints
the raw JSON for one state vector so you can see exactly what the API returns.

Reads from .env:
  OPENSKY_USER  (optional – anonymous works but is rate-limited)
  OPENSKY_PASS  (optional)
"""

import os, json, requests
from dotenv import load_dotenv

load_dotenv()

# ── credentials (anonymous if not set) ────────────────────────────────────────
user = os.getenv("OPENSKY_USER") or None
password = os.getenv("OPENSKY_PASS") or None
auth = (user, password) if user and password else None

# ── bounding box: contiguous US ───────────────────────────────────────────────
params = {
    "lamin": 24.5,   # south
    "lomin": -125.0, # west
    "lamax": 49.5,   # north
    "lomax": -66.0,  # east
}

URL = "https://opensky-network.org/api/states/all"

FIELDS = [
    "icao24", "callsign", "origin_country", "time_position",
    "last_contact", "longitude", "latitude", "baro_altitude",
    "on_ground", "velocity", "true_track", "vertical_rate",
    "sensors", "geo_altitude", "squawk", "spi", "position_source",
]

print("Connecting to OpenSky…")
print(f"Auth: {'✓ authenticated' if auth else '✗ anonymous (rate-limited)'}\n")

try:
    resp = requests.get(URL, params=params, auth=auth, timeout=15)
    resp.raise_for_status()
except requests.exceptions.HTTPError as e:
    print(f"HTTP error: {e}")
    raise SystemExit(1)
except requests.exceptions.RequestException as e:
    print(f"Connection error: {e}")
    raise SystemExit(1)

raw = resp.json()

total = len(raw.get("states") or [])
print(f"✓ Response received")
print(f"  Timestamp : {raw.get('time')}")
print(f"  Aircraft  : {total} in bounding box\n")

if not total:
    print("No aircraft returned – try again or widen the bounding box.")
    raise SystemExit(0)

# ── show one full raw state vector ────────────────────────────────────────────
first = raw["states"][0]
parsed = dict(zip(FIELDS, first))

print("=" * 60)
print("RAW STATE VECTOR (first aircraft)")
print("=" * 60)
print(json.dumps(parsed, indent=2))

print("\n--- raw list (as returned by API) ---")
print(first)