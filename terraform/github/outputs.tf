output "pitwall_data_pages_url" {
  value = "https://${var.github_owner}.github.io/pitwall-data/"
}

output "deploy_key_fingerprint" {
  value = github_repository_deploy_key.pitwall_data.key
}
