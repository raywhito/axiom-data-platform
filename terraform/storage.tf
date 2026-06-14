# Object storage for ephemeral source PDFs.
# A 1-day lifecycle rule enforces the GDPR data-minimisation principle:
# raw clinical documents are deleted automatically after extraction.

resource "google_storage_bucket" "uploads" {
  name                        = "${var.project_id}-axiom-uploads"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = true
  labels                      = var.labels

  lifecycle_rule {
    condition {
      age = 1 # days
    }
    action {
      type = "Delete"
    }
  }
}
