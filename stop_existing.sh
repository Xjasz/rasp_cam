#!/usr/bin/env bash
set -euo pipefail

patterns=("cam_main.py")

for pattern in "${patterns[@]}"; do
    pids=$(pgrep -f "$pattern" || true)
    if [ -z "$pids" ]; then
        echo "No processes matching [$pattern]"
        continue
    fi
    echo "Stopping [$pattern]: $pids"
    kill $pids 2>/dev/null || sudo kill $pids 2>/dev/null || true
    sleep 2
    remaining=$(pgrep -f "$pattern" || true)
    if [ -n "$remaining" ]; then
        echo "Force killing [$pattern]: $remaining"
        kill -9 $remaining 2>/dev/null || sudo kill -9 $remaining 2>/dev/null || true
    fi
done