import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.api.v1.router import api_router
from app.middleware import RequestResponseLoggerMiddleware

STATIC_DIR = Path(__file__).resolve().parent / "app" / "static"
PHOTOS_DIR = Path(__file__).resolve().parent / "photos"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

logger = logging.getLogger(__name__)


def _get_network_ip() -> str | None:
    """Return this machine's LAN IP (e.g. 192.168.1.x) or None if not available."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Print URLs to console (network URL works only if server was started with --host 0.0.0.0)
    port = os.environ.get("PORT", "8000")
    network_ip = _get_network_ip()
    print("\n" + "=" * 60)
    print("  Backend running")
    print("  Local:   http://127.0.0.1:%s" % port)
    print("  Local:   http://localhost:%s" % port)
    if network_ip:
        print("  Network: http://%s:%s" % (network_ip, port))
    else:
        print("  Network: (could not detect LAN IP)")
    print("  (Network URL works only if started with --host 0.0.0.0)")
    print("  Run: uv run start   or   uvicorn main:app --reload --host 0.0.0.0")
    print("=" * 60 + "\n")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
CivicCare API for MCD Delhi grievance management.

## Roles & access
- **citizen**: Register, login (phone+password), create grievance, vote, comment, view grievances.
- **fieldAssistant**: Login (user_id+password), update grievance (PATCH), attendance (clock-in/out), view data.
- **fieldManager**: Login (user_id+password), assign field assistants to grievances, create field assistants/zones/wards/departments/categories; cannot update grievance status.
- **admin**: Full access: can update grievance, assign field assistants, create all resources, attendance.

Protected routes require `Authorization: Bearer <access_token>`.
    """.strip(),
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
    tags_metadata=[
        {"name": "auth", "description": "Registration, login (phone or user_id + password), token refresh. No auth for register/login."},
        {"name": "grievances", "description": "Grievance CRUD, assign worker, vote, comments. List/get: public. Create: any authenticated. Update: fieldAssistant or admin. Assign: fieldManager or admin."},
        {"name": "field assistants", "description": "Field assistants (fieldManager/fieldAssistant). List/get: public. Create: fieldManager or admin."},
        {"name": "attendance", "description": "Clock-in, clock-out, status. Access: fieldManager, fieldAssistant, or admin."},
        {"name": "wards & departments", "description": "Zones, wards, departments, grievance categories. List/get: public. Create: fieldManager or admin."},
        {"name": "health", "description": "Service health check."},
        {"name": "admin", "description": "Admin dashboard (HTML)."},
    ],
)

# Order: last added = outermost. We want logger to run for every request, so add it last
# so it wraps CORS -> then request hits Logger first, then CORS, then app.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RequestResponseLoggerMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
(PHOTOS_DIR / "grievances").mkdir(parents=True, exist_ok=True)
(PHOTOS_DIR / "resolutions").mkdir(parents=True, exist_ok=True)
app.mount("/photos", StaticFiles(directory=str(PHOTOS_DIR)), name="photos")

ASSETS_DIR.mkdir(parents=True, exist_ok=True)
(ASSETS_DIR / "audio").mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get(
    "/admin",
    tags=["admin"],
    summary="Admin dashboard",
    description="Serve the HTML admin dashboard. No auth required to load; create/update actions require staff login.",
)
def admin_dashboard():
    index_path = STATIC_DIR / "admin" / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return {"message": "Admin dashboard not found"}


@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Service health and version. No auth required.",
    response_description="status, service name, version.",
)
async def health_check():
    return {"status": "ok", "service": settings.PROJECT_NAME, "version": settings.VERSION}

def start():
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )

if __name__ == "__main__":
    start()
