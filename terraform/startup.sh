#!/usr/bin/env bash
# VM startup script — installs Docker and launches the AXIOM data platform stack.
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git

# Install Docker Engine + Compose plugin
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Fetch the application code and bring the stack up
# (replace the URL with your GitHub repository)
git clone https://github.com/YOUR_USERNAME/axiom-data-platform.git /opt/axiom || true
cd /opt/axiom/axiom-data-platform || cd /opt/axiom
docker compose -f docker/docker-compose.yml up -d --build

# Seed + ETL once the database is healthy
sleep 30
docker compose -f docker/docker-compose.yml exec -T api python scripts/seed_oltp.py || true
docker compose -f docker/docker-compose.yml exec -T api python scripts/etl_oltp_to_olap.py || true
