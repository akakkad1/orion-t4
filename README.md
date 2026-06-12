# Orion Intelligence — Movement Data Analysis
**2026 VTSP Technical Track · Team 4 (Anvita Kar, Adit Kakkad, Simon Joeng, Vincent Tjoeng)**

> Turning raw aircraft and ship position data into insight: anomalies, summaries, and patterns hidden in the noise.

---

## What this project does

Aircraft and ships constantly broadcast where they are. This project processes that stream of public position data — from OpenSky (flights) and AISStream (ships) — and surfaces the stories inside it: vessels going dark, aircraft flying odd patterns, ships lingering where they shouldn't.

**Build chosen: B + C (Movement Summarizer + Fleet Dashboard)**

---

## Repo structure

```
├── data/               # Saved sample datasets (not raw API keys)
│   ├── sample_flights.csv
│   └── sample_ships.csv
├── notebooks/          # Exploration and analysis
│   ├── 01_data_pull.ipynb
│   ├── 02_cleaning.ipynb
│   └── 03_analysis.ipynb
├── src/                # Production code
│   ├── fetch.py        # Data ingestion from OpenSky / AISStream
│   ├── clean.py        # Data cleaning and normalisation
│   ├── detect.py       # Core logic (anomaly / summary / dashboard)
│   └── app.py          # Streamlit app entry point
├── docs/
│   ├── team-charter.md
│   └── weekly-notes.md
├── tests/
├── requirements.txt
└── README.md
```

---

## Setup

**Requirements:** Python 3.11, git

```bash
# 1. Clone the repo
git clone (https://github.com/akakkad1/orion-t4.git)
cd orion-t4

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your API keys
cp .env.example .env
# Edit .env and fill in OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET, AISSTREAM_API_KEY
```

**Never commit your `.env` file.** It's already in `.gitignore`.

---

## Data sources

| Source | What it provides | Docs |
|--------|-----------------|------|
| [OpenSky Network](https://opensky-network.org) | Live and historical ADS-B aircraft positions | [API docs](https://openskynetwork.github.io/opensky-api/rest.html) |
| [AISStream](https://aisstream.io) | Live global AIS ship positions via WebSocket | [Docs](https://aisstream.io/documentation) |

Both are free for non-commercial use. Sign up for accounts before running `fetch.py`.

---

## Running the app

```bash
# Pull a fresh data sample
python src/fetch.py

# Run the Streamlit dashboard
streamlit run src/app.py
```

---

## Weekly progress

| Week | Goal | Status |
|------|------|--------|
| 1 | Set up tools, understand data, choose build | 🔄 In progress |
| 2 | Pull real data, clean it, explore it | ⬜ Not started |
| 3 | Build core feature (detect / summarise / visualise) | ⬜ Not started |
| 4 | Evaluate honestly, improve, add interface | ⬜ Not started |
| 5 | Final report and demo for Orion leadership | ⬜ Not started |

---

## Key decisions log

_We'll track important design choices here so anyone reading the repo understands why things are built the way they are._

| Date | Decision | Why |
|------|----------|-----|
| 6/11/2026 | Chose Option B and C | We decided that after completing option B, option C would be a great way to display our data. After reiteration with Mr. Nagalingam, we have agreed to work on both option B and Option C. |

---

## Notes on data quirks

Things we've learned about the data that anyone working in this repo should know:

- OpenSky callsigns are padded to 8 characters — always call `.strip()` before matching
- Unix timestamps need `datetime.fromtimestamp()` to be human-readable
- AIS `TrueHeading` of `511` means "not available" — treat as null
- AIS `NavigationalStatus` of `15` means "not defined" — treat as null
- Duplicate MMSI numbers exist — two ships can share one ID

---

## Useful links

- [OpenSky API reference](https://openskynetwork.github.io/opensky-api/rest.html)
- [AISStream documentation](https://aisstream.io/documentation)
- [pandas 10-minute intro](https://pandas.pydata.org/docs/user_guide/10min.html)
- [folium docs](https://python-visualization.github.io/folium/)
- [Streamlit get started](https://docs.streamlit.io/get-started)
- [Git & GitHub crash course](https://www.youtube.com/watch?v=RGOj5yH7evk)

---

## License

For educational use only as part of the 2026 VTSP program. Data sourced from OpenSky Network and AISStream under their respective non-commercial terms.
