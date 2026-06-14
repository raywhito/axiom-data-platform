# Managed PostgreSQL (Cloud SQL) — operational + analytical store.
# In production, attach via Private Service Access; kept simple here for the demo.

resource "google_sql_database_instance" "postgres" {
  name             = "axiom-postgres"
  database_version = "POSTGRES_16"
  region           = var.region

  # Allows `terraform destroy` to remove it (set true in production).
  deletion_protection = false

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
    disk_size         = 10
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    ip_configuration {
      ipv4_enabled = true
      authorized_networks {
        name  = "operator"
        value = var.admin_cidr
      }
    }

    user_labels = var.labels
  }
}

resource "google_sql_database" "axiom" {
  name     = "axiom"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "axiom" {
  name     = "axiom"
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}
