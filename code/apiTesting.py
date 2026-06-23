import os
from dotenv import load_dotenv
from opensky_api import OpenSkyApi
from datetime import datetime, timezone
import asyncio
import websockets
import json

load_dotenv()
OPENSKY_CLIENT_ID = os.getenv("OPENSKY_CLIENT_ID")
OPENSKY_CLIENT_SECRET = os.getenv("OPENSKY_CLIENT_SECRET")
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY")
print("AIS key loaded:", AISSTREAM_API_KEY[:10] if AISSTREAM_API_KEY else None)

# OpenSky
api = OpenSkyApi(client_id=OPENSKY_CLIENT_ID, client_secret=OPENSKY_CLIENT_SECRET)

# Arrivals at Atlanta Airport (KATL) between 14:00 and 15:00 UTC on June 1, 2026
start_date = int(datetime(2026, 6, 1, 14, 0).timestamp())
end_date = int(datetime(2026, 6, 1, 15, 0).timestamp())

katlArrivals = api.get_arrivals_by_airport("KATL", start_date, end_date)
print(katlArrivals)


# AISStream
async def connect_ais_stream():
    print("Connecting to AISStream...")
    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as websocket:
        subscribe_message = {
            "APIKey": AISSTREAM_API_KEY,
            # Georgia, USA | East Coast
            "BoundingBoxes": [[[31.0, -81.5], [32.2, -80.5]]], # Lat1, Lon1, Lat2, Lon2
            "FilterMessageTypes": ["PositionReport"]
        }
        await websocket.send(json.dumps(subscribe_message))
        print("Subscribed! Waiting for messages...")

        async for message_json in websocket:
            message = json.loads(message_json)
            message_type = message["MessageType"]

            if message_type == "PositionReport":
                ais_message = message['Message']['PositionReport']
                print(f"[{datetime.now(timezone.utc)}] ShipId: {ais_message['UserID']} Lat: {ais_message['Latitude']} Lon: {ais_message['Longitude']}")


if __name__ == "__main__":
    asyncio.run(connect_ais_stream()) 
