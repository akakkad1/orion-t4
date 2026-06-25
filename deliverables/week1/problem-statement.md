## One Paragraph Problem Statement:
Aircraft and ships transiting the western hemisphere generate continuous streams of public position data, but analysts have no fast way to turn that flood into actionable insight. A vessel loitering off a coastline, a flight deviating from its corridor, or a ship going dark mid-transit are all visible in the raw data — but only to someone with the time and tools to look. This project builds a combined fleet dashboard and movement summarizer focused on the western hemisphere transit zone: an interactive map where analysts can visually scan active tracks, filter by area or behavior, and click any vessel or aircraft to instantly receive a plain-language brief describing where it went, how it moved, and what stands out — turning raw position data into the kind of concise, readable intelligence summary that drives faster, better decisions. 


## INPUT OUTPUT SKETCH

```
[ INPUT: Raw CSV/API ]
  ├── Timestamp
  ├── Hex ID / MMSI (Vehicle ID)
  ├── Latitude & Longitude
  └── Speed & Heading
          │
          ▼
[ PROCESSING ENGINE (src/) ]
  ├── Spatial Filter: Is it within our bounding box?
  ├── Track Aggregator: Group pings by Vehicle ID & sort by time
  └── Metric Calculator: Compute distance, stop durations, and max speeds
          │
          ▼
[ INTEGRATED OUTPUT (Streamlit App) ]
  ├── Visual Layer (Map): Interactive plot of sorted flight/ship tracks
  └── Narrative Layer (Sidebar): Text generation engine printing the analyst brief
```
