# Teslog

Stats dashboard for [TeslaMate](https://github.com/teslamate-org/teslamate) with route-vs-odometer
analysis: for each completed drive, compares an OSRM-routed driving distance and the raw GPS
trace distance against the car's actual odometer delta, and surfaces the drift between them.

Stage 1 (this repo, current) runs entirely off TeslaMate's PostgreSQL database after a drive
completes — no MQTT required, so there's no Mosquitto broker in this stack (both TeslaMate and
TeslaMateApi run with `DISABLE_MQTT=true`). Stage 2 (real-time Tesla navigation drift) needs MQTT
and will reintroduce it — see [docs/phase-2-nav-odometer-drift.md](docs/phase-2-nav-odometer-drift.md).

No Grafana either — Teslog is its own dashboard now, so TeslaMate's stock Grafana dashboards aren't
part of this stack. If you want that broader TeslaMate coverage (battery degradation trends,
charging curves, drive maps) alongside Teslog, you can always run
[TeslaMate's own compose stack](https://github.com/teslamate-org/teslamate) with Grafana separately
against the same database.

## Stack

Teslog runs alongside an existing (or fresh) TeslaMate deployment:

- `teslamate` — Tesla data logger
- `database` — shared Postgres instance (separate `teslamate` and `teslog` databases)
- `teslamateapi` — REST API in front of TeslaMate's data
- `teslog` — this app: background sync + web dashboard

Routing distances come from [OSRM](https://project-osrm.org/) — by default the public demo
server, which needs no signup or API key. No third-party account or login is required anywhere in
this stack except your own Tesla account.

## Usage

Runs on macOS and Linux (including a Raspberry Pi — TeslaMate itself is commonly run there, and
every base image in this stack ships an arm64 build).

```bash
./teslog.sh setup   # first time, or to wipe everything and start completely over
./teslog.sh up       # day-to-day: start the already-configured stack
./teslog.sh down     # stop it
./teslog.sh -h       # help
```

**`setup`** is a destructive reset, not a day-to-day command — it wipes `.env` and all stored data
(TeslaMate/Teslog databases, your Tesla sign-in) and installs from a clean slate. It asks for
confirmation first. It will:

1. Check Docker is installed and running.
2. Generate fresh secrets into `.env` (`TM_ENCRYPTION_KEY`, DB passwords).
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

**On a headless Raspberry Pi:** this step needs a real screen — `tesla_auth` is a GUI window and
the auto-submit drives a real browser, neither of which can run on a barebones/Lite Pi with no
desktop. That's a hard constraint, not a missing-binary problem — installing WebKitGTK and a fake
display on the Pi just to work around it isn't worth it. Instead, run this step from your Mac (or
any machine with a screen), pointed at the Pi over the network:

```bash
TESLAMATE_URL=http://<pi-ip>:4000/sign_in ./scripts/get-tesla-tokens.sh
```

Tesla auth doesn't care which machine submits the form, only that TeslaMate's sign-in page receives
it — so this works identically to running it locally, just aimed at the Pi's IP instead of
`localhost`. This also composes with `./teslog.sh setup` itself: run `setup` on the Pi as normal —
it wipes/regenerates everything and starts the stack same as always — and when it reaches the Tesla
sign-in step, `get-tesla-tokens.sh` detects there's no display, prints the same override command
above, and exits (the stack is already up at that point, nothing hangs). Run that command from your
Mac to finish signing in.

### Backing up your stats to Google Drive

Optional. Mirrors Teslog's own computed stats (the same CSVs downloadable from the dashboard —
drift, distance comparison, energy, charging) to Google Drive on a schedule, as a durable off-machine
backup and a way to check your numbers from your phone. No TeslaMate raw data (drives, positions,
charges) is touched, and your local Postgres stays the source of truth — the dashboard keeps working
exactly as before, on or off the internet, whether or not this is set up.

Uses [`rclone`](https://rclone.org/) rather than Google Drive for Desktop, since rclone works
identically on both Mac and a future Raspberry Pi (Drive for Desktop is Mac/Windows only).

One-time setup:

```bash
brew install rclone         # macOS
# curl https://rclone.org/install.sh | sudo bash   # Raspberry Pi / Linux

rclone config                # follow the prompts to add a Google Drive remote,
                              # e.g. name it "gdrive" — this opens a browser to
                              # authorize access to your account
```

Then add the remote (and path within it) to `.env`:

```bash
RCLONE_REMOTE=gdrive:teslog
```

Run it manually any time:

```bash
./scripts/export-to-drive.sh
```

Or install a cron entry so it runs every 15 minutes on its own (idempotent — safe to run again,
won't create a duplicate; leaves any of your other existing cron jobs alone):

```bash
./scripts/install-drive-export-cron.sh
```

If `RCLONE_REMOTE` isn't set, `export-to-drive.sh` just skips itself — safe to leave the cron entry
installed even before you've configured rclone.

## Configuration

See [config/.env.example](config/.env.example) for the full list of variables. Notable ones:

| Variable | Purpose |
|---|---|
| `TESLOG_CAR_ID` | Which TeslaMate car ID to track (single-car app) |
| `OSRM_BASE_URL` | OSRM routing server for the route-distance comparison (public demo server by default) |
| `TESLOG_SYNC_INTERVAL_SECONDS` | How often to check for newly completed drives (default 900) |
| `RCLONE_REMOTE` | Optional — enables the Google Drive backup export (see above) |

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

## Testing

`tests/test_dashboard_integration.py` is a real end-to-end test: it spins up throwaway Postgres
databases in Docker, seeds them with fake data (`tests/data/*.sql`), runs the actual app against
them, and drives a real (headless) browser to confirm the dashboard renders that data correctly —
not just that the API returns the right numbers. Never touches Google Drive. Not wired into CI yet;
run it locally:

```bash
python3.12 -m venv .venv-test
.venv-test/bin/pip install -e ".[test]"
.venv-test/bin/playwright install chromium   # one-time

.venv-test/bin/pytest tests/test_dashboard_integration.py -v
```

Needs Docker running (for the test Postgres) and Python 3.12+ on the host for this venv — separate
from the app itself, which only ever runs inside Docker.
