resource "google_compute_network" "vpc" {
  name                    = "axiom-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "axiom-subnet"
  ip_cidr_range = "10.10.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

# SSH — restricted to the operator's IP only
resource "google_compute_firewall" "ssh" {
  name      = "axiom-allow-ssh"
  network   = google_compute_network.vpc.id
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = [var.admin_cidr]
  target_tags   = ["axiom-app"]
}

# Application + monitoring UIs — restricted to the operator's IP only
resource "google_compute_firewall" "app" {
  name      = "axiom-allow-app"
  network   = google_compute_network.vpc.id
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["8000", "3000", "9090"] # API, Grafana, Prometheus
  }

  source_ranges = [var.admin_cidr]
  target_tags   = ["axiom-app"]
}
