"""
ETL : OLTP (operational) -> OLAP warehouse (star schema).
Full refresh — safe and idempotent for the demo.

Run inside the api container:
    docker compose exec -T api python scripts/etl_oltp_to_olap.py
"""
from __future__ import annotations

import calendar
import os
from datetime import date

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://axiom:axiom@postgres:5432/axiom")


def age_band(age: int | None) -> str:
    if age is None:
        return "unknown"
    lo = (age // 10) * 10
    return f"{lo}-{lo + 9}"


def main() -> None:
    eng = create_engine(DATABASE_URL, future=True)
    with eng.begin() as c:
        # 1. full refresh — wipe facts then dims
        c.execute(text("TRUNCATE warehouse.fact_biomarker_measurement, warehouse.fact_analysis RESTART IDENTITY"))
        c.execute(text("TRUNCATE warehouse.dim_patient, warehouse.dim_biomarker, warehouse.dim_lab "
                       "RESTART IDENTITY CASCADE"))
        c.execute(text("DELETE FROM warehouse.dim_date"))

        # 2. dim_date from distinct report dates
        dates = [r[0] for r in c.execute(text(
            "SELECT DISTINCT report_date FROM oltp.analysis_reports WHERE report_date IS NOT NULL"
        )).all()]
        for d in dates:
            dk = d.year * 10000 + d.month * 100 + d.day
            c.execute(text(
                """
                INSERT INTO warehouse.dim_date
                  (date_key, full_date, year, quarter, month, month_name, week, day_of_month, is_weekend)
                VALUES (:k, :d, :y, :q, :m, :mn, :w, :dom, :we)
                ON CONFLICT (date_key) DO NOTHING
                """
            ), {"k": dk, "d": d, "y": d.year, "q": (d.month - 1) // 3 + 1, "m": d.month,
                "mn": calendar.month_name[d.month], "w": int(d.strftime("%V")),
                "dom": d.day, "we": d.weekday() >= 5})

        # 3. dim_lab
        c.execute(text(
            "INSERT INTO warehouse.dim_lab (lab_name) "
            "SELECT DISTINCT lab_name FROM oltp.analysis_reports WHERE lab_name IS NOT NULL"
        ))

        # 4. dim_biomarker
        c.execute(text(
            "INSERT INTO warehouse.dim_biomarker (name, category, unit, optimal_min, optimal_max, priority) "
            "SELECT name, category, unit, optimal_min, optimal_max, priority FROM oltp.biomarker_thresholds"
        ))

        # 5. dim_patient (age_band computed in Python)
        for r in c.execute(text("SELECT id, pseudonym, sex, age, segment FROM oltp.patients")).mappings().all():
            c.execute(text(
                "INSERT INTO warehouse.dim_patient (patient_uuid, pseudonym, sex, age_band, segment) "
                "VALUES (:u, :ps, :sex, :ab, :seg)"
            ), {"u": r["id"], "ps": r["pseudonym"], "sex": r["sex"],
                "ab": age_band(r["age"]), "seg": r["segment"]})

        # 6. fact_analysis (report grain)
        c.execute(text(
            """
            INSERT INTO warehouse.fact_analysis
              (analysis_uuid, date_key, patient_key, lab_key, optimality_score, biological_age,
               total_biomarkers, red_flag_count, has_red_flags, extraction_confidence)
            SELECT  ar.id,
                    (EXTRACT(YEAR FROM ar.report_date)*10000
                      + EXTRACT(MONTH FROM ar.report_date)*100
                      + EXTRACT(DAY FROM ar.report_date))::int,
                    dp.patient_key, dl.lab_key,
                    ar.optimality_score, ar.biological_age, ar.total_biomarkers,
                    ar.red_flag_count, ar.has_red_flags, ar.extraction_confidence
            FROM oltp.analysis_reports ar
            JOIN warehouse.dim_patient dp ON dp.patient_uuid = ar.patient_id
            LEFT JOIN warehouse.dim_lab dl ON dl.lab_name = ar.lab_name
            """
        ))

        # 7. fact_biomarker_measurement (atomic grain) with optimality gap + additive flags
        c.execute(text(
            """
            INSERT INTO warehouse.fact_biomarker_measurement
              (date_key, patient_key, biomarker_key, lab_key, analysis_uuid, value,
               optimality_gap, is_below_optimal, is_above_optimal, is_optimal, is_red_flag)
            SELECT  (EXTRACT(YEAR FROM ar.report_date)*10000
                      + EXTRACT(MONTH FROM ar.report_date)*100
                      + EXTRACT(DAY FROM ar.report_date))::int,
                    dp.patient_key, db.biomarker_key, dl.lab_key, ar.id, br.value,
                    CASE
                      WHEN br.value < db.optimal_min THEN db.optimal_min - br.value
                      WHEN br.value > db.optimal_max THEN br.value - db.optimal_max
                      ELSE 0 END,
                    CASE WHEN br.optimality_status = 'BELOW_OPTIMAL' THEN 1 ELSE 0 END,
                    CASE WHEN br.optimality_status = 'ABOVE_OPTIMAL' THEN 1 ELSE 0 END,
                    CASE WHEN br.optimality_status = 'OPTIMAL' THEN 1 ELSE 0 END,
                    CASE WHEN br.is_red_flag THEN 1 ELSE 0 END
            FROM oltp.biomarker_results br
            JOIN oltp.analysis_reports ar ON ar.id = br.report_id
            JOIN warehouse.dim_patient dp ON dp.patient_uuid = ar.patient_id
            JOIN warehouse.dim_biomarker db ON db.name = br.biomarker_name
            LEFT JOIN warehouse.dim_lab dl ON dl.lab_name = ar.lab_name
            """
        ))

        n_fa = c.execute(text("SELECT count(*) FROM warehouse.fact_analysis")).scalar_one()
        n_fbm = c.execute(text("SELECT count(*) FROM warehouse.fact_biomarker_measurement")).scalar_one()

    print(f"ETL complete: dim_date={len(dates)} | fact_analysis={n_fa} | fact_biomarker_measurement={n_fbm}")


if __name__ == "__main__":
    main()
