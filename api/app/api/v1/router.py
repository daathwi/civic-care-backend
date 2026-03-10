from fastapi import APIRouter

from app.api.v1.endpoints import auth, grievances, workers, attendance, wards, uploads, chat, internal_messages, analytics

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(grievances.router)
api_router.include_router(workers.router)
api_router.include_router(attendance.router)
api_router.include_router(wards.router)
api_router.include_router(uploads.router)
api_router.include_router(chat.router)
api_router.include_router(internal_messages.router, prefix="/internal-messages", tags=["internal-messages"])
api_router.include_router(analytics.router)
