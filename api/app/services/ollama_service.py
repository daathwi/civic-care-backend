import uuid
import json
import logging
import httpx
from typing import Tuple
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.config import settings
from app.models.models import User, WorkerProfile, Grievance, GrievanceCategory, Assignment, AuditLog

logger = logging.getLogger(__name__)

async def is_spam(
    title: str | None, 
    description: str | None,
    department: str | None = None,
    category: str | None = None
) -> bool:
    """
    Check if a grievance is spam using the local Ollama instance.
    Returns True if the AI identifies it as spam, False otherwise.
    """
    if not title and not description:
        return True

    prompt = (
        "Analyze the following civic grievance. Is it spam, nonsensical, or a valid civic issue? "
        "Consider the context: does this issue make sense for the selected department and category? "
        "Respond with EXACTLY one word: 'spam' or 'valid'.\n\n"
        f"Department: {department or 'N/A'}\n"
        f"Category: {category or 'N/A'}\n"
        f"Title: {title or 'N/A'}\n"
        f"Description: {description or 'N/A'}"
    )

    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,  # Deterministic response
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            answer = data.get("response", "").strip().lower()
            
            # Extract the first word in case the model rambles
            answer_word = answer.split()[0].strip().replace(".", "").replace(",", "")
            
            logger.info("Ollama spam check response: %s (first word: %s)", answer, answer_word)
            return "spam" in answer_word
            
    except Exception as e:
        logger.error("Failed to check spam with Ollama: %s", str(e))
        # Default to False in case of AI failure to avoid blocking valid users
        return False

async def recommend_worker(db: AsyncSession, grievance_id: uuid.UUID) -> Tuple[uuid.UUID | None, str | None]:
    """
    AI-driven worker recommendation based on experience, workload, and rating.
    Analyzes on-duty workers in the grievance's department and recommends the best match.
    Updates the grievance with the recommended worker_id and reason.
    """
    try:
        # 1. Fetch Grievance with Category & Dept
        result = await db.execute(
            select(Grievance)
            .options(selectinload(Grievance.category).selectinload(GrievanceCategory.department))
            .where(Grievance.id == grievance_id)
        )
        g = result.scalar_one_or_none()
        if not g or not g.category:
            logger.warning("Grievance %s not found for AI recommendation", grievance_id)
            return None, "Grievance or category not found."

        dept_id = g.category.dept_id

        # 2. Fetch onDuty workers in this department
        # First attempt: Workers in the SAME ward
        worker_result = await db.execute(
            select(User)
            .join(WorkerProfile, User.id == WorkerProfile.user_id)
            .where(
                WorkerProfile.department_id == dept_id,
                WorkerProfile.ward_id == g.ward_id,
                User.role == "fieldAssistant"
            )
            .options(selectinload(User.worker_profile))
        )
        workers = worker_result.scalars().all()

        if not workers:
            # Second attempt: Any on-duty worker in the department (wider search)
            logger.info("No workers in ward %s, searching department-wide", g.ward_id)
            worker_result = await db.execute(
                select(User)
                .join(WorkerProfile, User.id == WorkerProfile.user_id)
                .where(
                    WorkerProfile.department_id == dept_id,
                    User.role == "fieldAssistant"
                )
                .options(selectinload(User.worker_profile))
            )
            workers = worker_result.scalars().all()

        if not workers:
            logger.info("No workers available in department %s for grievance %s", dept_id, grievance_id)
            g.ai_suggestion_reason = "No available workers found for recommendation."
            await db.commit()
            return None, "No workers available in this department."

        # 3. Prepare worker data for AI
        worker_list_str = ""
        for w in workers:
            wp = w.worker_profile
            worker_list_str += (
                f"- ID: {w.id}\n"
                f"  Name: {w.name}\n"
                f"  Rating: {wp.rating or 0.0} ({wp.ratings_count or 0} reviews)\n"
                f"  Active Tasks: {wp.tasks_active or 0}\n"
                f"  Completed Tasks (Experience): {wp.tasks_completed or 0}\n\n"
            )

        print(worker_list_str)

        # 4. Prompt AI
        prompt = (
            "You are CivicCare's intelligent task dispatcher.\n\n"
            "## PRIORITY RULES (strictly in this order)\n"
            "1. AVAILABILITY (HIGHEST PRIORITY) — Always prefer the worker with the LOWEST Active Tasks count. "
            "A worker with 0 active tasks beats a worker with 2 active tasks, regardless of rating or experience.\n"
            "2. SKILL MATCH — If two workers have equal Active Tasks, prefer the one whose department or task history matches this grievance type.\n"
            "3. PERFORMANCE — If still tied, prefer the higher Rating.\n"
            "4. EXPERIENCE — If still tied, prefer more Completed Tasks.\n\n"
            "## GRIEVANCE\n"
            f"Title: {g.title}\n"
            f"Description: {g.description}\n\n"
            "## ON-DUTY WORKERS\n"
            f"{worker_list_str}\n\n"
            "## DECISION PROCESS\n"
            "Step 1: Sort all workers by Active Tasks (ascending). Identify the worker(s) with the MINIMUM active task count.\n"
            "Step 2: If only one worker has the minimum, SELECT that worker immediately.\n"
            "Step 3: If multiple workers share the minimum active task count, apply rules 2→3→4 as tiebreakers.\n"
            "Step 4: You MUST always select exactly one worker. Never leave unassigned.\n\n"
            "## OUTPUT FORMAT\n"
            "Respond ONLY with a valid JSON object. No markdown. No text outside the JSON.\n"
            "{\n"
            '  "worker_id": "<copy the exact uuid from the worker list — do not paraphrase or shorten it>",\n'
            '  "reason": "<max 15 words explaining why this specific worker was chosen over others>"\n'
            "}\n"
        )

        payload = {
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2}
        }

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            raw_response = data.get("response", "{}")
            
            try:
                ai_data = json.loads(raw_response)
                print(ai_data)
            except json.JSONDecodeError:
                # If model rambles outside JSON, try to extract it
                import re
                match = re.search(r'\{.*\}', raw_response, re.DOTALL)
                if match:
                    ai_data = json.loads(match.group())
                else:
                    raise ValueError("Could not parse JSON from AI response")

            worker_id_str = ai_data.get("worker_id")
            reason = ai_data.get("reason", "Optimized assignment based on performance and availability.")

            if worker_id_str:
                worker_id = uuid.UUID(worker_id_str)
                w = next((w for w in workers if w.id == worker_id), None)
                if w:
                    g.ai_suggested_worker_id = worker_id
                    g.ai_suggestion_reason = reason
                    g.status = "assigned"
                    g.updated_at = datetime.now(timezone.utc)
                    
                    assignment = Assignment(
                        grievance_id=g.id,
                        assigned_to_id=worker_id,
                    )
                    db.add(assignment)
                    
                    if w.worker_profile:
                        w.worker_profile.tasks_active = (w.worker_profile.tasks_active or 0) + 1
                        
                    db.add(AuditLog(
                        grievance_id=g.id,
                        title="Auto-Assigned by AI",
                        description=f"AI assigned ticket to {w.name}. Reason: {reason}",
                        icon_name="auto_awesome_rounded",
                    ))
                    
                    await db.commit()
                    logger.info("AI auto-assigned worker %s for grievance %s", worker_id, grievance_id)
                    return worker_id, reason
                else:
                    logger.warning("AI suggested invalid worker_id %s for grievance %s", worker_id_str, grievance_id)

    except Exception as e:
        logger.error("Failed to get AI recommendation: %s", str(e))
    
    return None, None
async def recommend_worker_task(grievance_id: uuid.UUID):
    """
    Background task wrapper for recommend_worker.
    Creates its own DB session to avoid issues with closing the main request session.
    """
    from app.db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await recommend_worker(db, grievance_id)
