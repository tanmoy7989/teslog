#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE=".env"
EXAMPLE_FILE="config/.env.example"

if [[ ! -f "$ENV_FILE" ]]; then
    cp "$EXAMPLE_FILE" "$ENV_FILE"
    echo "Created $ENV_FILE from $EXAMPLE_FILE"
fi

random_secret() {
    openssl rand -hex "$1"
}

set_if_blank() {
    local key="$1" value="$2"
    if grep -qE "^${key}=$" "$ENV_FILE"; then
        sed -i.bak "s|^${key}=\$|${key}=${value}|" "$ENV_FILE"
        rm -f "${ENV_FILE}.bak"
        echo "Set ${key}"
    fi
}

set_if_blank "TM_ENCRYPTION_KEY" "$(random_secret 32)"
set_if_blank "TM_DB_PASS" "$(random_secret 16)"
set_if_blank "TESLOG_DB_PASS" "$(random_secret 16)"
set_if_blank "GRAFANA_PW" "$(random_secret 12)"

echo "Secrets populated in $ENV_FILE."
