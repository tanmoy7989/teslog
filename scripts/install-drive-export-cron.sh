#!/bin/bash
# Installs a cron entry that runs export-to-drive.sh every 15 minutes.
# Safe to re-run — won't add a duplicate entry.
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_DIR="$(pwd)"
SCRIPT_PATH="$REPO_DIR/scripts/export-to-drive.sh"
LOG_PATH="$REPO_DIR/data/drive-export/export.log"
CRON_LINE="*/15 * * * * cd $REPO_DIR && $SCRIPT_PATH >> $LOG_PATH 2>&1"

mkdir -p "$REPO_DIR/data/drive-export"

existing_crontab="$(crontab -l 2>/dev/null || true)"

if [[ "$existing_crontab" == *"$SCRIPT_PATH"* ]]; then
    echo "Cron entry already installed."
else
    {
        [[ -n "$existing_crontab" ]] && printf '%s\n' "$existing_crontab"
        printf '%s\n' "$CRON_LINE"
    } | crontab -
    echo "Installed cron entry:"
    echo "  $CRON_LINE"
fi

echo "Logs: $LOG_PATH"
