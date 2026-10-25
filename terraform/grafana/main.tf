resource "grafana_folder" "pitwall" {
  title = "Pitwall"
}

resource "grafana_cloud_plugin_installation" "business_charts" {
  stack_slug = var.grafana_stack_slug
  slug       = "volkovlabs-echarts-panel"
  version    = "7.2.5"
}

resource "grafana_cloud_plugin_installation" "dynamic_text" {
  stack_slug = var.grafana_stack_slug
  slug       = "marcusolsson-dynamictext-panel"
  version    = "6.3.0"
}

# Grafana Cloud's built-in "grafanacloud-infinity" data source is read-only
# (Terraform cannot manage it) and has no allowedHosts restriction. This is
# a separate, Terraform-managed Infinity data source scoped to only the
# pitwall-data GitHub Pages host; the Race Centre dashboard's panel queries
# point at this one, not the built-in one.
resource "grafana_data_source" "pitwall_infinity" {
  name = "pitwall-infinity"
  type = "yesoreyeram-infinity-datasource"

  json_data_encoded = jsonencode({
    allowedHosts = ["https://${var.infinity_allowed_host}"]
  })
}
