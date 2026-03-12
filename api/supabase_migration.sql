-- ============================================
-- LinkedIn Crawler Scheduler - Supabase Schema
-- ============================================
-- CARA SETUP:
-- 1. Login ke Supabase Dashboard (https://supabase.com)
-- 2. Pilih project kamu
-- 3. Klik "SQL Editor" di sidebar
-- 4. Copy paste semua SQL ini dan klik "Run"
-- 5. Get Service Role Key dari Project Settings > API
-- 6. Tambahkan ke backend/api/.env:
--    SUPABASE_URL=https://xxxxx.supabase.co
--    SUPABASE_KEY=your_service_role_key (bukan anon key!)
-- ============================================

-- Drop existing tables if you want to start fresh (CAREFUL!)
-- DROP TABLE IF EXISTS crawler_history CASCADE;
-- DROP TABLE IF EXISTS crawler_schedules CASCADE;

-- ============================================
-- 1. Schedules Table
-- ============================================
CREATE TABLE IF NOT EXISTS crawler_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    start_schedule TEXT NOT NULL,
    stop_schedule TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused')),
    profile_urls JSONB DEFAULT '[]'::jsonb,
    max_workers INTEGER DEFAULT 3 CHECK (max_workers > 0 AND max_workers <= 10),
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 2. Crawl History Table
-- ============================================
CREATE TABLE IF NOT EXISTS crawler_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schedule_id UUID REFERENCES crawler_schedules(id) ON DELETE CASCADE,
    profile_url TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing', 'completed', 'failed', 'skipped')),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    output_file TEXT
);

-- ============================================
-- 3. Indexes for Performance
-- ============================================
CREATE INDEX IF NOT EXISTS idx_schedules_status ON crawler_schedules(status);
CREATE INDEX IF NOT EXISTS idx_schedules_created ON crawler_schedules(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_schedule ON crawler_history(schedule_id);
CREATE INDEX IF NOT EXISTS idx_history_status ON crawler_history(status);
CREATE INDEX IF NOT EXISTS idx_history_started ON crawler_history(started_at DESC);

-- ============================================
-- 4. Row Level Security (RLS)
-- ============================================
ALTER TABLE crawler_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE crawler_history ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Service role full access schedules" ON crawler_schedules;
DROP POLICY IF EXISTS "Service role full access history" ON crawler_history;
DROP POLICY IF EXISTS "Authenticated users read schedules" ON crawler_schedules;
DROP POLICY IF EXISTS "Authenticated users read history" ON crawler_history;

-- Service role can do everything (for API backend)
CREATE POLICY "Service role full access schedules"
    ON crawler_schedules FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service role full access history"
    ON crawler_history FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Authenticated users can read (for frontend)
CREATE POLICY "Authenticated users read schedules"
    ON crawler_schedules FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Authenticated users read history"
    ON crawler_history FOR SELECT
    TO authenticated
    USING (true);

-- ============================================
-- 5. Functions & Triggers
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for schedules
DROP TRIGGER IF EXISTS update_schedules_updated_at ON crawler_schedules;
CREATE TRIGGER update_schedules_updated_at
    BEFORE UPDATE ON crawler_schedules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 6. Sample Data (Optional - for testing)
-- ============================================

-- Uncomment to insert sample schedule
/*
INSERT INTO crawler_schedules (name, start_schedule, stop_schedule, profile_urls, max_workers)
VALUES (
    'Daily Lead Crawler',
    '0 9 * * *',
    '0 18 * * *',
    '["https://www.linkedin.com/in/example1", "https://www.linkedin.com/in/example2"]'::jsonb,
    3
);
*/

-- ============================================
-- 7. Verify Installation
-- ============================================

-- Check tables exist
SELECT 
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'public' 
    AND table_name IN ('crawler_schedules', 'crawler_history')
ORDER BY table_name;

-- Check indexes
SELECT 
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
    AND tablename IN ('crawler_schedules', 'crawler_history')
ORDER BY tablename, indexname;

-- Check RLS policies
SELECT 
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd
FROM pg_policies
WHERE schemaname = 'public'
    AND tablename IN ('crawler_schedules', 'crawler_history')
ORDER BY tablename, policyname;

-- ============================================
-- DONE! 
-- ============================================
-- Your database is ready for the crawler scheduler!
-- 
-- Next steps:
-- 1. Get your Supabase Service Role Key from:
--    Project Settings > API > service_role key
-- 2. Add it to backend/api/.env:
--    SUPABASE_KEY=your_service_role_key_here
-- 3. Start the API server
-- ============================================
-- Search Templates table for storing job templates and requirements
CREATE TABLE IF NOT EXISTS search_templates (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    job_title VARCHAR(255),
    job_description TEXT,
    requirements JSONB,
    company_id UUID,
    external_source VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_search_templates_name ON search_templates(name);
CREATE INDEX IF NOT EXISTS idx_search_templates_job_title ON search_templates(job_title);
CREATE INDEX IF NOT EXISTS idx_search_templates_company_id ON search_templates(company_id);
CREATE INDEX IF NOT EXISTS idx_search_templates_external_source ON search_templates(external_source);
CREATE INDEX IF NOT EXISTS idx_search_templates_created_at ON search_templates(created_at);

-- RLS policies for search_templates table
ALTER TABLE search_templates ENABLE ROW LEVEL SECURITY;

-- Allow all operations for now (adjust based on your auth requirements)
CREATE POLICY "Allow all operations on search_templates" ON search_templates
    FOR ALL USING (true) WITH CHECK (true);