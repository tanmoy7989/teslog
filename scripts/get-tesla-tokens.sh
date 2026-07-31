#!/bin/bash
# Installs (if needed) tesla_auth, runs it to generate a Tesla API access +
# refresh token pair, and automatically submits them into TeslaMate's
# sign-in page.
#
# tesla_auth is a third-party tool by TeslaMate's maintainer:
# https://github.com/adriankumpf/tesla_auth
#
# This needs a real display — tesla_auth is a GUI window and this script
# drives a real browser to submit the form. It will NOT work on a headless
# machine (e.g. a barebones Raspberry Pi with no desktop). If TeslaMate runs
# on a headless Pi, run this script from your Mac (or any machine with a
# screen) instead, pointing it at the Pi over the network:
#
#   TESLAMATE_URL=http://<pi-ip>:4000/sign_in ./scripts/get-tesla-tokens.sh
set -euo pipefail

cd "$(dirname "$0")/.."

TESLA_AUTH_VERSION="0.13.0"
BIN_DIR="bin"
BIN_PATH="$BIN_DIR/tesla_auth"
VENV_DIR=".venv-tesla-auth"

OS="$(uname -s)"

case "$OS" in
    Darwin)
        case "$(uname -m)" in
            arm64)  TARGET="aarch64-apple-darwin" ;;
            x86_64) TARGET="x86_64-apple-darwin" ;;
            *)
                echo "Unsupported architecture: $(uname -m)" >&2
                exit 1
                ;;
        esac
        ;;
    Linux)
        if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
            echo "No display detected (\$DISPLAY / \$WAYLAND_DISPLAY are unset)." >&2
            echo "tesla_auth is a GUI app and this script drives a real browser — neither" >&2
            echo "works on a headless machine (e.g. a barebones Raspberry Pi)." >&2
            echo >&2
            echo "Run this script from a machine with a screen instead, pointing it at" >&2
            echo "this host's TeslaMate over the network:" >&2
            echo "  TESLAMATE_URL=http://<this-host-ip>:4000/sign_in ./scripts/get-tesla-tokens.sh" >&2
            exit 1
        fi
        case "$(uname -m)" in
            aarch64|arm64) TARGET="aarch64-unknown-linux-gnu" ;;
            x86_64)        TARGET="x86_64-unknown-linux-gnu" ;;
            *)
                echo "Unsupported architecture: $(uname -m)" >&2
                exit 1
                ;;
        esac
        ;;
    *)
        echo "Unsupported OS: $OS" >&2
        exit 1
        ;;
esac

verify_checksum() {
    local asset="$1" sumfile="$2"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -c "$sumfile"
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -c "$sumfile"
    else
        echo "Neither sha256sum nor shasum found — can't verify the download. Aborting." >&2
        exit 1
    fi
}

if [[ ! -x "$BIN_PATH" ]]; then
    mkdir -p "$BIN_DIR"
    ASSET="tesla_auth-${TARGET}.tar.xz"
    BASE_URL="https://github.com/adriankumpf/tesla_auth/releases/download/v${TESLA_AUTH_VERSION}"

    echo "Installing tesla_auth v${TESLA_AUTH_VERSION} for ${TARGET}..."
    tmp_dir=$(mktemp -d)
    trap 'rm -rf "$tmp_dir"' EXIT

    curl -sL -o "$tmp_dir/$ASSET" "$BASE_URL/$ASSET"
    curl -sL -o "$tmp_dir/$ASSET.sha256" "$BASE_URL/$ASSET.sha256"

    (cd "$tmp_dir" && verify_checksum "$ASSET" "$ASSET.sha256")

    tar -xf "$tmp_dir/$ASSET" -C "$tmp_dir"
    mv "$tmp_dir/tesla_auth-${TARGET}/tesla_auth" "$BIN_PATH"
    chmod +x "$BIN_PATH"
    echo "Installed to $BIN_PATH"
    echo

    if [[ "$OS" == "Linux" ]]; then
        echo "Note: on Linux, tesla_auth also needs WebKitGTK (per its own docs). If it fails to launch:" >&2
        echo "  Debian/Ubuntu: sudo apt install libwebkit2gtk-4.1-dev libxdo-dev" >&2
        echo >&2
    fi
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
