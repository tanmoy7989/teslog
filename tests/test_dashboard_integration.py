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
import statistics
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
# come from. Distance/efficiency are reported in miles (converted from the
# km-native TeslaMate/Teslog data at the API boundary — see metrics.py's
# _mi()/_KM_TO_MI), so the km figures are converted here too (x0.621371,
# same rounding as _mi()) rather than duplicating separate fixture data.
_KM_TO_MI = 0.621371
EXPECTED_OSRM_DRIFT_PCT = [4.35, 3.85, 4.32, 3.77, 4.48]
EXPECTED_HAVERSINE_DRIFT_PCT = [-2.44, -2.17, -1.36, -1.79, -2.1]
EXPECTED_ODOMETER_MI = [round(x * _KM_TO_MI, 2) for x in (12.0, 13.5, 14.5, 11.0, 14.0)]
EXPECTED_KWH_USED = [2.43, 2.74, 2.89, 2.28, 2.89]
# Computed from the same raw inputs as EXPECTED_KWH_USED (teslamate_seed.sql's per-drive
# distance/rated-range and the car's 0.152 kWh/km efficiency), not by converting the already
# *rounded* Wh/mi figure — that loses precision right at the rounding boundary and can disagree
# with the app's actual (unrounded-until-the-end) computation by 0.1 at one or two indices.
EXPECTED_WH_PER_MI = [326.2, 326.2, 320.5, 333.6, 332.0]
EXPECTED_CHARGE_ENERGY = [25.40, 30.10, 18.75]
EXPECTED_CHARGE_COST = [8.50, 10.20, None]

# Progressive cumulative drift, computed the same way metrics.cumulative_drift_series does: at
# each drive, (odometer_end − metrics.PRE_TRACKING_ODOMETER_KM) is "real distance driven since
# tracking began", compared against the running OSRM/GPS total through that drive. Uses the real
# PRE_TRACKING_ODOMETER_KM constant (not a fixture-specific one), so these numbers only make sense
# alongside that constant — if it's ever changed, these need recomputing too.
_ODOMETER_END_KM = [1012.0, 1025.5, 1040.0, 1051.0, 1065.0]
_OSRM_KM = [11.5, 13.0, 13.9, 10.6, 13.4]
_GPS_KM = [12.3, 13.8, 14.7, 11.2, 14.3]


def _cumulative_drift(distances_km: list[float]) -> list[float]:
    from teslog.metrics import PRE_TRACKING_ODOMETER_KM

    cum = 0.0
    out = []
    for odo_end, d in zip(_ODOMETER_END_KM, distances_km, strict=True):
        cum += d
        driven_since_tracking = odo_end - PRE_TRACKING_ODOMETER_KM
        out.append(round((driven_since_tracking - cum) / cum * 100, 2))
    return out


EXPECTED_CUM_OSRM_DRIFT_PCT = _cumulative_drift(_OSRM_KM)
EXPECTED_CUM_GPS_DRIFT_PCT = _cumulative_drift(_GPS_KM)


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

        cumulative_drift = client.get("/api/metrics/cumulative-drift").json()
        assert [row["cum_osrm_drift_pct"] for row in cumulative_drift] == EXPECTED_CUM_OSRM_DRIFT_PCT
        assert [row["cum_gps_drift_pct"] for row in cumulative_drift] == EXPECTED_CUM_GPS_DRIFT_PCT

        distance = client.get("/api/metrics/distance").json()
        assert len(distance) == 5
        assert [row["odometer_mi"] for row in distance] == EXPECTED_ODOMETER_MI

        energy_used = client.get("/api/metrics/energy-used").json()
        assert [row["kwh_used"] for row in energy_used] == EXPECTED_KWH_USED

        efficiency = client.get("/api/metrics/energy-efficiency").json()
        assert [row["wh_per_mi"] for row in efficiency] == EXPECTED_WH_PER_MI

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

        # The drift KPI tile shows both OSRM and Haversine drift as mean +/- sample stdev
        # across every seeded drive, not the latest drive's value. Hand-computed from
        # EXPECTED_OSRM_DRIFT_PCT / EXPECTED_HAVERSINE_DRIFT_PCT with Python's statistics
        # module (sample stdev, ddof=1 — same as dashboard.js's implementation). Tile
        # intentionally displays 1 decimal place (dashboard.js toFixed(1)).
        osrm_drift_value = page.locator("#kpi-drift .drift-value-osrm").inner_text()
        assert osrm_drift_value == f"{statistics.mean(EXPECTED_OSRM_DRIFT_PCT):.1f}%"
        osrm_drift_delta = page.locator("#kpi-drift .drift-delta-osrm").inner_text()
        assert osrm_drift_delta == f"±{statistics.stdev(EXPECTED_OSRM_DRIFT_PCT):.1f}pp"

        haversine_drift_value = page.locator("#kpi-drift .drift-value-haversine").inner_text()
        assert haversine_drift_value == f"{statistics.mean(EXPECTED_HAVERSINE_DRIFT_PCT):.1f}%"
        haversine_drift_delta = page.locator("#kpi-drift .drift-delta-haversine").inner_text()
        assert haversine_drift_delta == f"±{statistics.stdev(EXPECTED_HAVERSINE_DRIFT_PCT):.1f}pp"

        # Cumulative Odometer Drift tile — same mean +/- sample stdev contract, different series.
        cum_osrm_value = page.locator("#kpi-cumulative-drift .cum-drift-value-osrm").inner_text()
        assert cum_osrm_value == f"{statistics.mean(EXPECTED_CUM_OSRM_DRIFT_PCT):.1f}%"
        cum_osrm_delta = page.locator("#kpi-cumulative-drift .cum-drift-delta-osrm").inner_text()
        assert cum_osrm_delta == f"±{statistics.stdev(EXPECTED_CUM_OSRM_DRIFT_PCT):.1f}pp"

        cum_gps_value = page.locator("#kpi-cumulative-drift .cum-drift-value-gps").inner_text()
        assert cum_gps_value == f"{statistics.mean(EXPECTED_CUM_GPS_DRIFT_PCT):.1f}%"
        cum_gps_delta = page.locator("#kpi-cumulative-drift .cum-drift-delta-gps").inner_text()
        assert cum_gps_delta == f"±{statistics.stdev(EXPECTED_CUM_GPS_DRIFT_PCT):.1f}pp"

        # The pre-tracking odometer annotation on the Distance comparison legend — server-rendered
        # (Jinja) from metrics.PRE_TRACKING_ODOMETER_MI/_DATE, not fetched, so this checks the
        # template wiring rather than any API response.
        from teslog.metrics import PRE_TRACKING_ODOMETER_DATE, PRE_TRACKING_ODOMETER_MI

        legend_text = page.locator("#legend-distance").inner_text()
        assert f"Pre-tracking odometer: {PRE_TRACKING_ODOMETER_MI} mi ({PRE_TRACKING_ODOMETER_DATE})" in legend_text

        # Battery health has no live TeslaMateApi behind it — should show the
        # "unavailable" placeholder, not a crash or a stale chart.
        battery_value = page.locator("#kpi-battery .value").inner_text()
        assert battery_value == "—"

        # Efficiency KPI: same mean +/- sample stdev contract as the drift tile, in Wh/mi,
        # rounded to whole numbers (dashboard.js Math.round).
        efficiency_value = page.locator("#kpi-efficiency .value").inner_text()
        assert efficiency_value == f"{round(statistics.mean(EXPECTED_WH_PER_MI))}"
        efficiency_delta = page.locator("#kpi-efficiency .delta").inner_text()
        assert efficiency_delta == f"±{round(statistics.stdev(EXPECTED_WH_PER_MI))} Wh/mi"

        # Chart canvases actually mounted (Chart.js draws into a <canvas>) — including the new
        # odometer-vs-traced-distance scatter — and charging cost is gone (chart removed from
        # the dashboard grid; the API/export field itself is untouched, see routes.py).
        assert page.locator("#chart-drift").count() == 1
        assert page.locator("#chart-distance").count() == 1
        assert page.locator("#chart-scatter").count() == 1
        assert page.locator("#chart-charging-cost").count() == 0

        browser.close()
