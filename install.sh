#!/bin/bash
set -euo pipefail

#############################################
# >>>>> EDIT THESE TWO LINES <<<<<
GITHUB_USER="pierslyon"          # <-- change to your GitHub username
REPO_NAME="Curium"           # <-- change to your repo name
#############################################

APP_HOME="/home/pi/curium-office-status"
PYBIN="$APP_HOME/venv/bin/python"
PORT="5000"

# Your Microsoft 365 credentials (as requested: embedded)
CLIENT_ID="da89527b-1749-4fbf-830a-c2dd3371c767"
CLIENT_SECRET="gPt8Q~AgZMxhSqWOBK.5Vorzo_2K5LrUgggYzc4Z"
TENANT_ID="dabc8b2f-75ca-45fb-9bf4-1a2e4193bf69"
ROOM_EMAIL="curiumoffice@curiumsolutions.com"

echo "=== Curium Panel: updating system ==="
sudo apt update && sudo apt full-upgrade -y

echo "=== Installing packages ==="
# chromium-browser is a wrapper on Bookworm; this pulls the right browser
sudo apt install -y python3 python3-venv python3-pip git chromium-browser unclutter x11-xserver-utils curl

echo "=== Cloning repo to $APP_HOME ==="
if [ -d "$APP_HOME/.git" ]; then
  echo "Repo already present, pulling latest..."
  cd "$APP_HOME" && git pull --ff-only
else
  sudo rm -rf "$APP_HOME"
  git clone "https://github.com/${GITHUB_USER}/${REPO_NAME}.git" "$APP_HOME"
fi

cd "$APP_HOME"

echo "=== Creating Python venv & installing requirements ==="
python3 -m venv "$APP_HOME/venv"
source "$APP_HOME/venv/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Writing .env with credentials ==="
cat > "$APP_HOME/.env" <<EOF
CLIENT_ID=$CLIENT_ID
CLIENT_SECRET=$CLIENT_SECRET
TENANT_ID=$TENANT_ID
ROOM_EMAIL=$ROOM_EMAIL
EOF
chmod 600 "$APP_HOME/.env"

echo "=== Creating backend systemd service ==="
sudo tee /etc/systemd/system/curium-backend.service >/dev/null <<EOF
[Unit]
Description=Curium Office Status (Flask backend)
After=network-online.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=$APP_HOME
Environment=PORT=$PORT
Environment=PATH=$APP_HOME/venv/bin:/usr/bin
ExecStart=$APP_HOME/venv/bin/python $APP_HOME/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now curium-backend.service

echo "=== Writing kiosk launcher script ==="
cat > "$APP_HOME/kiosk-launch.sh" <<'SH'
#!/bin/bash
set -e
APP_HOME="/home/pi/curium-office-status"

# Prevent display sleeping/blanking in X
xset s off || true
xset -dpms || true
xset s noblank || true

# Hide cursor
unclutter -idle 0.1 -root &

# Wait for backend to answer
for i in {1..60}; do
  if curl -fsS http://localhost:5000/ >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Choose chromium command
BROWSER=$(command -v chromium-browser || command -v chromium)
exec "$BROWSER" --kiosk --app=http://localhost:5000 \
  --no-first-run --no-default-browser-check \
  --disable-translate --disable-session-crashed-bubble \
  --overscroll-history-navigation=0 \
  --check-for-update-interval=31536000
SH
chmod +x "$APP_HOME/kiosk-launch.sh"
chown -R pi:pi "$APP_HOME"

echo "=== Creating desktop autostart entry ==="
AUTOSTART_DIR="/home/pi/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/curium-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Curium Kiosk
Exec=$APP_HOME/kiosk-launch.sh
X-GNOME-Autostart-enabled=true
EOF
chown -R pi:pi "$AUTOSTART_DIR"

echo "=== Ensuring desktop autologin (best effort) ==="
if command -v raspi-config >/dev/null 2>&1; then
  # B4 = Desktop autologin on current RPi OS
  sudo raspi-config nonint do_boot_behaviour B4 || true
fi

echo "✅ Install complete. Rebooting into kiosk…"
sudo reboot
