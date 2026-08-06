#!/bin/bash
# Teslog setup + stack control.
#
# 'setup' generates config and signs in to TeslaMate — run it wherever you
# have a real screen (e.g. a Mac). 'up'/'down' start and stop the actual
# server — run those on whichever machine is meant to serve Teslog
# day-to-day (e.g. a Raspberry Pi). See scripts/migrate-to-pi.sh to move a
# signed-in setup from one machine onto the other.
set -euo pipefail

cd "$(dirname "$0")"

ENV_FILE=".env"
EXAMPLE_FILE="config/.env.example"
VENV_TESLA_AUTH=".venv-tesla-auth"
VENV_TEST=".venv-test"

COMPOSE=(docker compose --env-file .env -f docker/compose.yml)
CRON_TAG="# teslog-drive-export"
EXPORT_HOURS_DEFAULT="24"
EXPORT_LOCATION_DEFAULT="teslog"
PI_ROOT_DEFAULT="teslog"

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

# Installs/replaces the single teslog-drive-export cron line (tagged so it can be found and
# replaced idempotently without touching any of the user's other cron entries).
install_export_cron() {
    local hours="$1" repo_dir
    repo_dir="$(pwd)"
    # The `|| true` matters: with no pre-existing crontab (a fresh Pi, or one where this is the
    # only cron job ever installed), `crontab -l` and/or `grep -vF` finding nothing to keep both
    # exit non-zero — under `set -e` that would abort this function before the line below ever
    # gets written, silently leaving nothing scheduled.
    { crontab -l 2>/dev/null | grep -vF "$CRON_TAG" || true
      echo "0 */${hours} * * * cd ${repo_dir} && ./scripts/export-to-drive.sh >> drive-export.log 2>&1 ${CRON_TAG}"
    } | crontab -
}

remove_export_cron() {
    crontab -l 2>/dev/null | grep -vF "$CRON_TAG" | crontab - 2>/dev/null || true
}

usage() {
    cat <<EOF
Usage: ./teslog.sh COMMAND

Commands:
  setup   Wipe any existing .env/data and install fresh: generate secrets,
          ask the one-time config questions, and sign in to TeslaMate
          (briefly starting just enough of the stack to do so, then
          stopping it again). Does NOT start the server — see 'up'.
  up      Start the already-configured stack. Run this on whichever machine
          is actually going to serve Teslog day-to-day. Also (re)installs a
          cron job that exports Teslog's stats to Google Drive via rclone
          (needs an rclone 'gdrive' remote already configured on this
          machine — see README.md). Optional flags, persisted into .env so
          a later plain 'up' remembers them:
            --export-hours N      how often, in hours (default $EXPORT_HOURS_DEFAULT)
            --export-location DIR  folder in the gdrive remote (default $EXPORT_LOCATION_DEFAULT)
  down    Stop the stack and remove the Google Drive export cron job (a
          later 'up' reinstalls it).
  update  Deploy a code change: git pull, rebuild the teslog image, and
          recreate just that container. teslamate/teslamateapi/database
          (and the Drive-export cron) are untouched and keep running
          throughout — no need for 'down' first. Refuses to pull over
          uncommitted local changes.
  -h      Show this help.

Examples:
  ./teslog.sh setup                                            # generate config + sign in to TeslaMate
  ./scripts/migrate-to-pi.sh user@pi-host                      # copy that onto a Pi (~/$PI_ROOT_DEFAULT there)
  ssh user@pi-host 'cd ~/$PI_ROOT_DEFAULT && ./teslog.sh up'    # start serving, on the Pi
  ssh user@pi-host 'cd ~/$PI_ROOT_DEFAULT && ./teslog.sh up --export-hours 12 --export-location backups'
  ssh user@pi-host 'cd ~/$PI_ROOT_DEFAULT && ./teslog.sh update'  # deploy a code change, on the Pi
  ./teslog.sh down                                             # stop (on whichever machine is running it)
EOF
}

COMMAND="${1:-}"

case "$COMMAND" in
    ""|-h|--help)
        usage
        exit 0
        ;;
    setup|up|down|update)
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
    remove_export_cron
    exec "${COMPOSE[@]}" down
fi

if [[ "$COMMAND" == "up" ]]; then
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "No $ENV_FILE found — run './teslog.sh setup' first."
        exit 1
    fi

    shift
    export_hours="" export_location=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --export-hours)
                export_hours="${2:?--export-hours needs a value}"
                shift 2
                ;;
            --export-location)
                export_location="${2:?--export-location needs a value}"
                shift 2
                ;;
            *)
                echo "Unknown option for 'up': $1" >&2
                exit 1
                ;;
        esac
    done
    [[ -n "$export_hours" ]] && set_env "TESLOG_EXPORT_FREQUENCY_HOURS" "$export_hours"
    [[ -n "$export_location" ]] && set_env "TESLOG_EXPORT_LOCATION" "$export_location"

    resolved_hours=$(get_env "TESLOG_EXPORT_FREQUENCY_HOURS")
    resolved_location=$(get_env "TESLOG_EXPORT_LOCATION")
    resolved_hours="${resolved_hours:-$EXPORT_HOURS_DEFAULT}"
    resolved_location="${resolved_location:-$EXPORT_LOCATION_DEFAULT}"

    "${COMPOSE[@]}" up -d
    install_export_cron "$resolved_hours"

    echo
    echo "== Teslog is running =="
    echo "  Teslog dashboard: http://localhost:8080"
    echo "  Google Drive export: every ${resolved_hours}h to gdrive:${resolved_location}/"
    echo "    (needs the 'gdrive' rclone remote configured — see README.md; if it isn't yet,"
    echo "     the export just logs and skips itself each run until you run 'rclone config')"
    exit 0
fi

if [[ "$COMMAND" == "update" ]]; then
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "No $ENV_FILE found — run './teslog.sh setup' first."
        exit 1
    fi
    if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
        echo "Working tree has uncommitted changes — resolve those (see 'git status'), then re-run." >&2
        exit 1
    fi

    echo "-- Pulling latest --"
    git pull
    echo

    # --build only rebuilds services with a 'build:' key (just teslog); 'up -d' only recreates
    # containers whose image/config actually changed — teslamate/teslamateapi/database (and the
    # Drive-export cron) are left running throughout, so this needs no 'down' first. There's a
    # brief blip on the Teslog dashboard itself while its one container restarts.
    echo "-- Rebuilding + redeploying --"
    "${COMPOSE[@]}" up -d --build

    echo
    echo "== Updated =="
    echo "  Teslog dashboard: http://localhost:8080"
    exit 0
fi

# COMMAND == setup: wipe anything existing, install fresh, start, get Tesla tokens.

echo "This will stop the stack (if running) and permanently delete:"
echo "  - $ENV_FILE (all generated secrets)"
echo "  - data/ (TeslaMate's and Teslog's Postgres databases)"
echo "  - $VENV_TESLA_AUTH/ and $VENV_TEST/ (rebuilt fresh below)"
echo
echo "Any existing Tesla sign-in and recorded drives/charges will be gone."
read -r -p "Continue? [y/N]: " confirm_wipe || true
if [[ ! "${confirm_wipe:-}" =~ ^[Yy]$ ]]; then
    echo "Aborted, nothing was deleted."
    exit 1
fi

"${COMPOSE[@]}" down 2>/dev/null || true
rm -f "$ENV_FILE"
rm -rf data "$VENV_TESLA_AUTH" "$VENV_TEST"
echo

cp "$EXAMPLE_FILE" "$ENV_FILE"

prompt_default() {
    local prompt="$1" default="$2" reply
    read -r -p "$prompt [$default]: " reply || true
    echo "${reply:-$default}"
}

find_python312() {
    local candidate
    for candidate in python3.13 python3.12 python3; do
        if command -v "$candidate" >/dev/null 2>&1 \
            && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
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

# Not asked here — these are only ever adjusted via 'up's --export-hours/--export-location
# flags (which persist back into .env themselves). Defaulted here just so they're always set.
set_env "TESLOG_EXPORT_FREQUENCY_HOURS" "$EXPORT_HOURS_DEFAULT"
set_env "TESLOG_EXPORT_LOCATION" "$EXPORT_LOCATION_DEFAULT"

# Also not asked — scripts/migrate-to-pi.sh's destination on the Pi (~/$PI_ROOT_DEFAULT there).
set_env "PI_ROOT" "$PI_ROOT_DEFAULT"
echo

echo "-- Test environment --"
if python_bin=$(find_python312); then
    if "$python_bin" -m venv "$VENV_TEST" \
        && "$VENV_TEST/bin/pip" install --quiet --upgrade pip \
        && "$VENV_TEST/bin/pip" install --quiet -e ".[test]" \
        && "$VENV_TEST/bin/playwright" install chromium; then
        echo "Test environment ready: $VENV_TEST"
    else
        echo "Test environment setup failed — continuing without it (not required to run Teslog)."
        rm -rf "$VENV_TEST"
    fi
else
    echo "No Python 3.12+ found on this machine — skipping the test environment ($VENV_TEST)."
    echo "Not required to run Teslog; only needed for tests/test_dashboard_integration.py."
fi
echo

echo "-- Starting TeslaMate (for sign-in) --"
"${COMPOSE[@]}" up -d database teslamate
echo

echo "-- Tesla sign-in --"
./scripts/get-tesla-tokens.sh

echo
echo "-- Stopping local stack --"
"${COMPOSE[@]}" down
echo

pi_root=$(get_env "PI_ROOT")
pi_root="${pi_root:-$PI_ROOT_DEFAULT}"

echo "== Setup complete =="
echo "TeslaMate is signed in. Nothing is running locally — starting the server is a separate step:"
echo
echo "  ./teslog.sh up                                     # to run right here, or:"
echo "  ./scripts/migrate-to-pi.sh user@pi-host            # to move this onto a Raspberry Pi (~/$pi_root there)"
echo "  ssh user@pi-host 'cd ~/$pi_root && ./teslog.sh up'  # then start it there"
