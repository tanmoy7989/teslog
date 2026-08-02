#!/bin/bash
# Copies the already-signed-in TeslaMate state (.env + data/) from this
# machine to a Raspberry Pi, so the Pi's TeslaMate comes up already
# authenticated instead of needing tesla_auth's GUI login or a
# headless-chromium token submission on the Pi itself.
#
# Run ./teslog.sh setup here first (wherever you have a real screen, e.g. a
# Mac) and sign in to TeslaMate, then run this script to move that state to
# the Pi, into ~/$PI_ROOT there (see config/.env.example — set by 'setup',
# defaults to "teslog").
set -euo pipefail

cd "$(dirname "$0")/.."

PI_HOST="${1:-}"
if [[ -z "$PI_HOST" ]]; then
    echo "Usage: $0 <user@pi-host>" >&2
    exit 1
fi

ENV_FILE=".env"
DATA_DIR="data"

if [[ ! -f "$ENV_FILE" || ! -d "$DATA_DIR" ]]; then
    echo "No $ENV_FILE and/or $DATA_DIR found here — run './teslog.sh setup' (and sign in to TeslaMate) on this machine first." >&2
    exit 1
fi

get_env() {
    local line
    line=$(grep -E "^$1=" "$ENV_FILE" 2>/dev/null || true)
    echo "${line#*=}"
}

PI_ROOT=$(get_env "PI_ROOT")
PI_ROOT="${PI_ROOT:-teslog}"

COMPOSE=(docker compose --env-file .env -f docker/compose.yml)

echo "This will overwrite ~/$PI_ROOT/.env and ~/$PI_ROOT/data on $PI_HOST with the copies from"
echo "this machine, and briefly stop the local stack so the copy of data/"
echo "(Postgres's files) is consistent. It's brought back up afterward."
read -r -p "Continue? [y/N]: " confirm || true
if [[ ! "${confirm:-}" =~ ^[Yy]$ ]]; then
    echo "Aborted, nothing was copied."
    exit 1
fi

was_running=false
if [[ -n "$("${COMPOSE[@]}" ps -q 2>/dev/null)" ]]; then
    was_running=true
    echo
    echo "-- Stopping local stack for a consistent copy --"
    "${COMPOSE[@]}" down
fi

echo
echo "-- Ensuring ~/$PI_ROOT exists on $PI_HOST --"
ssh "$PI_HOST" "mkdir -p \"\$HOME/$PI_ROOT\""

copy() {
    rsync -avzP "$1" "${PI_HOST}:~/${PI_ROOT}/"
}

echo
echo "-- Copying $ENV_FILE --"
copy "$ENV_FILE"

echo
echo "-- Copying $DATA_DIR (this may take a while) --"
copy "$DATA_DIR"

if [[ "$was_running" == true ]]; then
    echo
    echo "-- Restarting local stack --"
    "${COMPOSE[@]}" up -d
fi

echo
echo "== Done =="
echo "On $PI_HOST, run:"
echo "  cd ~/$PI_ROOT && ./teslog.sh up"
