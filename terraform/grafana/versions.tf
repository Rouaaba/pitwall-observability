terraform {
  required_version = ">= 1.17.0"

  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "4.50.0"
    }
  }

  cloud {
    organization = "formula"
    workspaces {
      name = "pitwall-grafana"
    }
  }
}

provider "grafana" {
  # Instance-scoped resources (dashboards, folders, data sources)
  url      = var.grafana_url
  auth     = var.grafana_auth
  stack_id = var.grafana_stack_id

  # Cloud-scoped resources (plugin installation), separate API/auth surface
  cloud_access_policy_token = var.grafana_cloud_api_key
  # If the provider ever rejects store_dashboard_sha256 for v2 dashboards
  # (terraform-provider-grafana#2911/#2912), set
  # store_dashboard_sha256 = false here.
}
