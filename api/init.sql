-- PostgreSQL Database Schema untuk LinkedIn Crawler
-- Migrasi dari Supabase ke PostgreSQL

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Schedules table
CREATE TABLE IF NOT EXISTS crawler_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    template_id UUID,
    start_schedule TEXT NOT NULL,
    stop_schedule TEXT,
    status TEXT DEFAULT 'active',
    profile_urls JSONB DEFAULT '[]'::jsonb,
    max_workers INTEGER DEFAULT 3,
    external_source TEXT,
    webhook_url TEXT,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Crawl history table
CREATE TABLE IF NOT EXISTS crawler_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schedule_id UUID REFERENCES crawler_schedules(id) ON DELETE CASCADE,
    profile_url TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    output_file TEXT
);

-- Search templates table
CREATE TABLE IF NOT EXISTS search_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    description TEXT,
    search_criteria JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Companies table
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    domain TEXT,
    industry TEXT,
    size TEXT,
    location TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Leads table
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    full_name TEXT NOT NULL,
    linkedin_url TEXT,
    email TEXT,
    phone TEXT,
    position TEXT,
    status TEXT DEFAULT 'new',
    source TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Profiles table (untuk scoring)
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    linkedin_url TEXT UNIQUE NOT NULL,
    full_name TEXT,
    headline TEXT,
    location TEXT,
    experience JSONB DEFAULT '[]'::jsonb,
    education JSONB DEFAULT '[]'::jsonb,
    skills JSONB DEFAULT '[]'::jsonb,
    raw_data JSONB DEFAULT '{}'::jsonb,
    score DECIMAL(5,2),
    score_breakdown JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes untuk performance
CREATE INDEX IF NOT EXISTS idx_schedules_status ON crawler_schedules(status);
CREATE INDEX IF NOT EXISTS idx_schedules_template ON crawler_schedules(template_id);
CREATE INDEX IF NOT EXISTS idx_history_schedule ON crawler_history(schedule_id);
CREATE INDEX IF NOT EXISTS idx_history_status ON crawler_history(status);
CREATE INDEX IF NOT EXISTS idx_leads_company ON leads(company_id);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);

-- Add company_id FK to search_templates (migration)
ALTER TABLE search_templates ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES companies(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_templates_company ON search_templates(company_id);
CREATE INDEX IF NOT EXISTS idx_profiles_url ON profiles(linkedin_url);
CREATE INDEX IF NOT EXISTS idx_profiles_score ON profiles(score);

-- Insert sample data
INSERT INTO search_templates (id, name, description, search_criteria) VALUES
(uuid_generate_v4(), 'Backend Developer Senior', 'Senior backend developers with 5+ years experience', '{"keywords": ["backend", "senior", "python", "java"], "experience_years": 5}'),
(uuid_generate_v4(), 'Frontend Developer', 'Frontend developers with React/Vue experience', '{"keywords": ["frontend", "react", "vue", "javascript"], "experience_years": 3}'),
(uuid_generate_v4(), 'Data Scientist', 'Data scientists with ML/AI background', '{"keywords": ["data scientist", "machine learning", "python", "AI"], "experience_years": 3}')
ON CONFLICT DO NOTHING;

-- Insert sample company
INSERT INTO companies (id, name, domain, industry, size, location) VALUES
(uuid_generate_v4(), 'Tech Startup Indonesia', 'techstartup.id', 'Technology', '50-100', 'Jakarta, Indonesia')
ON CONFLICT DO NOTHING;