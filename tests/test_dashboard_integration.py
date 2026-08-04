"""End-to-end integration test: spins up real, throwaway Postgres databases,
seeds them with fake data (tests/data/*.sql), runs the real Teslog app
against them, and confirms the dashboard actually renders that data in a
real browser. Saves a full-page screenshot to tests/screenshots/dashboard.png
each run, for visual review.

Never touches Google Drive: RCLONE_REMOTE is left unset, and the app itself
has no code path to rclone at all — only the separate scripts/export-to-drive.sh
script does, which this test never invokes.

Run with:
    .venv-test/bin/pytest tests/test_dashboard_integration.py -v

Requires Docker (for the ephemeral Postgres) and Playwright's Chromium
(installed via `playwright install chromium` in the test venv).
"""

import contextlib
import importlib
import os
import pathlib
import threading
import time

# Disable testcontainers' Ryuk cleanup-reaper container: on Docker Desktop for
# Mac it fails to mount the docker socket (a known Docker Desktop issue, not
# specific to this project). Not needed for correctness here anyway — the
# `with PostgresContainer(...)` block below already guarantees cleanup on a
# normal exit; Ryuk only exists as a backstop for an unclean process crash.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import httpx
import psycopg
import pytest
import uvicorn
from playwright.sync_api import sync_playwright
from testcontainers.community.postgres import PostgresContainer

DATA_DIR = pathlib.Path(__file__).parent / "data"
SCREENSHOT_PATH = pathlib.Path(__file__).parent / "screenshots" / "dashboard.png"
TEST_HOST = "127.0.0.1"
TEST_PORT = 18080
BASE_URL = f"http://{TEST_HOST}:{TEST_PORT}"
CAR_ID = 1

# Expected values, hand-derived independently from the fixture data in
# tests/data/ (not by re-running the app's own formulas) — see the
# odometer/osrm/gps distance columns in tests/data/teslog_seed.sql and the
# kwh_used / wh_per_km comments in teslamate_seed.sql for the inputs these
# come from.
EXPECTED_OSRM_DRIFT_PCT = [4.35, 3.85, 4.32, 3.77, 4.48]
EXPECTED_HAVERSINE_DRIFT_PCT = [-2.44, -2.17, -1.36, -1.79, -2.1]
EXPECTED_KWH_USED = [2.43, 2.74, 2.89, 2.28, 2.89]
EXPECTED_WH_PER_KM = [202.7, 202.7, 199.2, 207.3, 206.3]
EXPECTED_CHARGE_ENERGY = [25.40, 30.10, 18.75]
EXPECTED_CHARGE_COST = [8.50, 10.20, None]


def _run_sql_file(conn: psycopg.Connection, path: pathlib.Path) -> None:
    with conn.cursor() as cur:
        cur.execute(path.read_text())
    conn.commit()


@pytest.fixture(scope="module")
def live_app():
    with PostgresContainer("postgres:18-trixie", username="test", password="test", dbname="postgres") as pg:
        host = pg.get_container_host_ip()
        port = int(pg.get_exposed_port(5432))

        # testcontainers only gives us one database; create the two Teslog expects.
        admin_conn = psycopg.connect(host=host, port=port, user="test", password="test", dbname="postgres")
        admin_conn.autocommit = True
        with admin_conn.cursor() as cur:
            cur.execute("CREATE DATABASE teslamate_test")
            cur.execute("CREATE DATABASE teslog_test")
        admin_conn.close()

        tm_conn = psycopg.connect(host=host, port=port, user="test", password="test", dbname="teslamate_test")
        _run_sql_file(tm_conn, DATA_DIR / "teslamate_schema.sql")
        _run_sql_file(tm_conn, DATA_DIR / "teslamate_seed.sql")
        tm_conn.close()

        # Point the app at the test databases. Set every DB-relevant var
        # explicitly so nothing leaks in from a real .env in this repo.
        os.environ.update(
            {
                "TM_DB_HOST": host,
                "TM_DB_PORT": str(port),
                "TM_DB_USER": "test",
                "TM_DB_PASS": "test",
                "TM_DB_NAME": "teslamate_test",
                "TESLOG_DB_HOST": host,
                "TESLOG_DB_PORT": str(port),
                "TESLOG_DB_USER": "test",
                "TESLOG_DB_PASS": "test",
                "TESLOG_DB_NAME": "teslog_test",
                "TESLOG_CAR_ID": str(CAR_ID),
                # Deliberately unreachable: proves the dashboard still renders
                # cleanly (battery health just shows "unavailable") without a
                # running TeslaMateApi.
                "TESLAMATE_API_URL": "http://127.0.0.1:1",
                "OSRM_BASE_URL": "",
                # Long enough that the background sync loop only runs once
                # (at startup) during the test, not repeatedly.
                "TESLOG_SYNC_INTERVAL_SECONDS": "100000",
                "TESLOG_HOST": TEST_HOST,
                "TESLOG_PORT": str(TEST_PORT),
                "TESLOG_RELOAD": "false",
            }
        )
        os.environ.pop("RCLONE_REMOTE", None)  # belt-and-suspenders: no Drive export possible

        import teslog.config

        teslog.config.get_settings.cache_clear()

        import teslog.db

        teslog.db.init_teslog_db()
        teslog_conn = psycopg.connect(host=host, port=port, user="test", password="test", dbname="teslog_test")
        _run_sql_file(teslog_conn, DATA_DIR / "teslog_seed.sql")
        teslog_conn.close()

        import teslog.app

        importlib.reload(teslog.app)  # pick up the settings set above, not any prior import

        config = uvicorn.Config(teslog.app.app, host=TEST_HOST, port=TEST_PORT, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with contextlib.suppress(httpx.HTTPError):
                if httpx.get(f"{BASE_URL}/healthz", timeout=1).status_code == 200:
                    break
            time.sleep(0.2)
        else:
            raise RuntimeError("Teslog server didn't come up in time")

        yield BASE_URL

        server.should_exit = True
        thread.join(timeout=10)


def test_dashboard_shows_seeded_data(live_app):
    base_url = live_app

    # --- The underlying data pipeline: real SQL against the fake Postgres data ---
    with httpx.Client(base_url=base_url) as client:
        drift = client.get("/api/metrics/drift").json()
        assert [row["osrm_drift_pct"] for row in drift] == EXPECTED_OSRM_DRIFT_PCT
        assert [row["haversine_drift_pct"] for row in drift] == EXPECTED_HAVERSINE_DRIFT_PCT

        distance = client.get("/api/metrics/distance").json()
        assert len(distance) == 5
        assert distance[0]["odometer_km"] == 12.0

        energy_used = client.get("/api/metrics/energy-used").json()
        assert [row["kwh_used"] for row in energy_used] == EXPECTED_KWH_USED

        efficiency = client.get("/api/metrics/energy-efficiency").json()
        assert [row["wh_per_km"] for row in efficiency] == EXPECTED_WH_PER_KM

        charging_energy = client.get("/api/metrics/charging-energy").json()
        assert [row["kwh_added"] for row in charging_energy] == EXPECTED_CHARGE_ENERGY

        charging_cost = client.get("/api/metrics/charging-cost").json()
        assert [row["cost"] for row in charging_cost] == EXPECTED_CHARGE_COST

        # No TeslaMateApi running (deliberately unreachable URL above) — the
        # dashboard should degrade gracefully, not error.
        battery = client.get("/api/metrics/battery-health")
        assert battery.status_code == 200
        assert battery.json() == {}

    # --- The actual dashboard, rendered in a real browser ---
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1400})
        page.goto(base_url, wait_until="networkidle")

        # Snapshot of the dashboard with the fake data rendered, for visual
        # review — captured before the assertions below so it's still saved
        # even if one of them fails.
        SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=SCREENSHOT_PATH, full_page=True)

        # Real data present: the empty-state placeholders must be gone.
        assert page.locator(".empty-state", has_text="No drift data yet").count() == 0
        assert page.locator(".empty-state", has_text="No completed drives yet").count() == 0
        assert page.locator(".empty-state", has_text="No energy data yet").count() == 0
        assert page.locator(".empty-state", has_text="No charging sessions yet").count() == 0

        # The drift KPI tile reflects the latest (most recent) seeded drive.
        # The tile intentionally displays 1 decimal place (dashboard.js
        # toFixed(1)), coarser than the underlying 2-decimal API value.
        drift_value = page.locator("#kpi-drift .value").inner_text()
        assert drift_value == f"{EXPECTED_OSRM_DRIFT_PCT[-1]:.1f}%"

        # Battery health has no live TeslaMateApi behind it — should show the
        # "unavailable" placeholder, not a crash or a stale chart.
        battery_value = page.locator("#kpi-battery .value").inner_text()
        assert battery_value == "—"

        # Chart canvases actually mounted (Chart.js draws into a <canvas>).
        assert page.locator("#chart-drift").count() == 1
        assert page.locator("#chart-distance").count() == 1

        browser.close()
