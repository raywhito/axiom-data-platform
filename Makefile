# AXIOM Data Platform — convenience targets
# Requires Docker Desktop (Docker Engine + Compose plugin).

COMPOSE = docker compose -f docker/docker-compose.yml

.PHONY: help up down clean logs ps seed etl load health demo

help:
	@echo "Targets:"
	@echo "  make up      - build & start the full stack"
	@echo "  make seed    - load Golden Data + synthetic analyses into OLTP"
	@echo "  make etl     - run OLTP -> warehouse (star schema) ETL"
	@echo "  make load    - generate live API traffic (for monitoring)"
	@echo "  make demo    - up + seed + etl + load (one-shot)"
	@echo "  make health  - probe all endpoints"
	@echo "  make logs    - follow logs"
	@echo "  make ps      - list containers"
	@echo "  make down    - stop the stack"
	@echo "  make clean   - stop & remove volumes (wipe data)"

up:
	$(COMPOSE) up -d --build
	@echo "API       http://localhost:8000"
	@echo "Grafana   http://localhost:3000  (admin/admin)"
	@echo "Prometheus http://localhost:9090"

down:
	$(COMPOSE) down

clean:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

seed:
	$(COMPOSE) exec -T api python scripts/seed_oltp.py

etl:
	$(COMPOSE) exec -T api python scripts/etl_oltp_to_olap.py

load:
	$(COMPOSE) exec -T api python scripts/generate_load.py

health:
	bash scripts/healthcheck.sh

demo: up
	@echo "Waiting for the database to become healthy..."
	@sleep 25
	$(MAKE) seed
	$(MAKE) etl
	$(MAKE) load
	@echo ""
	@echo "Demo ready -> open Grafana at http://localhost:3000 (admin/admin)"
