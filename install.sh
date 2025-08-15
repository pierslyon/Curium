#!/bin/bash
set -e

echo "=== Curium Office Status Kiosk Installer ==="

# Prompt for Microsoft 365 details
read -p "Enter CLIENT_ID: " CLIENT_ID
read -p "Enter CLIENT_SECRET: " CLIENT_SECRET
read -p "Enter TENANT_ID: " TENANT_ID
read -p "Enter ROOM_EMAIL: " ROOM_EMAIL

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3 python3-pip python3-venv git chromium-browser unclutter

# Create app folder
mkdir -p ~/curium-office-status/templates
cd ~/curium-office-status

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install flask msal requests python-dotenv

# Create .env file
cat <<EOF > .env
CLIENT_ID=$CLIENT_ID
CLIENT_SECRET=$CLIENT_SECRET
TENANT_ID=$TENANT_ID
ROOM_EMAIL=$ROOM_EMAIL
EOF

# Create app.py
cat <<'EOF' > app.py
import os
import datetime
from flask import Flask, render_template
from msal import ConfidentialClientApplication
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")
ROOM_EMAIL = os.getenv("ROOM_EMAIL")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]

def get_token():
    app_msal = ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    token_result = app_msal.acquire_token_silent(SCOPES, account=None)
    if not token_result:
        token_result = app_msal.acquire_token_for_client(scopes=SCOPES)
    return token_result.get("access_token")

def get_calendar_events():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    start = datetime.datetime.utcnow()
    end = start + datetime.timedelta(days=7)
    params = {
        "startDateTime": start.isoformat() + "Z",
        "endDateTime": end.isoformat() + "Z",
        "$orderby": "start/dateTime"
    }
    url = f"https://graph.microsoft.com/v1.0/users/{ROOM_EMAIL}/calendarView"
    r = requests.get(url, headers=headers, params=params)
    if r.status_code == 200:
        return r.json().get("value", [])
    return []

@app.template_filter("todatetime")
def todatetime(value):
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))

@app.route("/")
def index():
    events = get_calendar_events()
    return render_template("index.html", events=events, now=datetime.datetime.utcnow())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
EOF

# Create templates/index.html
cat <<'EOF' > templates/index.html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Curium Office Status</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #222;
            color: white;
            margin: 0;
            padding: 0;
        }
        h1 {
            font-size: 2.5em;
            text-align: center;
            margin: 20px 0;
        }
        .event {
            padding: 20px;
            margin: 10px;
            border-radius: 8px;
            font-size: 1.5em;
        }
        .current {
            background-color: #28a745; /* Green */
        }
        .upcoming {
            background-color: #007bff; /* Blue */
        }
        .past {
            background-color: #555; /* Grey */
        }
    </style>
</head>
<body>
    <h1>Curium Office Status</h1>
    {% if events %}
        {% for event in events %}
            {% set start = event.start.dateTime | todatetime %}
            {% set end = event.end.dateTime | todatetime %}
            {% if start <= now and end >= now %}
                {% set status_class = "current" %}
            {% elif start > now %}
                {% set status_class = "upcoming" %}
            {% else %}
                {% set status_class = "past" %}
            {% endif %}
            <div class="event {{ status_class }}">
                <strong>{{ event.subject }}</strong><br>
                {{ event.start.dateTime }} - {{ event.end.dateTime }}
            </div>
        {% endfor %}
    {% else %}
        <p style="text-align:center; font-size: 1.5em;">No upcoming meetings.</p>
    {% endif %}
</body>
</html>
EOF

# Create start_panel.sh
cat <<'EOF' > start_panel.sh
#!/bin/bash
cd /home/pi/curium-office-status
source venv/bin/activate
python3 app.py &
sleep 10
chromium-browser --kiosk --app=http://localhost:5000 --noerrdialogs --disable-infobars --check-for-update-interval=31536000
EOF
chmod +x start_panel.sh

# Setup autostart
mkdir -p /home/pi/.config/lxsession/LXDE-pi
cat <<EOF > /home/pi/.config/lxsession/LXDE-pi/autostart
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@unclutter -idle 0
@/home/pi/curium-office-status/start_panel.sh
EOF

echo "=== Install complete! Rebooting... ==="
sudo reboot
