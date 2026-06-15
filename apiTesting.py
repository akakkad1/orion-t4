import os
from dotenv import load_dotenv
from opensky_api import OpenSkyApi

load_dotenv()
OPENSKY_CLIENT_ID=os.getenv("OPENSKY_CLIENT_ID")
OPENSKY_CLIENT_SECRET=os.getenv("OPENSKY_CLIENT_SECRET")
AISSTREAM_API_KEY=os.getenv("AISSTREAM_API_KEY")

# OpenSky
