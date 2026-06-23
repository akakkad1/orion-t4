# Data Note — Movement Summarizer (WHTC Maritime & Aviation Intel)

## TL;DR

The deliverable asks for "a cleaned, saved dataset." This system is architected as a **live data feed, not a static dataset** — there is no dataset sitting on disk anywhere in the codebase. Vessel and aircraft positions are held in memory (`st.session_state.vessels`) for the duration of a session and are never persisted. This note explains why that's a deliberate design choice, documents the schema of the data as it exists in memory, and provides a snapshot utility (`snapshot_vessels.py`) that exports a cleaned, timestamped CSV/JSON capture on demand — so a saved artifact exists, while making clear it's a point-in-time sample of a live stream rather than "the" dataset.

---

## 1. Why there's no saved dataset by default

The app pulls from two live sources:

| Source | Mechanism | Update pattern |
|---|---|---|
| **OpenSky Network** (`fetch_opensky()`) | REST poll of `/api/states/all` + per-aircraft `/api/tracks/all` | On-demand, triggered by the "Fetch / Refresh" button |
| **AISStream.io** (`start_aisstream()`) | Persistent WebSocket (`wss://stream.aisstream.io/v0/stream`) | Continuous, pushed in a background daemon thread from app load |

Both feeds write into a single in-memory structure, `st.session_state.vessels`, keyed by `plane_<icao24>` or `ship_<mmsi>`. There is no `to_csv`, `to_sql`, or file-write call anywhere in the source — by design, this is an operational situational-awareness tool (think: a live ops-room map), not a data collection pipeline. Saving a single static dataset would misrepresent what the tool does and would go stale the moment it's written, since aircraft/ship positions are only meaningful in near-real time.

This is also why "cleaning" in the traditional sense (deduping a CSV, fixing column types) doesn't really apply upstream — the cleaning that exists today happens inline, per-record, at ingest time (see Section 3).

## 2. What data exists, and where

| Layer | Lives where | Persists across reruns? | Persists across sessions? |
|---|---|---|---|
| Raw API responses | Local variables inside `fetch_opensky()` / `on_message()` | No | No |
| Parsed vessel records | `st.session_state.vessels` (Python dict) | Yes, within a browser session | No — gone when the session ends |
| AI-generated briefs | `st.session_state.briefs` | Yes, within a browser session | No |

Nothing here touches disk. Restarting the Streamlit process, or even just the user closing the tab, wipes all of it.

## 3. Schema of an in-memory vessel record

Each entry in `st.session_state.vessels` is a dict with a shape that differs slightly by vessel type:

**Aircraft (`type: "plane"`):**

| Field | Type | Source | Notes |
|---|---|---|---|
| `id` | str | derived (`plane_<icao24>`) | |
| `name` / `callsign` | str | OpenSky `callsign` | falls back to ICAO24 hex if blank |
| `icao24` | str | OpenSky | unique aircraft identifier |
| `lat`, `lon` | float | OpenSky | current position |
| `altitude` | float (m) | OpenSky | |
| `speed` | float (kt) | OpenSky, converted from m/s (`× 1.944`) | |
| `course` | float (°) | OpenSky | |
| `vertical_rate` | float (m/s) | OpenSky | |
| `origin_country` | str | OpenSky | |
| `timestamp` | unix epoch | OpenSky | |
| `track` | list of `(lat, lon, ts, speed)` tuples | `/api/tracks/all`, speed backfilled from current state | up to full flight history |

**Ship (`type: "ship"`):**

| Field | Type | Source | Notes |
|---|---|---|---|
| `id` | str | derived (`ship_<mmsi>`) | |
| `name` | str | AISStream `MetaData.ShipName` | falls back to MMSI if blank |
| `mmsi` | str | AISStream | unique vessel identifier |
| `lat`, `lon` | float | AISStream `PositionReport` | |
| `speed` | float (kn) | AISStream `Sog` | |
| `course` | float (°) | AISStream `Cog` | |
| `flag`, `destination` | str | AISStream `MetaData` | destination often "Unknown" |
| `timestamp` | unix epoch | local capture time | |
| `track` | list of `(lat, lon, ts, speed)` tuples | appended live, capped at 200 points | rolling window, not full history |

**Known data-quality caveats inherited from the live feeds (carried into any snapshot):**
- Aircraft `track` points have speed = 0.0 for every point except the most recent (the OpenSky tracks endpoint doesn't return speed; only the last point is backfilled from the live state vector).
- Ship `track` is a rolling 200-point buffer per vessel, not the full history — older points are silently dropped.
- `destination` for ships is frequently `"Unknown"` — it's self-reported by the vessel and not always populated.
- Records for a vessel only exist once at least one valid position report has been received; there's no canonical list of "all vessels in the WHTC," only "all vessels we've seen since the session started."

## 4. What "cleaned, saved" means here

Since there's no dataset to clean in the traditional sense, we built `snapshot_vessels.py`, a small export utility that:

1. Takes the current in-memory `vessels` dict (same shape used by the app) as input.
2. Flattens each vessel's latest state into one row (drops the nested track list into a separate row-per-point table).
3. Applies basic cleaning:
   - Drops records with null/zero-zero coordinates.
   - Coerces numeric fields and fills missing optional fields (`destination`, `origin_country`) with `"Unknown"` rather than leaving blanks.
   - Removes the duplicate placeholder speed=0.0 track points described above where a better value is available, and flags interpolated points.
4. Writes two timestamped, versioned files: `vessels_snapshot_<UTC timestamp>.csv` (one row per vessel, current state) and `tracks_snapshot_<UTC timestamp>.csv` (one row per track point, for movement analysis).

This produces a real, saved, cleaned artifact you can hand in — but it is explicitly a **point-in-time sample of a live feed**, not an authoritative, continuously maintained dataset. Re-running it five minutes later will produce a different file with different vessels and positions, because that's the nature of the system being documented.
