# pitwall-observability

A race-weekend companion for the current Formula 1 season, built and run
like a production system: a near-live ingestion pipeline with SLOs and
alerting, plus a rehearsal tool that replays last year's race at the same
circuit through that same pipeline before each real Grand Prix. Each car is
a service, laps are traces, sectors are spans, tyre wear is error-budget
burn, and race control messages are incident annotations.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full picture:
the Briefing/Debrief/pipeline/rehearsal parts, the `season`/`race`/`session`
label convention, and why OpenF1's free-tier rate limit shapes the whole
cache-once design.

## Status

Phase 3: dashboards, plus a restructure into a shared pipeline. `docker
compose up` replays the cached 2023 Qatar GP and sends live metrics, logs
and traces to Grafana Cloud; import the dashboards in
[`dashboards/`](dashboards/) to watch it as a pit wall, a driver deep dive,
and the pipeline's own self-observability. `python -m pipeline.briefing`
generates precomputed Briefing snapshots from OpenF1 (see
[`docs/OPERATIONS.md`](docs/OPERATIONS.md)); the Briefing UI itself,
Debrief, SLOs and alerting are still to come.

## Project layout

```
pitwall-observability/
├── pipeline/           # Python ingestion pipeline (rehearsal + production use)
├── tests/              # pytest unit tests
├── alloy/              # Alloy config
├── dashboards/         # dashboard JSON
├── docs/                # architecture docs
├── terraform/           # Grafana Cloud as code
├── deploy/              # Helm charts / k8s manifests
├── plugins/trackmap/    # Grafana panel plugin
├── chaos/                # experiments and write-ups
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
   `.venv/bin/python -m pipeline.fetch_openf1 --year 2023 --meeting Qatar`
4. Explore the data: `.venv/bin/jupyter lab notebooks/`

## Running the replay

```
docker compose up --build
```

This starts Grafana Alloy and the replay engine, which streams the cached
2023 Qatar GP (`SEASON=2023 RACE=Qatar SESSION_TYPE=Race`, the default) at
1x speed and sends `pitwall_*` metrics over OTLP to Alloy, which forwards
them to Grafana Cloud. Override the speed with an environment variable:

```
SPEED=60 docker compose up --build
```

`--speed` accepts `1`, `5`, `10` or `60`. Every emitted metric is timestamped
with the real wall-clock moment it's sent, so dashboards always show "now" —
at higher speeds the whole race simply plays out faster in real time.

### Choosing a race

The replay is configurable by season, race and session type — not hardcoded
to one session. Pick a race with flags or environment variables:

```
.venv/bin/python -m pipeline --season 2023 --race "United Arab Emirates" --session-type Qualifying --speed 10
```

```
SEASON=2023 RACE="United Arab Emirates" SESSION_TYPE=Qualifying docker compose up --build
```

Season/race/session are matched against whatever's cached under `data/`
(see [Setup](#setup) to fetch a new one first). If the race isn't cached,
the replay fails fast and tells you exactly what *is* cached and the
`fetch_openf1.py` command to download the one you asked for. You can also
skip the lookup and target a cached session directly with
`--session-key <key>` (e.g. `--session-key 9221`), which is what the
project used exclusively before this became configurable.

These three values become labels on every `pitwall_*` metric, named exactly
`season`, `race` and `session` (matching Grafana dashboard variable names):

| Label | Example | Shape |
|---|---|---|
| `season` | `2023` | string year |
| `race` | `qatar`, `abu_dhabi` | lowercase, spaces/punctuation → `_` |
| `session` | `R`, `Q`, `S`, `SQ`, `FP1`, `FP2`, `FP3` | short code |

The same three values are also set as resource attributes
(`pitwall.season`, `pitwall.race`, `pitwall.session`) on the logs and traces
providers, for consistency — but dashboards filtering on metrics should use
the per-metric labels above, not resource attributes. Grafana Cloud's
OTLP-to-Prometheus path mostly surfaces resource attributes as `target_info`
rather than as labels on every series, so relying on them for metric
filtering would silently break.

The replay also reports on itself: `pitwall_replay_events_total` (by event
kind) and `pitwall_replay_lag_seconds` (how far behind schedule it is) are
sent alongside the race metrics, the same way you'd instrument any
production service.

## Traces and logs

Each completed lap becomes one trace: a root `lap` span covering the lap's
real duration, with three back-to-back `sector_1`/`sector_2`/`sector_3` child
spans built from the sector durations, and a `pit_stop` child span on laps
with a pit stop. Spans carry `driver`, `team`, `compound`, `tyre_age`,
`position` and `lap_number` as attributes — lap number is fine on spans,
since span attributes don't create new metric series the way a label would.

Race control messages, pit stops, stint changes and team radio (just the
`recording_url` — transcription is a stretch goal) are sent as logs. Only
`service.name` and `session_key` are Loki labels; driver, flag, lap number
and compound stay as structured log attributes so label cardinality stays
flat regardless of race length.

Race control severity: a red flag is `ERROR`, a safety car or yellow flag is
`WARN`, everything else is `INFO`.

Pit stop and race control log lines carry the `trace_id` of whichever lap
trace most recently completed for that driver, so a Loki derived field can
jump straight to the matching Tempo trace. This is a best-effort link, not
exact forensic lap attribution — a pit stop is logged against the latest
*completed* lap trace at the moment it's processed, since OpenF1's data
doesn't let the single-pass replay know in advance which lap a pit stop
"belongs" to.

Example TraceQL query — every sector 2 slower than 32 seconds on medium
tyres:

```
{ name = "sector_2" && duration > 32s && span.compound = "MEDIUM" }
```

### One-time Grafana Cloud setup

To click from a pit-stop log line to its trace, add a **derived field** on
the Loki data source in Grafana Cloud: match the `trace_id` log attribute
and point it at the Tempo data source. This is manual UI configuration (not
yet in Terraform — that's Phase 4) and only needs doing once per stack.

### Running outside Docker

```
.venv/bin/python -m pipeline --season 2023 --race Qatar --session-type Race --speed 1 --otlp-endpoint localhost:4317
```

### Alloy self-monitoring

Alloy scrapes its own `/metrics` endpoint and routes the result through the
same OTLP exporter used for the replay's own telemetry, so
`otelcol_exporter_sent_*`/`otelcol_exporter_send_failed_*` reach Grafana
Cloud without a second credential. These series carry `job="alloy"`.

## Tests and linting

```
.venv/bin/pytest tests/ -v
.venv/bin/ruff check .
```

## Pre-commit hooks

A gitleaks pre-commit hook scans every commit for hardcoded secrets before
it's created. Install it once per checkout:

```
.venv/bin/pre-commit install
```

After that, `git commit` runs the scan automatically and blocks the commit
if it finds anything.
