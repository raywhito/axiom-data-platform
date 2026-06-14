variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region — Paris for HDS data sovereignty"
  type        = string
  default     = "europe-west9"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "europe-west9-a"
}

variable "vm_machine_type" {
  description = "Compute Engine machine type for the application server"
  type        = string
  default     = "e2-medium"
}

variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-custom-1-3840"
}

variable "db_password" {
  description = "Password for the Cloud SQL 'axiom' user"
  type        = string
  sensitive   = true
}

variable "admin_cidr" {
  description = "Your public IP in CIDR form, allowed to reach SSH and the app/monitoring ports"
  type        = string
  # Example: "203.0.113.4/32" — never leave 0.0.0.0/0 for a health-data system.
}

variable "labels" {
  description = "Common resource labels"
  type        = map(string)
  default = {
    project = "axiom"
    block   = "data-architecture"
    env     = "demo"
  }
}
