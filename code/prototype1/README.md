# Flight & Vessel Intelligence Tool

---

> ## ⚠️ IMPORTANT — READ BEFORE DOING ANYTHING
>
> **1. Copy `main.py` to your local machine before running it.**
> Do NOT run it directly from the GitHub repository folder.
>
> **2. Never commit the `data/` folder to GitHub.**
> Every run generates raw CSVs, cleaned CSVs, and HTML maps under `data/`.
> These files can be large and contain pulled API data — they do not belong in the repo.
>
> **3. Never commit your `.env` file.**
> Your API keys live in `.env` — if this gets pushed to GitHub, your keys are exposed publicly and must be rotated immediately.

---

## What This Tool Does

Pulls, cleans, and maps real-time and historical position data for:
- **Aircraft** — flight arrivals at two airports of your choice (OpenSky Network)
- **Marine vessels** — live AIS vessel positions for a region of your choice (AISStream)

Each run produces a timestamped folder under `data/` with raw CSVs, cleaned CSVs, and interactive HTML maps.

---

## Setup

### 1. Copy the file locally
Copy `main.py` to a folder on your local machine. Do **not** run it from inside the cloned repo.

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Create your `.env` file
In the same folder as `main.py`, create a file called `.env` with your credentials:
```
OPENSKY_CLIENT_ID=your_opensky_username
OPENSKY_CLIENT_SECRET=your_opensky_password
AISSTREAM_API_KEY=your_aisstream_key
```
> Register for free at [opensky-network.org](https://opensky-network.org) and [aisstream.io](https://aisstream.io).

### 4. Run the tool
```bash
python main.py
```

---

## What Happens When You Run It

1. You are prompted to enter two ICAO airport codes (e.g. `KATL`, `KJFK`)
2. The tool validates each code against the airport database and asks you to confirm
3. OpenSky pulls one hour of arrival data for each airport (June 1 2026, 14:00–15:00 UTC)
4. AIS collects live vessel positions for 10 seconds from the configured bounding box
5. All data is cleaned and saved
6. Interactive HTML maps are generated for each dataset

---

## Output Structure

Every run creates a new timestamped folder so runs never overwrite each other:

```
data/
└── YYYY-MM-DD hhmmss/
    ├── raw/
    │   ├── opensky_{ICAO}_raw.csv
    │   ├── opensky_{ICAO}_raw.csv
    │   └── ais_raw.csv
    ├── clean/
    │   ├── opensky_{ICAO}_clean.csv
    │   ├── opensky_{ICAO}_clean.csv
    │   └── ais_clean.csv
    └── graphs/
        ├── opensky_{ICAO}_map.html
        ├── opensky_{ICAO}_map.html
        └── ais_map.html
```

Open any `.html` file in your browser — fully interactive, zoom and hover to explore.

---

## Maps

### Flight route maps (`opensky_*_map.html`)
- Red marker at the arrival airport
- Blue lines from every departure airport — thicker lines = more flights
- Hover any line or dot for airport code and flight count

### Vessel map (`ais_map.html`)
- Heatmap layer showing vessel density
- Color-coded dots by speed: 🟢 < 5 kn (anchored) · 🟠 5–15 kn · 🔴 > 15 kn
- Hover any dot for MMSI, speed, heading, and timestamp

---

## Data Sources

| Source | Data | Access |
|--------|------|--------|
| [OpenSky Network](https://opensky-network.org) | Historical flight arrivals | Free account required |
| [AISStream.io](https://aisstream.io) | Live vessel AIS positions | Free API key required |

---

## What NOT to Commit

| Item | Why |
|------|-----|
| `data/` folder | Contains pulled API data — can be large, regenerated any time |
| `.env` file | Contains your private API keys |

The `.gitignore` covers both. Before pushing, run `git status` and confirm neither appears in the staged files.
