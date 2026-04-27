#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f "./stop_existing.sh" ]; then
    chmod +x ./stop_existing.sh
    ./stop_existing.sh
fi

if [ ! -f ".env" ]; then
    echo "Missing .env. Run: ./install.sh YOUR_DEVICE_KEY"
    exit 1
fi

set -a
. ./.env
set +a

. ./.venv/bin/activate
python cam_main.py
