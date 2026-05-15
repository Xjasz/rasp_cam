#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Unit name: an explicit arg wins (used by version_manager to retire a specific
# sibling); otherwise derive it from this dir's VERSION; fall back to the legacy
# unversioned name for a v1.0.x install.
if [ "$#" -ge 1 ] && [ -n "${1:-}" ]; then
    SERVICE_NAME="$1"
else
    APP_VERSION="$(tr -d '[:space:]' < "$SCRIPT_DIR/VERSION" 2>/dev/null || true)"
    if printf '%s' "$APP_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
        SERVICE_NAME="codalata-rasp-cam-${APP_VERSION}"
    else
        SERVICE_NAME="codalata-rasp-cam"
    fi
fi

sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
sudo rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl reset-failed "$SERVICE_NAME" 2>/dev/null || true
echo "Service ${SERVICE_NAME} removed."

# Remove the install directory itself -- but ONLY if it actually looks like a
# rasp_cam install dir, never anything else. Deferred so this script (which
# lives inside the dir) can finish first.
DIR_BASE="$(basename "$SCRIPT_DIR")"
case "$DIR_BASE" in
    rasp_cam|rasp_cam_*)
        ( sleep 5 && rm -rf "$SCRIPT_DIR" ) </dev/null >/dev/null 2>&1 &
        disown || true
        echo "Directory ${SCRIPT_DIR} will be removed in 5s."
        ;;
    *)
        echo "Directory name '${DIR_BASE}' is not a rasp_cam install dir -- leaving it in place."
        ;;
esac
