# 1ne.ai Backend — Project Guide

A single reference for understanding, setting up, and working with the 1ne.ai backend. Use this document as the primary onboarding and day-to-day guide.

---

## Table of Contents

1. [What Is This Project?](#1-what-is-this-project)
2. [Purpose & Goals](#2-purpose--goals)
3. [Tech Stack](#3-tech-stack)
4. [Architecture Overview](#4-architecture-overview)
5. [Request & Data Flow](#5-request--data-flow)
6. [Project Structure](#6-project-structure)
7. [Setup Guide](#7-setup-guide)
8. [Environment Configuration](#8-environment-configuration)
9. [Key Domains](#9-key-domains)
10. [Database Layer](#10-database-layer)
11. [LLM (AI) Layer](#11-llm-ai-layer)
12. [Running & Troubleshooting](#12-running--troubleshooting)
13. [Next Steps for Learning](#13-next-steps-for-learning)

---

## 1. What Is This Project?

**1ne.ai Backend** is the server-side API for **1ne.ai**, an AI-powered teacher assistant platform. It provides:

- **REST APIs** for the frontend (web/mobile) to handle signup, login, user and institution management, chatbots, subscriptions, and templates.
- **Business logic** for authentication, authorization, multi-tenancy, subscriptions, and AI chat.
- **Integration** with external AI providers (OpenAI, Anthropic, Google) for chatbot and AI features.

The backend is the API layer that clients call; it does not include the frontend or mobile apps.

---

## 2. Purpose & Goals

- **Multi-tenancy:** Support platform, organization, and institution (e.g. schools) tenants so different customers use the same product in isolation.
- **Auth & roles:** Secure signup, login, JWT tokens, roles (e.g. super_admin, institution_admin, teacher, student, parent), and permissions.
- **Chatbots:** Expose AI chatbots (by slug), conversations, and messages; route requests to the right LLM provider with fallback and rate limiting.
- **Subscriptions:** Manage subscription tiers, features, quotas, and usage for free/trial/paid plans.
- **Templates:** Store and serve templates (e.g. worksheets) and track executions.
- **Reliability:** Use a relational database (PostgreSQL), migrations (Alembic), structured errors, health checks, and optional caching/rate limiting.

---

## 3. Tech Stack

| Layer        | Technology      | Purpose                                              |
|-------------|-----------------|------------------------------------------------------|
| Language    | Python 3.11+    | Runtime                                              |
| Web         | FastAPI         | REST API, async, OpenAPI docs                         |
| Database    | PostgreSQL      | Relational data                                      |
| ORM         | SQLAlchemy 2.x  | Models, queries, session management                   |
| Migrations  | Alembic         | Schema changes over time                             |
| Validation  | Pydantic v2     | Request/response schemas, settings                   |
| Server      | Uvicorn         | ASGI server                                          |
| Auth        | JWT, passlib    | Tokens and password hashing                          |
| LLM         | OpenAI, Anthropic, Google | AI chatbot responses                        |
| Optional    | Redis           | Caching (if configured)                              |

**Note:** This project uses **PostgreSQL** and **SQLAlchemy**. It does **not** use MongoDB.

---

## 4. Architecture Overview

1. **Client** sends an HTTP request to the API.
2. **FastAPI** receives it, applies middleware (CORS, timeouts), and routes to the correct **router**.
3. **Routers** (in `app/api/v1/` and `app/domains/*/routes.py`) define endpoints; they use **dependencies** (e.g. `get_db`, `get_current_user`) and call **services**.
4. **Services** contain business logic; they use **SQLAlchemy sessions** and **models** to read/write the database.
5. **Models** (in `app/domains/*/models.py` and `app/models/`) map to PostgreSQL tables.
6. **Schemas** (Pydantic) define request/response shapes and validation.
7. For AI features, services use the **LLM router** (`app/llm/`), which talks to OpenAI/Anthropic/Google with fallback, caching, and rate limiting.

**Summary:** Request → Router → Dependencies → Service → Model/DB (and optionally LLM).

---

## 5. Request & Data Flow

### Entry point

- **`app/main.py`** creates the FastAPI app, registers middleware (timeout, CORS), exception handlers, and includes the v1 API router.
- The v1 router is defined in **`app/api/v1/__init__.py`** and mounts: auth, subscriptions, chatbots, templates, and demo routes.

### Typical request path

1. **HTTP request** → `app/main.py` (FastAPI app).
2. **Routing** → e.g. `POST /api/v1/auth/login` → auth router in `app/domains/auth/routes.py`.
3. **Dependencies** run (e.g. `get_db()` opens a DB session, `get_current_user()` validates JWT and loads user).
4. **Route handler** receives validated body (Pydantic schema), DB session, and current user (if required).
5. **Handler** calls a **service** (e.g. `AuthService(db).login(...)`).
6. **Service** uses the **session** to query/update **models** (e.g. `User`, `RefreshToken`).
7. **Service** returns a result; the handler maps it to a **response schema** and returns it.

### Flow summary

- **Public endpoints** (e.g. register, login): no auth dependency; handler → service → DB.
- **Protected endpoints** (e.g. get my profile): `get_current_user` runs first; then handler → service → DB.
- **Role-protected endpoints** (e.g. admin-only): `require_role` or `require_permission` runs after `get_current_user`; then handler → service → DB.

---

## 6. Project Structure

```
1ne_backend/
├── app/
│   ├── main.py                 # FastAPI app, middleware, exception handlers, /health
│   ├── core/                   # Config, logging, security, exceptions, middleware
│   │   ├── config.py           # Settings from .env
│   │   ├── logging.py
│   │   ├── security.py         # Password hashing, JWT
│   │   ├── exceptions.py       # Custom exception classes
│   │   └── middleware.py       # Timeout middleware
│   ├── db/
│   │   ├── base.py             # SQLAlchemy Base; imports all models (for Alembic)
│   │   └── session.py          # Engine, SessionLocal, get_db() dependency
│   ├── api/
│   │   └── v1/
│   │       ├── __init__.py     # Aggregates auth, subscriptions, chatbots, templates, demo
│   │       ├── routes_templates.py
│   │       └── routes_demo.py
│   ├── domains/
│   │   ├── auth/               # Users, tenants, roles, login, signup, memberships
│   │   │   ├── routes.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── dependencies.py # get_current_user, require_role, require_permission
│   │   │   └── services/
│   │   ├── chatbots/           # Chatbots, conversations, messages, LLM
│   │   │   ├── routes.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   └── services/
│   │   └── subscriptions/      # Tiers, features, quotas
│   │       ├── routes.py
│   │       ├── models.py
│   │       ├── schemas.py
│   │       └── services/
│   ├── models/                 # Shared/template models (Template, TemplateVersion, etc.)
│   ├── llm/                    # LLM provider abstraction (OpenAI, Anthropic, Google)
│   │   ├── router.py           # ModelRouter: provider selection, fallback, cache
│   │   ├── config.py
│   │   └── providers/
│   ├── seed/                   # CLI to seed DB (roles, permissions, admin, templates)
│   └── utils/                  # Helpers (email, file storage, etc.)
├── alembic/                    # Database migrations
│   ├── env.py
│   └── versions/
├── tests/                      # pytest test suite
├── .env.example                # Example environment variables (copy to .env)
├── .env                        # Local config (never commit)
├── requirements.txt
├── README.md
├── SETUP.md
├── SUPER_ADMIN_GUIDE.md
└── PROJECT_GUIDE.md            # This document
```

---

## 7. Setup Guide

### Prerequisites

- **Python 3.11+** — Check: `python --version` or `python3 --version`.
- **PostgreSQL** — A database URL provided by your team (e.g. Supabase or shared dev DB), or a local PostgreSQL instance.
- **pip** — Usually bundled with Python; upgrade with `pip install --upgrade pip`.

### Steps

1. **Clone and open** the repository in your editor (e.g. Cursor).

2. **Create and activate a virtual environment:**
   - Windows (PowerShell): `python -m venv venv` then `.\venv\Scripts\Activate.ps1`
   - macOS/Linux: `python3 -m venv venv` then `source venv/bin/activate`
   - You should see `(venv)` in your prompt.

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment file:**
   - Copy: `copy .env.example .env` (Windows) or `cp .env.example .env` (macOS/Linux).
   - Edit **`.env`** and set at least **`DATABASE_URL`** (PostgreSQL connection string provided by your team or your local DB).
   - Optionally set **`SECRET_KEY`** for JWT and **`OPENAI_API_KEY`** (and **`USE_REAL_LLM=true`**) for LLM features.
   - Never commit `.env`; it is in `.gitignore`.

5. **Database migrations:**
   ```bash
   alembic upgrade head
   ```

6. **Seed data and super admin:**
   ```bash
   python -m app.seed.cli --auth
   python -m app.seed.cli --create-admin --interactive
   ```
   Optional: `python -m app.seed.cli --templates` and/or `python -m app.seed.cli --chatbots` if your team uses them.

7. **Run the server:**
   ```bash
   uvicorn app.main:app --reload
   ```
   Or use the project script: `.\start_server.ps1` (Windows).

8. **Verify:**
   - Health: `http://localhost:8000/health` — expect `{"status":"ok","database":"connected"}` (or similar).
   - API docs: `http://localhost:8000/docs`.

---

## 8. Environment Configuration

Key variables (see **`.env.example`** for the full list):

| Variable         | Required | Description |
|------------------|----------|-------------|
| **DATABASE_URL** | Yes      | PostgreSQL URL, e.g. `postgresql://user:password@host:port/dbname`. |
| **ENVIRONMENT**  | No       | `dev`, `staging`, or `prod`. |
| **LOG_LEVEL**    | No       | e.g. `DEBUG`, `INFO`. |
| **SECRET_KEY**   | Yes for auth | Used to sign JWTs; must be secret and strong in production. |
| **FRONTEND_URL** | No       | Used for CORS and links (e.g. password reset). |
| **OPENAI_API_KEY** | If using LLM | Required when using OpenAI. |
| **USE_REAL_LLM** | No       | `true` to call real LLM APIs; `false` for stubbed responses. |

Config is loaded in **`app/core/config.py`** via **pydantic-settings** from `.env`. The app uses **`settings`** (e.g. `settings.DATABASE_URL`, `settings.SECRET_KEY`).

---

## 9. Key Domains

### Auth (`app/domains/auth/`)

- **Purpose:** Signup, login, JWT access/refresh tokens, user and tenant management, roles (super_admin, institution_admin, teacher, student, parent), permissions, memberships (institution vs personal workspace), invites, profile (including profile picture), password reset, email verification.
- **Routes:** Under **`/api/v1/auth/`** (e.g. `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`, `/auth/me/profile`).
- **Models:** `User`, `Tenant`, `Role`, `Permission`, `UserRole`, `RefreshToken`, `Institution`, `UserMembership`, `Invite`, `AuditLog`, etc.
- **Flow:** Route → dependency (`get_db`, `get_current_user`, or `require_role`) → service → DB.

### Chatbots (`app/domains/chatbots/`)

- **Purpose:** List and get chatbots (by slug), create conversations, send messages, stream AI responses; integrate with the LLM router (OpenAI/Anthropic/Google) with fallback and rate limiting.
- **Routes:** Under **`/api/v1/chatbots/`** (e.g. `GET /chatbots`, `GET /chatbots/{slug}`, conversation and message endpoints).
- **Models:** `Chatbot`, `ChatbotConversation`, `ChatbotMessage`, etc.
- **Flow:** Route → optional `get_current_user` (for premium chatbots) → service → DB and/or LLM router.

### Subscriptions (`app/domains/subscriptions/`)

- **Purpose:** Subscription tiers, feature flags, quotas, and usage for the current user.
- **Routes:** Under **`/api/v1/subscriptions/`** (e.g. `GET /subscriptions/me`, `GET /subscriptions/me/features`).
- **Models:** Subscription tiers, user subscription, usage quotas, usage logs.
- **Flow:** Route → `get_current_user` → service → DB.

### Templates (`app/api/v1/routes_templates.py` & `app/models/`)

- **Purpose:** Manage templates (e.g. worksheets), versions, and executions.
- **Models:** In **`app/models/`** (e.g. `Template`, `TemplateVersion`, `TemplateExecution`).
- **Flow:** Route → optional auth → service → DB.

---

## 10. Database Layer

- **Database:** PostgreSQL only (no MongoDB).
- **ORM:** SQLAlchemy 2.x. All models inherit from **`app.db.base.Base`** and are imported in **`app.db.base`** so Alembic can see them.
- **Session:** **`app.db.session`** creates the engine (from `settings.DATABASE_URL`), `SessionLocal`, and **`get_db()`**. Routes use `Depends(get_db)` to get a session; the session is closed after the request.
- **Migrations:** **Alembic.** After changing models, create a new migration: `alembic revision -m "description"`, edit the file in `alembic/versions/`, then run `alembic upgrade head`.
- **Cloud DB (e.g. Supabase):** The app uses SSL when `DATABASE_URL` contains `supabase.co` or `pooler.supabase.com` (see `app/db/session.py`).

---

## 11. LLM (AI) Layer

- **Location:** **`app/llm/`**.
- **Role:** Select AI provider (OpenAI, Anthropic, Google) for a request; handle fallback if one fails; optional caching and rate limiting; optional cost tracking.
- **Usage:** Chatbot (and any other) code that needs AI calls uses the **ModelRouter** from `app/llm/router.py`; the router uses providers in **`app/llm/providers/`**.
- **Config:** LLM-related env vars (API keys, model names, cache, rate limits) are in **`app/llm/config.py`** and/or **`app/core/config.py`**.

---

## 12. Running & Troubleshooting

### Running

- **Start:** `uvicorn app.main:app --reload` (or `.\start_server.ps1`).
- **Base URL:** `http://localhost:8000`.
- **Docs:** `http://localhost:8000/docs`, ReDoc: `http://localhost:8000/redoc`.

### Common issues

- **Database connection failed:** Check `DATABASE_URL` in `.env`, ensure the DB is running and reachable, and (for cloud) SSL settings.
- **Import errors:** Ensure the venv is activated and `pip install -r requirements.txt` was run from the project root.
- **Alembic can't find models:** All models must be imported in **`app/db/base.py`**.
- **401 on protected routes:** Use a valid JWT from `/auth/login` or `/auth/register` in the `Authorization: Bearer <token>` header.

---

## 13. Next Steps for Learning

1. **Run the app** and open `/docs`; call a few endpoints (e.g. register, login, then a protected route).
2. **Trace one flow** end-to-end (e.g. login): from `app/domains/auth/routes.py` → `AuthService` → `app/domains/auth/models.py` and `app/db/session.py`.
3. **Read one domain** in order: `routes.py` → `schemas.py` → `services/` → `models.py`.
4. **Make a small change** (e.g. add a harmless field to a response schema or a new optional query param) and run the app and tests.
5. **Use your editor** to “Find usages” of `get_db`, `get_current_user`, or a service to see how they are used across the codebase.

Keep this guide open while you work and update your own notes as you learn. For setup details, also refer to **README.md**, **SETUP.md**, and **.env.example**.
