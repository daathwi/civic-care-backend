"""Idempotent DDL for tables added after initial deploy."""

import logging

from sqlalchemy import text

from app.db.database import engine
from app.models.models import CivicImpactScoreSnapshot, CisSchedulerState

logger = logging.getLogger(__name__)


async def ensure_civic_impact_score_snapshots_table() -> None:
    """Create `civic_impact_score_snapshots` if it does not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: CivicImpactScoreSnapshot.__table__.create(sync_conn, checkfirst=True)
        )
    logger.info("Table civic_impact_score_snapshots is present")


async def ensure_cis_scheduler_and_user_last_cis() -> None:
    """Create `cis_scheduler_state`, add `users.last_updated_cis` if missing."""
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: CisSchedulerState.__table__.create(sync_conn, checkfirst=True)
        )
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_updated_cis TIMESTAMPTZ NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS cis_score NUMERIC(6, 2) NULL"
            )
        )
    logger.info("CIS scheduler state table and users.last_updated_cis are present")


async def ensure_department_sdg_and_description() -> None:
    """Add optional SDG and description columns to departments if missing."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE departments ADD COLUMN IF NOT EXISTS sdg VARCHAR(100) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE departments ADD COLUMN IF NOT EXISTS description TEXT NULL"
            )
        )
    logger.info("Department SDG and description columns are present")
