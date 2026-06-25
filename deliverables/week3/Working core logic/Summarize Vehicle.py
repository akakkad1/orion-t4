"""
summarize_vehicle.py — Week 3, Day 1: first working version of the core
summarization logic, running end-to-end on SAVED data (the CSVs produced by
snapshot_vessels.py), not the live app.

This intentionally does the bare minimum to go end to end:
  1. Load a saved vessels_snapshot_*.csv + tracks_snapshot_*.csv
  2. Compute basic stats for one vehicle from its saved track points
  3. Produce a brief — Gemini if GEMINI_API_KEY is set, else a plain-text
     fallback built from the same structured facts (so the pipeline runs
     end-to-end even without an API key plugged in)

Deliberately NOT done yet (later Week 3 days):
  - Strict definition of "what the summary must always include" (Day 2)
  - Handling messy/edge-case tracks: gaps, 1-point tracks, bad values (Day 3)
  - Running across the whole dataset + saving results (Day 4)
  - Refactor into load/analyze/summarize/save modules + README (Day 5)

Usage:
    python summarize_vehicle.py vessels_snapshot_<ts>.csv tracks_snapshot_<ts>.csv VEHICLE_ID
    python summarize_vehicle.py vessels_snapshot_<ts>.csv tracks_snapshot_<ts>.csv   # summarizes first 5 vehicles
"""

import csv
import math
import os
import sys
from datetime import datetime


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def load_vessels(vessels_csv_path):
    """Load the saved vessels snapshot into a dict keyed by id."""
    with open(vessels_csv_path, newline="") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


def load_tracks(tracks_csv_path):
    """Load the saved tracks snapshot, grouped by vessel_id, sorted by point_index."""
    tracks = {}
    with open(tracks_csv_path, newline="") as f:
        for row in csv.DictReader(f):
            tracks.setdefault(row["vessel_id"], []).append(row)
    for vid in tracks:
        tracks[vid].sort(key=lambda r: int(r["point_index"]))
    return tracks


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_stats(track_rows):
    """Basic stats from a saved track (list of row dicts). First pass —
    no gap/edge-case handling yet, that's Day 3."""
    if len(track_rows) < 2:
        return {}

    pts = [(float(r["lat"]), float(r["lon"])) for r in track_rows]
    dist_km = sum(
        _haversine_km(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        for i in range(len(pts) - 1)
    )

    speeds = [float(r["speed"]) for r in track_rows if r["speed"] != "" and r["speed_known"] == "True"]

    t0 = datetime.fromisoformat(track_rows[0]["timestamp_utc"])
    t1 = datetime.fromisoformat(track_rows[-1]["timestamp_utc"])
    duration_min = round((t1 - t0).total_seconds() / 60, 1)

    return {
        "total_distance_km": round(dist_km, 1),
        "avg_speed": round(sum(speeds) / len(speeds), 1) if speeds else None,
        "max_speed": round(max(speeds), 1) if speeds else None,
        "duration_minutes": duration_min,
        "start_time_utc": track_rows[0]["timestamp_utc"],
        "end_time_utc": track_rows[-1]["timestamp_utc"],
        "start_pos": pts[0],
        "end_pos": pts[-1],
    }


def _fallback_summary(vessel, stats, su):
    """Plain-text brief with no LLM — keeps the pipeline runnable end-to-end
    without an API key. Always includes the same facts an LLM version would."""
    name = vessel.get("name", vessel["id"])
    if not stats:
        return f"{name}: insufficient track history to summarize (fewer than 2 points)."

    moved = f"traveled {stats['total_distance_km']} km over {stats['duration_minutes']} min"
    speed_part = (
        f", avg speed {stats['avg_speed']} {su} (max {stats['max_speed']} {su})"
        if stats["avg_speed"] is not None else ", speed data unavailable for this window"
    )
    return (
        f"{name} {moved}{speed_part}. "
        f"Moved from {stats['start_pos'][0]:.3f},{stats['start_pos'][1]:.3f} "
        f"to {stats['end_pos'][0]:.3f},{stats['end_pos'][1]:.3f}."
    )


def _gemini_summary(vessel, stats, su):
    """LLM-based brief. Only called if GEMINI_API_KEY is set."""
    from google import genai

    name = vessel.get("name", vessel["id"])
    prompt = (
        f"Write a 2-3 sentence plain-language movement brief for {name} "
        f"({vessel.get('type','vehicle')}). It traveled {stats['total_distance_km']} km "
        f"over {stats['duration_minutes']} minutes, average speed "
        f"{stats['avg_speed']} {su}, max speed {stats['max_speed']} {su}. "
        f"It moved from {stats['start_pos']} to {stats['end_pos']}. "
        f"No headers, no bullets, professional tone."
    )
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model="gemini-3.5-flash", contents=prompt)
    return response.text.strip()


def summarize_vehicle(vessel, track_rows):
    """Core function: one vessel row + its track rows -> one brief string.

    This is the v1 core logic for Day 1. It always returns *something*
    (never raises) so it's safe to run across many vehicles end-to-end.
    """
    su = "kn" if vessel.get("type") == "ship" else "kt"
    stats = compute_stats(track_rows)

    if GEMINI_API_KEY and stats:
        try:
            return _gemini_summary(vessel, stats, su)
        except Exception as e:
            return f"[Gemini failed, fallback used: {e}] " + _fallback_summary(vessel, stats, su)

    return _fallback_summary(vessel, stats, su)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python summarize_vehicle.py vessels_snapshot.csv tracks_snapshot.csv [VEHICLE_ID]")
        sys.exit(1)

    vessels = load_vessels(sys.argv[1])
    tracks = load_tracks(sys.argv[2])

    if len(sys.argv) >= 4:
        ids_to_run = [sys.argv[3]]
    else:
        ids_to_run = list(vessels.keys())[:5]  # quick smoke test on a handful

    for vid in ids_to_run:
        if vid not in vessels:
            print(f"{vid}: not found in vessels snapshot")
            continue
        brief = summarize_vehicle(vessels[vid], tracks.get(vid, []))
        print(f"\n--- {vid} ---")
        print(brief)
