#!/bin/bash
# Install and run Teslog (Mac and Linux/Raspberry Pi).
set -euo pipefail

cd "$(dirname "$0")"

ENV_FILE=".env"
EXAMPLE_FILE="config/.env.example"

# The dev overlay bind-mounts src/ for live-reload — useful on a Mac dev
# machine, wrong for a Pi running as a production appliance.
if [[ "$(uname -s)" == "Darwin" ]]; then
    COMPOSE=(docker compose --env-file .env -f docker/compose.yml -f docker/compose.dev.yml)
else
    COMPOSE=(docker compose --env-file .env -f docker/compose.yml)
fi

usage() {
    cat <<'EOF'
Usage: ./teslog.sh COMMAND

Commands:
  setup   Wipe any existing .env/data and install fresh: generate secrets,
          ask the one-time config questions, start the stack, then run the
          Tesla sign-in token generator and print the tokens to paste into
          TeslaMate.
  up      Start the already-configured stack (day-to-day — after a reboot
          or './teslog.sh down', use this, not 'setup').
  down    Stop the stack.
  -h      Show this help.

Examples:
  ./teslog.sh setup   # first time, or to reset and start completely over
  ./teslog.sh up       # every day after that
  ./teslog.sh down
EOF
}

COMMAND="${1:-}"

case "$COMMAND" in
    ""|-h|--help)
        usage
        exit 0
        ;;
    setup|up|down)
        ;;
    *)
        echo "Unknown command: $COMMAND" >&2
        echo >&2
        usage >&2
        exit 1
        ;;
esac

if ! command -v docker >/dev/null 2>&1; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo "Docker is required but wasn't found. Install Docker Desktop:"
        echo "  https://www.docker.com/products/docker-desktop/"
    else
        echo "Docker is required but wasn't found. Install it with:"
        echo "  curl -sSL https://get.docker.com | sh"
        echo "then add your user to the docker group and re-login:"
        echo "  sudo usermod -aG docker \$USER"
    fi
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo "Docker is installed but doesn't seem to be running. Start Docker Desktop and re-run this script."
    else
        echo "Docker is installed but doesn't seem to be running (or your user lacks permission)."
        echo "  sudo systemctl start docker"
    fi
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "The 'docker compose' plugin is required but wasn't found (comes with Docker Desktop)."
    exit 1
fi

if [[ "$COMMAND" == "down" ]]; then
    exec "${COMPOSE[@]}" down
fi

if [[ "$COMMAND" == "up" ]]; then
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "No $ENV_FILE found — run './teslog.sh setup' first."
        exit 1
    fi
    "${COMPOSE[@]}" up -d
    echo
    echo "== Teslog is running =="
    echo "  Teslog dashboard: http://localhost:8080"
    exit 0
fi

# COMMAND == setup: wipe anything existing, install fresh, start, get Tesla tokens.

echo "This will stop the stack (if running) and permanently delete:"
echo "  - $ENV_FILE (all generated secrets)"
echo "  - data/ (TeslaMate's and Teslog's Postgres databases)"
echo
echo "Any existing Tesla sign-in and recorded drives/charges will be gone."
read -r -p "Continue? [y/N]: " confirm_wipe || true
if [[ ! "${confirm_wipe:-}" =~ ^[Yy]$ ]]; then
    echo "Aborted, nothing was deleted."
    exit 1
fi

"${COMPOSE[@]}" down 2>/dev/null || true
rm -f "$ENV_FILE"
rm -rf data
echo

cp "$EXAMPLE_FILE" "$ENV_FILE"

get_env() {
    local line
    line=$(grep -E "^$1=" "$ENV_FILE" 2>/dev/null || true)
    echo "${line#*=}"
}

set_env() {
    local key="$1" value="$2"
    if grep -qE "^${key}=" "$ENV_FILE"; then
        sed -i.bak -E "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    elif grep -qE "^# ${key}=" "$ENV_FILE"; then
        sed -i.bak -E "s|^# ${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
    rm -f "${ENV_FILE}.bak"
}

prompt_default() {
    local prompt="$1" default="$2" reply
    read -r -p "$prompt [$default]: " reply || true
    echo "${reply:-$default}"
}

echo "== Teslog setup =="
echo
echo "-- Secrets --"
./scripts/init-secrets.sh
echo

echo "-- Configuration --"

detected_tz=$(readlink /etc/localtime 2>/dev/null | sed 's#.*/zoneinfo/##')
tz=$(prompt_default "Timezone (TM_TZ)" "${detected_tz:-America/Los_Angeles}")
set_env "TM_TZ" "$tz"

car_id=$(prompt_default "TeslaMate car ID to track (1 if you only have one car; you can change this later once paired)" "1")
set_env "TESLOG_CAR_ID" "$car_id"

osrm_url=$(prompt_default "OSRM routing server (public demo server is fine for light personal use)" "https://router.project-osrm.org")
set_env "OSRM_BASE_URL" "$osrm_url"
echo

echo "-- Starting stack --"
"${COMPOSE[@]}" up -d
echo

echo "-- Tesla sign-in --"
./scripts/get-tesla-tokens.sh

echo
echo "== Teslog is running =="
echo "  TeslaMate:        http://localhost:4000 (auto-signed in above, unless that failed — see output)"
echo "  Teslog dashboard: http://localhost:8080"
