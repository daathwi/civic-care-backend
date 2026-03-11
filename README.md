# ⚙️ CivicCare (Backend)

**High-Performance API for Civic Grievance Management** — Powering transparency and accountability with FastAPI and AI.

This repository contains the backend server for the CivicCare platform. It handles user authentication, grievance lifecycle management, role-based access control (RBAC), and integrates with local AI models for intelligent orchestration.

---

## ✨ Key Features

-   **🔐 Robust Auth:** JWT-based authentication supporting phone-based login for citizens and UID-based login for staff.
-   **📋 Grievance Lifecycle:** End-to-end management of civic complaints, including geotagged photo uploads, public voting, and commenting.
-   **🔨 Workforce Management:** Tools for Field Managers to assign tasks to Field Assistants and track resolution progress.
-   **🕒 Attendance System:** Integrated clock-in/out mechanism for ground workers to track field activity.
-   **🤖 AI Orchestration:** Integration with LLaMA 3.2 via Ollama for fraud detection, smart categorization, and automated dispatch.
-   **📍 Geospatial Governance:** Ward and Zone-based routing to ensure complaints are directed to the correct local authorities.

---

## 🛠️ Tech Stack

-   **Framework:** [FastAPI](https://fastapi.tiangolo.com) (Python 3.14+)
-   **ORM:** [SQLAlchemy](https://www.sqlalchemy.org) (Async/Await)
-   **Database:** [PostgreSQL](https://www.postgresql.org)
-   **Validation:** [Pydantic v2](https://docs.pydantic.dev)
-   **Auth:** [python-jose](https://github.com/mpdavis/python-jose), [passlib](https://passlib.readthedocs.io/) (bcrypt)
-   **Package Manager:** [uv](https://github.com/astral-sh/uv)
-   **AI Infrastructure:** [Ollama](https://ollama.com) (Llama 3.2)

---

## ⚡ Quick Start

### Prerequisites
- [uv](https://github.com/astral-sh/uv) (Extremely fast Python package manager)
- [PostgreSQL](https://www.postgresql.org/download/)
- [Ollama](https://ollama.com) with the `llama3.2:3b` model.

### Installation & Run

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/daathwi/civic-care-backend.git
    cd civic-care-backend/api
    ```

2.  **Install dependencies:**
    `uv` will automatically create a virtual environment and install everything:
    ```bash
    uv run start
    ```

3.  **Environment Setup:**
    Copy `.env.example` to `.env` and configure your credentials:
    - `DATABASE_URL`
    - `SECRET_KEY`

---

## 👥 Roles & Access Control

| Role | Permissions |
| :--- | :--- |
| **Citizen** | Register, Login (Phone), Create Grievances, Vote, Comment. |
| **Field Assistant** | Login (UID), Update Assigned Grievances, Clock-in/out. |
| **Field Manager** | Assign Workers, Create Resources (Zones/Wards), Manage Workforce. |
| **Admin** | Full system access, including manual grievance overrides and staff management. |

---

## 📡 API Reference

Once the server is running, visit the interactive documentation:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---
*Built by Stack Syndicate · Engineering Digital Democracy*
