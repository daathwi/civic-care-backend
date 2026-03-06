-- Sample Data to Verify MCD Hierarchy Logic
-- This script populates the schema with data from the Engineering and Sanitation departments

-- 1. Bases
INSERT INTO departments (name) VALUES ('Engineering'), ('Sanitation');
INSERT INTO zones (name, code) VALUES ('North Zone', 'NZ01');
INSERT INTO wards (zone_id, name, number) 
SELECT id, 'Ward A', 1 FROM zones WHERE code = 'NZ01';

-- 2. Designations
INSERT INTO designations (dept_id, title, hierarchy_level) 
SELECT id, 'Deputy Commissioner', 1 FROM departments WHERE name = 'Engineering'; -- Shared level

INSERT INTO designations (dept_id, title, hierarchy_level) 
SELECT id, 'Superintending Engineer', 2 FROM departments WHERE name = 'Engineering';
INSERT INTO designations (dept_id, title, hierarchy_level) 
SELECT id, 'Executive Engineer', 3 FROM departments WHERE name = 'Engineering';
INSERT INTO designations (dept_id, title, hierarchy_level) 
SELECT id, 'Assistant Engineer', 4 FROM departments WHERE name = 'Engineering';
INSERT INTO designations (dept_id, title, hierarchy_level) 
SELECT id, 'Junior Engineer', 5 FROM departments WHERE name = 'Engineering';

-- 3. Officers (Engineering Chain)
DO $$
DECLARE
    dept_id UUID;
    zone_id UUID;
    dc_id UUID;
    se_id UUID;
    ee_id UUID;
    ae_id UUID;
    je_id UUID;
BEGIN
    SELECT id INTO dept_id FROM departments WHERE name = 'Engineering';
    SELECT id INTO zone_id FROM zones WHERE code = 'NZ01';

    -- Level 1: DC
    INSERT INTO officers (name, email, password_hash, designation_id, zone_id)
    VALUES ('Dr. DC Smith', 'dc@mcd.gov.in', 'hashed_pwd', (SELECT id FROM designations WHERE title = 'Deputy Commissioner'), zone_id)
    RETURNING id INTO dc_id;

    -- Level 2: SE
    INSERT INTO officers (name, email, password_hash, designation_id, zone_id, supervisor_id)
    VALUES ('Mr. SE Brown', 'se@mcd.gov.in', 'hashed_pwd', (SELECT id FROM designations WHERE title = 'Superintending Engineer'), zone_id, dc_id)
    RETURNING id INTO se_id;

    -- Level 3: EE
    INSERT INTO officers (name, email, password_hash, designation_id, zone_id, supervisor_id)
    VALUES ('Ms. EE Green', 'ee@mcd.gov.in', 'hashed_pwd', (SELECT id FROM designations WHERE title = 'Executive Engineer'), zone_id, se_id)
    RETURNING id INTO ee_id;

    -- Level 4: AE
    INSERT INTO officers (name, email, password_hash, designation_id, zone_id, supervisor_id)
    VALUES ('Mr. AE White', 'ae@mcd.gov.in', 'hashed_pwd', (SELECT id FROM designations WHERE title = 'Assistant Engineer'), zone_id, ee_id)
    RETURNING id INTO ae_id;

    -- Level 5: JE
    INSERT INTO officers (name, email, password_hash, designation_id, zone_id, supervisor_id)
    VALUES ('Ms. JE Black', 'je@mcd.gov.in', 'hashed_pwd', (SELECT id FROM designations WHERE title = 'Junior Engineer'), zone_id, ae_id)
    RETURNING id INTO je_id;

    RAISE NOTICE 'Engineering hierarchy created: DC -> SE -> EE -> AE -> JE';
END $$;
