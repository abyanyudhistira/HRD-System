-- ============================================
-- Manual SQL Commands - Run these in PostgreSQL
-- ============================================
-- Since PostgreSQL is already running, run these manually

-- 1. Create users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Insert default admin user (password: admin123)
-- Hash generated with bcrypt for 'admin123'
INSERT INTO users (email, password_hash, name, role) 
VALUES (
    'admin@hrd.com', 
    '$2b$12$aKCwleca8MWDmc3eOf6fOew2lctnHSRh6lwYIzx7ptdmlDepiIDZC', 
    'Admin User', 
    'admin'
) ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash;

-- 3. Create index for better performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);

-- 4. Verify table created
SELECT * FROM users;