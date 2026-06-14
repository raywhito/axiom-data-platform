# Virtual server hosting the containerised AXIOM data platform.
# The startup script installs Docker and brings the stack up automatically,
# so the same docker-compose stack used locally also runs on the cloud VM.

resource "google_compute_instance" "app" {
  name         = "axiom-app"
  machine_type = var.vm_machine_type
  zone         = var.zone
  tags         = ["axiom-app"]
  labels       = var.labels

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 30
      type  = "pd-balanced"
    }
  }

  network_interface {
    network    = google_compute_network.vpc.id
    subnetwork = google_compute_subnetwork.subnet.id
    access_config {} # ephemeral public IP
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  metadata_startup_script = file("${path.module}/startup.sh")

  service_account {
    scopes = ["cloud-platform"]
  }
}
