-- CivicCare PostgreSQL Seed Data
-- Run this after schema_definitions_v2.sql to populate the database with mock test data.

-- =========================================================================
-- 1. Administrative Structure & Hierarchy
-- =========================================================================
INSERT INTO zones (id, name, code)
VALUES 
    ('11111111-1111-1111-1111-111111111111', 'North Zone', 'NZ01'),
    ('22222222-2222-2222-2222-222222222222', 'South Zone', 'SZ01')
ON CONFLICT DO NOTHING;

INSERT INTO wards (id, zone_id, name, number)
VALUES 
    ('33333333-3333-3333-3333-333333333333', '11111111-1111-1111-1111-111111111111', 'Model Town', 42),
    ('44444444-4444-4444-4444-444444444444', '11111111-1111-1111-1111-111111111111', 'Civil Lines', 43),
    ('55555555-5555-5555-5555-555555555555', '22222222-2222-2222-2222-222222222222', 'Hauz Khas', 85)
ON CONFLICT DO NOTHING;

-- Fixed department UUIDs (must match init_db.py SEED_DEPARTMENTS)
INSERT INTO departments (id, name, short_code, primary_color, icon, manager_title, assistant_title, jurisdiction_label)
VALUES
    ('a1000001-0001-4000-8000-000000000001', 'Sanitation and waste', 'SW', '0xFF00796B', 'delete_outline_rounded', 'Sanitary Inspector', 'Field Worker', 'Ward'),
    ('a1000002-0002-4000-8000-000000000002', 'Engineering', 'ENG', '0xFF1976D2', 'construction_rounded', 'Assistant Engineer', 'Junior Engineer', 'Cluster of wards'),
    ('a1000003-0003-4000-8000-000000000003', 'Public Health', 'PH', '0xFF43A047', 'health_and_safety_rounded', 'Public Health Inspector', 'Health Worker', 'Ward'),
    ('a1000004-0004-4000-8000-000000000004', 'Horticulture', 'HTC', '0xFF7CB342', 'nature_rounded', 'Section Officer', 'Gardener', 'Ward')
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    short_code = EXCLUDED.short_code,
    primary_color = EXCLUDED.primary_color,
    icon = EXCLUDED.icon,
    manager_title = EXCLUDED.manager_title,
    assistant_title = EXCLUDED.assistant_title,
    jurisdiction_label = EXCLUDED.jurisdiction_label;

-- =========================================================================
-- 2. Personnel & Identity
-- =========================================================================

-- Create a mock citizen
INSERT INTO users (id, password_hash, name, phone, role)
VALUES 
    ('aaaa0000-aaaa-0000-aaaa-000000000000', '$2b$10$Epz9b03/tY9Q2ZzQ5Z7Zzu.8Q5/5y5/5/5/5/5/5/5/5/5/5/5/5', 'Ravi Kumar', '+919876543210', 'citizen')
ON CONFLICT DO NOTHING;

-- Create Field Manager (e.g., Sanitary Inspector)
INSERT INTO users (id, password_hash, name, phone, role)
VALUES 
    ('bbbb0000-bbbb-0000-bbbb-000000000000', '$2b$10$Epz9b03/tY9Q2ZzQ5Z7Zzu.8Q5/5y5/5/5/5/5/5/5/5/5/5/5/5', 'Priya Sharma', '+919876543211', 'fieldManager')
ON CONFLICT DO NOTHING;

INSERT INTO worker_profiles (user_id, department_id, designation_title, zone_id, ward_id)
VALUES 
    ('bbbb0000-bbbb-0000-bbbb-000000000000', 'a1000001-0001-4000-8000-000000000001', 'Sanitary Inspector', '11111111-1111-1111-1111-111111111111', '33333333-3333-3333-3333-333333333333')
ON CONFLICT DO NOTHING;

-- Create Field Assistant (e.g., Field Worker)
INSERT INTO users (id, password_hash, name, phone, role)
VALUES 
    ('cccc0000-cccc-0000-cccc-000000000000', '$2b$10$Epz9b03/tY9Q2ZzQ5Z7Zzu.8Q5/5y5/5/5/5/5/5/5/5/5/5/5/5', 'Amit Patel', '+919876543212', 'fieldAssistant')
ON CONFLICT DO NOTHING;

INSERT INTO worker_profiles (user_id, department_id, designation_title, zone_id, ward_id, supervisor_id, tasks_completed, tasks_active, rating)
VALUES 
    ('cccc0000-cccc-0000-cccc-000000000000', 'a1000001-0001-4000-8000-000000000001', 'Field Worker', '11111111-1111-1111-1111-111111111111', '33333333-3333-3333-3333-333333333333', 'bbbb0000-bbbb-0000-bbbb-000000000000', 42, 2, 4.8)
ON CONFLICT DO NOTHING;

-- =========================================================================
-- 3. The Community Ecosystem (Complaints)
-- =========================================================================

-- Categories
INSERT INTO grievance_categories (id, dept_id, name)
VALUES 
    ('dddd0000-dddd-0000-dddd-000000000000', 'a1000001-0001-4000-8000-000000000001', 'Overflowing Bin'),
    ('dddd1111-dddd-1111-dddd-111111111111', 'a1000002-0002-4000-8000-000000000002', 'Pothole')
ON CONFLICT DO NOTHING;

-- A pending (unassigned) grievance
INSERT INTO grievances (id, title, description, lat, lng, address, status, priority, category_id, ward_id, reporter_id, upvotes_count)
VALUES 
    ('eeee0000-eeee-0000-eeee-000000000000', 'Overflowing Garbage Bin', 'The main bin near the park is completely full and spilling over into the street.', 28.6139, 77.2090, 'Sector 4, Model Town', 'pending', 'high', 'dddd0000-dddd-0000-dddd-000000000000', '33333333-3333-3333-3333-333333333333', 'aaaa0000-aaaa-0000-aaaa-000000000000', 14)
ON CONFLICT DO NOTHING;

-- Media for the grievance
INSERT INTO grievance_media (grievance_id, media_url, type, is_resolution_proof)
VALUES 
    ('eeee0000-eeee-0000-eeee-000000000000', 'https://example.com/overflowing_bin.jpg', 'image', false)
ON CONFLICT DO NOTHING;

-- An assigned grievance
INSERT INTO grievances (id, title, description, lat, lng, address, status, priority, category_id, ward_id, reporter_id)
VALUES 
    ('eeee1111-eeee-1111-eeee-111111111111', 'Dangerous Pothole', 'Deep pothole on the main artery road causing traffic issues.', 28.6145, 77.2100, 'Ring Road intersection', 'assigned', 'high', 'dddd1111-dddd-1111-dddd-111111111111', '33333333-3333-3333-3333-333333333333', 'aaaa0000-aaaa-0000-aaaa-000000000000')
ON CONFLICT DO NOTHING;

-- Assignment Record
INSERT INTO assignments (grievance_id, assigned_to_id, assigned_by_id, status)
VALUES 
    ('eeee1111-eeee-1111-eeee-111111111111', 'cccc0000-cccc-0000-cccc-000000000000', 'bbbb0000-bbbb-0000-bbbb-000000000000', 'pending')
ON CONFLICT DO NOTHING;

-- Audit Logs (Timeline)
INSERT INTO audit_logs (grievance_id, title, description, icon_name)
VALUES 
    ('eeee1111-eeee-1111-eeee-111111111111', 'Complaint Registered', 'Ticket created by citizen.', 'info_outline'),
    ('eeee1111-eeee-1111-eeee-111111111111', 'Assigned to Field Worker', 'Ticket assigned to Amit Patel.', 'assignment_ind_rounded')
ON CONFLICT DO NOTHING;
