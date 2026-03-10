from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, and_
from app.db.database import get_db
from app.models.models import Grievance, GrievanceCategory, Department
from datetime import timedelta
from typing import List, Dict, Any

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/departments")
async def get_department_analytics(db: AsyncSession = Depends(get_db)):
    # SLA threshold (48 hours)
    SLA_HOURS = 48
    
    # Base query to join Department -> Category -> Grievance
    # We use func.coalesce to handle None values from departments with no grievances
    query = (
        select(
            Department.id,
            Department.name,
            func.count(Grievance.id).label("total"),
            func.sum(case((Grievance.status == 'resolved', 1), else_=0)).label("resolved"),
            func.sum(case((and_(Grievance.id != None, Grievance.status != 'resolved'), 1), else_=0)).label("pending"),
            func.sum(case((and_(Grievance.status == 'resolved', Grievance.updated_at - Grievance.created_at > timedelta(hours=SLA_HOURS)), 1), else_=0)).label("sla_breaches_resolved"),
            func.sum(case((and_(Grievance.status != 'resolved', func.now() - Grievance.created_at > timedelta(hours=SLA_HOURS)), 1), else_=0)).label("sla_breaches_pending"),
            func.sum(case((Grievance.reopen_count > 0, 1), else_=0)).label("repeat_complaints"),
            func.sum(func.coalesce(Grievance.reopen_count, 0)).label("total_repeat_count"),
            func.sum(case((Grievance.status == 'escalated', 1), else_=0)).label("escalated")
        )
        .select_from(Department)
        .join(GrievanceCategory, Department.id == GrievanceCategory.dept_id, isouter=True)
        .join(Grievance, GrievanceCategory.id == Grievance.category_id, isouter=True)
        .group_by(Department.id, Department.name)
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    analytics = []
    for row in rows:
        t = row.total
        r = row.resolved
        p = row.pending
        # Breaches (Bad)
        bh = row.sla_breaches_resolved
        bp = row.sla_breaches_pending
        
        # S is now exclusively "Resolved within SLA"
        s_count = r - bh
        
        rc = row.repeat_complaints
        sum_ri = row.total_repeat_count
        e = row.escalated
        
        # Operational Efficiency
        resolution_rate = r / t if t > 0 else 0
        pending_score = 1 - (p / t) if t > 0 else 1
        
        # Service Velocity (SLA Adherence)
        # Using S/R to measure timeliness of completed work
        sla_rate = s_count / r if r > 0 else 1.0
        
        # Quality & Escalation
        recurrence_rate = rc / t if t > 0 else 0
        average_recurrence = sum_ri / rc if rc > 0 else 0
        recurrence_score = 1 - (sum_ri / r) if r > 0 else (1 if sum_ri == 0 else 0)
        
        # Escalation Mitigation (1 - E/T)
        escalation_rate = e / t if t > 0 else 0
        escalation_score = 1 - escalation_rate
        
        # Composite DPI
        dpi = (
            0.30 * resolution_rate +
            0.25 * sla_rate +
            0.20 * pending_score +
            0.15 * max(0, recurrence_score) + 
            0.10 * escalation_score
        ) * 100
        
        # Performance Classification
        performance = "Excellent"
        if dpi < 60: performance = "Critical"
        elif dpi < 70: performance = "Poor"
        elif dpi < 80: performance = "Average"
        elif dpi < 90: performance = "Good"
        
        analytics.append({
            "id": str(row.id),
            "name": row.name,
            "metrics": {
                "total": t,
                "resolved": r,
                "pending": p,
                "sla_resolved": s_count,
                "repeat_complaints": rc,
                "total_repeat_count": int(sum_ri),
                "escalated": e
            },
            "scores": {
                "resolution_rate": round(resolution_rate, 4),
                "pending_score": round(pending_score, 4),
                "sla_rate": round(sla_rate, 4),
                "recurrence_rate": round(recurrence_rate, 4),
                "average_recurrence": round(average_recurrence, 2),
                "recurrence_score": round(max(0, recurrence_score), 4),
                "escalation_rate": round(escalation_rate, 4),
                "escalation_score": round(escalation_score, 4),
                "dpi": round(dpi, 2)
            },
            "performance": performance
        })
        
    # Sort by DPI descending
    analytics.sort(key=lambda x: x["scores"]["dpi"], reverse=True)
    
    return analytics

@router.get("/wards")
async def get_ward_analytics():
    return {"message": "Ward analytics placeholder"}

@router.get("/zones")
async def get_zone_analytics():
    return {"message": "Zone analytics placeholder"}

@router.get("/sustainability")
async def get_sustainability_analytics():
    return {"message": "Sustainability analytics placeholder"}
