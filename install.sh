#!/bin/bash
set -e

echo "=== Updating system ==="
sudo apt update && sudo apt upgrade -y

echo "=== Installing dependencies ==="
sudo apt install -y python3 python3-venv python3-pip git chromium-browser xdotool unclutter

echo "=== Cloning repo into /home/pi/curium-office-status ==="
if [ ! -d "/home/pi/curium-office-status" ]; then
  git clone https://github.com/pierslyon/Curium.git /home/pi/curium-office-status
else
  echo "Repo already cloned, pulling latest..."
  cd /home/pi/curium-office-status && git pull
fi

cd /home/pi/curium-office-status

echo "=== Setting up Python virtual environment ==="
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Creating .env file ==="
cat > .env <<EOF
CLIENT_ID=da89527b-1749-4fbf-830a-c2dd3371c767
CLIENT_SECRET=gPt8Q~AgZMxhSqWOBK.5Vorzo_2K5LrUgggYzc4Z
TENANT_ID=dabc8b2f-75ca-45fb-9bf4-1a2e4193bf69
ROOM_EMAIL=curiumoffice@curiumsolutions.com
EOF

echo "=== Creating start_panel.sh ==="
cat > start_panel.sh <<'EOF'
#!/bin/bash
cd /home/pi/curium-office-status
source venv/bin/activate
python3 app.py &
sleep 10
chromium-browser --kiosk --app=http://localhost:5000
EOF

chmod +x start_panel.sh

echo "=== Creating systemd service ==="
SERVICE_FILE=/etc/systemd/system/curium-panel.service
sudo bash -c "cat > \$SERVICE_FILE" <<'EOF'
[Unit]
Description=Curium Office Status Panel
After=network-online.target

[Service]
ExecStart=/home/pi/curium-office-status/start_panel.sh
WorkingDirectory=/home/pi/curium-office-status
User=pi
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/pi/.Xauthority
Restart=always

[Install]
WantedBy=graphical.target
EOF

echo "=== Enabling service ==="
sudo systemctl daemon-reexec
sudo systemctl enable curium-panel.service

echo "=== Setup complete. Rebooting now ==="
sudo reboot
