output "vm_external_ip" {
  description = "Public IP of the application VM"
  value       = google_compute_instance.app.network_interface[0].access_config[0].nat_ip
}

output "api_url" {
  description = "AXIOM ingestion API"
  value       = "http://${google_compute_instance.app.network_interface[0].access_config[0].nat_ip}:8000"
}

output "grafana_url" {
  description = "Grafana UI"
  value       = "http://${google_compute_instance.app.network_interface[0].access_config[0].nat_ip}:3000"
}

output "prometheus_url" {
  description = "Prometheus UI"
  value       = "http://${google_compute_instance.app.network_interface[0].access_config[0].nat_ip}:9090"
}

output "cloudsql_connection_name" {
  description = "Cloud SQL instance connection name"
  value       = google_sql_database_instance.postgres.connection_name
}

output "cloudsql_public_ip" {
  description = "Cloud SQL public IP"
  value       = google_sql_database_instance.postgres.public_ip_address
}

output "uploads_bucket" {
  description = "Ephemeral uploads bucket"
  value       = google_storage_bucket.uploads.url
}
