# pitwall-observability

A race, treated like a production system. A replay engine streams a historical
Formula racing session at any speed and re-times it onto the current clock, so
it can be demoed any day of the week. Each car is a service, laps are traces,
sectors are spans, tyre wear is error-budget burn, and race control messages
are incident annotations.

Built in phases on top of a small Python service that replays a past race and
sends lap metrics to Grafana Cloud via Grafana Alloy (OpenTelemetry). Later
phases add traces, SLOs, a Kubernetes deployment, a custom Grafana panel
plugin, and chaos experiments.

## Status

Phase 1: replay engine and metrics. `docker compose up` replays the cached
2023 Qatar GP and sends live metrics to Grafana Cloud.

## Project layout

```
pitwall-observability/
├── replay/            # Python replay engine
├── tests/              # pytest unit tests (clock, events, engine)
├── alloy/             # Alloy config
├── dashboards/        # dashboard JSON
├── terraform/         # Grafana Cloud as code
├── deploy/            # Helm charts / k8s manifests
├── plugins/trackmap/  # Grafana panel plugin
├── chaos/             # experiments and write-ups
├── notebooks/
├── Dockerfile
├── docker-compose.yml
└── README.md
```

<!-- TODO: GIF of the replay driving a Grafana Cloud dashboard, once Phase 2/3 dashboards exist -->

## Design rules

- **Re-time everything to now.** Grafana Cloud's metrics backend rejects
  samples that are too old, so the replay shifts every historical timestamp
  onto the current clock.
- **Watch cardinality.** Label by driver, team and session, never by lap
  number.
- **One collector.** Everything goes through Grafana Alloy, so the pipeline
  is the same locally and on Kubernetes.
- **Everything as code.** Dashboards, alerts and SLOs end up in Terraform by
  Phase 4.

## Setup

1. Copy `.env.example` to `.env` and fill in your Grafana Cloud OTLP
   credentials (endpoint, instance ID, token).
2. Create a virtualenv and install dependencies:
   ```
   python3 -m venv .venv
   .venv/bin/pip install -r requirements-dev.txt
   ```
3. Fetch and cache race data (only needed once per session):
   `.venv/bin/python replay/fetch_openf1.py --year 2023 --meeting Qatar`
4. Explore the data: `.venv/bin/jupyter lab notebooks/`

## Running the replay

```
docker compose up --build
```

This starts Grafana Alloy and the replay engine, which streams the cached
2023 Qatar GP (`session_key=9221`) at 1x speed and sends `pitwall_*` metrics
over OTLP to Alloy, which forwards them to Grafana Cloud. Override the
session or speed with environment variables:

```
SPEED=60 docker compose up --build
```

`--speed` accepts `1`, `5`, `10` or `60`. Every emitted metric is timestamped
with the real wall-clock moment it's sent, so dashboards always show "now" —
at higher speeds the whole race simply plays out faster in real time.

The replay also reports on itself: `pitwall_replay_events_total` (by event
kind) and `pitwall_replay_lag_seconds` (how far behind schedule it is) are
sent alongside the race metrics, the same way you'd instrument any
production service.

### Running outside Docker

```
.venv/bin/python -m replay --session-key 9221 --speed 1 --otlp-endpoint localhost:4317
```

## Tests and linting

```
.venv/bin/pytest tests/ -v
.venv/bin/ruff check .
```
