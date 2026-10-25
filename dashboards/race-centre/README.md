# Pitwall: Race Centre

Grafana dashboard (`dashboard.grafana.app/v2`, UID `roscr2t`). It shows the race weekend for the selected meeting across five tabs. Pre-race and Post-race are never shown together, so only four are visible at once:

| Tab | Layout | Shown when |
|---|---|---|
| Weekend | GridLayout | always |
| Pre-race | AutoGridLayout (3 cols) | `$phase == pre_race` |
| Post-race | AutoGridLayout (3 cols) | `$phase == post_race` |
| Strategy & circuit history | GridLayout | always |
| Championship | GridLayout | always |

All data comes from the `pitwall-data` JSON snapshots (`https://rouaaba.github.io/pitwall-data/data/snapshots/`), which are queried through the Infinity datasource (`pitwall-infinity`, a Terraform-managed data source scoped via allowedHosts to rouaaba.github.io (not the read-only Grafana Cloud built-in Infinity data source)). The `$meeting` variable picks the snapshot (`race_${meeting}.json`, where the default is `latest`). The hidden `$phase` variable is read from that snapshot and controls which of the Pre-race and Post-race tabs is shown.

## Layout

- `dashboard.json` holds the full dashboard resource. Its `metadata` keeps only `name` and `namespace`. Fields the server manages (`uid`, `resourceVersion`, `generation`, `creationTimestamp`, `labels`, `annotations`) are removed so they don't cause Terraform diffs.
- `panels/<element-key>.js` holds the ECharts `getOption` script for a Business Charts (`volkovlabs-echarts-panel`) panel. Each file is named after its key in `spec.elements` (for example `panel-1.js`). The file holds the function body only, and the panel runtime supplies `context`. The first line is a comment that names the panel.

## Build convention

In `dashboard.json`, each `getOption` value is the placeholder string `"__PANEL_JS__:<element-key>"`. `scripts/build_dashboards.py` (not written yet) replaces each placeholder with the contents of `panels/<element-key>.js` and writes the deployable JSON. Edit the JS in `panels/`, not in `dashboard.json`.
