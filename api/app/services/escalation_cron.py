"""Cron job to escalate overdue grievances (older than 48 hours)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.models.models import AuditLog, Grievance

# Grievances older than this are escalated (48 hours)
ESCALATION_HOURS = 48


async def escalate_overdue_grievances() -> int:
    """
    Escalate grievances that are still pending/assigned/inprogress after 48 hours.
    Returns the number of grievances escalated.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ESCALATION_HOURS)

    async with AsyncSessionLocal() as db:
        # Find grievances to escalate
        result = await db.execute(
            select(Grievance.id).where(
                Grievance.status.in_(["pending", "assigned", "inprogress"]),
                Grievance.created_at < cutoff,
            )
        )
        ids = [row[0] for row in result]

        if not ids:
            return 0

        # Update status
        await db.execute(
            update(Grievance)
            .where(Grievance.id.in_(ids))
            .values(status="escalated", updated_at=datetime.now(timezone.utc))
        )

        # Add audit log for each escalated grievance
        for gid in ids:
            db.add(
                AuditLog(
                    grievance_id=gid,
                    title="Escalated",
                    description="Auto-escalated: grievance exceeded 48-hour SLA without resolution.",
                    icon_name="report_problem",
                    actor_id=None,
                )
            )

        await db.commit()
    return len(ids)
