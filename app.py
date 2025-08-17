cat > app.py <<'PY'
from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta, timezone, date
import os, requests, msal
from dotenv import load_dotenv

# --- Timezone handling: zoneinfo if available, else pytz (pure Python) ---
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    TZ = ZoneInfo("Europe/London")
    def localize_naive(dt_naive):
        return dt_naive.replace(tzinfo=TZ)
except Exception:
    import pytz
    TZ = pytz.timezone("Europe/London")
    def localize_naive(dt_naive):
        return TZ.localize(dt_naive)

load_dotenv()

CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID     = os.getenv("TENANT_ID")
ROOM_EMAIL    = os.getenv("ROOM_EMAIL")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES    = ["https://graph.microsoft.com/.default"]
GRAPH     = "https://graph.microsoft.com/v1.0"

# Birmingham, UK
BHM_LAT = 52.489471
BHM_LON = -1.898575

app = Flask(__name__)

# ---------------- Microsoft Graph ----------------
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
        "endDateTime":   end_utc.isoformat().replace("+00:00", "Z"),
        "$orderby": "start/dateTime",
        "$top": "100",
    }
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH}/users/{ROOM_EMAIL}/calendarView"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        return r.json().get("value", [])
    except Exception as e:
        print("Graph error:", e)
        return []

# ---------------- Weather (Open-Meteo) ----------------
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

def _get(url, **params):
    try:
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("Weather fetch failed:", e)
        return None

def get_weather_next_8_hours():
    # 1) Current weather
    cur = _get("https://api.open-meteo.com/v1/forecast",
               latitude=BHM_LAT, longitude=BHM_LON,
               current_weather="true", timezone="Europe/London")
    cur_temp, cur_icon = None, "unknown"
    if cur and isinstance(cur.get("current_weather"), dict):
        cw = cur["current_weather"]
        t, wc = cw.get("temperature"), cw.get("weathercode")
        if isinstance(t, (int, float)): cur_temp = round(t)
        if wc is not None:
            try: cur_icon = icon_id_for_wmo(int(wc))
            except Exception: pass

    # 2) Hourly forecast → next 8 hours
    hourly = _get("https://api.open-meteo.com/v1/forecast",
                  latitude=BHM_LAT, longitude=BHM_LON,
                  hourly="temperature_2m,weathercode",
                  forecast_days=2, timezone="Europe/London")

    out = []
    try: now_local = datetime.now(TZ)
    except Exception: now_local = datetime.now(timezone.utc)
    end_local = now_local + timedelta(hours=8)

    if hourly and isinstance(hourly.get("hourly"), dict):
        hh = hourly["hourly"]
        times = hh.get("time", []) or []
        temps = hh.get("temperature_2m", []) or []
        codes = hh.get("weathercode", []) or []
        for i in range(min(len(times), len(temps), len(codes))):
            try:
                naive = datetime.fromisoformat(times[i])  # local naive
                dt_local = localize_naive(naive)
            except Exception:
                continue
            if now_local <= dt_local <= end_local:
                out.append({
                    "label": dt_local.strftime("%H:%M"),
                    "t": round(temps[i]) if isinstance(temps[i], (int, float)) else None,
                    "icon": icon_id_for_wmo(int(codes[i])) if codes[i] is not None else "unknown",
                })
            if len(out) >= 8: break

    if not out:
        out = [{"label": now_local.strftime("%H:%M"), "t": cur_temp, "icon": cur_icon}]

    header_temp = cur_temp if cur_temp is not None else (out[0]["t"] if out else None)
    header_icon = cur_icon if cur_icon != "unknown" else (out[0]["icon"] if out else "unknown")
    return {"temp_c": header_temp, "icon": header_icon, "hourly8": out}

# ---------------- Filters & routes ----------------
@app.template_filter("to_local")
def to_local(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(TZ)
    except Exception:
        try: return datetime.now(TZ)
        except Exception: return datetime.now(timezone.utc)

@app.template_filter("fmt_time")
def fmt_time(dt):
    try: return dt.strftime("%H:%M")
    except Exception: return ""

@app.template_filter("fmt_date")
def fmt_date(dt):
    try: return dt.strftime("%d %b %Y")
    except Exception: return ""

@app.get("/health")
def health(): return jsonify(ok=True)

@app.get("/wx")
def wx(): return jsonify(get_weather_next_8_hours())

@app.get("/")
def index():
    events  = get_events_next_7_days()
    weather = get_weather_next_8_hours()
    try: now_local = datetime.now(TZ)
    except Exception: now_local = datetime.now(timezone.utc)

    current = None
    for e in events:
        s = datetime.fromisoformat(e["start"]["dateTime"].replace("Z", "+00:00")).astimezone(TZ)
        t = datetime.fromisoformat(e["end"]["dateTime"].replace("Z", "+00:00")).astimezone(TZ)
        if s <= now_local < t: current = e; break

    next_three = []
    for e in events:
        s = datetime.fromisoformat(e["start"]["dateTime"].replace("Z", "+00:00")).astimezone(TZ)
        if s > now_local: next_three.append(e)
        if len(next_three) >= 3: break

    return render_template("index.html", now=now_local, current=current, next_three=next_three, weather=weather)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
PY
