# Terraform — GCP infrastructure

Provisions the cloud target for the AXIOM data platform in **`europe-west9` (Paris)**
for HDS data sovereignty:

| Resource | File | Purpose |
|---|---|---|
| VPC + subnet + firewall | `network.tf` | Isolated network; SSH/app ports restricted to your IP |
| Compute Engine VM | `compute.tf` + `startup.sh` | Virtual server that auto-runs the Docker stack |
| Cloud SQL (PostgreSQL 16) | `database.tf` | Managed operational + analytical store |
| Cloud Storage bucket | `storage.tf` | Ephemeral PDF uploads (1-day lifecycle delete) |

## Usage

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # then edit values
gcloud auth application-default login           # authenticate

terraform init
terraform plan
terraform apply
```

Outputs include the VM IP and the Grafana/Prometheus URLs.

## Teardown (avoid charges)

```bash
terraform destroy
```

## Notes
- `admin_cidr` must be your own IP `/32` — the firewall never opens to `0.0.0.0/0`
  for a health-data system.
- `deletion_protection` on Cloud SQL is `false` for the demo; set it to `true` in production.
- For production, enable the remote GCS backend in `versions.tf` and use Private
  Service Access for Cloud SQL instead of public IP.
- This costs money while running — destroy it when the demo is recorded.
  The local Docker Compose stack (`make up`) is the zero-cost equivalent.
