#!/bin/bash
# Fetches Teslog's combined stats CSV (see GET /api/export/full.csv) and uploads it to Google
# Drive via rclone, as teslog_<timestamp>.csv.
#
# Invoked on a schedule by the cron entry `./teslog.sh up` installs (see install_export_cron in
# teslog.sh) — running it by hand is harmless too, e.g. to test the rclone/gdrive setup.
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE=".env"

get_env() {
    local line
    line=$(grep -E "^$1=" "$ENV_FILE" 2>/dev/null || true)
    echo "${line#*=}"
}

log() {
    echo "$(date -Iseconds) $*"
}

if ! command -v rclone >/dev/null 2>&1; then
    log "rclone not found on this machine — skipping export." >&2
    exit 0
fi

if ! rclone listremotes 2>/dev/null | grep -qx "gdrive:"; then
    log "No 'gdrive' rclone remote configured (run 'rclone config' first) — skipping export." >&2
    exit 0
fi

port=$(get_env "TESLOG_PORT")
port="${port:-8080}"
location=$(get_env "TESLOG_EXPORT_LOCATION")
location="${location:-teslog}"

tmp_file="/tmp/teslog_$(date +%y-%m-%d_%H:%M).csv"

if ! curl -sf "http://localhost:${port}/api/export/full.csv" -o "$tmp_file"; then
    log "Failed to fetch the export CSV from Teslog (is the stack up?)." >&2
    rm -f "$tmp_file"
    exit 1
fi

if ! rclone copy "$tmp_file" "gdrive:${location}/"; then
    log "rclone copy failed — leaving $tmp_file in place for inspection/retry." >&2
    exit 1
fi

log "Exported to gdrive:${location}/$(basename "$tmp_file")"
rm -f "$tmp_file"
