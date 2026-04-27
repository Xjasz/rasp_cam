#!/usr/bin/env bash
set -euo pipefail

DEVICE_KEY="${1:-}"

if [ -z "$DEVICE_KEY" ]; then
    echo "Usage: ./install.sh YOUR_DEVICE_KEY"
    exit 1
fi

sudo apt update
sudo apt install -y python3-venv python3-pip python3-picamera2 python3-opencv python3-numpy i2c-tools python3-smbus

sudo raspi-config nonint do_i2c 0 || true

python3 -m venv --system-site-packages .venv

. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

printf "RASP_DEVICE_KEY=%s\n" "$DEVICE_KEY" > .env
chmod 600 .env

chmod +x run.sh

echo "Install complete."
echo "Start the camera with: ./run.sh"
