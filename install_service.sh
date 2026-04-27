#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="codalata-rasp-cam"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="${SUDO_USER:-$(id -un)}"
DEVICE_KEY="${1:-}"

cd "$APP_DIR"

chmod +x install.sh
if [ ! -f ".env" ] || [ ! -f ".venv/bin/activate" ]; then
    if [ -z "$DEVICE_KEY" ]; then
        echo "Missing install files. Run one of these:"
        echo "./install.sh YOUR_DEVICE_KEY"
        echo "./install_service.sh YOUR_DEVICE_KEY"
        exit 1
    fi
    ./install.sh "$DEVICE_KEY"
fi

chmod +x run.sh
[ -f stop_existing.sh ] && chmod +x stop_existing.sh

sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=Codalata RASP Camera Client
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/run.sh
Restart=always
RestartSec=5
TimeoutStopSec=20
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "Service installed and started."
echo "Status: sudo systemctl status ${SERVICE_NAME}"
echo "Logs:   journalctl -u ${SERVICE_NAME} -f"