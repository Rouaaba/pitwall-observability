output "folder_uid" {
  value = grafana_folder.pitwall.uid
}

output "pitwall_infinity_datasource_uid" {
  value       = grafana_data_source.pitwall_infinity.uid
  description = "Point dashboard panel queries at this UID, not the read-only grafanacloud-infinity built-in."
}

output "race_centre_dashboard_url" {
  value = "${var.grafana_url}/d/roscr2t"
}
