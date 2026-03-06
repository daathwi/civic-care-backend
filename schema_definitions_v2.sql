-- CivicCare PostgreSQL Schema Initialization
-- Designed to support MCD hierarchical workflows and public community reporting.

-- Extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Extension for geospatial queries (Needs PostGIS installed on the server)
-- CREATE EXTENSION IF NOT EXISTS "postgis"; 

-- =========================================================================
-- 1. Administrative Structure & Hierarchy
-- =========================================================================

CREATE TABLE IF NOT EXISTS zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS wards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id UUID REFERENCES zones(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    number INTEGER NOT NULL,
    polygon_geojson JSONB, -- For precise geofencing boundary checks
    representative_name VARCHAR(255),
    representative_phone TEXT[] -- list of phone numbers
);

CREATE TABLE IF NOT EXISTS departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    short_code VARCHAR(20) NOT NULL,
    primary_color VARCHAR(10) NOT NULL,
    icon VARCHAR(100) NOT NULL,
    manager_title VARCHAR(100) NOT NULL,
    assistant_title VARCHAR(100) NOT NULL,
    jurisdiction_label VARCHAR(50) NOT NULL
);

-- =========================================================================
-- 2. Personnel & Identity
-- =========================================================================

CREATE TYPE user_role AS ENUM ('citizen', 'fieldManager', 'fieldAssistant');

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    role user_role NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(512) UNIQUE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TYPE worker_status AS ENUM ('onDuty', 'offDuty');

CREATE TABLE IF NOT EXISTS worker_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    designation_title VARCHAR(255) NOT NULL,
    zone_id UUID REFERENCES zones(id) ON DELETE SET NULL,
    ward_id UUID REFERENCES wards(id) ON DELETE SET NULL,
    supervisor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    rating DECIMAL(3,2) DEFAULT 0.00,
    tasks_completed INTEGER DEFAULT 0,
    tasks_active INTEGER DEFAULT 0,
    current_status worker_status DEFAULT 'offDuty',
    last_active_lat DECIMAL(9,6),
    last_active_lng DECIMAL(9,6)
);

-- =========================================================================
-- 3. The Community Ecosystem (Complaints)
-- =========================================================================

CREATE TABLE IF NOT EXISTS grievance_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dept_id UUID REFERENCES departments(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL
);

CREATE TYPE complaint_status AS ENUM ('pending', 'assigned', 'inprogress', 'resolved');
CREATE TYPE complaint_priority AS ENUM ('low', 'medium', 'high');

CREATE TABLE IF NOT EXISTS grievances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    lat DECIMAL(9,6) NOT NULL,
    lng DECIMAL(9,6) NOT NULL,
    address VARCHAR(500),
    status complaint_status DEFAULT 'pending',
    priority complaint_priority DEFAULT 'medium',
    category_id UUID REFERENCES grievance_categories(id) ON DELETE SET NULL,
    ward_id UUID REFERENCES wards(id) ON DELETE SET NULL,
    reporter_id UUID REFERENCES users(id) ON DELETE SET NULL,
    upvotes_count INTEGER DEFAULT 0,
    downvotes_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TYPE media_type AS ENUM ('image', 'video');

CREATE TABLE IF NOT EXISTS grievance_media (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grievance_id UUID REFERENCES grievances(id) ON DELETE CASCADE,
    media_url TEXT NOT NULL,
    type media_type DEFAULT 'image',
    is_resolution_proof BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 4. Social Collaboration
-- =========================================================================

CREATE TABLE IF NOT EXISTS grievance_votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grievance_id UUID REFERENCES grievances(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    vote_type INTEGER NOT NULL, -- 1 for upvote, -1 for downvote
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(grievance_id, user_id) -- Only one vote per user per ticket
);

CREATE TABLE IF NOT EXISTS grievance_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grievance_id UUID REFERENCES grievances(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 5. Operations & Workflows
-- =========================================================================

CREATE TYPE assignment_status AS ENUM ('pending', 'accepted', 'in_progress', 'completed');

CREATE TABLE IF NOT EXISTS assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grievance_id UUID REFERENCES grievances(id) ON DELETE CASCADE,
    assigned_to_id UUID REFERENCES users(id) ON DELETE CASCADE,
    assigned_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    status assignment_status DEFAULT 'pending',
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grievance_id UUID REFERENCES grievances(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    icon_name VARCHAR(100),
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    clock_in_time TIMESTAMP WITH TIME ZONE NOT NULL,
    clock_in_lat DECIMAL(9,6) NOT NULL,
    clock_in_lng DECIMAL(9,6) NOT NULL,
    clock_out_time TIMESTAMP WITH TIME ZONE,
    clock_out_lat DECIMAL(9,6),
    clock_out_lng DECIMAL(9,6),
    total_duration_seconds INTEGER
);

-- Indexes for performance
CREATE INDEX idx_grievances_status ON grievances(status);
CREATE INDEX idx_grievances_ward ON grievances(ward_id);
CREATE INDEX idx_assignments_worker ON assignments(assigned_to_id);
CREATE INDEX idx_attendance_user_date ON attendance_records(user_id, date);
