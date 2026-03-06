-- Grievance App Database Schema
-- Designed for MCD (Municipal Corporation of Delhi) Hierarchy

-- 1. Administrative Structure
CREATE TABLE zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE wards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id UUID REFERENCES zones(id),
    name VARCHAR(255) NOT NULL,
    number INTEGER NOT NULL
);

CREATE TABLE departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL -- Engineering, Sanitation, Horticulture, Public Health
);

-- 2. Personnel & Hierarchy
CREATE TABLE designations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dept_id UUID REFERENCES departments(id),
    title VARCHAR(255) NOT NULL,
    hierarchy_level INTEGER NOT NULL -- e.g., 1 for DC, 2 for SE, etc.
);

CREATE TABLE officers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    password_hash VARCHAR(255) NOT NULL,
    designation_id UUID REFERENCES designations(id),
    zone_id UUID REFERENCES zones(id),
    ward_id UUID REFERENCES wards(id), -- Nullable for higher-level officers
    supervisor_id UUID REFERENCES officers(id), -- Self-referencing for direct reporting
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- 3. Citizens
CREATE TABLE citizens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255),
    phone VARCHAR(20) UNIQUE NOT NULL,
    is_phone_verified BOOLEAN DEFAULT FALSE,
    otp_hash VARCHAR(255),
    otp_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- 4. Authentication & Sessions
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL, -- UUID of Citizen or Officer
    user_type VARCHAR(50) NOT NULL, -- 'CITIZEN', 'OFFICER'
    refresh_token VARCHAR(512) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Grievances
CREATE TABLE grievance_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dept_id UUID REFERENCES departments(id),
    name VARCHAR(255) NOT NULL -- e.g., 'Street Light Repair', 'Waste Collection'
);

CREATE TABLE grievances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    citizen_id UUID REFERENCES citizens(id),
    category_id UUID REFERENCES grievance_categories(id),
    ward_id UUID REFERENCES wards(id),
    description TEXT,
    lat DECIMAL(9,6),
    lng DECIMAL(9,6),
    status VARCHAR(50) DEFAULT 'PENDING', -- PENDING, ASSIGNED, IN_PROGRESS, RESOLVED, CLOSED
    priority VARCHAR(20) DEFAULT 'MEDIUM',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE grievance_media (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grievance_id UUID REFERENCES grievances(id),
    url TEXT NOT NULL,
    media_type VARCHAR(20) -- IMAGE, VIDEO
);

-- 6. Assignment & Workflow
CREATE TABLE assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grievance_id UUID REFERENCES grievances(id),
    assigned_to_id UUID REFERENCES officers(id),
    assigned_by_id UUID REFERENCES officers(id),
    status VARCHAR(50) NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    remarks TEXT
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grievance_id UUID REFERENCES grievances(id),
    action VARCHAR(255) NOT NULL,
    actor_id UUID NOT NULL, -- UUID of Citizen or Officer
    actor_type VARCHAR(50) NOT NULL, -- 'CITIZEN', 'OFFICER'
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details JSONB
);
