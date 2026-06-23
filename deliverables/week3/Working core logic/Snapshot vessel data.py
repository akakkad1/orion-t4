"""
snapshot_vessels.py

Exports a point-in-time, cleaned snapshot of the live `vessels` dict used by
the Movement Summarizer app (same shape as st.session_state.vessels) to two
CSV files:

  - vessels_snapshot_<UTC timestamp>.csv  -> one row per vessel, current state
  - tracks_snapshot_<UTC timestamp>.csv   -> one row per track point, for
                                              movement / trajectory analysis

This does NOT change the live app. It's a standalone export step you run
against a vessels dict (e.g. pulled from a running session, or built by
calling the app's fetch_opensky() / AIS collector directly) when you need a
saved artifact instead of (or in addition to) the live view.

Usage:
    python snapshot_vessels.py path/to/vessels.json
    # or import and call snapshot(vessels_dict) directly from your own script
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _is_valid_coord(lat, lon):
    if lat is None or lon is None:
        return False
    if lat == 0 and lon == 0:
        return False  # (0, 0) almost always means a missing/null GPS fix
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return False
    return True


def clean_vessel_row(vid, v):
    """Flatten one vessel record into a single cleaned row. Returns None if
    the record fails basic validity checks (e.g. no usable position)."""
    lat, lon = v.get("lat"), v.get("lon")
    if not _is_valid_coord(lat, lon):
        return None

    is_ship = v.get("type") == "ship"
    track = v.get("track", []) or []

    row = {
        "id": vid,
        "type": v.get("type", "unknown"),
        "name": v.get("name") or v.get("callsign") or "Unknown",
        "lat": lat,
        "lon": lon,
        "speed": v.get("speed", 0.0),
        "speed_unit": "kn" if is_ship else "kt",
        "course_deg": v.get("course", 0.0),
        "timestamp_utc": (
            datetime.fromtimestamp(v["timestamp"], tz=timezone.utc).isoformat()
            if v.get("timestamp") else ""
        ),
        "track_point_count": len(track),
    }

    if is_ship:
        row.update({
            "mmsi": v.get("mmsi", ""),
            "flag": v.get("flag") or "Unknown",
            "destination": v.get("destination") or "Unknown",
            "icao24": "",
            "altitude_m": "",
            "vertical_rate_mps": "",
            "origin_country": "",
        })
    else:
        row.update({
            "mmsi": "",
            "flag": "",
            "destination": "",
            "icao24": v.get("icao24", ""),
            "altitude_m": v.get("altitude", 0),
            "vertical_rate_mps": v.get("vertical_rate", 0.0),
            "origin_country": v.get("origin_country") or "Unknown",
        })

    return row


def clean_track_rows(vid, v):
    """Flatten one vessel's track history into row-per-point records.

    Known caveat (see data note Section 3): for aircraft, every track point
    except the most recent has speed == 0.0 because the OpenSky /tracks/all
    endpoint doesn't return speed. We flag those as interpolated/unknown
    rather than silently presenting them as a true zero speed.
    """
    is_ship = v.get("type") == "ship"
    track = v.get("track", []) or []
    rows = []

    for i, pt in enumerate(track):
        if len(pt) < 4:
            continue
        lat, lon, ts, spd = pt[0], pt[1], pt[2], pt[3]
        if not _is_valid_coord(lat, lon):
            continue

        is_last = (i == len(track) - 1)
        speed_known = is_ship or is_last or (spd not in (0, 0.0, None))

        rows.append({
            "vessel_id": vid,
            "point_index": i,
            "lat": lat,
            "lon": lon,
            "timestamp_utc": (
                datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else ""
            ),
            "speed": spd if speed_known else "",
            "speed_known": speed_known,
        })

    return rows


def snapshot(vessels: dict, out_dir: str = "."):
    """Write cleaned vessels + tracks CSVs for the given vessels dict.
    Returns (vessels_path, tracks_path)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()

    vessel_rows = []
    track_rows = []
    dropped = 0

    for vid, v in vessels.items():
        row = clean_vessel_row(vid, v)
        if row is None:
            dropped += 1
            continue
        vessel_rows.append(row)
        track_rows.extend(clean_track_rows(vid, v))

    vessels_path = out_dir / f"vessels_snapshot_{stamp}.csv"
    tracks_path = out_dir / f"tracks_snapshot_{stamp}.csv"

    vessel_fields = [
        "id", "type", "name", "lat", "lon", "speed", "speed_unit",
        "course_deg", "timestamp_utc", "track_point_count",
        "mmsi", "flag", "destination",
        "icao24", "altitude_m", "vertical_rate_mps", "origin_country",
    ]
    with open(vessels_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=vessel_fields)
        writer.writeheader()
        writer.writerows(vessel_rows)

    track_fields = ["vessel_id", "point_index", "lat", "lon",
                     "timestamp_utc", "speed", "speed_known"]
    with open(tracks_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=track_fields)
        writer.writeheader()
        writer.writerows(track_rows)

    print(f"Snapshot complete: {len(vessel_rows)} vessels written, "
          f"{dropped} dropped (invalid/missing position).")
    print(f"  -> {vessels_path}")
    print(f"  -> {tracks_path} ({len(track_rows)} track points)")

    return str(vessels_path), str(tracks_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python snapshot_vessels.py path/to/vessels.json [out_dir]")
        sys.exit(1)

    src_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    with open(src_path) as f:
        vessels_data = json.load(f)

    snapshot(vessels_data, out_dir)
