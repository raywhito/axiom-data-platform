terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
  }

  # For a real project, store state remotely (uncomment and set the bucket):
  # backend "gcs" {
  #   bucket = "axiom-tfstate"
  #   prefix = "data-platform"
  # }
}
