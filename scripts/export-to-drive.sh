#!/bin/bash
# Pulls Teslog's derived metric CSVs (the same ones downloadable from the
# dashboard) and pushes them to Google Drive via rclone. No raw TeslaMate
# data (drives/positions/charges) is touched — only Teslog's own computed
# stats.
#
# Requires a one-time `rclone config` to authorize access to your Drive —
# see README.md. Safe to run repeatedly (e.g. from cron): if RCLONE_REMOTE
# isn't configured yet, it just skips.
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE=".env"
EXPORT_DIR="data/drive-export"
TESLOG_URL="${TESLOG_URL:-http://localhost:8080}"

get_env() {
    local line
    line=$(grep -E "^$1=" "$ENV_FILE" 2>/dev/null || true)
    echo "${line#*=}"
}

RCLONE_REMOTE="${RCLONE_REMOTE:-$(get_env RCLONE_REMOTE)}"

if [[ -z "$RCLONE_REMOTE" ]]; then
    echo "RCLONE_REMOTE isn't set in .env — skipping Drive export. See README.md for setup." >&2
    exit 0
fi

if ! command -v rclone >/dev/null 2>&1; then
    echo "rclone is required but wasn't found." >&2
    echo "  macOS:         brew install rclone" >&2
    echo "  Raspberry Pi:  curl https://rclone.org/install.sh | sudo bash" >&2
    exit 1
fi

mkdir -p "$EXPORT_DIR"

METRICS=(drift distance energy-used energy-efficiency charging-energy charging-cost)
for metric in "${METRICS[@]}"; do
    if ! curl -sf "$TESLOG_URL/api/metrics/${metric}.csv" -o "$EXPORT_DIR/${metric}.csv"; then
        echo "Could not fetch ${metric}.csv from $TESLOG_URL — is the teslog container running?" >&2
        exit 1
    fi
done

rclone copy "$EXPORT_DIR" "$RCLONE_REMOTE" --quiet

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") — exported to $RCLONE_REMOTE"
