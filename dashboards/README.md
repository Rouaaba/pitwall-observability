# Dashboards

Three plain Grafana dashboard JSON files, not yet managed by Terraform
(that's Phase 4). Import them directly through the Grafana Cloud UI.

- `pit-wall.json` — race overview: positions, gap to leader, tyre strategy,
  lap time heatmap, race control log panel.
- `driver-deep-dive.json` — single-driver telemetry, sector pace, stint
  history, lap traces (`$session`/`$driver` filtered).
- `replay-health.json` — the replay's own self-observability: events/sec,
  replay lag, export success/failure.

## Importing

1. In Grafana Cloud: **Dashboards → New → Import**.
2. Upload the JSON file (or paste its contents).
3. When prompted, map the datasource inputs:
   - `DS_PROMETHEUS` → your stack's Prometheus/Mimir datasource
   - `DS_LOKI` → your stack's Loki datasource
   - `DS_TEMPO` → your stack's Tempo datasource (driver deep dive only)
4. Click Import.

## Prerequisites

- The replay must have sent at least a few minutes of data (`docker compose
  up`) so the `$driver` template variable has values to populate from.
- For the pit-stop/race-control-to-trace link described in the root
  README, add a **Loki derived field** (Settings → Data sources → your Loki
  datasource → Derived fields) matching the `trace_id` log attribute and
  pointing at your Tempo datasource. This is one-time manual setup, not
  expressible in these dashboard JSON files.

## Known gaps / things to verify after importing

These were flagged during design because they depend on exactly how your
Grafana Cloud stack is configured, and couldn't be verified without query
access to it:

- **Lap time heatmap** (`pit-wall.json`) assumes `pitwall_lap_time_distribution_seconds`
  lands as a classic Prometheus histogram (`_bucket`/`_sum`/`_count`). If
  your OTLP pipeline instead produces a native Prometheus histogram, change
  the panel's query to `pitwall_lap_time_distribution_seconds{driver=~"$driver"}`
  and switch the heatmap's histogram format to "Native" in the panel editor.
- **Positions panel Y-axis inversion** uses `fieldConfig.defaults.custom.axisInverted`.
  If your Grafana version doesn't support this field, use a Standard
  options override instead: Min=20.5, Max=0.5.
- **Race control / tyre strategy LogQL** assumes `logfmt`-style attribute
  flattening on log lines. If Grafana Cloud's OTLP→Loki translation uses
  JSON instead, swap `| logfmt` for `| json` in the affected queries
  (`pit-wall.json` panels 3 and 5, the Race Control annotation, and
  `driver-deep-dive.json` panel 4).
- **`$session` dashboard variable**: deliberately not added. `session_key`
  is currently only a label on `pitwall_build_info`, not on per-event
  metrics (`pitwall_lap_time_seconds` etc.) — see `pipeline/engine.py`'s
  `_attrs()`. These dashboards assume a single session is being replayed
  at a time, which matches how the replay is actually run today. Loki and
  Tempo panels still carry `pitwall.session_key` as a resource
  attribute/label if you want to add session filtering to those queries
  later.
- **Replay Health's Alloy/export-error panels** will show "No data" until
  Alloy is configured to scrape and export its own metrics — it currently
  only proxies the replay's OTLP data (see `alloy/config.alloy`). Adding
  Alloy self-monitoring is deferred; the panels are included so they're
  ready once that's wired up.
- **Tyre strategy state-timeline** is built from `stint_start` log lines
  (via Loki extract-fields/group-by transforms), not the `pitwall_tyre_age_laps`
  gauge, so it renders as clean gap-free blocks per stint. If the
  transform chain doesn't render as expected in your Grafana version,
  check Explore on the underlying Loki query first to confirm `driver`
  and `compound` are being extracted as fields.
