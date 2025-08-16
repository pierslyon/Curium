from flask import Flask, render_template
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os, requests, msal
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")
ROOM_EMAIL = os.getenv("ROOM_EMAIL")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]
GRAPH = "https://graph.microsoft.com/v1.0"

# Birmingham, UK
BHM_LAT = 52.489471
BHM_LON = -1.898575
TZ = ZoneInfo("Europe/London")

app = Flask(__name__)

def get_access_token():
    cca = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    result = cca.acquire_token_silent(SCOPES, account=None)
    if not result:
        result = cca.acquire_token_for_client(scopes=SCOPES)
    return result.get("access_token")

def get_events_next_7_days():
    token = get_access_token()
    if not token:
        return []
    now_utc = datetime.now(timezone.utc)
    end_utc = now_utc + timedelta(days=7)
    params = {
        "startDateTime": now_utc.isoformat().replace("+00:00", "Z"),
        "endDateTime": end_utc.isoformat().replace("+00:00", "Z"),
        "$orderby": "start/dateTim
