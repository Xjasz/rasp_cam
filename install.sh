#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="${SUDO_USER:-$(id -un)}"

# The version drives the systemd unit name so multiple versions can coexist
# on one device during a self-update (see helpers/version_manager.py).
APP_VERSION="$(tr -d '[:space:]' < "$APP_DIR/VERSION" 2>/dev/null || true)"
if ! printf '%s' "$APP_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "ERROR: missing or invalid VERSION file in $APP_DIR"
    exit 1
fi
SERVICE_NAME="codalata-rasp-cam-${APP_VERSION}"
LEGACY_SERVICE_NAME="codalata-rasp-cam"

DEVICE_KEY=""
INSTALL_SERVICE=0
NO_START=0

usage() {
    echo "Usage:"
    echo "  ./install.sh YOUR_DEVICE_KEY"
    echo "  ./install.sh YOUR_DEVICE_KEY --service"
    echo "  ./install.sh --service              (reuse existing .env)"
    echo ""
    echo "  --no-start   install + enable the service but do not start it"
    echo "               (used by the self-updater; the reboot starts it)"
}

for arg in "$@"; do
    case "$arg" in
        --service|-s) INSTALL_SERVICE=1 ;;
        --no-start)   NO_START=1 ;;
        -*)
            echo "Unknown option: $arg"
            usage
            exit 1
            ;;
        *) DEVICE_KEY="$arg" ;;
    esac
done

cd "$APP_DIR"
if [ -z "$DEVICE_KEY" ] && [ ! -f ".env" ]; then
    echo "Missing device key."
    usage
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 was not found."
    exit 1
fi
if ! python3 -m venv --help >/dev/null 2>&1; then
    sudo apt install -y python3-venv
fi
if [ ! -f ".venv/bin/activate" ]; then
    python3 -m venv --system-site-packages .venv
fi
. .venv/bin/activate
python -m pip install -r requirements.txt
if [ -n "$DEVICE_KEY" ]; then
    printf "RASP_DEVICE_KEY=%s\n" "$DEVICE_KEY" > .env
fi
chmod 600 .env
chmod +x run.sh uninstall_service.sh 2>/dev/null || true
[ -f scripts/stop_existing.sh ] && chmod +x scripts/stop_existing.sh

if [ "$INSTALL_SERVICE" -eq 1 ]; then
    sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=Codalata RASP Camera Client ${APP_VERSION}
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

    # One-time migration: a device coming off v1.0.x has the legacy unversioned
    # unit. Remove it so the device never runs two camera clients at once.
    if [ "$SERVICE_NAME" != "$LEGACY_SERVICE_NAME" ] \
       && [ -f "/etc/systemd/system/${LEGACY_SERVICE_NAME}.service" ]; then
        echo "Removing legacy ${LEGACY_SERVICE_NAME} service..."
        sudo systemctl stop "$LEGACY_SERVICE_NAME" 2>/dev/null || true
        sudo systemctl disable "$LEGACY_SERVICE_NAME" 2>/dev/null || true
        sudo rm -f "/etc/systemd/system/${LEGACY_SERVICE_NAME}.service"
        sudo systemctl daemon-reload
        sudo systemctl reset-failed "$LEGACY_SERVICE_NAME" 2>/dev/null || true
    fi

    if [ "$NO_START" -eq 1 ]; then
        echo "Install complete. Service ${SERVICE_NAME} installed + enabled (NOT started)."
    else
        sudo systemctl restart "$SERVICE_NAME"
        echo "Install complete. Service ${SERVICE_NAME} installed + started."
    fi
    echo "Status: sudo systemctl status ${SERVICE_NAME}"
    echo "Logs:   journalctl -u ${SERVICE_NAME} -f"
else
    echo "Install complete."
    echo "Start the camera with: ./run.sh"
    echo "Install as service with: ./install.sh --service"
fi
