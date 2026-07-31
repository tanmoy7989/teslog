# Phase 2: NavOdometerDrift

Build this after Phase 1 is running on a always-on host (Raspberry Pi). Phase 1 already computes **OSRM route distance vs odometer delta** on completed drives without MQTT. Phase 2 adds **Tesla navigation planned distance vs odometer** in real time.

## Why Phase 2 exists

TeslaMate stores drive history in PostgreSQL (`start_km`, `end_km`, addresses, GPS positions). That is enough for post-trip OSRM route comparisons (Phase 1).

Tesla navigation metadata (`active_route_destination`, `active_route_miles_to_arrival`, etc.) is **not** persisted to PostgreSQL. TeslaMate publishes it to **MQTT only**, at nav start, during the trip, and when nav clears. If nothing listens during the drive, that data is lost.

Phase 2 adds an MQTT collector that records nav sessions and compares Tesla's planned route distance to the odometer delta for those trips only.

## What requires MQTT

| Feature | MQTT required? | Notes |
|---------|----------------|-------|
| Standard metrics (drives, charges, battery, energy) | No | TeslaMateApi + PostgreSQL |
| OSRM route vs odometer (Phase 1) | No | Computed after drive from DB + OSRM `/route` API |
| GPS trace vs odometer | No | Sum of `positions` after drive |
| **NavOdometerDrift (Phase 2)** | **Yes** | Capture nav start/end snapshots from MQTT |

Only the nav-session collector needs MQTT. The web UI and standard stats do not.

## Prerequisites

- Phase 1 deployed and stable
- Host runs 24/7 (Pi home server)
- Mosquitto added back to the compose stack — Phase 1 runs `DISABLE_MQTT=true` on both TeslaMate
  and TeslaMateApi since nothing in Stage 1 needs it; Phase 2 needs a real broker, and TeslaMate/
  TeslaMateApi need `DISABLE_MQTT` unset (or `false`) and `MQTT_HOST` pointed at it again
- Teslog collector container runs continuously alongside TeslaMate

## Architecture

```
Tesla (nav active)
  → TeslaMate (polls API)
  → Mosquitto MQTT (active_route topic)
  → Teslog nav collector (new)
  → Teslog DB (nav_sessions table)
  → Web UI (Nav Drift screen)
```

Phase 1 tables and APIs stay unchanged. Phase 2 adds tables and one background service.

## MQTT topics to subscribe

TeslaMate publishes (car ID may vary):

- `teslamate/cars/{id}/active_route` — JSON blob with all nav fields (preferred)
- Legacy per-field topics may also exist; prefer the consolidated `active_route` topic

Relevant fields:

| Field | Use |
|-------|-----|
| `active_route_destination` | Destination name; nav active when non-null |
| `active_route_miles_to_arrival` | Tesla planned remaining distance at snapshot time |
| `active_route_latitude` / `active_route_longitude` | Destination coordinates |
| `active_route_minutes_to_arrival` | Optional metadata |
| `active_route_traffic_minutes_delay` | Optional metadata |

On nav end, TeslaMate publishes cleared/null route data.

## Nav session lifecycle

```
1. NAV_START
   - active_route becomes non-null (was null, or destination changed)
   - Snapshot: timestamp, destination, dest lat/lon, miles_to_arrival, odometer
   - Odometer source: TeslaMateApi /status or latest position from PostgreSQL

2. NAV_ACTIVE (optional polling)
   - Update miles_to_arrival if needed for debugging; not required for MVP

3. NAV_END
   - active_route clears (destination null / "No active route available")
   - Snapshot: timestamp, odometer
   - Link to TeslaMate drive_id if drive overlaps same time window

4. COMPUTE (on NAV_END)
   - odometer_delta = odometer_end - odometer_start
   - tesla_nav_distance = miles_to_arrival at NAV_START (converted to km/mi per settings)
   - drift_pct = (odometer_delta - tesla_nav_distance) / tesla_nav_distance × 100
   - Optionally attach Phase 1 osrm_route_distance for same window if drive record exists
```

Handle edge cases:

- **Nav cancelled mid-route** — mark session `status: incomplete`; exclude from aggregates or show separately
- **Nav restarted to new destination** — close previous session as incomplete; open new session
- **Collector offline during drive** — session lost; no backfill possible for Tesla nav distance
- **Short trips** — Tesla odometer reports in ~0.1 mi increments (firmware 2025.2.6+); flag low-confidence sessions

## Database schema (Teslog)

Add to existing Teslog DB (same store as Phase 1 derived metrics):

```sql
CREATE TABLE nav_sessions (
    id              SERIAL PRIMARY KEY,
    car_id          INTEGER NOT NULL,
    drive_id        INTEGER,              -- FK to TeslaMate drives.id if matched
    status          TEXT NOT NULL,        -- active | complete | incomplete | cancelled
    destination     TEXT,
    dest_latitude   DOUBLE PRECISION,
    dest_longitude  DOUBLE PRECISION,
    nav_start_at    TIMESTAMPTZ NOT NULL,
    nav_end_at      TIMESTAMPTZ,
    odometer_start  DOUBLE PRECISION,
    odometer_end    DOUBLE PRECISION,
    tesla_nav_distance DOUBLE PRECISION,  -- miles_to_arrival at nav start
    odometer_delta  DOUBLE PRECISION,     -- computed at nav end
    drift_pct       DOUBLE PRECISION,     -- computed at nav end
    osrm_route_distance DOUBLE PRECISION, -- optional, from Phase 1 if drive matched
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

## Code modules to add

```
src/teslog/
├── collectors/
│   └── nav_route_collector.py    # MQTT subscriber, session state machine
├── stats/
│   └── nav_drift.py              # Aggregates, rolling averages
└── api/
    └── routes/nav_drift.py       # UI + JSON endpoints
```

Wire the collector as a separate process or container entrypoint:

```yaml
# docker-compose.pi.yml (or override)
services:
  teslog-collector:
    build: ./docker/teslog
    command: python -m teslog.collectors.nav_route_collector
    depends_on: [mosquitto, database, teslamate]
    restart: always
```

Phase 1 `teslog` web service stays as-is; only add the collector service on Pi.

## Configuration

Add to `.env` (no new secrets beyond Phase 1):

```bash
MQTT_HOST=mosquitto
MQTT_PORT=1883
# Optional: TESLOG_CAR_ID=1
```

Phase 1 `OSRM_BASE_URL` remains optional for cross-reference on matched drives.

## UI additions

New browser page (LAN only, same as Phase 1):

- **Nav Odometer Drift** — list of nav sessions with Tesla planned vs odometer delta vs drift %
- Rolling average drift (last N complete sessions)
- Filter: complete / incomplete
- Row detail: destination, timestamps, all three distances when available (Tesla nav, OSRM, GPS trace)

## Deployment checklist (Pi)

1. Migrate Teslog DB (apply `nav_sessions` schema)
2. Enable `teslog-collector` service in compose override
3. Confirm Mosquitto is running and TeslaMate publishes `active_route`
4. Test: start nav on Tesla, verify MQTT message, complete trip, verify session in UI
5. Monitor collector logs for missed sessions

## Testing without a drive

1. Subscribe manually: `mosquitto_sub -h localhost -t 'teslamate/cars/+/active_route' -v`
2. Start navigation in the car (or simulate if test harness added later)
3. Confirm collector writes `nav_sessions` row

## Relationship to Phase 1 metric

| Metric | Phase | When computed | Reference distance |
|--------|-------|---------------|-------------------|
| Route vs odometer (OSRM) | 1 | After every drive | OSRM `/route` API |
| **NavOdometerDrift (Tesla nav)** | 2 | At nav end (real time) | `active_route_miles_to_arrival` at nav start |
| GPS trace vs odometer | 1 or 2 | After drive | Sum of position points |

Phase 2 sessions can link to Phase 1 `drive_route_comparisons` (or equivalent) by `drive_id` so one trip shows OSRM, Tesla nav, and GPS comparisons side by side when data exists.

## Out of scope for Phase 2 MVP

- Home Assistant integration
- Public internet / TLS exposure
- Backfilling historical nav sessions (impossible without MQTT capture at trip time)
