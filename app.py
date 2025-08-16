from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta, timezone, date
import os, requests, msal
from dotenv import load_dotenv

# --- Timezone handling: zoneinfo if available, else pytz (no compile needed) ---
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    TZ = ZoneInfo("Europe/London")
except Exception:
    import pytz
    TZ = pytz.timezone("Europe/London")

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
        "startDateTime": now_utc.isoformat().replace("+00:00","Z"),
        "endDateTime":   end_utc.isoformat().replace("+00:00","Z"),
        "$orderby": "start/dateTime",
        "$top": "100",
    }
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH}/users/{ROOM_EMAIL}/calendarView"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        return r.json().get("value", [])
    except Exception:
        return []

def icon_id_for_wmo(code: int) -> str:
    if code == 0: return "sun"
    if code in (1,): return "few"
    if code in (2,): return "partly"
    if code in (3,): return "cloud"
    if code in (45, 48): return "fog"
    if code in (51, 53, 55, 56, 57, 80): return "drizzle"
    if code in (61, 63, 65, 81, 82): return "rain"
    if code in (66, 67): return "sleet"
    if code in (71, 73, 75, 77, 85, 86): return "snow"
    if code in (95, 96, 99): return "storm"
    return "unknown"

def get_weather_birmingham():
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": BHM_LAT,
                "longitude": BHM_LON,
                "current_weather": "true",
                "daily": "weathercode,temperature_2m_max,temperature_2m_min",
                "forecast_days": 7,
                "timezone": "Europe/London",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        cw = data.get("current_weather", {})
        daily = data.get("daily", {})

        out_daily = []
        times = daily.get("time", []) or []
        wcodes = daily.get("weathercode", []) or []
        tmax = daily.get("temperature_2m_max", []) or []
        tmin = daily.get("temperature_2m_min", []) or []

        for i in range(min(len(times), 7)):
            try:
                lbl = date.fromisoformat(times[i]).strftime("%a")
            except Exception:
                lbl = times[i]
            out_daily.append({
                "label": lbl,
                "icon": icon_id_for_wmo(int(wcodes[i])) if i < len(wcodes) and wcodes[i] is not None else "unknown",
                "tmax": round(tmax[i]) if i < len(tmax) and isinstance(tmax[i], (int,float)) else None,
                "tmin": round(tmin[i]) if i < len(tmin) and isinstance(tmin[i], (int,float)) else None,
            })

        temp_c = cw.get("temperature")
        wcode = cw.get("weathercode")
        return {
            "temp_c": round(temp_c) if isinstance(temp_c, (int,float)) else None,
            "icon": icon_id_for_wmo(int(wcode)) if wcode is not None else "unknown",
            "daily": out_daily,
        }
    except Exception:
        return {"temp_c": None, "icon": "unknown", "daily": []}

# ---------- Jinja filters & routes ----------
@app.template_filter("to_local")
def to_local(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z","+00:00"))
        # zoneinfo or pytz tzinfo both work with astimezone()
        return dt.astimezone(TZ)
    except Exception:
        # fallback to "now" to avoid template errors
        # if using pytz: localize properly, but we only need a tz-aware now()
        try:
            return datetime.now(TZ)
        except Exception:
            return datetime.now(timezone.utc)

@app.template_filter("fmt_time")
def fmt_time(dt):
    try:
        return dt.strftime("%H:%M")
    except Exception:
        return ""

@app.template_filter("fmt_date")
def fmt_date(dt):
    try:
        return dt.strftime("%d %b %Y")
    except Exception:
        return ""

@app.route("/health")
def health():
    return jsonify(ok=True)

@app.route("/")
def index():
    events = get_events_next_7_days()
    weather = get_weather_birmingham()

    # "now/next" in Europe/London
    try:
        now_local = datetime.now(TZ)
    except Exception:
        now_local = datetime.now(timezone.utc)

    current = None
    nxt = None
    for e in events:
        s = datetime.fromisoformat(e["start"]["dateTime"].replace("Z","+00:00")).astimezone(TZ)
        t = datetime.fromisoformat(e["end"]["dateTime"].replace("Z","+00:00")).astimezone(TZ)
        if s <= now_local < t:
            current = e
            break
    if not current:
        for e in events:
            s = datetime.fromisoformat(e["start"]["dateTime"].replace("Z","+00:00")).astimezone(TZ)
            if s > now_local:
                nxt = e
                break

    return render_template("index.html", now=now_local, current=current, nxt=nxt, events=events, weather=weather)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
