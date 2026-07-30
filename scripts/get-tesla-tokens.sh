#!/bin/bash
# Installs (if needed) tesla_auth, runs it to generate a Tesla API access +
# refresh token pair, and automatically submits them into TeslaMate's
# sign-in page (http://localhost:4000/sign_in).
#
# tesla_auth is a third-party tool by TeslaMate's maintainer:
# https://github.com/adriankumpf/tesla_auth
set -euo pipefail

cd "$(dirname "$0")/.."

TESLA_AUTH_VERSION="0.13.0"
BIN_DIR="bin"
BIN_PATH="$BIN_DIR/tesla_auth"
VENV_DIR=".venv-tesla-auth"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This script only supports macOS right now." >&2
    exit 1
fi

case "$(uname -m)" in
    arm64)  TARGET="aarch64-apple-darwin" ;;
    x86_64) TARGET="x86_64-apple-darwin" ;;
    *)
        echo "Unsupported architecture: $(uname -m)" >&2
        exit 1
        ;;
esac

if [[ ! -x "$BIN_PATH" ]]; then
    mkdir -p "$BIN_DIR"
    ASSET="tesla_auth-${TARGET}.tar.xz"
    BASE_URL="https://github.com/adriankumpf/tesla_auth/releases/download/v${TESLA_AUTH_VERSION}"

    echo "Installing tesla_auth v${TESLA_AUTH_VERSION} for ${TARGET}..."
    tmp_dir=$(mktemp -d)
    trap 'rm -rf "$tmp_dir"' EXIT

    curl -sL -o "$tmp_dir/$ASSET" "$BASE_URL/$ASSET"
    curl -sL -o "$tmp_dir/$ASSET.sha256" "$BASE_URL/$ASSET.sha256"

    (cd "$tmp_dir" && shasum -a 256 -c "$ASSET.sha256")

    tar -xf "$tmp_dir/$ASSET" -C "$tmp_dir"
    mv "$tmp_dir/tesla_auth-${TARGET}/tesla_auth" "$BIN_PATH"
    chmod +x "$BIN_PATH"
    echo "Installed to $BIN_PATH"
    echo
fi

if [[ ! -x "$VENV_DIR/bin/playwright" ]]; then
    echo "Setting up browser automation to auto-submit your tokens (one-time)..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet playwright
    "$VENV_DIR/bin/playwright" install chromium
    echo
fi

"$VENV_DIR/bin/python" scripts/tesla_signin.py "$BIN_PATH"
