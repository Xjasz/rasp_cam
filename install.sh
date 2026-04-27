#!/usr/bin/env bash
set -euo pipefail

DEVICE_KEY="${1:-}"

if [ -z "$DEVICE_KEY" ]; then
    echo "Usage: ./install.sh YOUR_DEVICE_KEY"
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 was not found."
    exit 1
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
    sudo apt install -y python3-venv
fi

python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -r requirements.txt

printf "RASP_DEVICE_KEY=%s\n" "$DEVICE_KEY" > .env
chmod 600 .env

chmod +x run.sh stop_existing.sh

echo "Install complete..."
echo "Start the camera with: ./run.sh"