#!/usr/bin/env python3
"""Runs tesla_auth, then submits the resulting token pair into TeslaMate's
sign-in page automatically.

tesla_auth is a GUI app (a WebKit window) that never exits on its own once
it shows the final token screen — the window stays open until you close it.
It also prints both tokens to stdout in a fixed, parseable banner, but only
once its process actually exits (piped stdout isn't guaranteed to flush
before then). So: sign in in the window that opens, then close it once you
see your tokens — this script picks them up right after and drives the
sign-in for you. If anything about the auto-submit fails, the tokens are
printed for you to paste in by hand instead.
"""

import os
import re
import subprocess
import sys

TESLAMATE_URL = os.environ.get("TESLAMATE_URL", "http://localhost:4000/sign_in")

TOKEN_PATTERN = re.compile(
    r"ACCESS TOKEN -+\s*\n\s*\n(?P<access>\S+)\s*\n.*?"
    r"REFRESH TOKEN -+\s*\n\s*\n(?P<refresh>\S+)",
    re.DOTALL,
)


def get_tokens(binary: str) -> tuple[str, str]:
    result = subprocess.run([binary], capture_output=True, text=True)
    print(result.stdout)
    match = TOKEN_PATTERN.search(result.stdout)
    if not match:
        raise RuntimeError("tesla_auth didn't produce a token pair (login canceled or failed?)")
    return match.group("access"), match.group("refresh")


def submit_to_teslamate(access: str, refresh: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(TESLAMATE_URL, wait_until="networkidle")
        page.fill('input[name="tokens[access]"]', access)
        page.fill('input[name="tokens[refresh]"]', refresh)
        page.click('button[type="submit"]', timeout=10_000)
        page.wait_for_timeout(1000)
        browser.close()


def main() -> None:
    binary = sys.argv[1] if len(sys.argv) > 1 else "./bin/tesla_auth"
    print("A window will open for you to sign in with your Tesla account.")
    print("Once you see your tokens there, close that window to continue.\n")

    access, refresh = get_tokens(binary)

    print("Got tokens — signing in to TeslaMate automatically...")
    try:
        submit_to_teslamate(access, refresh)
        print("Signed in to TeslaMate.")
    except Exception as exc:
        print(f"Auto sign-in failed ({exc}).")
        print(f"Paste these into {TESLAMATE_URL} manually:")
        print(f"  Access Token:  {access}")
        print(f"  Refresh Token: {refresh}")


if __name__ == "__main__":
    main()
