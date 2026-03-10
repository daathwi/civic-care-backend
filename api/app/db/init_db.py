"""
Create PostgreSQL enum types (if missing) and all tables on startup.
Safe to run every time: enums use DO $$ ... EXCEPTION, tables use IF NOT EXISTS via SQLAlchemy.
Imports wards from backend_tests/mcd_wards_data.csv if the wards table is empty.
Seeds a default staff user (phone 9999999999, password admin123) when no staff user exists.
"""
import csv
import json
from pathlib import Path

from sqlalchemy import text

from app.core.security import get_password_hash
from app.db.database import Base, engine

# Import all models so they are registered with Base.metadata
import app.models.models  # noqa: F401

# PostgreSQL enum definitions: create if not exists (ignore duplicate_object).
# Each block must be executed as one statement (do not split on ";" inside DO $$ $$).
ENUM_BLOCKS = [
    """
    DO $$ BEGIN
        CREATE TYPE user_role AS ENUM ('citizen', 'fieldManager', 'fieldAssistant', 'admin');
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE worker_status AS ENUM ('onDuty', 'offDuty');
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE complaint_status AS ENUM ('pending', 'assigned', 'inprogress', 'resolved');
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE complaint_priority AS ENUM ('low', 'medium', 'high');
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE media_type AS ENUM ('image', 'video');
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE assignment_status AS ENUM ('pending', 'accepted', 'in_progress', 'completed');
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END $$;
    """,
]


ADD_USERS_WARD_COLUMN = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'ward'
  ) THEN
    ALTER TABLE users ADD COLUMN ward VARCHAR(255);
  END IF;
END $$;
"""

ADD_USERS_ZONE_COLUMN = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'zone'
  ) THEN
    ALTER TABLE users ADD COLUMN zone VARCHAR(255);
  END IF;
END $$;
"""

ADD_USERS_WARD_ID_COLUMN = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'ward_id'
  ) THEN
    ALTER TABLE users ADD COLUMN ward_id UUID REFERENCES wards(id) ON DELETE SET NULL;
  END IF;
END $$;
"""

ADD_USERS_ZONE_ID_COLUMN = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'zone_id'
  ) THEN
    ALTER TABLE users ADD COLUMN zone_id UUID REFERENCES zones(id) ON DELETE SET NULL;
  END IF;
END $$;
"""

ADD_USERS_EMAIL_COLUMN = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'email'
  ) THEN
    ALTER TABLE users ADD COLUMN email VARCHAR(255);
  END IF;
END $$;
"""

ADD_USERS_ADDRESS_COLUMN = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'address'
  ) THEN
    ALTER TABLE users ADD COLUMN address TEXT;
  END IF;
END $$;
"""

ADD_WARDS_REPRESENTATIVE_NAME = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'wards' AND column_name = 'representative_name'
  ) THEN
    ALTER TABLE wards ADD COLUMN representative_name VARCHAR(255);
  END IF;
END $$;
"""

ADD_WARDS_REPRESENTATIVE_PHONE = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'wards' AND column_name = 'representative_phone'
  ) THEN
    ALTER TABLE wards ADD COLUMN representative_phone TEXT[];
  END IF;
END $$;
"""

# Migrate departments.id and referencing columns from VARCHAR to UUID (referenced column must be done first)
ALTER_DEPARTMENTS_ID_AND_FKS_TO_UUID = """
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'departments' AND column_name = 'id'
      AND data_type = 'character varying'
  ) THEN
    ALTER TABLE grievance_categories DROP CONSTRAINT IF EXISTS grievance_categories_dept_id_fkey;
    ALTER TABLE worker_profiles DROP CONSTRAINT IF EXISTS worker_profiles_department_id_fkey;
    DELETE FROM grievance_categories;
    UPDATE worker_profiles SET department_id = NULL;
    DELETE FROM departments;
    ALTER TABLE departments ALTER COLUMN id TYPE UUID USING id::uuid;
    ALTER TABLE grievance_categories ALTER COLUMN dept_id TYPE UUID USING dept_id::uuid;
    ALTER TABLE worker_profiles ALTER COLUMN department_id TYPE UUID USING department_id::uuid;
    ALTER TABLE grievance_categories ADD CONSTRAINT grievance_categories_dept_id_fkey
      FOREIGN KEY (dept_id) REFERENCES departments(id) ON DELETE CASCADE;
    ALTER TABLE worker_profiles ADD CONSTRAINT worker_profiles_department_id_fkey
      FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL;
  END IF;
END $$;
"""

# When departments.id is already UUID but child columns were still varchar (e.g. partial migration)
ALTER_GRIEVANCE_CATEGORIES_DEPT_ID_UUID = """
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'grievance_categories' AND column_name = 'dept_id'
      AND data_type = 'character varying'
  ) THEN
    ALTER TABLE grievance_categories
      ALTER COLUMN dept_id TYPE UUID USING dept_id::uuid;
  END IF;
END $$;
"""

ALTER_WORKER_PROFILES_DEPARTMENT_ID_UUID = """
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'worker_profiles' AND column_name = 'department_id'
      AND data_type = 'character varying'
  ) THEN
    ALTER TABLE worker_profiles
      ALTER COLUMN department_id TYPE UUID USING department_id::uuid;
  END IF;
END $$;
"""

# Add 'admin' to user_role enum (for DBs created before admin was added)
ADD_USER_ROLE_ADMIN = """
DO $$ BEGIN
  ALTER TYPE user_role ADD VALUE 'admin';
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;
"""

# Migrate grievance status enum from old values to: pending, assigned, inprogress, resolved
MIGRATE_COMPLAINT_STATUS_ENUM = """
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_enum e
    JOIN pg_type t ON e.enumtypid = t.oid
    WHERE t.typname = 'complaint_status' AND e.enumlabel = 'incompleteUnassigned'
  ) THEN
    CREATE TYPE complaint_status_new AS ENUM ('pending', 'assigned', 'inprogress', 'resolved');
    ALTER TABLE grievances ALTER COLUMN status DROP DEFAULT;
    ALTER TABLE grievances ALTER COLUMN status TYPE complaint_status_new USING (
      CASE status::text
        WHEN 'incompleteUnassigned' THEN 'pending'::complaint_status_new
        WHEN 'incompleteAssigned' THEN 'assigned'::complaint_status_new
        WHEN 'ongoing' THEN 'inprogress'::complaint_status_new
        WHEN 'completed' THEN 'resolved'::complaint_status_new
        ELSE 'pending'::complaint_status_new
      END
    );
    ALTER TABLE grievances ALTER COLUMN status SET DEFAULT 'pending'::complaint_status_new;
    DROP TYPE complaint_status;
    ALTER TYPE complaint_status_new RENAME TO complaint_status;
    ALTER TABLE grievances ALTER COLUMN status SET DEFAULT 'pending'::complaint_status;
  END IF;
END $$;
"""

ADD_GRIEVANCES_IS_SENSITIVE_COLUMN = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'grievances' AND column_name = 'is_sensitive'
  ) THEN
    ALTER TABLE grievances ADD COLUMN is_sensitive BOOLEAN DEFAULT FALSE;
  END IF;
END $$;
"""

ADD_GRIEVANCES_CITIZEN_RATING_COLUMN = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'grievances' AND column_name = 'citizen_rating'
  ) THEN
    ALTER TABLE grievances ADD COLUMN citizen_rating INTEGER;
  END IF;
END $$;
"""

ADD_COMPLAINT_STATUS_ESCALATED = """
DO $$ BEGIN
  ALTER TYPE complaint_status ADD VALUE 'escalated';
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;
"""


ADD_INTERNAL_MESSAGES_CONVERSATION_ID_COLUMN = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'internal_messages' AND column_name = 'conversation_id'
  ) THEN
    ALTER TABLE internal_messages ADD COLUMN conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE;
  END IF;
END $$;
"""

ADD_CONVERSATIONS_GRIEVANCE_ID_COLUMN = """
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'conversations' AND column_name = 'grievance_id'
  ) THEN
    ALTER TABLE conversations ADD COLUMN grievance_id UUID REFERENCES grievances(id) ON DELETE CASCADE;
  END IF;
END $$;
"""

ALTER_INTERNAL_MESSAGES_RECEIVER_ID_NULLABLE = "ALTER TABLE internal_messages ALTER COLUMN receiver_id DROP NOT NULL;"


# Path to MCD wards CSV (testing/backend_tests/mcd_wards_data.csv)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
_TESTING_DIR = _BACKEND_DIR.parent.parent
MCD_WARDS_CSV_PATH = _TESTING_DIR / "backend_tests" / "mcd_wards_data.csv"

# Delhi MCD zones (12 zones) — seeded on startup so they always exist
DELHI_ZONES = [
    ("CENTRE", "CE"),
    ("SOUTH", "SO"),
    ("WEST", "WE"),
    ("NAJAFGARH", "NAJ"),
    ("ROHINI", "ROH"),
    ("CIVIL LINES", "CL"),
    ("KAROL BAGH", "KB"),
    ("SP CITY", "SPC"),
    ("KESHAVPURAM", "KES"),
    ("NARELA", "NAR"),
    ("SHAHDARA NORTH", "SN"),
    ("SHAHDARA SOUTH", "SS"),
]

# Departments — seeded on startup with fixed UUIDs (id, name, short_code, primary_color, icon, manager_title, assistant_title, jurisdiction_label)
import uuid as _uuid

_DEPT_SANITATION = _uuid.UUID("a1000001-0001-4000-8000-000000000001")
_DEPT_ENGINEERING = _uuid.UUID("a1000002-0002-4000-8000-000000000002")
_DEPT_HEALTH = _uuid.UUID("a1000003-0003-4000-8000-000000000003")
_DEPT_HORTICULTURE = _uuid.UUID("a1000004-0004-4000-8000-000000000004")

SEED_DEPARTMENTS = [
    (_DEPT_SANITATION, "Sanitation and waste", "SW", "0xFF00796B", "delete_outline_rounded", "Sanitary Inspector", "Field Worker", "Ward"),
    (_DEPT_ENGINEERING, "Engineering", "ENG", "0xFF1976D2", "construction_rounded", "Assistant Engineer", "Junior Engineer", "Cluster of wards"),
    (_DEPT_HEALTH, "Public Health", "PH", "0xFF43A047", "health_and_safety_rounded", "Public Health Inspector", "Health Worker", "Ward"),
    (_DEPT_HORTICULTURE, "Horticulture", "HTC", "0xFF7CB342", "nature_rounded", "Section Officer", "Gardener", "Ward"),
]

# Default admin/staff user for admin dashboard (seeded when no staff user exists)
_ADMIN_USER_ID = _uuid.UUID("b2000001-0001-4000-8000-000000000001")
SEED_ADMIN_PHONE = "9999999999"
SEED_ADMIN_PASSWORD = "admin123"
SEED_ADMIN_NAME = "Admin"

# Grievance categories per department (dept_id, name). IDs are stable via uuid5.
_CATEGORY_NS = _uuid.uuid5(_uuid.NAMESPACE_DNS, "civiccare.grievance_categories")

SEED_GRIEVANCE_CATEGORIES = [
    (_DEPT_SANITATION, "Overflowing bin"),
    (_DEPT_SANITATION, "Carcass (Animal Dead Body)"),
    (_DEPT_SANITATION, "Industrial Waste"),
    (_DEPT_SANITATION, "Litter"),
    (_DEPT_ENGINEERING, "Potholes"),
    (_DEPT_ENGINEERING, "Deep Cracks"),
    (_DEPT_ENGINEERING, "Missing Manhole Caps"),
    (_DEPT_ENGINEERING, "Water logging"),
    (_DEPT_ENGINEERING, "Broken Public Infra"),
    (_DEPT_ENGINEERING, "Live Wire"),
    (_DEPT_ENGINEERING, "Broken Pipes"),
    (_DEPT_ENGINEERING, "Non Functional Streetlights"),
    (_DEPT_ENGINEERING, "Dirty Community Centers"),
    (_DEPT_ENGINEERING, "Non functional cremation furnaces"),
    (_DEPT_ENGINEERING, "Public Toilets"),
    (_DEPT_HEALTH, "Stagnant water"),
    (_DEPT_HEALTH, "Dengue Risk"),
    (_DEPT_HEALTH, "Stray animal agression"),
    (_DEPT_HORTICULTURE, "Fallen Trees"),
    (_DEPT_HORTICULTURE, "Overgrown grass"),
    (_DEPT_HORTICULTURE, "Dry plants"),
]


def _load_wards_csv(path: Path) -> list[dict]:
    """Load ward rows from CSV. Uses large field size for polygon_geojson."""
    csv.field_size_limit(10**7)
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


async def _import_wards_from_csv(conn) -> None:
    """If wards table is empty and CSV exists, insert wards only. Does not touch zones table."""
    count = (await conn.execute(text("SELECT COUNT(*) FROM wards"))).scalar() or 0
    if count > 0:
        return
    if not MCD_WARDS_CSV_PATH.exists():
        return
    rows = _load_wards_csv(MCD_WARDS_CSV_PATH)
    if not rows:
        return
    # Only insert wards whose zone_id already exists (do not insert/update zones)
    zone_rows = (await conn.execute(text("SELECT id FROM zones"))).fetchall()
    existing_zone_ids = {str(r[0]) for r in zone_rows}
    rows = [r for r in rows if str(r.get("zone_id", "")).strip() in existing_zone_ids]
    if not rows:
        return
    await conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_wards_zone_number
            ON wards (zone_id, number)
            """
        )
    )
    for row in rows:
        try:
            geojson_obj = json.loads(row["polygon_geojson"]) if row.get("polygon_geojson") else None
        except (json.JSONDecodeError, TypeError):
            geojson_obj = None
        # asyncpg JSONB encoder expects a string, not a list/dict
        polygon_geojson_param = json.dumps(geojson_obj) if geojson_obj is not None else None
        phones = row.get("representative_phone") or ""
        rep_phones = [p.strip() for p in str(phones).split(",") if p.strip()]
        await conn.execute(
            text(
                """
                INSERT INTO wards (id, zone_id, name, number, polygon_geojson, representative_name, representative_phone)
                VALUES (gen_random_uuid(), :zone_id, :name, :number, :polygon_geojson, :representative_name, :representative_phone)
                ON CONFLICT (zone_id, number) DO NOTHING
                """
            ),
            {
                "zone_id": row["zone_id"],
                "name": row["name"],
                "number": int(row["number"]),
                "polygon_geojson": polygon_geojson_param,
                "representative_name": (row.get("representative_name") or "").strip() or None,
                "representative_phone": rep_phones,
            },
        )


async def init_db() -> None:
    """Create enum types and all tables. Idempotent."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        for block in ENUM_BLOCKS:
            await conn.execute(text(block.strip()))
        await conn.execute(text(ADD_USER_ROLE_ADMIN.strip()))
        await conn.run_sync(Base.metadata.create_all)
        # Ensure seeded admin user has role 'admin' (idempotent)
        await conn.execute(
            text(
                "UPDATE users SET role = 'admin' WHERE id = :id"
            ),
            {"id": str(_ADMIN_USER_ID)},
        )
        await conn.execute(text(ADD_USERS_WARD_COLUMN.strip()))
        await conn.execute(text(ADD_USERS_ZONE_COLUMN.strip()))
        await conn.execute(text(ADD_USERS_WARD_ID_COLUMN.strip()))
        await conn.execute(text(ADD_USERS_ZONE_ID_COLUMN.strip()))
        await conn.execute(text(ADD_USERS_EMAIL_COLUMN.strip()))
        await conn.execute(text(ADD_USERS_ADDRESS_COLUMN.strip()))
        await conn.execute(text(ADD_WARDS_REPRESENTATIVE_NAME.strip()))
        await conn.execute(text(ADD_WARDS_REPRESENTATIVE_PHONE.strip()))
        await conn.execute(text(ALTER_DEPARTMENTS_ID_AND_FKS_TO_UUID.strip()))
        await conn.execute(text(ALTER_GRIEVANCE_CATEGORIES_DEPT_ID_UUID.strip()))
        await conn.execute(text(ALTER_WORKER_PROFILES_DEPARTMENT_ID_UUID.strip()))
        await conn.execute(text(MIGRATE_COMPLAINT_STATUS_ENUM.strip()))
        await conn.execute(text(ADD_COMPLAINT_STATUS_ESCALATED.strip()))
        await conn.execute(text(ADD_GRIEVANCES_IS_SENSITIVE_COLUMN.strip()))
        await conn.execute(text(ADD_GRIEVANCES_CITIZEN_RATING_COLUMN.strip()))
        await conn.execute(text(ADD_INTERNAL_MESSAGES_CONVERSATION_ID_COLUMN.strip()))
        await conn.execute(text(ADD_CONVERSATIONS_GRIEVANCE_ID_COLUMN.strip()))
        await conn.execute(text(ALTER_INTERNAL_MESSAGES_RECEIVER_ID_NULLABLE.strip()))
        # Seed zones only when empty
        zones_count = (await conn.execute(text("SELECT COUNT(*) FROM zones"))).scalar() or 0
        if zones_count == 0:
            for name, code in DELHI_ZONES:
                await conn.execute(
                    text(
                        """
                        INSERT INTO zones (id, name, code)
                        VALUES (gen_random_uuid(), :name, :code)
                        """
                    ),
                    {"name": name, "code": code},
                )
        # Seed departments only when empty
        depts_count = (await conn.execute(text("SELECT COUNT(*) FROM departments"))).scalar() or 0
        if depts_count == 0:
            for (
                dept_id,
                name,
                short_code,
                primary_color,
                icon,
                manager_title,
                assistant_title,
                jurisdiction_label,
            ) in SEED_DEPARTMENTS:
                await conn.execute(
                    text(
                        """
                        INSERT INTO departments (id, name, short_code, primary_color, icon, manager_title, assistant_title, jurisdiction_label)
                        VALUES (:id, :name, :short_code, :primary_color, :icon, :manager_title, :assistant_title, :jurisdiction_label)
                        """
                    ),
                    {
                        "id": str(dept_id),
                        "name": name,
                        "short_code": short_code,
                        "primary_color": primary_color,
                        "icon": icon,
                        "manager_title": manager_title,
                        "assistant_title": assistant_title,
                        "jurisdiction_label": jurisdiction_label,
                    },
                )
        # Seed grievance categories only when empty
        categories_count = (await conn.execute(text("SELECT COUNT(*) FROM grievance_categories"))).scalar() or 0
        if categories_count == 0:
            for dept_id, name in SEED_GRIEVANCE_CATEGORIES:
                cat_id = _uuid.uuid5(_CATEGORY_NS, f"{dept_id}:{name}")
                await conn.execute(
                    text(
                        """
                        INSERT INTO grievance_categories (id, dept_id, name)
                        VALUES (:id, :dept_id, :name)
                        """
                    ),
                    {"id": str(cat_id), "dept_id": str(dept_id), "name": name},
                )
        await _import_wards_from_csv(conn)

        # Seed default admin user for admin dashboard when no admin/staff user exists
        staff_count = (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM users WHERE role IN ('fieldManager', 'fieldAssistant', 'admin')"
                )
            )
        ).scalar() or 0
        if staff_count == 0:
            password_hash = get_password_hash(SEED_ADMIN_PASSWORD)
            await conn.execute(
                text(
                    """
                    INSERT INTO users (id, password_hash, name, phone, role)
                    VALUES (:id, :password_hash, :name, :phone, 'admin')
                    """
                ),
                {
                    "id": str(_ADMIN_USER_ID),
                    "password_hash": password_hash,
                    "name": SEED_ADMIN_NAME,
                    "phone": SEED_ADMIN_PHONE,
                },
            )
            # WorkerProfile so the user appears in workers list and has full staff capabilities
            await conn.execute(
                text(
                    """
                    INSERT INTO worker_profiles (user_id, designation_title, department_id, tasks_completed, tasks_active)
                    VALUES (:user_id, 'Admin', :department_id, 0, 0)
                    """
                ),
                {
                    "user_id": str(_ADMIN_USER_ID),
                    "department_id": str(_DEPT_SANITATION),
                },
            )
