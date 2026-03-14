-- ============================================
-- HRD System - PostgreSQL + pgvector Schema
-- ============================================
-- Auto-executed on first container startup
-- ============================================

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. Companies Table (referenced by search_templates)
-- ============================================
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    code TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 2. Search Templates Table
-- ============================================
CREATE TABLE IF NOT EXISTS search_templates (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    job_title VARCHAR(255),
    url TEXT,
    note TEXT,
    job_description TEXT,
    requirements JSONB,
    external_source VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- 3. Crawler Schedules Table
-- ============================================
CREATE TABLE IF NOT EXISTS crawler_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    start_schedule TEXT NOT NULL,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused')),
    last_run TIMESTAMPTZ,
    template_id UUID REFERENCES search_templates(id) ON DELETE CASCADE,
    external_source TEXT,
    external_metadata JSONB,
    webhook_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 4. Connection History Table
-- ============================================
CREATE TABLE IF NOT EXISTS connection_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID REFERENCES search_templates(id) ON DELETE CASCADE,
    date DATE DEFAULT CURRENT_DATE,
    leads JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 5. Leads List Table (Main candidate storage)
-- ============================================
CREATE TABLE IF NOT EXISTS leads_list (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    template_id UUID REFERENCES search_templates(id) ON DELETE SET NULL,
    date DATE DEFAULT CURRENT_DATE,
    name VARCHAR(255),
    note_sent TEXT,
    search_url TEXT,
    profile_url TEXT UNIQUE NOT NULL,
    connection_status VARCHAR(50) DEFAULT 'pending',
    score FLOAT,
    processed_at TIMESTAMPTZ,
    profile_data JSONB,
    scoring_data JSONB,
    sent_at TIMESTAMPTZ
);



-- ============================================
-- 6. Indexes for Performance
-- ============================================

-- Companies indexes
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);
CREATE INDEX IF NOT EXISTS idx_companies_code ON companies(code);

-- Search templates indexes
CREATE INDEX IF NOT EXISTS idx_search_templates_name ON search_templates(name);
CREATE INDEX IF NOT EXISTS idx_search_templates_job_title ON search_templates(job_title);
CREATE INDEX IF NOT EXISTS idx_search_templates_company_id ON search_templates(company_id);
CREATE INDEX IF NOT EXISTS idx_search_templates_external_source ON search_templates(external_source);
CREATE INDEX IF NOT EXISTS idx_search_templates_created_at ON search_templates(created_at);

-- Crawler schedules indexes
CREATE INDEX IF NOT EXISTS idx_schedules_status ON crawler_schedules(status);
CREATE INDEX IF NOT EXISTS idx_schedules_template_id ON crawler_schedules(template_id);
CREATE INDEX IF NOT EXISTS idx_schedules_created ON crawler_schedules(created_at DESC);

-- Connection history indexes
CREATE INDEX IF NOT EXISTS idx_connection_history_template_id ON connection_history(template_id);
CREATE INDEX IF NOT EXISTS idx_connection_history_date ON connection_history(date DESC);

-- Leads list indexes
CREATE INDEX IF NOT EXISTS idx_leads_profile_url ON leads_list(profile_url);
CREATE INDEX IF NOT EXISTS idx_leads_template_id ON leads_list(template_id);
CREATE INDEX IF NOT EXISTS idx_leads_connection_status ON leads_list(connection_status);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads_list(score DESC);
CREATE INDEX IF NOT EXISTS idx_leads_date ON leads_list(date DESC);
CREATE INDEX IF NOT EXISTS idx_leads_profile_data ON leads_list USING GIN (profile_data);
CREATE INDEX IF NOT EXISTS idx_leads_scoring_data ON leads_list USING GIN (scoring_data);

-- ============================================
-- 7. Functions & Triggers
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_schedules_updated_at
    BEFORE UPDATE ON crawler_schedules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_templates_updated_at
    BEFORE UPDATE ON search_templates
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_leads_updated_at
    BEFORE UPDATE ON leads_list
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_jobs_updated_at
    BEFORE UPDATE ON crawler_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 8. Sample Data (Optional - for testing)
-- ============================================

-- Insert sample company
INSERT INTO companies (id, name, code)
VALUES (
    'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    'BPR KS Bandung',
    'BPR_KS'
) ON CONFLICT (id) DO NOTHING;

-- Insert sample template
INSERT INTO search_templates (id, company_id, name, job_title, job_description, requirements)
VALUES (
    '8191cb53-725e-46f5-a54a-79affc378811',
    'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    'Desk Collection - BPR KS Bandung',
    'Desk Collection',
    'Desk collection position for BPR KS Bandung',
    '{
        "position": "Desk Collection - BPR KS Bandung",
        "requirements": [
            {"id": "gender", "type": "gender", "label": "Gender: Female", "value": "female"},
            {"id": "location", "type": "location", "label": "Location: Bandung", "value": "bandung"},
            {"id": "age_range", "type": "age", "label": "Age: 20-35 years", "value": "20-35"},
            {"id": "min_experience", "type": "experience", "label": "Minimum 1 years experience", "value": 1}
        ]
    }'::jsonb
) ON CONFLICT (id) DO NOTHING;

-- ============================================
-- 9. Verification Queries
-- ============================================

-- Check tables
SELECT 
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'public' 
    AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- Check extensions
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'uuid-ossp');

-- ============================================
-- DONE! Database initialized successfully
-- ============================================


-- ============================================
-- Additional Trigger for sync_leads_to_list
-- ============================================

CREATE OR REPLACE FUNCTION sync_leads_to_list()
RETURNS TRIGGER AS $
DECLARE
    lead_item jsonb;
BEGIN
    FOR lead_item IN
        SELECT * FROM jsonb_array_elements(NEW.leads)
    LOOP
        -- Skip if profile_url contains /sales/
        IF (lead_item ->> 'profile_url') LIKE '%/sales/%' THEN
            CONTINUE;
        END IF;

        INSERT INTO leads_list (
            template_id,
            date,
            name,
            note_sent,
            search_url,
            profile_url,
            connection_status,
            score
        )
        SELECT
            NEW.template_id,
            NEW.date,
            lead_item ->> 'name',
            lead_item ->> 'note_sent',
            lead_item ->> 'search_url',
            lead_item ->> 'profile_url',
            'pending',
            NULL
        WHERE NOT EXISTS (
            SELECT 1 FROM leads_list
            WHERE profile_url = lead_item ->> 'profile_url'
        );
    END LOOP;

    RETURN NEW;
END;
$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_leads
    AFTER INSERT ON connection_history
    FOR EACH ROW
    EXECUTE FUNCTION sync_leads_to_list();
