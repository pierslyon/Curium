#!/bin/bash
set -e

echo "======================================="
echo " Curium Office Status Panel Installer"
echo "======================================="

# Step 1: Update system
echo "[1/6] Updating system..."
sudo apt update && sudo apt upgrade -y

# Step 2: Install dependencies
echo "[2/6] Installing dependencies..."
sudo apt install -y python3 python3-pip python3-venv git chromium-browser

# Step 3: Clone repo (public, no password needed)
echo "[3/6] Cloning GitHub repo..."
cd /home/pi
if [ -d "curium-office-status" ]; then
    echo "Repo already exists. Pulling latest..."
    cd curium-office-status
    git pull
else
    git clone https://github.com/pierslyon/curium-office-status.git
    cd curium-office-status
fi

# Step 4: Set up Python virtual environment
echo "[4/6] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Step 5: Create .env file with credentials
echo "[5/6] Setting up environment variables..."
cat > .env <<EOL
CLIENT_ID=da89527b-1749-4fbf-830a-c2dd3371c767
CLIENT_SECRET=gPt8Q~AgZMxhSqWOBK.5Vorzo_2K5LrUgggYzc4Z
TENANT_ID=dabc8b2f-75ca-45fb-9bf4-1a2e4193bf69
ROOM_EMAIL=curiumoffice@curiumsolutions.com
EOL

# Step 6: Create autostart script
echo "[6/6] Setting up autostart..."
mkdir -p /home/pi/.config/lxsession/LXDE-pi

cat > /home/pi/.config/lxsession/LXDE-pi/autostart <<EOL
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
point-rpi

# Start Flask app
@bash /home/pi/curium-office-status/start_panel.sh
EOL

# Create start_panel.sh
cat > /home/pi/curium-office-status/start_panel.sh <<EOL
#!/bin/bash
cd /home/pi/curium-office-status
source venv/bin/activate
python3 app.py &
sleep 10
chromium-browser --kiosk --app=http://localhost:5000
EOL

chmod +x /home/pi/curium-office-status/start_panel.sh

echo "======================================="
echo " Installation complete! Reboot required."
echo " Your panel will auto-launch on startup."
echo "======================================="
