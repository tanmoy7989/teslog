# Teslog

Stats dashboard for [TeslaMate](https://github.com/teslamate-org/teslamate) with route-vs-odometer
analysis: for each completed drive, compares an OSRM-routed driving distance and the raw GPS
trace distance against the car's actual odometer delta, and surfaces the drift between them.

Stage 1 (this repo, current) runs entirely off TeslaMate's PostgreSQL database after a drive
completes — no MQTT required. Stage 2 (real-time Tesla navigation drift, MQTT-based) is planned
in [docs/phase-2-nav-odometer-drift.md](docs/phase-2-nav-odometer-drift.md).

## Stack

Teslog runs alongside an existing (or fresh) TeslaMate deployment:

- `teslamate` — Tesla data logger
- `database` — shared Postgres instance (separate `teslamate` and `teslog` databases)
- `grafana` — TeslaMate's stock dashboards
- `mosquitto` — MQTT broker (used by TeslaMate/TeslaMateApi for live status; not required by Teslog stage 1)
- `teslamateapi` — REST API in front of TeslaMate's data
- `teslog` — this app: background sync + web dashboard

Routing distances come from [OSRM](https://project-osrm.org/) — by default the public demo
server, which needs no signup or API key. No third-party account or login is required anywhere in
this stack except your own Tesla account.

## Usage

```bash
./teslog.sh setup   # first time, or to wipe everything and start completely over
./teslog.sh up       # day-to-day: start the already-configured stack
./teslog.sh down     # stop it
./teslog.sh -h       # help
```

**`setup`** is a destructive reset, not a day-to-day command — it wipes `.env` and all stored data
(TeslaMate/Teslog databases, Grafana dashboards, your Tesla sign-in) and installs from a clean
slate. It asks for confirmation first. It will:

1. Check Docker is installed and running.
2. Generate fresh secrets into `.env` (`TM_ENCRYPTION_KEY`, DB passwords, `GRAFANA_PW`).
3. Ask the one-time config questions: timezone, which TeslaMate car ID to track, the OSRM server.
4. Start the stack.
5. Run the Tesla sign-in token generator (see below) and print the tokens for you to paste into
   TeslaMate.

Use `up` for everything after that — starting the stack again after a reboot or `down` — without
touching any of the above.

Once running: TeslaMate is at `http://localhost:4000`, the Teslog dashboard at
`http://localhost:8080`. Teslog picks up drives once TeslaMate has recorded at least one completed
one.

### Tesla sign-in

TeslaMate's sign-in page (`http://localhost:4000/sign_in`) asks for an Access Token and Refresh
Token — there's no `TESLA_...` variable in `.env`, and TeslaMate doesn't do the Tesla login itself.

`./teslog.sh setup` handles this automatically — end to end, no copy-pasting. You can also run it
standalone (e.g. if your tokens ever need regenerating without a full wipe):

```bash
./scripts/get-tesla-tokens.sh
```

First run: installs [`tesla_auth`](https://github.com/adriankumpf/tesla_auth) (checksum-verified)
to `bin/tesla_auth` — a small third-party tool by TeslaMate's own maintainer — and sets up a local
Python environment (`.venv-tesla-auth/`, gitignored) with a headless browser for the auto-submit
step. Every run: a window opens for you to sign in with your real Tesla account (2FA included).
**Once you see your tokens there, close that window** — `tesla_auth` never exits on its own, so
this script waits for you to close it, then reads the tokens and submits them into TeslaMate's
sign-in page for you automatically. If the auto-submit fails for any reason, it prints both tokens
so you can paste them in by hand instead.

TeslaMate stores the tokens (encrypted with `TM_ENCRYPTION_KEY`) in its own database and silently
refreshes the short-lived (~8h) access token in the background from then on — you don't repeat this
routinely. You'd only need to again if the refresh token itself gets invalidated (Tesla password
change, revoked app access) or `TM_ENCRYPTION_KEY` changes, i.e. after `./teslog.sh setup`.

> **Note:** if TeslaMate is *already* signed in, re-running this can trip a pre-existing TeslaMate
> bug (its sign-in page doesn't gracefully handle a resubmission while already authenticated — it
> logs an error and that one page's connection resets, but nothing else is affected). This doesn't
> come up during normal use since `./teslog.sh setup` always wipes TeslaMate's stored session first.

## Configuration

See [config/.env.example](config/.env.example) for the full list of variables. Notable ones:

| Variable | Purpose |
|---|---|
| `TESLOG_CAR_ID` | Which TeslaMate car ID to track (single-car app) |
| `OSRM_BASE_URL` | OSRM routing server for the route-distance comparison (public demo server by default) |
| `TESLOG_SYNC_INTERVAL_SECONDS` | How often to check for newly completed drives (default 900) |

There's no login/auth on the dashboard itself — it's built for LAN-only use.

## How it works

On a fixed interval (and on-demand via the dashboard's "Sync now" button / `POST /api/sync`),
Teslog:

1. Reads completed drives (`end_date IS NOT NULL`) for the configured car directly from
   TeslaMate's Postgres database.
2. Reads that drive's GPS trace from TeslaMate's `positions` table and sums point-to-point
   distance (haversine) for the GPS-trace comparison.
3. Calls OSRM's `/route` API between the first and last recorded GPS point for the route-distance
   comparison.
4. Computes `odometer_delta` from the drive's `start_km`/`end_km` and stores everything —
   including drift % vs the OSRM route distance — in Teslog's own `drive_route_comparisons` table.

> **Note:** the direct TeslaMate DB queries (`drives`, `positions`, `addresses` tables) assume the
> standard open-source TeslaMate schema. If your TeslaMate version has renamed/removed any of
> those columns, sync will fail — check the `teslog` container's logs.
>
> **Note:** the public OSRM demo server is meant for light, non-commercial use and isn't guaranteed
> uptime/rate limits. For a permanent Pi deployment, consider self-hosting OSRM (a Docker image
> with a regional OSM extract) and pointing `OSRM_BASE_URL` at it — no other code changes needed.
