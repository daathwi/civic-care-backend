import uuid
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Grievance, Ward

async def get_ward_maxima(db: AsyncSession, ward_ids: list[uuid.UUID]):
    """Fetch max age and max netvotes for specified wards."""
    if not ward_ids:
        return {}
    
    # Max age per ward
    age_query = (
        select(Grievance.ward_id, func.max(func.extract('epoch', datetime.now(timezone.utc) - Grievance.created_at)))
        .where(Grievance.ward_id.in_(ward_ids))
        .group_by(Grievance.ward_id)
    )
    # Max netvotes per ward
    votes_query = (
        select(Grievance.ward_id, func.max(Grievance.upvotes_count - Grievance.downvotes_count))
        .where(Grievance.ward_id.in_(ward_ids))
        .group_by(Grievance.ward_id)
    )
    
    age_res = await db.execute(age_query)
    votes_res = await db.execute(votes_query)
    
    maxima = {wid: {"max_age": 1.0, "max_netvotes": 1.0} for wid in ward_ids}
    for wid, val in age_res:
        maxima[wid]["max_age"] = float(val) if val and val > 0 else 1.0
    for wid, val in votes_res:
        maxima[wid]["max_netvotes"] = float(val) if val and val > 0 else 1.0
        
    return maxima

def calculate_eps(g: Grievance, max_age: float, max_netvotes: float):
    """Calculate the 4-component composite Escalation Priority Score (EPS)."""
    # 1. Escalation Age (30%)
    age_seconds = (datetime.now(timezone.utc) - g.created_at).total_seconds()
    age_score = (age_seconds / max_age) * 30.0 if max_age > 0 else 0.0
    age_score = min(age_score, 30.0)
    
    # 2. Reopen Frequency (25%)
    # Max count = 3 (1st=0, 2nd=12.5, 3rd=25)
    reopen_score = (min(g.reopen_count or 0, 3) / 3.0) * 25.0
    
    # 3. Netvotes Impact (25%)
    net_votes = g.upvotes_count - g.downvotes_count
    votes_score = (net_votes / max_netvotes) * 25.0 if max_netvotes > 0 else 0.0
    votes_score = max(0.0, min(votes_score, 25.0))
    
    # 4. Grievance Severity (20%)
    # High=20, Medium=12, Low=6
    severity_map = {"high": 20.0, "medium": 12.0, "low": 6.0}
    severity_score = severity_map.get((g.priority or "medium").lower(), 12.0)
    
    total = age_score + reopen_score + votes_score + severity_score
    
    return {
        "total": round(total, 2),
        "breakdown": {
            "age": round(age_score, 2),
            "reopen": round(reopen_score, 2),
            "votes": round(votes_score, 2),
            "severity": round(severity_score, 2)
        }
    }
