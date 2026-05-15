#!/usr/bin/env bash
set -euo pipefail

# Kill only cam_main.py processes running from THIS install directory.
#
# During a self-update reboot two versions' systemd units start together, each
# running run.sh -> stop_existing.sh. A bare `pgrep -f cam_main.py` kill would
# make the two installs kill each other. Scoping by the process working
# directory keeps each install's cleanup to its own process.

SELF_DIR="$(cd "$(dirname "$0")/.." && pwd)"

pids="$(pgrep -f 'cam_main.py' || true)"
if [ -z "$pids" ]; then
    echo "No cam_main.py processes."
    exit 0
fi

kill_if_self() {
    pid="$1"
    pcwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    [ "$pcwd" = "$SELF_DIR" ]
}

for pid in $pids; do
    if kill_if_self "$pid"; then
        echo "Stopping cam_main.py from $SELF_DIR (pid $pid)"
        kill "$pid" 2>/dev/null || sudo kill "$pid" 2>/dev/null || true
    fi
done

sleep 2

for pid in $pids; do
    if kill -0 "$pid" 2>/dev/null && kill_if_self "$pid"; then
        echo "Force killing pid $pid"
        kill -9 "$pid" 2>/dev/null || sudo kill -9 "$pid" 2>/dev/null || true
    fi
done
