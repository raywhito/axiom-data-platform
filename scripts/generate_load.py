"""
Generate live traffic against the ingestion API so Prometheus/Grafana show
activity during the demo. Uses only the standard library.

Run inside the api container (recommended):
    docker compose exec -T api python scripts/generate_load.py
Env:
    API_URL     (default http://localhost:8000)
    LOAD_COUNT  (default 60)
    LOAD_DELAY  (default 0.3 seconds between calls)
"""
from __future__ import annotations

import os
import time
import urllib.request

API_URL = os.getenv("API_URL", "http://localhost:8000")
COUNT = int(os.getenv("LOAD_COUNT", "60"))
DELAY = float(os.getenv("LOAD_DELAY", "0.3"))


def post(path: str) -> int:
    req = urllib.request.Request(API_URL + path, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except Exception as exc:  # noqa: BLE001
        print("  request failed:", exc)
        return 0


def main() -> None:
    print(f"Sending {COUNT} ingest requests to {API_URL} ...")
    ok = 0
    for i in range(1, COUNT + 1):
        status = post("/ingest")
        ok += 1 if status == 200 else 0
        if i % 10 == 0:
            print(f"  {i}/{COUNT} (last status {status})")
        time.sleep(DELAY)
    print(f"Done. {ok}/{COUNT} successful ingestions.")


if __name__ == "__main__":
    main()
