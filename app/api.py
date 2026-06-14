"""
AXIOM Data Platform — instrumented ingestion API.

A lightweight, self-contained service that represents the AXIOM ingestion layer
for the Block 2 (Data Architecture) deliverable. It does NOT call external LLM
APIs; instead it deterministically simulates an analysis so the *data
architecture* and *observability* can be demonstrated end-to-end and offline.

Exposes:
  GET  /            service info
  GET  /health      liveness + DB readiness
  GET  /metrics     Prometheus metrics
  POST /ingest      simulate ingesting one blood-test analysis (writes to OLTP)
  GET  /stats       quick OLTP counters (JSON)
"""
from __future__ import annotations

import os
import random
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, timedelta

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://axiom:axiom@postgres:5432/axiom",
)

# ── Prometheus metrics ───────────────────────────────────────────────────────
REQUESTS = Counter(
    "axiom_http_requests_total", "HTTP requests", ["method", "path", "status"]
)
LATENCY = Histogram(
    "axiom_http_request_duration_seconds", "Request latency (s)", ["path"]
)
INGESTIONS = Counter("axiom_ingestions_total", "Analyses ingested")
REDFLAGS = Counter("axiom_red_flags_total", "Red-flag biomarkers detected")
G_ANALYSES = Gauge("axiom_oltp_analyses_total", "Rows in oltp.analysis_reports")
G_PATIENTS = Gauge("axiom_oltp_patients_total", "Rows in oltp.patients")
G_RESULTS = Gauge("axiom_oltp_biomarker_results_total", "Rows in oltp.biomarker_results")
G_FACTS = Gauge("axiom_warehouse_fact_rows_total", "Rows in warehouse.fact_analysis")
G_REDFLAG_RATE = Gauge("axiom_redflag_rate", "Share of analyses with red flags (0..1)")

LABS = ["Cerba", "Biogroup", "Synlab", "Eurofins"]
SEGMENTS = ["athlete", "executive", "student", "general"]

engine: Engine | None = None


def get_engine() -> Engine:
    global engine
    if engine is None:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
    return engine


def db_ready() -> bool:
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("db_not_ready", error=str(exc))
        return False


def refresh_gauges() -> None:
    try:
        with get_engine().connect() as c:
            G_ANALYSES.set(c.execute(text("SELECT count(*) FROM oltp.analysis_reports")).scalar_one())
            G_PATIENTS.set(c.execute(text("SELECT count(*) FROM oltp.patients")).scalar_one())
            G_RESULTS.set(c.execute(text("SELECT count(*) FROM oltp.biomarker_results")).scalar_one())
            facts = c.execute(text("SELECT count(*) FROM warehouse.fact_analysis")).scalar_one()
            G_FACTS.set(facts)
            rf = c.execute(
                text("SELECT coalesce(avg(case when has_red_flags then 1 else 0 end),0) "
                     "FROM oltp.analysis_reports")
            ).scalar_one()
            G_REDFLAG_RATE.set(float(rf))
    except Exception as exc:  # noqa: BLE001
        log.warning("gauge_refresh_failed", error=str(exc))


def load_thresholds() -> list[dict]:
    """Read active optimality thresholds + red-flag bounds from OLTP."""
    with get_engine().connect() as c:
        rows = c.execute(text(
            """
            SELECT t.name, t.unit, t.optimal_min, t.optimal_max, t.category,
                   r.red_flag_low, r.red_flag_high
            FROM oltp.biomarker_thresholds t
            LEFT JOIN oltp.red_flag_thresholds r ON r.biomarker_name = t.name
            WHERE t.is_active = TRUE
            """
        )).mappings().all()
    return [dict(r) for r in rows]


def simulate_analysis() -> dict:
    """Create one synthetic analysis and persist it into the OLTP schema."""
    thresholds = load_thresholds()
    if not thresholds:
        raise RuntimeError("No thresholds seeded. Run scripts/seed_oltp.py first.")

    eng = get_engine()
    with eng.begin() as c:
        # pick or create a patient
        pid = c.execute(text(
            "SELECT id FROM oltp.patients ORDER BY random() LIMIT 1"
        )).scalar()
        if pid is None or random.random() < 0.2:
            pid = uuid.uuid4()
            c.execute(text(
                "INSERT INTO oltp.patients (id, pseudonym, age, sex, segment) "
                "VALUES (:id, :ps, :age, :sex, :seg)"
            ), {"id": pid, "ps": "anon_" + uuid.uuid4().hex[:10],
                "age": random.randint(22, 65), "sex": random.choice(["M", "F"]),
                "seg": random.choice(SEGMENTS)})

        report_id = uuid.uuid4()
        rdate = date.today() - timedelta(days=random.randint(0, 540))
        lab = random.choice(LABS)

        optimal_count = 0
        red_flags = 0
        results = []
        for t in thresholds:
            omin = float(t["optimal_min"]) if t["optimal_min"] is not None else 0.0
            omax = float(t["optimal_max"]) if t["optimal_max"] is not None else omin + 1
            span = max(omax - omin, 0.1)
            # value drawn around the optimal band, sometimes deficient/excess
            value = round(random.gauss((omin + omax) / 2, span * 0.9), 3)
            if value < omin:
                status = "BELOW_OPTIMAL"
            elif value > omax:
                status = "ABOVE_OPTIMAL"
            else:
                status = "OPTIMAL"
                optimal_count += 1
            rf = False
            if t["red_flag_low"] is not None and value < float(t["red_flag_low"]):
                rf = True
            if t["red_flag_high"] is not None and value > float(t["red_flag_high"]):
                rf = True
            if rf:
                red_flags += 1
            results.append((t["name"], value, t["unit"], status, rf))

        total = len(thresholds)
        score = round(100.0 * optimal_count / total, 2) if total else 0.0
        bio_age = round(random.uniform(-8, 12) + 40, 2)
        confidence = round(random.uniform(0.93, 0.99), 3)

        c.execute(text(
            """
            INSERT INTO oltp.analysis_reports
              (id, patient_id, lab_name, report_date, total_biomarkers,
               optimality_score, biological_age, has_red_flags, red_flag_count,
               extraction_confidence)
            VALUES (:id, :pid, :lab, :d, :tot, :score, :ba, :hrf, :rfc, :conf)
            """
        ), {"id": report_id, "pid": pid, "lab": lab, "d": rdate, "tot": total,
            "score": score, "ba": bio_age, "hrf": red_flags > 0,
            "rfc": red_flags, "conf": confidence})

        for name, value, unit, status, rf in results:
            c.execute(text(
                """
                INSERT INTO oltp.biomarker_results
                  (id, report_id, biomarker_name, value, unit, optimality_status, is_red_flag)
                VALUES (:id, :rid, :n, :v, :u, :st, :rf)
                """
            ), {"id": uuid.uuid4(), "rid": report_id, "n": name, "v": value,
                "u": unit, "st": status, "rf": rf})

    INGESTIONS.inc()
    if red_flags:
        REDFLAGS.inc(red_flags)
    return {"analysis_id": str(report_id), "lab": lab, "optimality_score": score,
            "biological_age": bio_age, "red_flags": red_flags, "biomarkers": total}


@asynccontextmanager
async def lifespan(_: FastAPI):
    for attempt in range(30):
        if db_ready():
            break
        log.info("waiting_for_db", attempt=attempt)
        time.sleep(2)
    refresh_gauges()
    yield


app = FastAPI(title="AXIOM Data Platform API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def observe(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    path = request.url.path
    LATENCY.labels(path=path).observe(time.perf_counter() - start)
    REQUESTS.labels(method=request.method, path=path, status=response.status_code).inc()
    return response


@app.get("/")
def root():
    return {"service": "AXIOM Data Platform API", "status": "ok",
            "endpoints": ["/health", "/metrics", "/ingest", "/stats"]}


@app.get("/health")
def health():
    ok = db_ready()
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "degraded", "database": "up" if ok else "down"},
    )


@app.get("/metrics")
def metrics():
    refresh_gauges()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/ingest")
def ingest():
    try:
        result = simulate_analysis()
        refresh_gauges()
        return {"status": "ingested", **result}
    except Exception as exc:  # noqa: BLE001
        log.error("ingest_failed", error=str(exc))
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc)})


@app.get("/stats")
def stats():
    with get_engine().connect() as c:
        return {
            "patients": c.execute(text("SELECT count(*) FROM oltp.patients")).scalar_one(),
            "analyses": c.execute(text("SELECT count(*) FROM oltp.analysis_reports")).scalar_one(),
            "biomarker_results": c.execute(text("SELECT count(*) FROM oltp.biomarker_results")).scalar_one(),
            "warehouse_facts": c.execute(text("SELECT count(*) FROM warehouse.fact_analysis")).scalar_one(),
        }
