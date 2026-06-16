"""
check_aisstream.py
------------------
Connects to AISStream, waits for the first AIS message, pretty-prints
the raw JSON, then exits cleanly.

Reads from .env:
  AISSTREAM_KEY  – your API key from aisstream.io
"""

import os, json, asyncio
import websockets
from dotenv import load_dotenv

load_dotenv()
$ print("KEY:", os.getenv("AISSTREAM_API_KEY"))


API_KEY = os.getenv("AISSTREAM_KEY") or os.getenv("AISSTREAM_API_KEY")
if not API_KEY:
    raise SystemExit(
        "ERROR: No AISStream key found.\n"
        "Set AISSTREAM_KEY=<your_key> in your .env file."
    )

WS_URL = "wss://stream.aisstream.io/v0/stream"

# Subscribe to all message types in a broad bounding box (North Atlantic + US coasts)
SUBSCRIBE = {
    "APIKey": API_KEY,
    "BoundingBoxes": [[[-90, -180], [90, 180]]],  # whole world
    "FilterMessageTypes": [],  # empty = all types
}


async def run():
    print("Connecting to AISStream…")
    try:
        async with websockets.connect(WS_URL, open_timeout=15) as ws:
            print(f"✓ WebSocket connected: {WS_URL}")
            await ws.send(json.dumps(SUBSCRIBE))
            print("✓ Subscription sent – waiting for first message…\n")

            raw = await asyncio.wait_for(ws.recv(), timeout=30)

    except asyncio.TimeoutError:
        print("Timed out waiting for a message (30 s). The stream may be quiet – try a busier bounding box.")
        raise SystemExit(1)
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"WebSocket rejected: {e}\nCheck your AISSTREAM_KEY.")
        raise SystemExit(1)
    except OSError as e:
        print(f"Connection error: {e}")
        raise SystemExit(1)

    msg = json.loads(raw)

    print("=" * 60)
    print("RAW AIS MESSAGE (first received)")
    print("=" * 60)
    print(json.dumps(msg, indent=2))

    print("\n--- top-level keys ---")
    for k, v in msg.items():
        snippet = str(v)[:80] + ("…" if len(str(v)) > 80 else "")
        print(f"  {k:20s}: {snippet}")

    print("\n✓ Done – connection closed cleanly.")


asyncio.run(run())