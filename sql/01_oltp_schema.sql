-- ════════════════════════════════════════════════════════════════════════════
-- AXIOM Data Platform — OLTP (operational) schema
-- Purpose : transactional store behind the AXIOM ingestion pipeline.
-- Engine  : PostgreSQL 16
-- This file is executed automatically by the Postgres container on first boot
-- (mounted into /docker-entrypoint-initdb.d).
-- ════════════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS oltp;
SET search_path TO oltp, public;

-- ─────────────────────────────────────────────────────────────────────────────
-- Reference data : optimality thresholds (the proprietary "Golden Data")
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS oltp.biomarker_thresholds (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                VARCHAR(200) NOT NULL UNIQUE,
    unit                VARCHAR(50),
    category            VARCHAR(100),
    optimal_min         NUMERIC(12, 4),
    optimal_max         NUMERIC(12, 4),
    lab_ref_min         NUMERIC(12, 4),
    lab_ref_max         NUMERIC(12, 4),
    priority            SMALLINT DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    evidence            TEXT,
    version             VARCHAR(20) DEFAULT '1.0',
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Reference data : pathological thresholds (medical safety guardrail)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS oltp.red_flag_thresholds (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    biomarker_name      VARCHAR(200) NOT NULL UNIQUE,
    unit                VARCHAR(50),
    red_flag_low        NUMERIC(12, 4),
    red_flag_high       NUMERIC(12, 4),
    urgency             VARCHAR(20) NOT NULL CHECK (urgency IN ('URGENT', 'HIGH', 'MEDIUM')),
    message             TEXT,
    validated_by        VARCHAR(200),     -- medical validator (governance trace)
    validated_at        DATE,
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Reference data : Cure / Diet / Lifestyle recommendations
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS oltp.recommendations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    biomarker_id        UUID NOT NULL REFERENCES oltp.biomarker_thresholds(id) ON DELETE CASCADE,
    type                VARCHAR(20) NOT NULL CHECK (type IN ('cure', 'diet', 'lifestyle')),
    description         TEXT NOT NULL,
    condition           VARCHAR(20) CHECK (condition IN ('BELOW_OPTIMAL', 'ABOVE_OPTIMAL', 'BOTH')),
    product_name        VARCHAR(200),
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Subjects : anonymised patients (no full name ever stored — GDPR minimisation)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS oltp.patients (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pseudonym           VARCHAR(40) NOT NULL UNIQUE,   -- e.g. hash / external uid
    age                 SMALLINT CHECK (age BETWEEN 0 AND 120),
    sex                 CHAR(1) CHECK (sex IN ('M', 'F')),
    segment             VARCHAR(40),                   -- persona segment (e.g. 'athlete')
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Transactions : one analysis per submitted blood-test
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS oltp.analysis_reports (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id              UUID REFERENCES oltp.patients(id) ON DELETE CASCADE,
    lab_name                VARCHAR(100),
    report_date             DATE NOT NULL,
    total_biomarkers        SMALLINT,
    optimality_score        NUMERIC(5, 2),     -- 0..100
    biological_age          NUMERIC(5, 2),     -- PhenoAge estimate
    has_red_flags           BOOLEAN DEFAULT FALSE,
    red_flag_count          SMALLINT DEFAULT 0,
    extraction_confidence   NUMERIC(4, 3),     -- 0..1 (Agent 1 quality)
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Transactions : individual biomarker results per analysis
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS oltp.biomarker_results (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id           UUID NOT NULL REFERENCES oltp.analysis_reports(id) ON DELETE CASCADE,
    biomarker_name      VARCHAR(200) NOT NULL,
    value               NUMERIC(12, 4),
    unit                VARCHAR(50),
    lab_status          VARCHAR(20),           -- LOW / NORMAL / HIGH (lab reference)
    optimality_status   VARCHAR(20),           -- BELOW_OPTIMAL / OPTIMAL / ABOVE_OPTIMAL
    is_red_flag         BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Performance indexes
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_reports_patient        ON oltp.analysis_reports(patient_id);
CREATE INDEX IF NOT EXISTS idx_reports_date           ON oltp.analysis_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_results_report         ON oltp.biomarker_results(report_id);
CREATE INDEX IF NOT EXISTS idx_results_name           ON oltp.biomarker_results(biomarker_name);
CREATE INDEX IF NOT EXISTS idx_thresholds_name        ON oltp.biomarker_thresholds(name);

-- ─────────────────────────────────────────────────────────────────────────────
-- updated_at trigger
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION oltp.touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_thresholds_touch ON oltp.biomarker_thresholds;
CREATE TRIGGER trg_thresholds_touch BEFORE UPDATE ON oltp.biomarker_thresholds
    FOR EACH ROW EXECUTE FUNCTION oltp.touch_updated_at();

DROP TRIGGER IF EXISTS trg_patients_touch ON oltp.patients;
CREATE TRIGGER trg_patients_touch BEFORE UPDATE ON oltp.patients
    FOR EACH ROW EXECUTE FUNCTION oltp.touch_updated_at();

COMMENT ON SCHEMA oltp IS 'AXIOM operational (transactional) store — ingestion pipeline backend';
COMMENT ON TABLE  oltp.biomarker_thresholds IS 'Proprietary optimality thresholds (Golden Data)';
COMMENT ON TABLE  oltp.red_flag_thresholds  IS 'Pathological thresholds triggering doctor referral';
COMMENT ON TABLE  oltp.patients             IS 'Anonymised subjects (GDPR data minimisation)';
COMMENT ON TABLE  oltp.analysis_reports     IS 'One row per submitted blood-test analysis';
COMMENT ON TABLE  oltp.biomarker_results    IS 'One row per biomarker measured in an analysis';
