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

# Birmingham, UK coords (no API key needed with Open-Meteo)
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
        "$orderby": "start/dateTime",
        "$top": "100",
    }
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH}/users/{ROOM_EMAIL}/calendarView"

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json().get("value", [])
    except Exception:
        return []

def weather_symbol(code: int) -> str:
    # Map WMO weather codes (Open-Meteo) to a simple symbol
    if code == 0: return "☀️"
    if code in (1,): return "🌤️"
    if code in (2,): return "⛅"
    if code in (3,): return "☁️"
    if code in (45, 48): return "🌫️"
    if code in (51, 53, 55, 56, 57, 80): return "🌦️"
    if code in (61, 63, 65, 81, 82): return "🌧️"
    if code in (66, 67): return "🌧️❄️"
    if code in (71, 73, 75, 77, 85, 86): return "🌨️"
    if code in (95, 96, 99): return "⛈️"
    return "🌡️"

def get_weather_birmingham():
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": BHM_LAT,
                "longitude": BHM_LON,
                "current_weather": "true",
                "timezone": "Europe/London",
            },
            timeout=10,
        )
        r.raise_for_status()
        cw = r.json().get("current_weather", {})
        temp_c = cw.get("temperature")
        wcode = cw.get("weathercode")
        return {
            "temp_c": round(temp_c) if isinstance(temp_c, (int, float)) else None,
            "symbol": weather_symbol(int(wcode)) if wcode is not None else "🌡️",
        }
    except Exception:
        return {"temp_c": None, "symbol": "🌡️"}

# -------- Jinja filters for clean formatting --------
@app.template_filter("to_local")
def to_local(iso_str):
    # ISO8601 -> aware dt in Europe/London
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(TZ)
    except Exception:
        return datetime.now(TZ)

@app.template_filter("fmt_time")
def fmt_time(dt):
    try:
        return dt.strftime("%H:%M")  # hours:minutes only
    except Exception:
        return ""

@app.template_filter("fmt_date")
def fmt_date(dt):
    try:
        return dt.strftime("%d %b %Y")  # e.g., 16 Aug 2025
    except Exception:
        return ""

@app.route("/")
def index():
    events = get_events_next_7_days()
    weather = get_weather_birmingham()
    now = datetime.now(TZ)
    return render_template("index.html", events=events, now=now, weather=weather)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
