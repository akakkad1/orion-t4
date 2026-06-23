# Movement Summarizer — Snapshot & Summarize Pipeline

This README covers the saved-data side of the project: turning the live app's
in-memory data into saved files, and generating a written movement brief for
each vehicle from those saved files.

## How it fits together

The live Streamlit app (`app.py`) tracks planes and ships in real time —
positions update constantly while the app runs, and none of it is saved to
disk by default. The two scripts below add a saved, reproducible layer on
top of that live view:

```
[ Live app ]  -->  [ snapshot_vessels.py ]  -->  [ summarize_vehicle.py ]
  in-memory          saves a freeze-frame          reads the saved CSVs,
  vehicle data        to two CSV files              writes a brief per vehicle
```

## Step 1 — Run the live app and export a snapshot

1. Run the app as usual:
   ```bash
   streamlit run app.py
   ```
2. Let it collect some data (wait for AIS ship pings, and/or click
   **"Fetch / Refresh OpenSky"** for aircraft).
3. In the sidebar, under **Snapshot Export**, click **"⬇ Download
   vessels.json"**. This saves a JSON file with everything currently in
   memory, named like `vessels_20260623T211907Z.json`.

## Step 2 — Turn the JSON into cleaned, saved CSVs

```bash
python snapshot_vessels.py vessels_<timestamp>.json
```

This produces two files in the current directory:

| File | Contents |
|---|---|
| `vessels_snapshot_<timestamp>.csv` | One row per vehicle — name, type, current position, speed, etc. |
| `tracks_snapshot_<timestamp>.csv` | One row per track point — the breadcrumb trail of positions over time for each vehicle |

What it does along the way:
- Drops any vehicle with no usable position (e.g. lat/lon stuck at 0,0).
- Flags aircraft track points where speed isn't actually known (the
  OpenSky track history only has real speed data on the most recent point)
  instead of treating a missing value as a real zero.

This is a **point-in-time export**, not a live or continuously updating
dataset — running it again later, after the app has collected more data,
produces a new, different snapshot. See `data_note.md` for the full
explanation of why the system is built this way.

Optional: pass a second argument to choose the output folder:
```bash
python snapshot_vessels.py vessels_<timestamp>.json ./snapshots
```

## Step 3 — Generate written summaries from the saved CSVs

```bash
python summarize_vehicle.py vessels_snapshot_<timestamp>.csv tracks_snapshot_<timestamp>.csv
```

By default this prints a brief for the first 5 vehicles in the file. To
summarize one specific vehicle, pass its id:

```bash
python summarize_vehicle.py vessels_snapshot_<timestamp>.csv tracks_snapshot_<timestamp>.csv plane_abc123
```

For each vehicle, it computes (from the saved track points):
- Total distance traveled
- Average and max speed
- Duration of the tracked window
- Start and end position

Then it writes a short brief using those facts. If a `GEMINI_API_KEY`
environment variable is set, it asks Gemini to phrase the brief in natural
language. If no key is set, or the Gemini call fails for any reason, it
automatically falls back to a plain templated sentence built from the same
facts — so this step always produces output, with or without an API key.

**Edge case handling (current version):** if a vehicle has fewer than 2
track points, there's no path to measure distance/speed from, so it
returns `"insufficient track history to summarize"` instead of crashing or
guessing.

## Example output

```
--- plane_abc123 ---
UAL123 traveled 97.8 km over 10.0 min, avg speed 450.0 kt (max 450.0 kt).
Moved from 25.000,-81.000 to 25.500,-80.200.

--- ship_222333 ---
EVER GIVEN traveled 15.3 km over 5.0 min, avg speed 11.7 kn (max 12.4 kn).
Moved from 18.400,-77.100 to 18.500,-77.000.

--- ship_lonepoint ---
LONE PINGER: insufficient track history to summarize (fewer than 2 points).
```

## Files in this pipeline

| File | Purpose |
|---|---|
| `app.py` | Live app — tracking, map, AI briefs, and the snapshot export button |
| `snapshot_vessels.py` | Exports live data to cleaned, saved CSVs |
| `summarize_vehicle.py` | Reads saved CSVs, generates a movement brief per vehicle |
| `data_note.md` | Explains the live-data architecture and known data-quality caveats |

## Known limitations (to be addressed in later iterations)

- No strict, locked-down definition yet of exactly which facts every brief
  must include — current version includes whatever `compute_stats()` finds.
- Not yet tested against tracks with gaps, very few points beyond the
  1-point case, or unusual/extreme values.
- Doesn't yet run across an entire snapshot and save all results to a
  file — currently prints to the console for a handful of vehicles at a
  time.
