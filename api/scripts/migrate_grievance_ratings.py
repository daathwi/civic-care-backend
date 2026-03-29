#!/usr/bin/env python3
"""
Create grievance_resolution_ratings table and backfill from existing data.
Run from api/ directory: uv run python -m scripts.migrate_grievance_ratings
"""
import asyncio
import sys
from pathlib import Path

# Add parent so we can import app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.database import engine


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS grievance_resolution_ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grievance_id UUID NOT NULL REFERENCES grievances(id) ON DELETE CASCADE,
    worker_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_grievance_resolution_ratings_worker_id
    ON grievance_resolution_ratings(worker_id)
"""

BACKFILL = """
INSERT INTO grievance_resolution_ratings (id, grievance_id, worker_id, rating, created_at)
SELECT gen_random_uuid(), g.id, sub.assigned_to_id, g.citizen_rating, NOW()
FROM grievances g
JOIN (
    SELECT DISTINCT ON (grievance_id) grievance_id, assigned_to_id
    FROM assignments
    WHERE status = 'completed' AND assigned_to_id IS NOT NULL
    ORDER BY grievance_id, assigned_at DESC
) sub ON sub.grievance_id = g.id
WHERE g.citizen_rating IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM grievance_resolution_ratings grr WHERE grr.grievance_id = g.id);
"""


async def main():
    async with engine.begin() as conn:
        print("Creating grievance_resolution_ratings table...")
        await conn.execute(text(CREATE_TABLE))
        print("Creating index...")
        await conn.execute(text(CREATE_INDEX))
        print("Backfilling from existing grievances...")
        result = await conn.execute(text(BACKFILL))
        # INSERT doesn't return rowcount easily in asyncpg, but we can check
        print("Done. Table grievance_resolution_ratings is ready.")


if __name__ == "__main__":
    asyncio.run(main())
