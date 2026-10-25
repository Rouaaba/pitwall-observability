variable "github_owner" {
  description = "GitHub account that owns pitwall-data and pitwall-observability"
  type        = string
  default     = "Rouaaba"
}

variable "github_token" {
  description = "GitHub personal access token with repo + admin:public_key scopes on pitwall-data and pitwall-observability. Never commit this. Bootstrapping note: this token must be created manually (by a human, in GitHub's UI) before Terraform can run -- it can't create the credential it authenticates with. Its value is then stored as the GH_TERRAFORM_TOKEN secret in pitwall-observability (manually, once) so CI can run terraform plan/apply for this module."
  type        = string
  sensitive   = true
}

variable "grafana_auth_secret" {
  description = "Grafana service account token, mirrored into pitwall-observability's GRAFANA_AUTH Actions secret for CI's terraform plan."
  type        = string
  sensitive   = true
}

variable "grafana_cloud_api_key_secret" {
  description = "Grafana Cloud access policy token, mirrored into pitwall-observability's GRAFANA_CLOUD_API_KEY Actions secret."
  type        = string
  sensitive   = true
}

variable "tf_api_token_secret" {
  description = "HCP Terraform API token, mirrored into pitwall-observability's TF_API_TOKEN Actions secret."
  type        = string
  sensitive   = true
}

variable "grafana_otlp_endpoint" {
  description = "Same value as GRAFANA_OTLP_ENDPOINT in .env, mirrored into Actions secrets for the snapshot-schedule workflow."
  type        = string
  sensitive   = true
}

variable "grafana_instance_id" {
  description = "Same value as GRAFANA_INSTANCE_ID in .env, mirrored into Actions secrets for the snapshot-schedule workflow."
  type        = string
  sensitive   = true
}

variable "grafana_otlp_token" {
  description = "Same value as GRAFANA_OTLP_TOKEN in .env, mirrored into Actions secrets for the snapshot-schedule workflow."
  type        = string
  sensitive   = true
}
