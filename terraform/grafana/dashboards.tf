# Dashboard JSON lives under dashboards/<name>/dashboard.json + panels/*.js
# in the repo root, assembled into build/<name>.json by
# scripts/build_dashboards.py (panels/*.js injected back into the
# __PANEL_JS__:<key> placeholders). Terraform reads the assembled file.

locals {
  race_centre_dashboard = jsondecode(file("${path.module}/build/race-centre.json"))
}

resource "grafana_apps_dashboard_dashboard_v2" "race_centre" {
  metadata {
    uid        = "roscr2t"
    folder_uid = grafana_folder.pitwall.uid
  }

  options {
    # UI edits are the normal workflow here (edit live, then
    # scripts/export_dashboards.py pulls the change back into git) -- see
    # docs/DEPLOY.md. Without this, Terraform would overwrite UI edits on
    # the next apply.
    allow_ui_updates = true
    overwrite        = true
  }

  spec {
    title = local.race_centre_dashboard.spec.title
    json  = jsonencode(local.race_centre_dashboard.spec)
  }
}
