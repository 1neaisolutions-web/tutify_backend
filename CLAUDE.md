# 1ne.ai Backend

Python 3.11+ FastAPI application with PostgreSQL, Alembic migrations, pgvector, and multi-provider LLM support.  
See the [root CLAUDE.md](../CLAUDE.md) for the full API contract and shared conventions.

---

## Commands

```bash
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate          # Windows
# source venv/bin/activate       # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Start dev server (port 8000 — matches 1ne-frontend VITE_API_BASE_URL when set to :8000; use `start_backend_now.ps1`)
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Or use the provided script
.\start_backend_now.ps1

# Database migrations
alembic upgrade head             # apply all pending migrations
alembic revision --autogenerate -m "description"   # generate new migration

# Run tests
.\run_tests.ps1
# or
pytest tests/

# Check backend health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/ready
```

---

## Environment

Copy `.env.example` to `.env`. Minimum required vars:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/1ne_db
ENVIRONMENT=dev           # dev | staging | prod
SECRET_KEY=<openssl rand -hex 32>
```

Optional but commonly needed:

```env
# LLM providers
USE_REAL_LLM=false        # true to call real APIs
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
DEFAULT_MODEL_PROVIDER=openai
DEFAULT_MODEL=gpt-4o-mini

# OCR (local by default, no external API calls)
OCR_MODE=local
OCR_ENGINE_DEFAULT=tesseract
# TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
# POPPLER_PATH=C:\poppler\Library\bin

# Frontend URL for CORS (dev: not needed, all origins allowed)
FRONTEND_URL=http://localhost:5173

# Email (for password reset / verification)
SMTP_HOST=smtp.gmail.com
SMTP_USER=...
SMTP_PASSWORD=...
```

---

## Project Structure

```
app/
├── main.py            # FastAPI app factory, CORS, exception handlers, startup/shutdown
├── api/
│   └── v1/
│       ├── __init__.py          # Assembles all domain routers
│       ├── routes_templates.py  # Template list/detail/execute/stream
│       └── routes_demo.py       # Demo routes
├── core/
│   ├── config.py      # Settings (Pydantic BaseSettings, reads .env)
│   ├── logging.py     # Structured logging setup
│   ├── middleware.py  # TimeoutMiddleware (30 s)
│   ├── exceptions.py  # Custom exception classes
│   └── rate_limit.py  # slowapi rate limiting
├── db/
│   └── session.py     # SQLAlchemy SessionLocal, get_db dependency
├── models/            # SQLAlchemy ORM models shared across domains
├── schemas/           # Pydantic schemas shared across domains
├── llm/               # Multi-provider LLM abstraction (OpenAI / Anthropic / Google / Fallback)
├── domains/           # Feature domains (one folder = one bounded context)
│   ├── auth/
│   ├── chatbots/
│   ├── content_factory/
│   ├── content_ingestion/
│   ├── content_registry/
│   ├── external_context/
│   ├── learning_hub/
│   ├── learning_progress/
│   ├── personalization/
│   ├── recommendation_analytics/
│   ├── recommendation_engine/
│   ├── subscriptions/
│   ├── teacher_identity/
│   └── teacher_intelligence/
├── seed/              # Database seeders (chatbots, roles, etc.)
├── services/          # Cross-domain services
└── utils/             # Pure utility functions
```

Each domain follows the same internal layout:
```
domains/<name>/
├── __init__.py
├── models.py      # SQLAlchemy models
├── schemas.py     # Pydantic request/response schemas
├── routes.py      # FastAPI router  ← router prefix defined here
├── services.py    # Business logic
└── dependencies.py  (optional, e.g. auth)
```

---

## Domain Router Prefixes

| Domain | Prefix |
|---|---|
| auth | `/api/v1` |
| chatbots | `/api/v1/chatbots` |
| content_ingestion | `/api/v1` (admin routes) |
| content_registry | `/api/v1/content-registry` |
| content_factory | `/api/v1/content-factory` |
| external_context | `/api/v1` (metadata routes) |
| learning_hub | `/api/v1/learning-hub` |
| learning_progress | `/api/v1/learning-progress` |
| personalization | `/api/v1/personalization` |
| personalization (admin) | `/api/v1/admin` |
| personalization (activity) | `/api/v1/activity` |
| personalization (content) | `/api/v1/content` |
| recommendation_analytics | `/api/v1/recommendation-analytics` |
| subscriptions | `/api/v1/subscriptions` |
| teacher_identity | `/api/v1/teacher-identity` |
| teacher_intelligence | `/api/v1/teacher-intelligence` |

---

## Authentication & RBAC

- JWT HS256. `SECRET_KEY` in env. Access: 24 h, Refresh: 1 day with rotation.
- FastAPI dependencies in `app/domains/auth/dependencies.py`:
  - `get_current_user` — validates Bearer token, returns `User`
  - `require_role(RoleName.teacher)` — raises 403 if role missing
  - `require_permission("some:action")` — fine-grained permission check
- Roles: `student`, `teacher`, `school_admin`, `super_admin`
- Account lockout after 5 failed logins; 30-minute lockout window.

---

## Database

- **PostgreSQL** via SQLAlchemy 2.x async-compatible ORM (sync sessions via `SessionLocal`).
- **pgvector** extension for embedding storage (content ingestion / semantic search).
- **Alembic** for schema migrations — always run `alembic upgrade head` after pulling.
- `app/db/session.py` provides `get_db` dependency (yields `Session`, auto-closes).

### Common migration commands
```bash
alembic upgrade head                        # apply all
alembic downgrade -1                        # roll back one
alembic history                             # list migrations
alembic current                             # show current revision
```

---

## LLM Layer

`app/llm/` abstracts over OpenAI, Anthropic, Google, and a Fallback (stub) provider.

- `USE_REAL_LLM=false` (default) uses the stub — safe for local dev without API keys.
- `LLM_OUTBOUND_ENABLED=false` blocks **all** paid provider traffic at `ModelRouter` (and PixGen / OpenAI embeddings). Template execution uses stubs even if `USE_REAL_LLM=true` by mistake. Set `true` only when you intend to spend tokens.
- `LEARNING_HUB_AUTO_LLM_ENABLED=false` (default) disables the gap worker loop and personalization **inventory LLM job** enqueue/processing; Learning Hub HTTP routes stay non-LLM.
- Set `DEFAULT_MODEL_PROVIDER` and `DEFAULT_MODEL` to control which real provider is used.
- `FALLBACK_ENABLED=true` silently falls back to the stub when all providers fail.

---

## Content Ingestion Pipeline

1. Upload document via `POST /api/v1/admin/documents`.
2. Async processing: OCR (tesseract/easyocr) → chunking → **topic validation** → embedding → pgvector storage.
3. Stable topic nodes live in `document_topics`; chunks link via `chunks.topic_fk`.
4. Quiz catalog: `POST /api/v1/quiz/catalog/structure` returns hierarchical book → chapter → topic trees.
5. Set `SCOPE_BY_TOPIC_ID_ENABLED=true` after migrations + backfill to enable UUID-based quiz retrieval (see root `RAG_PIPELINE_IMPROVEMENT_PLAN.md`).
6. Admin: `POST /api/v1/admin/documents/{id}/reprocess-topics` rebuilds topic tree without re-embedding.

---

## Background Worker

`GapGenerationWorker` runs as an `asyncio` task on startup (polls every 2 s).  
It processes pending content generation jobs from the `content_factory` domain and publishes results to `content_registry`.  
See `app/domains/content_factory/services/gap_generation_worker.py`.

---

## Adding a New Domain

1. Create `app/domains/<name>/` with `models.py`, `schemas.py`, `routes.py`, `services.py`.
2. Define `router = APIRouter(prefix="/api/v1/<name>", tags=["<name>"])` in `routes.py`.
3. Import and register the router in `app/api/v1/__init__.py`.
4. Generate an Alembic migration for any new models.
5. Import new models in `app/models/__init__.py` so Alembic auto-detects them.

---

## Deployment

Deployed on **Railway**. `railway.json` configures the build and start command:

```json
{
  "build": { "buildCommand": "pip install -r requirements.txt" },
  "deploy": { "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT" }
}
```

Production URL: `https://1nebackend-production.up.railway.app`  
API docs (Swagger): `https://1nebackend-production.up.railway.app/docs`

Set all required env vars in the Railway dashboard. `DATABASE_URL` is auto-injected by Railway's PostgreSQL plugin.
