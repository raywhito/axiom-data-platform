# Demo video script (3–5 min, Loom screencast)

Goal: prove the infrastructure is real, deployed and observable.

## Before recording
```bash
cd axiom-data-platform
cp .env.example .env
make up          # wait until `make ps` shows all containers healthy/up
```
Keep two browser tabs ready: Grafana (`:3000`) and Prometheus (`:9090`).

---

## 0:00 — Intro (20s)
> "This is the AXIOM data platform — the Block 2 data architecture. Everything you
> see is infrastructure-as-code: Terraform for GCP, Docker Compose for the runtime,
> PostgreSQL for storage, and Prometheus + Grafana for observability."

Show the repo tree (`terraform/`, `docker/`, `sql/`, `scripts/`).

## 0:20 — Architecture (40s)
Show `docs/architecture.png`. Walk the flow: ingestion API → OLTP → ETL → star-schema
warehouse → BI, with monitoring across everything.

## 1:00 — Containers running (30s)
```bash
make ps
```
> "Seven services: API, PostgreSQL, Prometheus, Grafana, and three exporters —
> postgres, node and cAdvisor."

## 1:30 — Data layer (50s)
```bash
make seed     # Golden Data + synthetic analyses into OLTP
make etl      # OLTP -> warehouse star schema
```
Optionally show the model:
```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U axiom -d axiom -c "\dt oltp.*" -c "\dt warehouse.*"
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U axiom -d axiom -c "SELECT * FROM warehouse.vw_deficiency_frequency LIMIT 5;"
```
> "OLTP is normalised for writes; the warehouse is a star schema for analytics —
> here, the biomarker deficiency frequency that drives the Biological Risk Score."

## 2:20 — Monitoring in action (90s)
```bash
make load     # live API traffic
```
Switch to **Grafana → AXIOM Data Platform — Overview**. Point out, live:
- Analyses ingested + red-flag rate climbing
- API request rate and p95 latency
- OLTP vs warehouse row counts
- PostgreSQL "UP"

Briefly show **Prometheus → Status → Targets**: all targets UP.

## 3:50 — Cloud + close (40s)
Show `terraform/` files.
> "The same stack deploys to a GCP VM in europe-west9 for HDS sovereignty —
> `terraform apply` provisions the VM, Cloud SQL and a bucket with a 1-day
> lifecycle for ephemeral PDFs. That's the full data architecture: modelled,
> deployed, and observable."

---

### Handy commands
| Action | Command |
|---|---|
| Start | `make up` |
| Seed + ETL + load | `make demo` |
| Health probe | `make health` |
| Logs | `make logs` |
| Tear down | `make clean` |
