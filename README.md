# ⚙️ CivicCare (Backend)

**High-Performance API for Civic Grievance Management** — Powering transparency and accountability with FastAPI and AI.

This repository contains the backend server for the CivicCare platform. It handles user authentication, grievance lifecycle management, role-based access control (RBAC), and integrates with local AI models for intelligent tool orchestration.

---

## ✨ Key Features

-   **🔐 Robust Auth:** JWT-based authentication with phone/user_id and role-based permissions (Citizen, Assistant, Manager, Admin).
-   **📋 Grievance Lifecycle:** Comprehensive CRUD operations for grievances, includes voting, commenting, and task assignment.
-   **🔨 Workforce Management:** Tools for managers to assign tasks to field workers and track attendance.
-   **🤖 AI Orchestration:** Integration with LLaMA 3.2 via Ollama and MCP (Model Context Protocol) for fraud detection and smart dispatch.
-   **📡 Real-Time Events:** WebSocket support for live comments and internal staff status changes.
-   **📍 Geospatial Support:** Ward and zone management with GeoJSON and coordinate-based lookups.

---

## 🛠️ Tech Stack

-   **Framework:** [FastAPI](https://fastapi.tiangolo.com) (Python 3.14+)
-   **ORM:** [SQLAlchemy](https://www.sqlalchemy.org) (Async)
-   **Database:** [PostgreSQL](https://www.postgresql.org)
-   **Validation:** [Pydantic](https://docs.pydantic.dev) (v2+)
-   **Auth:** [python-jose](https://github.com/mpdavis/python-jose), [bcrypt](https://github.com/pyca/bcrypt)
-   **Package Manager:** [uv](https://github.com/astral-sh/uv)
-   **AI:** [Ollama](https://ollama.com) (Local LLaMA 3.2-7B)

---

## ⚡ Quick Start

### Prerequisites
- [uv](https://github.com/astral-sh/uv) installed (recommended) or `pip`.
- [PostgreSQL](https://www.postgresql.org/download/) running locally.
- [Ollama](https://ollama.com) with the `llama3.2:7b` model pulled.

### Installation
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/daathwi/civic-care-backend.git
    cd civic-care-backend/api
    ```

2.  **Setup environment:**
    ```bash
    # Create venv and install dependencies
    uv venv
    source .venv/bin/activate
    uv pip install -r pyproject.toml
    ```

3.  **Configure `.env`:**
    Copy `.env.example` to `.env` and update your `DATABASE_URL` and `SECRET_KEY`.

4.  **Run the server:**
    ```bash
    # Using uv script
    uv run start

    # Or directly with uvicorn
    uvicorn main:app --reload --host 0.0.0.0
    ```

---

## 📡 API Reference

Once the server is running, visit:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---
*Built by Stack Syndicate · Digital Democracy*
