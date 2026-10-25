variable "grafana_url" {
  description = "Grafana Cloud instance URL"
  type        = string
  default     = "https://rouaabenayed.grafana.net"
}

variable "grafana_auth" {
  description = "Grafana service account token (Admin role), for instance-scoped resources (dashboards, folders, data sources). Never commit this."
  type        = string
  sensitive   = true
}

variable "grafana_cloud_api_key" {
  description = "Grafana Cloud access policy token with stack-plugins:read/write/delete scope, for cloud-scoped resources (plugin installation). Never commit this."
  type        = string
  sensitive   = true
}

variable "grafana_stack_slug" {
  description = "Grafana Cloud stack slug"
  type        = string
  default     = "rouaabenayed"
}

variable "grafana_stack_id" {
  description = "Grafana Cloud stack ID, required for App Platform (v2 dashboard) resources to resolve the correct stacks-<id> namespace"
  type        = number
  default     = 1398043
}

variable "infinity_allowed_host" {
  description = "Host the pitwall Infinity data source is allowed to query"
  type        = string
  default     = "rouaaba.github.io"
}
