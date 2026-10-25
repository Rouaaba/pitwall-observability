# Adopts the existing pitwall-data repo -- see docs/DEPLOY.md for the
# terraform import command. Never recreate this repo.
resource "github_repository" "pitwall_data" {
  name        = "pitwall-data"
  description = "Precomputed Pitwall briefing/race_centre snapshots, served via GitHub Pages for the Grafana Infinity data source to read."
  visibility  = "public"

  has_issues = true
  has_wiki   = true

  allow_merge_commit     = true
  allow_squash_merge     = true
  allow_rebase_merge     = true
  delete_branch_on_merge = false
}

resource "github_repository_pages" "pitwall_data" {
  repository = github_repository.pitwall_data.name

  source {
    branch = "main"
    path   = "/"
  }
}

# A dedicated deploy key, scoped to pitwall-data only, instead of using a
# personal access token for the scheduled snapshot pipeline.
resource "tls_private_key" "pitwall_data_deploy" {
  algorithm = "ED25519"
}

resource "github_repository_deploy_key" "pitwall_data" {
  repository = github_repository.pitwall_data.name
  title      = "pitwall-observability snapshot pipeline"
  key        = tls_private_key.pitwall_data_deploy.public_key_openssh
  read_only  = false
}

# The private half goes into pitwall-observability's own Actions secrets,
# since that's the repo whose scheduled workflow runs pipeline.briefing and
# needs to push to pitwall-data.
resource "github_actions_secret" "pitwall_data_deploy_key" {
  repository  = "pitwall-observability"
  secret_name = "PITWALL_DATA_DEPLOY_KEY"
  value       = tls_private_key.pitwall_data_deploy.private_key_openssh
}

# Grafana service account token, for the PR-plan workflow's `terraform plan`
# against terraform/grafana/.
resource "github_actions_secret" "grafana_auth" {
  repository  = "pitwall-observability"
  secret_name = "GRAFANA_AUTH"
  value       = var.grafana_auth_secret
}

resource "github_actions_secret" "grafana_cloud_api_key" {
  repository  = "pitwall-observability"
  secret_name = "GRAFANA_CLOUD_API_KEY"
  value       = var.grafana_cloud_api_key_secret
}

# HCP Terraform API token, for CI to run `terraform plan`/`apply` against
# both workspaces.
resource "github_actions_secret" "tf_api_token" {
  repository  = "pitwall-observability"
  secret_name = "TF_API_TOKEN"
  value       = var.tf_api_token_secret
}

# OTLP credentials, so the snapshot-schedule workflow's `pipeline.briefing`
# run can emit pitwall_snapshot_* metrics through Alloy to Grafana Cloud --
# same values as the local .env, mirrored into Actions secrets.
resource "github_actions_secret" "grafana_otlp_endpoint" {
  repository  = "pitwall-observability"
  secret_name = "GRAFANA_OTLP_ENDPOINT"
  value       = var.grafana_otlp_endpoint
}

resource "github_actions_secret" "grafana_instance_id" {
  repository  = "pitwall-observability"
  secret_name = "GRAFANA_INSTANCE_ID"
  value       = var.grafana_instance_id
}

resource "github_actions_secret" "grafana_otlp_token" {
  repository  = "pitwall-observability"
  secret_name = "GRAFANA_OTLP_TOKEN"
  value       = var.grafana_otlp_token
}
