#!/usr/bin/env bash
# Entry point for cron: one run at a time, one log file per day, 30 days of logs kept.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
log="logs/$(date +%F).log"

exec 9>logs/.lock
if ! flock -n 9; then
    echo "$(date -Is) another run is still in progress, skipping" >> "$log"
    exit 0
fi

find logs -name '*.log' -mtime +30 -delete
echo "=== $(date -Is) start" >> "$log"
status=0
docker compose run --rm collector "$@" >> "$log" 2>&1 || status=$?
echo "=== $(date -Is) exit ${status}" >> "$log"
exit "${status}"
