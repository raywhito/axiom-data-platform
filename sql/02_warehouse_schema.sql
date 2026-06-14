-- ════════════════════════════════════════════════════════════════════════════
-- AXIOM Data Platform — OLAP (analytical) warehouse : STAR SCHEMA
-- Purpose : cohort analytics & BI on de-identified data
--           (population optimality, deficiency frequency, Biological Risk Score).
-- Engine  : PostgreSQL 16 (same instance, separate schema)
-- Grain   :
--   fact_analysis               -> one row per analysis  (report-level)
--   fact_biomarker_measurement  -> one row per biomarker measured (atomic)
-- ════════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS warehouse;
SET search_path TO warehouse, public;

-- ─────────────────────────────────────────────────────────────────────────────
-- DIMENSIONS
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS warehouse.dim_date (
    date_key        INTEGER PRIMARY KEY,        -- yyyymmdd
    full_date       DATE NOT NULL,
    year            SMALLINT NOT NULL,
    quarter         SMALLINT NOT NULL,
    month           SMALLINT NOT NULL,
    month_name      VARCHAR(12) NOT NULL,
    week            SMALLINT NOT NULL,
    day_of_month    SMALLINT NOT NULL,
    is_weekend      BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS warehouse.dim_patient (
    patient_key     SERIAL PRIMARY KEY,
    patient_uuid    UUID NOT NULL UNIQUE,       -- natural key from OLTP
    pseudonym       VARCHAR(40),
    sex             CHAR(1),
    age_band        VARCHAR(12),                -- e.g. '30-39'
    segment         VARCHAR(40)
);

CREATE TABLE IF NOT EXISTS warehouse.dim_biomarker (
    biomarker_key   SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL UNIQUE,
    category        VARCHAR(100),
    unit            VARCHAR(50),
    optimal_min     NUMERIC(12, 4),
    optimal_max     NUMERIC(12, 4),
    priority        SMALLINT
);

CREATE TABLE IF NOT EXISTS warehouse.dim_lab (
    lab_key         SERIAL PRIMARY KEY,
    lab_name        VARCHAR(100) NOT NULL UNIQUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- FACTS
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS warehouse.fact_analysis (
    analysis_key            BIGSERIAL PRIMARY KEY,
    analysis_uuid           UUID NOT NULL UNIQUE,
    date_key                INTEGER REFERENCES warehouse.dim_date(date_key),
    patient_key             INTEGER REFERENCES warehouse.dim_patient(patient_key),
    lab_key                 INTEGER REFERENCES warehouse.dim_lab(lab_key),
    -- measures
    optimality_score        NUMERIC(5, 2),
    biological_age          NUMERIC(5, 2),
    total_biomarkers        SMALLINT,
    red_flag_count          SMALLINT,
    has_red_flags           BOOLEAN,
    extraction_confidence   NUMERIC(4, 3)
);

CREATE TABLE IF NOT EXISTS warehouse.fact_biomarker_measurement (
    measurement_key     BIGSERIAL PRIMARY KEY,
    date_key            INTEGER REFERENCES warehouse.dim_date(date_key),
    patient_key         INTEGER REFERENCES warehouse.dim_patient(patient_key),
    biomarker_key       INTEGER REFERENCES warehouse.dim_biomarker(biomarker_key),
    lab_key             INTEGER REFERENCES warehouse.dim_lab(lab_key),
    analysis_uuid       UUID,
    -- measures
    value               NUMERIC(12, 4),
    optimality_gap      NUMERIC(12, 4),     -- distance from optimal band (0 if inside)
    is_below_optimal    SMALLINT,           -- 0/1 additive flags for easy aggregation
    is_above_optimal    SMALLINT,
    is_optimal          SMALLINT,
    is_red_flag         SMALLINT
);

CREATE INDEX IF NOT EXISTS idx_fa_date       ON warehouse.fact_analysis(date_key);
CREATE INDEX IF NOT EXISTS idx_fa_patient    ON warehouse.fact_analysis(patient_key);
CREATE INDEX IF NOT EXISTS idx_fbm_date      ON warehouse.fact_biomarker_measurement(date_key);
CREATE INDEX IF NOT EXISTS idx_fbm_biomarker ON warehouse.fact_biomarker_measurement(biomarker_key);
CREATE INDEX IF NOT EXISTS idx_fbm_patient   ON warehouse.fact_biomarker_measurement(patient_key);

-- ─────────────────────────────────────────────────────────────────────────────
-- BI convenience view : biomarker deficiency frequency (drives Biological Risk Score)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW warehouse.vw_deficiency_frequency AS
SELECT  b.name                              AS biomarker,
        b.category,
        COUNT(*)                            AS measurements,
        SUM(m.is_below_optimal)             AS below_optimal,
        ROUND(100.0 * SUM(m.is_below_optimal) / NULLIF(COUNT(*), 0), 1) AS pct_below_optimal,
        SUM(m.is_red_flag)                  AS red_flags
FROM    warehouse.fact_biomarker_measurement m
JOIN    warehouse.dim_biomarker b ON b.biomarker_key = m.biomarker_key
GROUP BY b.name, b.category
ORDER BY pct_below_optimal DESC;

COMMENT ON SCHEMA warehouse IS 'AXIOM analytical warehouse — star schema for cohort BI';
COMMENT ON TABLE  warehouse.fact_analysis IS 'Report-grain fact: one row per analysis';
COMMENT ON TABLE  warehouse.fact_biomarker_measurement IS 'Atomic-grain fact: one row per biomarker measured';
