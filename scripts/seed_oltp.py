"""
Seed the OLTP schema with reference data (Golden Data + red flags) and a batch
of synthetic, fully anonymised analyses so the warehouse and dashboards have
something to show.

Run inside the api container:
    docker compose exec -T api python scripts/seed_oltp.py
Env:
    DATABASE_URL     (default postgresql+psycopg2://axiom:axiom@postgres:5432/axiom)
    SEED_PATIENTS    (default 40)
    SEED_ANALYSES    (default 120)
"""
from __future__ import annotations

import os
import random
import uuid
from datetime import date, timedelta

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://axiom:axiom@postgres:5432/axiom")
SEED_PATIENTS = int(os.getenv("SEED_PATIENTS", "40"))
SEED_ANALYSES = int(os.getenv("SEED_ANALYSES", "120"))

# name, unit, category, optimal_min, optimal_max, lab_min, lab_max, priority,
# red_flag_low, red_flag_high
BIOMARKERS = [
    ("Vitamin D", "ng/mL", "Vitamins", 50, 80, 20, 100, 1, 10, None),
    ("Ferritin", "ng/mL", "Hematology", 70, 150, 30, 300, 1, None, 1000),
    ("Fasting Glucose", "mg/dL", "Carbohydrates", 70, 90, 60, 109, 1, 50, 126),
    ("HbA1c", "%", "Carbohydrates", 4.8, 5.4, 4.0, 6.0, 1, None, 6.5),
    ("TSH", "mUI/L", "Hormones", 1.0, 2.5, 0.4, 4.0, 2, 0.1, 10.0),
    ("hsCRP", "mg/L", "Inflammation", 0.0, 1.0, 0.0, 5.0, 2, None, 10.0),
    ("HDL Cholesterol", "mg/dL", "Lipids", 55, 90, 40, 100, 3, 20, None),
    ("LDL Cholesterol", "mg/dL", "Lipids", 60, 100, 0, 130, 2, None, 190),
    ("Triglycerides", "mg/dL", "Lipids", 50, 90, 0, 150, 3, None, 500),
    ("Vitamin B12", "pg/mL", "Vitamins", 500, 900, 200, 1000, 2, 150, None),
    ("Magnesium", "mg/dL", "Minerals", 2.0, 2.5, 1.7, 2.6, 3, 1.2, None),
    ("Testosterone", "ng/dL", "Hormones", 600, 900, 300, 1000, 2, 150, None),
]


def main() -> None:
    eng = create_engine(DATABASE_URL, future=True)
    with eng.begin() as c:
        # ── reference: optimality thresholds + red flags + a sample recommendation
        for (name, unit, cat, omin, omax, lmin, lmax, prio, rf_low, rf_high) in BIOMARKERS:
            c.execute(text(
                """
                INSERT INTO oltp.biomarker_thresholds
                    (name, unit, category, optimal_min, optimal_max, lab_ref_min, lab_ref_max, priority, evidence)
                VALUES (:n, :u, :cat, :omin, :omax, :lmin, :lmax, :prio, :ev)
                ON CONFLICT (name) DO NOTHING
                """
            ), {"n": name, "u": unit, "cat": cat, "omin": omin, "omax": omax,
                "lmin": lmin, "lmax": lmax, "prio": prio,
                "ev": "Curated by AXIOM Medical Advisory Board"})

            if rf_low is not None or rf_high is not None:
                c.execute(text(
                    """
                    INSERT INTO oltp.red_flag_thresholds
                        (biomarker_name, unit, red_flag_low, red_flag_high, urgency, message, validated_by, validated_at)
                    VALUES (:n, :u, :low, :high, 'HIGH', :msg, 'Dr. Advisory Board', :d)
                    ON CONFLICT (biomarker_name) DO NOTHING
                    """
                ), {"n": name, "u": unit, "low": rf_low, "high": rf_high,
                    "msg": f"{name} outside safe limits — medical consultation required.",
                    "d": date(2026, 1, 15)})

        # one recommendation per biomarker (idempotent-ish: only if none exist)
        existing_reco = c.execute(text("SELECT count(*) FROM oltp.recommendations")).scalar_one()
        if existing_reco == 0:
            ids = c.execute(text("SELECT id, name FROM oltp.biomarker_thresholds")).mappings().all()
            for row in ids:
                c.execute(text(
                    """
                    INSERT INTO oltp.recommendations (biomarker_id, type, description, condition, product_name)
                    VALUES (:bid, 'cure', :desc, 'BELOW_OPTIMAL', :prod)
                    """
                ), {"bid": row["id"], "desc": f"Targeted supplementation for {row['name']}.",
                    "prod": f"{row['name']} cure"})

        # ── patients
        have = c.execute(text("SELECT count(*) FROM oltp.patients")).scalar_one()
        for _ in range(max(0, SEED_PATIENTS - have)):
            c.execute(text(
                "INSERT INTO oltp.patients (pseudonym, age, sex, segment) VALUES (:ps, :age, :sex, :seg)"
            ), {"ps": "anon_" + uuid.uuid4().hex[:10], "age": random.randint(22, 65),
                "sex": random.choice(["M", "F"]), "seg": random.choice(["athlete", "executive", "student", "general"])})

        patient_ids = [r[0] for r in c.execute(text("SELECT id FROM oltp.patients")).all()]
        thresholds = c.execute(text(
            """
            SELECT t.name, t.unit, t.optimal_min, t.optimal_max, r.red_flag_low, r.red_flag_high
            FROM oltp.biomarker_thresholds t
            LEFT JOIN oltp.red_flag_thresholds r ON r.biomarker_name = t.name
            """
        )).mappings().all()
        labs = ["Cerba", "Biogroup", "Synlab", "Eurofins"]

        # ── synthetic analyses
        for _ in range(SEED_ANALYSES):
            pid = random.choice(patient_ids)
            report_id = uuid.uuid4()
            rdate = date.today() - timedelta(days=random.randint(0, 540))
            lab = random.choice(labs)
            optimal, redflags, results = 0, 0, []
            for t in thresholds:
                omin, omax = float(t["optimal_min"]), float(t["optimal_max"])
                span = max(omax - omin, 0.1)
                value = round(random.gauss((omin + omax) / 2, span * 0.9), 3)
                if value < omin:
                    status = "BELOW_OPTIMAL"
                elif value > omax:
                    status = "ABOVE_OPTIMAL"
                else:
                    status, _ = "OPTIMAL", optimal
                    optimal += 1
                rf = ((t["red_flag_low"] is not None and value < float(t["red_flag_low"]))
                      or (t["red_flag_high"] is not None and value > float(t["red_flag_high"])))
                if rf:
                    redflags += 1
                results.append((t["name"], value, t["unit"], status, rf))

            total = len(thresholds)
            c.execute(text(
                """
                INSERT INTO oltp.analysis_reports
                  (id, patient_id, lab_name, report_date, total_biomarkers, optimality_score,
                   biological_age, has_red_flags, red_flag_count, extraction_confidence)
                VALUES (:id, :pid, :lab, :d, :tot, :score, :ba, :hrf, :rfc, :conf)
                """
            ), {"id": report_id, "pid": pid, "lab": lab, "d": rdate, "tot": total,
                "score": round(100.0 * optimal / total, 2), "ba": round(random.uniform(32, 52), 2),
                "hrf": redflags > 0, "rfc": redflags, "conf": round(random.uniform(0.93, 0.99), 3)})
            for name, value, unit, status, rf in results:
                c.execute(text(
                    """
                    INSERT INTO oltp.biomarker_results
                      (report_id, biomarker_name, value, unit, optimality_status, is_red_flag)
                    VALUES (:rid, :n, :v, :u, :st, :rf)
                    """
                ), {"rid": report_id, "n": name, "v": value, "u": unit, "st": status, "rf": rf})

    print(f"Seed complete: {SEED_PATIENTS} patients target, {SEED_ANALYSES} analyses added, "
          f"{len(BIOMARKERS)} biomarkers in Golden Data.")


if __name__ == "__main__":
    main()
