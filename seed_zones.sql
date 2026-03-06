-- Delhi MCD Zones (12 zones)
-- Run after schema_definitions_v2.sql. Idempotent: use ON CONFLICT so safe to re-run.

INSERT INTO zones (name, code)
VALUES
    ('CENTRE', 'CE'),
    ('SOUTH', 'SO'),
    ('WEST', 'WE'),
    ('NAJAFGARH', 'NAJ'),
    ('ROHINI', 'ROH'),
    ('CIVIL LINES', 'CL'),
    ('KAROL BAGH', 'KB'),
    ('SP CITY', 'SPC'),
    ('KESHAVPURAM', 'KES'),
    ('NARELA', 'NAR'),
    ('SHAHDARA NORTH', 'SN'),
    ('SHAHDARA SOUTH', 'SS')
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name;
