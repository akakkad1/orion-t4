import os                      # For environment variable access and directory creation
import json                    # For parsing WebSocket JSON messages from AISStream
import asyncio                 # For asynchronous operations (WebSocket connection)
import websockets              # For WebSocket client connection to AISStream
import pandas as pd            # For data manipulation and CSV I/O
import folium                  # For creating interactive maps
from folium.plugins import HeatMap  # Heatmap layer plugin for visualizing vessel density
import airportsdata            # For ICAO airport code lookup (lat/lon coordinates)
from airports import airports
from datetime import datetime, timezone  # For timestamp handling in UTC
from dotenv import load_dotenv  # For loading environment variables from .env file
from opensky_api import OpenSkyApi  # OpenSky API wrapper for flight data access

# Load environment variables from .env file (contains API keys and credentials)
load_dotenv()
# Retrieve API credentials from environment variables
OPENSKY_CLIENT_ID     = os.getenv("OPENSKY_CLIENT_ID")      # OpenSky API username
OPENSKY_CLIENT_SECRET = os.getenv("OPENSKY_CLIENT_SECRET")  # OpenSky API password
AISSTREAM_API_KEY     = os.getenv("AISSTREAM_API_KEY")      # AISStream API authentication key

# Create directory structure for raw, cleaned, and visualization output data
# exist_ok=True prevents errors if directories already exist
RUN_ID = datetime.now().strftime("%Y-%m-%d %H%M%S")  # Unique identifier for this run (timestamp)

os.makedirs(f"code/prototype1/data/{RUN_ID}/raw",    exist_ok=True) # Store raw API responses
os.makedirs(f"code/prototype1/data/{RUN_ID}/clean",  exist_ok=True) # Store cleaned/processed data
os.makedirs(f"code/prototype1/data/{RUN_ID}/graphs", exist_ok=True) # Store generated HTML map files

# Define the time window for historical flight data queries
# All OpenSky queries will retrieve flight data within this 1-hour window
# Year, Month, Date, Hour, Minute (UTC timezone)
start_time = datetime(2026, 6, 1, 14, 0)  # Start: June 1, 2026 at 2:00 PM UTC
end_time   = datetime(2026, 6, 1, 15, 0)  # End: June 1, 2026 at 3:00 PM UTC


# Load complete ICAO airport database (e.g., "KATL" → Atlanta, "KJFK" → New York JFK)
# This dictionary will be used to look up latitude/longitude coordinates for any ICAO code
AIRPORTS = airportsdata.load("ICAO")  # full ICAO lookup table

def airport_coords(icao: str):
    """
    Return (lat, lon) for an ICAO code, or None if not found.
    
    This helper function converts ICAO airport codes (like "KATL") into geographic
    coordinates (latitude, longitude) needed for mapping flight routes.
    
    Args:
        icao (str): 4-letter ICAO airport code (e.g., "KATL", "KJFK")
    
    Returns:
        tuple: (latitude, longitude) if found, None otherwise
    
    Example:
        >>> airport_coords("KATL")
        (33.6407, -84.4277)  # Atlanta airport coordinates
    """
    # Validate input: check if icao is provided and is a string type
    if not icao or not isinstance(icao, str):
        return None
    
    # Look up the airport code in the AIRPORTS dictionary (uppercase to standardize)
    a = AIRPORTS.get(icao.strip().upper())
    
    # If airport exists in database, extract and return latitude/longitude
    if a:
        return (a["lat"], a["lon"])
    
    # Return None if ICAO code not found in airport database
    return None



# ─── OPENSKY ──────────────────────────────────────────────────────────────────
# Section: Pull, clean, and visualize flight arrival data from OpenSky API
# OpenSky Network provides real-time flight tracking data via a REST API

def pull_opensky(airport: str) -> pd.DataFrame:
    """
    Pull flight arrival data from OpenSky API for a specific airport during the time window.
    
    This function connects to OpenSky API, authenticates with credentials, and retrieves
    all flights that arrived at the specified airport between start_time and end_time.
    Results are saved as raw CSV for audit trail.
    
    Args:
        airport (str): ICAO airport code (e.g., "KATL", "KJFK")
    
    Returns:
        pd.DataFrame: DataFrame with columns: icao24, callsign, estDepartureAirport, 
                      estArrivalAirport, firstSeen, lastSeen
    """
    # Initialize OpenSky API client with username/password authentication
    api = OpenSkyApi(client_id=OPENSKY_CLIENT_ID, client_secret=OPENSKY_CLIENT_SECRET)
    
    # Convert Python datetime objects to Unix timestamps (seconds since 1970-01-01)
    # required by the OpenSky API
    start_ts = int(start_time.timestamp())  # Start time as Unix timestamp
    end_ts   = int(end_time.timestamp())    # End time as Unix timestamp

    # Print status message showing what airport and time range we're querying
    print(f"[OpenSky] Pulling {airport} arrivals {start_time} → {end_time} …")
    
    # Query OpenSky API for all arrivals at the specified airport in the time window
    # Returns list of Flight objects (namedtuple-like) with flight information
    arrivals = api.get_arrivals_by_airport(airport, start_ts, end_ts)

    # Handle empty response: if no flights found, log message and return empty DataFrame
    if not arrivals:
        print(f"[OpenSky] No arrivals returned for {airport}.")
        return pd.DataFrame()

    # Convert list of Flight objects into list of dictionaries, extracting key fields
    df = pd.DataFrame([{
        "icao24":              f.icao24,                    # Unique aircraft identifier
        "callsign":            f.callsign,                  # Flight callsign (e.g., "UAL123")
        "estDepartureAirport": f.estDepartureAirport,       # Estimated origin airport
        "estArrivalAirport":   f.estArrivalAirport,         # Destination (should match airport param)
        "firstSeen":           f.firstSeen,                 # Unix timestamp: when radar first detected flight
        "lastSeen":            f.lastSeen,                  # Unix timestamp: when radar last detected flight
    } for f in arrivals])

    # Save raw API response to CSV file (unprocessed, for data integrity backup)
    df.to_csv(f"code/prototype1/data/{RUN_ID}/raw/opensky_{airport}_raw.csv", index=False)
    # Print confirmation with file path and row/column counts (shape)
    print(f"  Saved raw  → code/prototype1/data/{RUN_ID}/raw/opensky_{airport}_raw.csv  {df.shape}")
    
    # Return the DataFrame for further processing
    return df


def clean_opensky(df: pd.DataFrame, airport: str) -> pd.DataFrame:
    """
    Clean and validate flight data from OpenSky API.
    
    This function applies data quality steps:
    - Convert Unix timestamps to human-readable datetime objects (UTC timezone)
    - Remove leading/trailing whitespace from text fields
    - Drop duplicate rows (same flight appearing multiple times)
    - Remove rows with missing or empty aircraft IDs
    - Calculate actual flight duration in minutes
    
    Args:
        df (pd.DataFrame): Raw flight data from pull_opensky()
        airport (str): ICAO airport code (used only for output filename)
    
    Returns:
        pd.DataFrame: Cleaned and validated flight data
    """
    # If input DataFrame is empty, return it unchanged
    if df.empty:
        return df
    
    # Create a copy to avoid modifying the original DataFrame
    df = df.copy()
    
    # Convert Unix timestamps (seconds) to datetime objects with UTC timezone
    # This makes firstSeen/lastSeen human-readable (e.g., "2026-06-01 14:30:45+00:00")
    df["firstSeen"] = pd.to_datetime(df["firstSeen"], unit="s", utc=True)
    df["lastSeen"]  = pd.to_datetime(df["lastSeen"],  unit="s", utc=True)
    
    # Strip whitespace from ICAO24 (aircraft identifier) - handles leading/trailing spaces
    df["icao24"]    = df["icao24"].str.strip()
    # Strip whitespace from callsign (flight number) - handles leading/trailing spaces
    df["callsign"]  = df["callsign"].str.strip()
    
    # Remove completely duplicate rows (all columns identical)
    df = df.drop_duplicates()
    
    # Remove rows where icao24 is missing (NaN) or is an empty string
    # These rows have no aircraft identifier and cannot be tracked
    df = df[df["icao24"].notna() & (df["icao24"] != "")]
    
    # Calculate flight duration in minutes: (landing time - takeoff time) / 60 seconds
    # Round to 1 decimal place for readability
    df["duration_min"] = ((df["lastSeen"] - df["firstSeen"])
                          .dt.total_seconds() / 60).round(1)
    
    # Save cleaned data to CSV file for audit trail
    df.to_csv(f"code/prototype1/data/{RUN_ID}/clean/opensky_{airport}_clean.csv", index=False)
    # Print confirmation with file path and row/column counts
    print(f"  Saved clean → code/prototype1/data/{RUN_ID}/clean/opensky_{airport}_clean.csv  {df.shape}")
    
    # Return cleaned DataFrame for further processing (mapping)
    return df


def graph_opensky(df: pd.DataFrame, airport: str):
    """
    Create an interactive Folium map showing flight routes to arrival airport.
    
    Visualization elements:
    - Red marker at arrival airport
    - Blue lines from each departure airport to arrival airport (width = flight frequency)
    - Blue circles at each departure airport (size indicates frequency)
    - Tooltip info on hover (flight count, airport codes)
    
    Args:
        df (pd.DataFrame): Cleaned flight data from clean_opensky()
        airport (str): ICAO airport code (destination airport)
    
    Returns:
        None (saves HTML map file to disk)
    """
    # If DataFrame is empty, no data to visualize - return early
    if df.empty:
        return

    # Get latitude/longitude coordinates for the arrival airport
    dest_coords = airport_coords(airport)
    
    # If airport coordinates not found (not in database), log and skip visualization
    if not dest_coords:
        print(f"  [graph] Could not find coords for {airport}, skipping map.")
        return

    # Create a new Folium map centered at arrival airport
    # zoom_start=4 gives regional view (US state-level)
    # tiles="CartoDB positron" uses clean, simple map tiles
    m = folium.Map(location=dest_coords, zoom_start=4, tiles="CartoDB positron")

    # Add a marker at the arrival airport (destination)
    # Color=red, icon=plane to visually distinguish this as the key location
    folium.Marker(
        dest_coords,
        tooltip=f"✈ {airport} (arrival)",  # Hover text showing airport code
        icon=folium.Icon(color="red", icon="plane", prefix="fa"),  # Red plane icon
    ).add_to(m)

    # Count how many flights came from each departure airport
    # This frequency will be used to determine line thickness (more flights = thicker line)
    route_counts = (
        df["estDepartureAirport"]          # Get list of all departure airports
        .fillna("Unknown")                 # Replace missing values with "Unknown"
        .value_counts()                    # Count occurrences of each airport
        .to_dict()                         # Convert to dictionary {airport: count}
    )
    
    # Find the maximum count to use for scaling line weights (for visual proportion)
    # If no routes exist, use 1 as default to avoid division errors
    max_count = max(route_counts.values()) if route_counts else 1

    # Track which departure airports we've already drawn (to avoid duplicates)
    # A set keeps unique values and enables fast lookup
    drawn = set()
    
    # Iterate through each row in the flight data
    for _, row in df.iterrows():
        # Get the departure airport for this flight
        dep = row["estDepartureAirport"]
        
        # Skip if we've already drawn this departure airport (avoid duplicate lines)
        # Also skip if departure airport is not a string (is NaN or None)
        if dep in drawn or not isinstance(dep, str):
            continue
        
        # Look up latitude/longitude coordinates for the departure airport
        dep_coords = airport_coords(dep)
        
        # If coordinates not found, skip this route (airport not in database)
        if not dep_coords:
            continue

        # Get count of flights from this departure airport
        count  = route_counts.get(dep, 1)
        
        # Scale line weight (thickness) from 1 to 6 pixels based on flight frequency
        # More frequent routes get thicker lines for visual prominence
        weight = 1 + 5 * (count / max_count)

        # Draw a line from departure airport to arrival airport
        # Color blue (#1a6faf), opacity 0.6 for semi-transparency
        # Line weight scales with frequency
        folium.PolyLine(
            [dep_coords, dest_coords],     # Start and end coordinates
            color="#1a6faf",               # Blue color
            weight=weight,                 # Line thickness (1-6 pixels)
            opacity=0.6,                   # Semi-transparent (60% opaque)
            tooltip=f"{dep} → {airport}  ({count} flights)",  # Hover info
        ).add_to(m)

        # Draw a blue circle marker at the departure airport location
        # Indicates this is a departure point
        folium.CircleMarker(
            dep_coords,                    # Center of circle
            radius=4,                      # Circle radius in pixels
            color="#1a6faf",               # Blue color matching the line
            fill=True,                     # Filled circle (not just outline)
            fill_opacity=0.8,              # 80% opaque
            tooltip=f"{dep}  ({count} flights)",  # Hover info showing flight count
        ).add_to(m)

        # Mark this departure airport as drawn (add to set)
        # Prevents drawing duplicate lines/circles for repeated departures
        drawn.add(dep)

    # Save the map as an interactive HTML file
    path = f"code/prototype1/data/{RUN_ID}/graphs/opensky_{airport}_map.html"
    m.save(path)
    
    # Print confirmation with file path and number of routes visualized
    print(f"  Saved map  → {path}  ({len(drawn)} routes drawn)")


# ─── AISSTREAM ────────────────────────────────────────────────────────────────
# Section: Pull, clean, and visualize vessel position data from AISStream WebSocket
# AISStream provides real-time Automatic Identification System (AIS) data for maritime vessels

async def _collect_ais(bbox: list, max_messages: int = 200) -> list[dict]:
    """
    Collect vessel position reports from AISStream WebSocket in real-time.
    
    This asynchronous function:
    - Connects to AISStream WebSocket API
    - Authenticates with API key
    - Subscribes to a geographic bounding box
    - Collects PositionReport messages (vessel lat/lon/speed/heading)
    - Collects for 10 seconds or until max_messages received
    
    Args:
        bbox (list): Bounding box as [[min_lat, min_lon], [max_lat, max_lon]]
                     Example: [[31.0, -81.5], [32.2, -80.5]] for Georgia coast
        max_messages (int): Maximum position reports to collect (default 200)
    
    Returns:
        list[dict]: List of vessel position reports with keys:
                    received_utc, mmsi, latitude, longitude, sog, cog, heading, nav_status
    """
    # Initialize empty list to store collected vessel position reports
    records = []
    
    # Print status message showing data collection is starting
    print(f"[AIS] Connecting … collecting for 10 seconds …")
    
    # Try-except block to handle WebSocket errors gracefully
    try:
        # Establish WebSocket connection to AISStream server
        # open_timeout=15 seconds - fail if connection not established within 15 seconds
        async with websockets.connect("wss://stream.aisstream.io/v0/stream",
                                      open_timeout=15) as ws:
            # Send authentication and subscription request as JSON
            await ws.send(json.dumps({
                "APIKey":             AISSTREAM_API_KEY,           # API authentication key
                "BoundingBoxes":      [bbox],                      # Geographic filter for this region
                "FilterMessageTypes": ["PositionReport"],          # Only vessel position reports
            }))
            
            # Print status showing subscription is complete
            print("[AIS] Subscribed — waiting for messages …")

            # Define inner async function to collect messages from WebSocket
            async def collect():
                # Loop indefinitely while WebSocket is open
                async for raw in ws:
                    # Parse incoming JSON message from AISStream
                    msg = json.loads(raw)
                    
                    # Skip messages that are not PositionReports (ignore other message types)
                    if msg.get("MessageType") != "PositionReport":
                        continue
                    
                    # Extract the PositionReport data from the message structure
                    pr = msg["Message"]["PositionReport"]
                    
                    # Add vessel record to our collection list
                    # Capture UTC timestamp when we received this message
                    records.append({
                        "received_utc": datetime.now(timezone.utc).isoformat(),  # ISO 8601 timestamp
                        "mmsi":         pr.get("UserID"),          # Maritime Mobile Service Identity
                        "latitude":     pr.get("Latitude"),         # Vessel latitude coordinate
                        "longitude":    pr.get("Longitude"),        # Vessel longitude coordinate
                        "sog":          pr.get("Sog"),              # Speed Over Ground (knots)
                        "cog":          pr.get("Cog"),              # Course Over Ground (degrees)
                        "heading":      pr.get("TrueHeading"),      # Vessel heading (degrees)
                        "nav_status":   pr.get("NavigationalStatus"),  # Navigation status code
                    })
                    
                    # Print progress: message count and vessel details
                    print(f"  [{len(records):3d}] MMSI={pr.get('UserID')}  "
                          f"Lat={pr.get('Latitude'):.4f}  Lon={pr.get('Longitude'):.4f}")
                    
                    # Stop collecting if we've reached the maximum message count
                    if len(records) >= max_messages:
                        break

            # Run the collect() function with a 10-second timeout
            # asyncio.wait_for() cancels collect() if it doesn't complete within timeout
            await asyncio.wait_for(collect(), timeout=10)

    # Catch timeout exception (normal end of 10-second collection window)
    except asyncio.TimeoutError:
        print(f"[AIS] 10 seconds up — got {len(records)} records.")
    
    # Catch any other exception (network errors, JSON parsing errors, etc.)
    except Exception as exc:
        print(f"[AIS] Error: {exc}")

    # Return list of all collected vessel position records
    return records


def pull_ais(bbox: list) -> pd.DataFrame:
    records = asyncio.run(_collect_ais(bbox))
    if not records:
        print("[AIS] No records collected.")
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df.to_csv("code/prototype1/data/{RUN_ID}/raw/ais_raw.csv", index=False)
    print(f"  Saved raw  → code/prototype1/data/{RUN_ID}/raw/ais_raw.csv  {df.shape}")
    return df


def clean_ais(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and validate vessel position data from AISStream.
    
    This function applies data quality steps:
    - Remove completely duplicate rows (same vessel at same location/time)
    - Drop rows with missing latitude or longitude (unmappable)
    - Filter out impossible coordinates (lat outside -90 to 90, lon outside -180 to 180)
    - Remove vessels with unrealistic speeds (> 50 knots, likely data errors)
    
    Args:
        df (pd.DataFrame): Raw vessel data from pull_ais()
    
    Returns:
        pd.DataFrame: Cleaned and validated vessel position data
    """
    # If input DataFrame is empty, return it unchanged
    if df.empty:
        return df
    
    # Remove completely duplicate rows (all columns identical)
    # This handles vessels sending duplicate position reports
    df = df.drop_duplicates()
    
    # Drop rows where latitude OR longitude is missing (NaN)
    # Can't map vessels without coordinates
    df = df.dropna(subset=["latitude", "longitude"])
    
    # Filter to valid geographic coordinates
    # Latitude must be between -90 and +90 (pole to pole)
    # Longitude must be between -180 and +180 (international date line)
    # This removes data with GPS/transmission errors
    df = df[df["latitude"].between(-90, 90) & df["longitude"].between(-180, 180)]
    
    # Filter vessel speed: keep rows where speed is NaN (not reported) OR <= 50 knots
    # Removes impossible speeds (vessel exceeding 50 knots is likely data error)
    # 50 knots ≈ 57 mph (reasonable max for most vessels)
    df = df[df["sog"].isna() | (df["sog"] <= 50)]
    
    # Save cleaned data to CSV file (processed and validated)
    df.to_csv("code/prototype1/data/{RUN_ID}/clean/ais_clean.csv", index=False)
    
    # Print confirmation with file path and data shape (rows, columns)
    print(f"  Saved clean → code/prototype1/data/{RUN_ID}/clean/ais_clean.csv  {df.shape}")
    
    # Return cleaned DataFrame for visualization/mapping
    return df


def graph_ais(df: pd.DataFrame):
    """
    Create an interactive Folium map showing vessel positions with heatmap and color-coded speed.
    
    Visualization elements:
    - Heatmap layer: shows vessel density (more vessels = more intense color)
    - Color-coded markers: green (< 5 kn), orange (5-15 kn), red (> 15 kn)
    - Tooltip: hovering shows MMSI, speed, heading, timestamp
    - Legend: explains the color coding for vessel speeds
    
    Args:
        df (pd.DataFrame): Cleaned vessel data from clean_ais()
    
    Returns:
        None (saves HTML map file to disk)
    """
    # If DataFrame is empty, no data to visualize - print message and return
    if df.empty:
        print("  [graph] No AIS data to map.")
        return

    # Calculate the geographic center of all vessel positions
    # This becomes the center point of the map
    center_lat = df["latitude"].mean()   # Average of all latitudes
    center_lon = df["longitude"].mean()  # Average of all longitudes

    # Create new Folium map centered at the mean vessel position
    # zoom_start=8 gives a regional view (roughly city/county level)
    # tiles="CartoDB positron" uses clean, minimal map tiles
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8,
                   tiles="CartoDB positron")

    # Create heatmap layer showing vessel density
    # More vessels in an area = warmer/brighter color
    # Extract only latitude/longitude columns, drop any NaN values, convert to list of lists
    heat_data = df[["latitude", "longitude"]].dropna().values.tolist()
    
    # Add heatmap to map
    # radius=15: size of each heatmap point in pixels
    # blur=10: gaussian blur smoothness
    # min_opacity=0.4: minimum transparency (40% opaque minimum)
    HeatMap(heat_data, radius=15, blur=10, min_opacity=0.4).add_to(m)

    # Add individual vessel markers colored by speed (speed over ground)
    # Iterate through each vessel position report
    for _, row in df.iterrows():
        # Get vessel speed, or 0 if not reported (NaN)
        sog = row.get("sog") or 0
        
        # Assign color based on speed categories (realistic vessel speeds)
        # Green: < 5 kn = stationary/anchored/slow harbor movement
        # Orange: 5-15 kn = typical cruising speed
        # Red: > 15 kn = high speed (rare for most vessels)
        if sog < 5:
            color = "green"      # Anchored or moving very slowly
        elif sog < 15:
            color = "orange"     # Normal cruising speed
        else:
            color = "red"        # High speed (cargo ships ~15-20 kn, speedboats faster)

        # Add circle marker at vessel position
        # These are small circles (radius 5 px) showing each vessel location
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],  # Vessel coordinates
            radius=5,                                       # Circle radius in pixels
            color=color,                                    # Color based on speed
            fill=True,                                      # Filled (not just outline)
            fill_opacity=0.8,                               # 80% opaque
            # Tooltip: information shown when hovering over marker
            tooltip=(
                f"MMSI: {row['mmsi']}<br>"                          # Vessel identifier
                f"SOG: {sog} kn<br>"                                # Speed in knots
                f"Heading: {row.get('heading')}<br>"                # Direction vessel is heading
                f"Time: {row.get('received_utc', '')[:19]}"         # Timestamp (remove microseconds)
            ),
        ).add_to(m)

    # Create a custom legend explaining the speed color scheme
    # Fixed position at bottom-left of map
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:10px;border-radius:8px;
                border:1px solid #ccc;font-size:13px;">
        <b>Vessel speed (SOG)</b><br>
        <span style="color:green">●</span> &lt; 5 kn (anchored/slow)<br>
        <span style="color:orange">●</span> 5–15 kn<br>
        <span style="color:red">●</span> &gt; 15 kn
    </div>
    """
    
    # Add legend HTML element to the map
    m.get_root().html.add_child(folium.Element(legend_html))

    # Save the interactive map as an HTML file that can be opened in browser
    m.save("code/prototype1/data/{RUN_ID}/graphs/ais_map.html")
    
    # Print confirmation with file path and number of vessels mapped
    print(f"  Saved map  → code/prototype1/data/{RUN_ID}/graphs/ais_map.html  ({len(df)} vessels)")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
# Main entry point: orchestrate the complete data pipeline

def main():
    """
    Orchestrate the complete data pipeline:
    1. Pull flight data for two airports from OpenSky
    2. Clean and validate flight data
    3. Generate interactive flight route maps
    4. Pull vessel position data from AISStream (Georgia coast)
    5. Clean and validate vessel data
    6. Generate interactive vessel position map
    
    This function runs all data pipeline stages sequentially.
    Each stage produces intermediate CSV files and final HTML maps.
    """
    # Ensure this database loading line is placed somewhere before this block runs
    airports_db = airportsdata.load('ICAO')

    # --- FIRST AIRPORT ---
    while True:
        airport_1 = input("Enter first ICAO airport code (e.g., KATL): ").strip().upper()
        
        # Check database validity first
        a1_data = airports_db.get(airport_1)
        if not a1_data:
            print(f"'{airport_1}' is not a valid ICAO airport code. Please check the code and try again.\n")
            continue  # Restarts loop to prompt user again
            
        a1_name = a1_data['name']
        a1_info = input(f"You have entered airport: {a1_name}. Is this correct? (y/n): ").strip().lower()
        
        if a1_info == 'y':
            print(f"You have selected {a1_name}.\n")
            break  # Validated and confirmed, break loop to move forward
        elif a1_info == 'n':
            print("Please enter the correct ICAO code.\n")
        else:
            print("Invalid input. Please enter 'y' for yes or 'n' for no.\n")

    # --- SECOND AIRPORT ---
    while True:
        airport_2 = input("Enter second ICAO airport code (e.g., KJFK): ").strip().upper()
        
        # Check database validity first
        a2_data = airports_db.get(airport_2)
        if not a2_data:
            print(f"'{airport_2}' is not a valid ICAO airport code. Please check the code and try again.\n")
            continue  # Restarts loop to prompt user again
            
        a2_name = a2_data['name']
        a2_info = input(f"You have entered airport: {a2_name}. Is this correct? (y/n): ").strip().lower()
        
        if a2_info == 'y':
            print(f"You have selected {a2_name}.\n")
            break  # Validated and confirmed, break loop to move forward
        elif a2_info == 'n':
            print("Please enter the correct ICAO code.\n")
        else:
            print("Invalid input. Please enter 'y' for yes or 'n' for no.\n")

    # Your code will naturally continue uninterrupted right below this line
    # airport_1 and airport_2 hold the validated string codes (e.g., "KATL", "KJFK")



    # ─── OPENSKY  ─────────────────────────────────────────────────────────────
    # Pull, clean, and map flight arrivals at Atlanta Hartsfield-Jackson International
    print("\n=== Processing OpenSky - " + airport_1 + " ===")
    
    # Stage 1: Pull raw flight arrival data from OpenSky API
    a1_raw   = pull_opensky(airport_1)
    
    # Stage 2: Clean raw data (timestamps, duplicates, validation)
    a1_clean = clean_opensky(a1_raw, airport_1)
    
    # Stage 3: Generate interactive Folium map showing flight routes
    graph_opensky(a1_clean, airport_1)

    # Pull, clean, and map flight arrivals for airport 2
    print("\n=== Processing OpenSky - " + airport_2 + " ===")
    
    # Stage 1: Pull raw flight arrival data from OpenSky API
    a2_raw   = pull_opensky(airport_2)
    
    # Stage 2: Clean raw data (timestamps, duplicates, validation)
    a2_clean = clean_opensky(a2_raw, airport_2)
    
    # Stage 3: Generate interactive Folium map showing flight routes
    graph_opensky(a2_clean, airport_2)

    # ─── AIS VESSEL TRACKING (GEORGIA COAST) ───────────────────────────────────
    # Pull, clean, and map vessel positions near Georgia coast via AISStream
    print("\n=== Processing AISStream - Georgia Coast ===")
    
    # Define geographic bounding box for AIS data collection
    # Format: [[min_lat, min_lon], [max_lat, max_lon]]
    # This region covers the Georgia/Florida coast and nearby Atlantic waters
    GA_BBOX   = [[31.0, -81.5], [32.2, -80.5]]
    
    # Stage 1: Collect vessel position data from AISStream WebSocket (10-second collection)
    ais_raw   = pull_ais(GA_BBOX)
    
    # Stage 2: Clean raw data (coordinates, speeds, deduplication)
    ais_clean = clean_ais(ais_raw)
    
    # Stage 3: Generate interactive Folium map with heatmap and speed-colored vessels
    graph_ais(ais_clean)


# Standard Python pattern: only run main() if this script is executed directly
# (not if it's imported as a module in another script)
if __name__ == "__main__":
    # Execute the main data pipeline
    main()
