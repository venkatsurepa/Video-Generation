-- ============================================================
-- CrimeMill — Research Database & FOIA Tracking
-- ============================================================
-- Structured research library for public records collection.
-- Three tables: research_sources, case_files, foia_requests.
--
-- Design:
--   • Full-text search via GIN / to_tsvector on raw document text
--   • case_files aggregate multiple sources into a single case
--   • foia_requests tracks outbound FOIA lifecycle
--   • All tables: UUID PKs, TIMESTAMPTZ, TEXT CHECK constraints
-- ============================================================


-- ============================================================
-- 1. CASE FILES — aggregated research cases
-- ============================================================

CREATE TABLE IF NOT EXISTS case_files (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_name           TEXT NOT NULL,
    category            TEXT NOT NULL DEFAULT 'other'
        CHECK (category IN (
            'corporate_fraud', 'ponzi_scheme', 'art_forgery', 'cybercrime',
            'money_laundering', 'embezzlement', 'insurance_fraud', 'identity_theft',
            'murder', 'kidnapping', 'organized_crime', 'political_corruption',
            'environmental_crime', 'trafficking', 'other'
        )),
    summary             TEXT NOT NULL DEFAULT '',
    key_entities        JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_ids          UUID[] NOT NULL DEFAULT '{}',
    timeline            JSONB NOT NULL DEFAULT '[]'::jsonb,
    financial_impact_usd NUMERIC,
    status              TEXT NOT NULL DEFAULT 'researching'
        CHECK (status IN ('researching', 'ready', 'assigned', 'produced')),
    assigned_video_id   UUID REFERENCES videos(id) ON DELETE SET NULL,
    assigned_topic_id   UUID,
    notes               TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_case_files_updated_at
    BEFORE UPDATE ON case_files
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_case_files_category
    ON case_files (category);

CREATE INDEX IF NOT EXISTS idx_case_files_status
    ON case_files (status)
    WHERE status != 'produced';

CREATE INDEX IF NOT EXISTS idx_case_files_name_fts
    ON case_files
    USING GIN (to_tsvector('english', case_name || ' ' || summary));


-- ============================================================
-- 2. RESEARCH SOURCES — collected documents from public agencies
-- ============================================================

CREATE TABLE IF NOT EXISTS research_sources (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_file_id        UUID REFERENCES case_files(id) ON DELETE SET NULL,
    source_type         TEXT NOT NULL
        CHECK (source_type IN (
            'sec_filing', 'court_document', 'doj_press_release', 'fbi_press_release',
            'ftc_action', 'fincen_action', 'state_court', 'newspaper_article',
            'foia_document', 'academic_paper', 'other'
        )),
    title               TEXT NOT NULL,
    url                 TEXT NOT NULL DEFAULT '',
    source_name         TEXT NOT NULL DEFAULT '',  -- "SEC EDGAR", "PACER", "DOJ", etc.
    publication_date    DATE,
    raw_text            TEXT NOT NULL DEFAULT '',   -- extracted/OCR'd text for search
    entities            JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    relevance_score     NUMERIC(3, 2) DEFAULT 0
        CHECK (relevance_score >= 0 AND relevance_score <= 1),
    storage_path        TEXT,                       -- R2 path if document is stored
    used_in_video_ids   UUID[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_research_sources_updated_at
    BEFORE UPDATE ON research_sources
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Full-text search on document content
CREATE INDEX IF NOT EXISTS idx_research_sources_fts
    ON research_sources
    USING GIN (to_tsvector('english', raw_text));

CREATE INDEX IF NOT EXISTS idx_research_sources_type
    ON research_sources (source_type);

CREATE INDEX IF NOT EXISTS idx_research_sources_case_file
    ON research_sources (case_file_id)
    WHERE case_file_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_research_sources_pub_date
    ON research_sources (publication_date DESC)
    WHERE publication_date IS NOT NULL;


-- ============================================================
-- 3. FOIA REQUESTS — outbound request lifecycle tracking
-- ============================================================

CREATE TABLE IF NOT EXISTS foia_requests (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency                  TEXT NOT NULL,          -- "DOJ", "FBI", "SEC", "IRS", etc.
    description             TEXT NOT NULL,
    case_reference          TEXT NOT NULL DEFAULT '',
    case_file_id            UUID REFERENCES case_files(id) ON DELETE SET NULL,
    date_filed              DATE NOT NULL DEFAULT CURRENT_DATE,
    tracking_number         TEXT,
    method                  TEXT NOT NULL DEFAULT 'electronic'
        CHECK (method IN ('electronic', 'mail', 'email')),
    expected_response_date  DATE,  -- default: date_filed + 104 days
    actual_response_date    DATE,
    status                  TEXT NOT NULL DEFAULT 'filed'
        CHECK (status IN (
            'filed', 'acknowledged', 'processing',
            'received', 'appealed', 'denied', 'partial'
        )),
    documents_received      INT NOT NULL DEFAULT 0,
    cost_usd                NUMERIC(10, 2) NOT NULL DEFAULT 0,
    notes                   TEXT NOT NULL DEFAULT '',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_foia_requests_updated_at
    BEFORE UPDATE ON foia_requests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Overdue request detection
CREATE INDEX IF NOT EXISTS idx_foia_overdue
    ON foia_requests (expected_response_date)
    WHERE status IN ('filed', 'acknowledged', 'processing')
      AND expected_response_date IS NOT NULL;

-- Active requests (exclude terminal states)
CREATE INDEX IF NOT EXISTS idx_foia_status
    ON foia_requests (status)
    WHERE status NOT IN ('received', 'denied');

CREATE INDEX IF NOT EXISTS idx_foia_case_file
    ON foia_requests (case_file_id)
    WHERE case_file_id IS NOT NULL;


-- ============================================================
-- 4. ROW LEVEL SECURITY
-- ============================================================

ALTER TABLE case_files       ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE foia_requests    ENABLE ROW LEVEL SECURITY;

-- Service role has full access (pipeline and CLI)
CREATE POLICY case_files_service_all ON case_files
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY research_sources_service_all ON research_sources
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY foia_requests_service_all ON foia_requests
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
