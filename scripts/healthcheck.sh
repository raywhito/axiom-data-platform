#!/usr/bin/env bash
# Quick health probe for the AXIOM data platform stack (run from the host).
set -uo pipefail

check() {
  local name="$1" url="$2"
  if curl -fsS -o /dev/null --max-time 5 "$url"; then
    printf "  ✅ %-22s %s\n" "$name" "$url"
  else
    printf "  ❌ %-22s %s\n" "$name" "$url"
  fi
}

echo "AXIOM Data Platform — health check"
check "Ingestion API"      "http://localhost:8000/health"
check "API metrics"        "http://localhost:8000/metrics"
check "Prometheus"         "http://localhost:9090/-/healthy"
check "Grafana"            "http://localhost:3000/api/health"
check "Postgres exporter"  "http://localhost:9187/metrics"
echo "Done."
