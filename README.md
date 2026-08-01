# Teslog

Stats dashboard for [TeslaMate](https://github.com/teslamate-org/teslamate): for each completed
drive, compares an OSRM-routed driving distance and the GPS trace distance against the car's
actual odometer delta, and surfaces the drift between them.

Runs on macOS and Linux, including a Raspberry Pi. No MQTT, no Grafana — Teslog is its own
dashboard and doesn't need live status. Real-time nav-drift tracking (MQTT-based) is planned next —
see [docs/phase-2-nav-odometer-drift.md](docs/phase-2-nav-odometer-drift.md).

## Stack

- `teslamate` — Tesla data logger
- `database` — shared Postgres (separate `teslamate` and `teslog` databases)
- `teslamateapi` — REST API in front of TeslaMate's data
- `teslog` — this app: background sync + web dashboard

Routing distances come from [OSRM](https://project-osrm.org/)'s public demo server by default — no
signup or API key needed. No third-party account required anywhere except your own Tesla account.

## Usage

`setup` and `up`/`down` are meant to run on different machines: `setup` needs a real screen for
the Tesla sign-in, so it runs wherever you have one (e.g. a Mac); `up`/`down` start and stop the
actual server, so they run on whichever machine is meant to serve Teslog day-to-day (e.g. a
headless Raspberry Pi). `setup` itself never leaves the server running — see
[scripts/migrate-to-pi.sh](scripts/migrate-to-pi.sh) to move a signed-in setup from one machine to
the other.

```bash
./teslog.sh setup                        # on a machine with a screen: config + Tesla sign-in
./scripts/migrate-to-pi.sh user@pi-host  # copy that onto a Raspberry Pi
ssh user@pi-host './teslog.sh up'        # start serving, on the Pi
./teslog.sh down                         # stop it (on whichever machine is running it)
```

`setup` is a destructive reset — wipes `.env`, all stored data, and the local venvs — then
generates secrets, asks a few config questions, briefly starts just enough of the stack
(`database` + `teslamate`) to sign in to TeslaMate, and stops everything again. `up` is what
actually starts the server; use it for everything after that too (reboots, restarts).

## Tesla sign-in

TeslaMate's sign-in page needs an Access Token and Refresh Token — `setup` gets and submits these
for you automatically. To do it standalone (e.g. to regenerate tokens without a full wipe):

```bash
./scripts/get-tesla-tokens.sh
```

A window opens for you to sign in with your Tesla account — close it once you see your tokens, and
the script submits them into TeslaMate for you. On a headless Pi (no display), run this from a
machine that has one instead, pointed at the Pi:

```bash
TESLAMATE_URL=http://<pi-ip>:4000/sign_in ./scripts/get-tesla-tokens.sh
```

This is also how to re-authenticate later without redoing the whole setup — e.g. if the refresh
token ever gets invalidated (Tesla password change, revoked app access) after the Pi's been
running standalone for a while. Point it at the Pi's live TeslaMate over the network the same way;
this only touches TeslaMate's stored tokens, not `data/`, so the Pi's accumulated drive history is
untouched. (Re-running the full `setup` → `migrate-to-pi.sh` flow instead would overwrite the Pi's
`data/` with the setup machine's near-empty copy — don't do that for a routine re-auth.)

## Backing up to Google Drive

Planned, not yet implemented — will run directly from the Pi. See
[docs/phase-2-nav-odometer-drift.md](docs/phase-2-nav-odometer-drift.md) for other upcoming work.

## Configuration

See [config/.env.example](config/.env.example) for all variables. Notable ones:

| Variable | Purpose |
|---|---|
| `TESLOG_CAR_ID` | Which TeslaMate car ID to track |
| `OSRM_BASE_URL` | OSRM routing server (public demo by default) |
| `TESLOG_SYNC_INTERVAL_SECONDS` | How often to check for new drives (default 900) |

No login on the dashboard itself — it's built for LAN-only use.

## How it works

On a fixed interval (and via the dashboard's "Sync now" button), Teslog reads completed drives and
their GPS trace directly from TeslaMate's Postgres database, calls OSRM for the routed distance
between start and end, and stores the comparison — including drift % — in its own
`drive_route_comparisons` table.

## Testing

```bash
.venv-test/bin/pytest tests/test_dashboard_integration.py -v
```

`.venv-test` is built automatically by `./teslog.sh setup` (needs Python 3.12+ on the host). The
test spins up a throwaway Postgres in Docker, seeds fake data, and drives a real browser against
the actual app.
