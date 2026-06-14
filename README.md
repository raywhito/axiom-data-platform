# AXIOM Data Platform — Data Architecture (Block 2)

End-to-end **data infrastructure** for the AXIOM preventive-health platform:
an instrumented ingestion API, a PostgreSQL **operational store (OLTP)**, an
analytical **warehouse with a star schema (OLAP)**, an ETL pipeline, and a full
**Prometheus + Grafana** observability stack — all reproducible locally with
Docker Compose and deployable to **GCP (Paris / `europe-west9`)** with Terraform.

> Fictional project for the Block 2 "Data Architecture" assessment. Reuses the
> AXIOM project from the Automation & Deployment course.

---

## 1. Architecture overview

```
                         ┌──────────────────────────────┐
   Blood-test PDF ─────▶ │  Ingestion API (FastAPI)      │  /ingest  /metrics  /health
                         │  instrumented (Prometheus)    │
                         └───────┬───────────────┬───────┘
                 ephemeral write │               │ transactional writes
                                 ▼               ▼
                    ┌─────────────────┐   ┌──────────────────────┐
                    │ Object storage  │   │  OLTP — PostgreSQL    │  operational (3NF)
                    │ PDFs (1-day TTL)│   │  schema: oltp         │
                    └─────────────────┘   └──────────┬───────────┘
                                                ETL  │ (full refresh)
                                                     ▼
                                          ┌──────────────────────┐
                                          │  OLAP — PostgreSQL    │  analytical (star)
                                          │  schema: warehouse    │
                                          └──────────┬───────────┘
                                                     ▼
                                          BI / Biological Risk Score

   Observability (cross-cutting):  Prometheus  ◀── exporters (API, postgres, node, cAdvisor)
                                   Grafana     ◀── dashboards
```

Rendered diagrams: [`docs/architecture.png`](docs/architecture.png),
[`docs/erd.png`](docs/erd.png), [`docs/star_schema.png`](docs/star_schema.png).

---

## 2. Repository structure

```
axiom-data-platform/
├── terraform/        # GCP IaC — VM, Cloud SQL, GCS, VPC/firewall
├── docker/           # Dockerfile + docker-compose + Prometheus/Grafana config
├── sql/              # 01_oltp_schema.sql (ERD)  +  02_warehouse_schema.sql (star)
├── app/              # instrumented FastAPI ingestion service
├── scripts/          # seed, ETL (OLTP→OLAP), load generator, healthcheck
├── docs/             # diagrams + demo script
├── Makefile          # one-command workflows
└── README.md
```

---

## 3. Data models

### 3.1 Operational store — OLTP (`sql/01_oltp_schema.sql`)
Normalised (3NF) schema optimised for writes and integrity:

| Table | Role |
|---|---|
| `biomarker_thresholds` | Proprietary optimality bands ("Golden Data") |
| `red_flag_thresholds` | Pathological bounds → doctor referral (medical guardrail) |
| `recommendations` | Cure / diet / lifestyle actions per biomarker |
| `patients` | Anonymised subjects (pseudonym only — GDPR minimisation) |
| `analysis_reports` | One row per submitted analysis |
| `biomarker_results` | One row per biomarker measured |

### 3.2 Analytical warehouse — OLAP star schema (`sql/02_warehouse_schema.sql`)
Denormalised for fast aggregation / BI:

- **Facts**: `fact_analysis` (report grain), `fact_biomarker_measurement` (atomic grain,
  with additive flags `is_below_optimal`, `is_optimal`, `is_red_flag` and an `optimality_gap` measure).
- **Dimensions**: `dim_date`, `dim_patient` (age band, sex, segment), `dim_biomarker`
  (category, optimal band), `dim_lab`.
- **View**: `vw_deficiency_frequency` — % of measurements below optimal per biomarker,
  the basis for the population **Biological Risk Score**.

---

## 4. Technical stack & justification

| Layer | Choice | Why |
|---|---|---|
| Ingestion | **FastAPI** | Async, typed (Pydantic), native `/metrics` integration |
| Database | **PostgreSQL 16** | One engine for OLTP + OLAP (schemas) → simpler ops; JSONB, window funcs |
| Modelling | **3NF (OLTP) + star schema (OLAP)** | Separate write-optimised vs read/analytics-optimised concerns |
| IaC (cloud) | **Terraform** | Declarative, idempotent, reviewable; GCP provider |
| Containers | **Docker + Compose** | Identical stack locally and on the VM; reproducible |
| Cloud | **GCP `europe-west9`** | HDS-certified region, data sovereignty (Paris) |
| Monitoring | **Prometheus + Grafana** | Industry standard, pull-based, rich dashboards |
| Exporters | **postgres / node / cAdvisor** | DB, host and container observability |

---

## 5. Quickstart (local — zero cost)

Prerequisites: **Docker Desktop** (Docker Engine + Compose plugin) and `make`.

```bash
cd axiom-data-platform
cp .env.example .env

make demo        # build + start + seed + ETL + generate load (one command)
```

Then open:

| Service | URL | Credentials |
|---|---|---|
| Ingestion API | http://localhost:8000 | — |
| API metrics | http://localhost:8000/metrics | — |
| Grafana dashboard | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |

Step-by-step alternative:
```bash
make up      # start the stack
make seed    # load Golden Data + synthetic analyses (OLTP)
make etl     # build the star schema (OLAP)
make load    # generate live API traffic
make health  # probe every endpoint
make clean   # tear down + wipe volumes
```

The Grafana dashboard **AXIOM Data Platform — Overview** is auto-provisioned
(ingestions, red-flag rate, request rate, p95 latency, OLTP/warehouse volumes, Postgres up).

---

## 6. Cloud deployment (GCP)

See [`terraform/README.md`](terraform/README.md). In short:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # set project_id, db_password, admin_cidr
gcloud auth application-default login
terraform init && terraform apply
```

The VM startup script installs Docker and brings up the **same** Compose stack,
so behaviour is identical to local. Run `terraform destroy` afterwards to avoid charges.

---

## 7. Data governance alignment
- **Sovereignty**: all cloud resources pinned to `europe-west9` (Paris, HDS).
- **Minimisation**: object-storage lifecycle deletes source PDFs after 1 day;
  only de-identified scores persist.
- **Least privilege**: firewall opens SSH/app ports to the operator IP only.
- **Traceability**: `red_flag_thresholds.validated_by` records the medical validator.

(See the Block 1 Data Governance Plan for the full policy.)
