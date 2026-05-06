# Database Guide — 1ne.ai Backend

This document explains everything about the database layer in this project: what is used, how it is configured, how to run and use it, and how to work with migrations and models.

---

## Table of Contents

1. [What Is Used](#1-what-is-used)
2. [Connection String (DATABASE_URL)](#2-connection-string-database_url)
3. [Where the Database Lives in Code](#3-where-the-database-lives-in-code)
4. [How the Connection Works](#4-how-the-connection-works)
5. [How to Run and Set Up](#5-how-to-run-and-set-up)
6. [How to Use the Database in Code](#6-how-to-use-the-database-in-code)
7. [Models and Tables](#7-models-and-tables)
8. [Migrations (Alembic)](#8-migrations-alembic)
9. [Health Check](#9-health-check)
10. [Cloud Database (Supabase)](#10-cloud-database-supabase)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. What Is Used

| Component | Technology | Purpose |
|-----------|------------|--------|
| **Database** | **PostgreSQL** | Relational database. All app data (users, tenants, chatbots, subscriptions, templates, etc.) is stored here. |
| **ORM** | **SQLAlchemy 2.x** | Python library to define models (tables/columns), run queries, and manage sessions. The app does **not** write raw SQL for business logic; it uses SQLAlchemy. |
| **Driver** | **psycopg2-binary** | Low-level driver that connects Python to PostgreSQL. SQLAlchemy uses it under the hood. |
| **Migrations** | **Alembic** | Tool to change the database schema over time (add/remove tables, columns, indexes) in versioned scripts. |

**Important:** This project uses **PostgreSQL** and **SQLAlchemy** only. It does **not** use MongoDB, MySQL, or any other database.

---

## 2. Connection String (DATABASE_URL)

The app connects to PostgreSQL using a single environment variable: **`DATABASE_URL`**.

### Format

```
postgresql://USERNAME:PASSWORD@HOST:PORT/DATABASE_NAME
```

**Examples:**

- **Local PostgreSQL:**
  ```text
  postgresql://postgres:yourpassword@localhost:5432/1ne_db
  ```
- **Supabase (cloud):**
  ```text
  postgresql://postgres.xxxxx:password@aws-0-region.pooler.supabase.com:6543/postgres
  ```
  (Your team will give you the exact URL; it often includes `pooler.supabase.com` and uses port `6543`.)

### Where to Set It

1. Copy `.env.example` to `.env`.
2. In `.env`, set:
   ```env
   DATABASE_URL=postgresql://user:password@host:port/dbname
   ```
3. Never commit `.env`; it is in `.gitignore`.

The app loads `DATABASE_URL` in **`app/core/config.py`** via **pydantic-settings** and passes it to the database engine in **`app/db/session.py`**.

---

## 3. Where the Database Lives in Code

| Path | Purpose |
|------|---------|
| **`app/core/config.py`** | Reads `DATABASE_URL` and other settings from `.env`. |
| **`app/db/session.py`** | Creates the SQLAlchemy **engine**, **SessionLocal**, and **`get_db()`** dependency. This is the only place that opens connections to PostgreSQL. |
| **`app/db/base.py`** | Defines the SQLAlchemy **Base** class and **imports all models** so Alembic can see every table. |
| **`app/domains/auth/models.py`** | Auth-related models (User, Tenant, Role, RefreshToken, etc.). |
| **`app/domains/chatbots/models.py`** | Chatbot-related models (Chatbot, ChatbotConversation, ChatbotMessage, etc.). |
| **`app/domains/subscriptions/models.py`** | Subscription-related models (tiers, user subscription, quotas, etc.). |
| **`app/models/`** | Shared/template models (Template, TemplateVersion, TemplateExecution, etc.). |
| **`alembic/`** | Migration scripts and Alembic configuration. |

All tables are defined as **SQLAlchemy models** that inherit from **`app.db.base.Base`**. There are no separate “database” docs; the source of truth is the model classes and the Alembic migration files.

---

## 4. How the Connection Works

### Engine

In **`app/db/session.py`**, the app creates a SQLAlchemy **engine** using `settings.DATABASE_URL`. The engine:

- Uses a **connection pool** (e.g. `pool_size=10`, `max_overflow=20`) so multiple requests can reuse connections.
- Uses **pool_pre_ping=True** so bad connections are detected and replaced.
- For **Supabase/cloud** URLs (containing `supabase.co` or `pooler.supabase.com`), it uses **SSL** (`sslmode=require`).
- Sets a **statement timeout** (e.g. 10 seconds) and **timezone=UTC** per connection.

### SessionLocal

**SessionLocal** is a **session factory** bound to that engine. Each “unit of work” (e.g. one API request) gets its own session.

### get_db()

**`get_db()`** is a **generator** that:

1. Creates a new session from **SessionLocal**.
2. **Yields** it to the route (or dependency) that called it.
3. On success, **commits** the transaction.
4. On exception, **rolls back** the transaction.
5. **Closes** the session in a `finally` block.

It also includes **retry logic** (e.g. up to 3 attempts with exponential backoff) for connection failures, so temporary network issues can be handled without failing the request immediately.

**Summary:** One request → one session → one transaction (commit or rollback) → session closed. The app never keeps a session open across requests.

---

## 5. How to Run and Set Up

### Prerequisites

- A **PostgreSQL** server (local or cloud, e.g. Supabase).
- A **database** created on that server (e.g. `1ne_db` locally, or the default `postgres` database on Supabase).
- **`DATABASE_URL`** in `.env` pointing to that database.

### Step 1: Set DATABASE_URL

In `.env`:

```env
DATABASE_URL=postgresql://user:password@host:port/database_name
```

(Use the URL provided by your team for shared/dev, or your local PostgreSQL credentials.)

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs **sqlalchemy**, **alembic**, **psycopg2-binary**, and other app dependencies.

### Step 3: Run Migrations

Migrations create or update all tables to match the current models:

```bash
alembic upgrade head
```

- **`head`** means “latest revision.” Alembic runs all migration scripts in order from the current DB state to `head`.
- Tables are created in **`alembic/versions/`** (e.g. `52aabe358ec8_create_auth_models.py`, `7572e12d1331_create_subscription_models.py`, etc.).

You only need to run this once per environment (or after pulling new migrations).

### Step 4: Seed Data (Optional but Recommended)

Seed scripts insert initial data (roles, permissions, platform tenant, optional super admin, templates, chatbots):

```bash
# Required for auth: roles, permissions, platform tenant
python -m app.seed.cli --auth

# Create first super admin user (interactive)
python -m app.seed.cli --create-admin --interactive

# Optional: templates, chatbots
python -m app.seed.cli --templates
python -m app.seed.cli --chatbots
```

These use **`SessionLocal()`** in **`app/db/session.py`** to get a session and then call seeders that insert rows.

### Step 5: Start the App

```bash
uvicorn app.main:app --reload
```

The app will connect to the database using **`DATABASE_URL`** on the first request that needs a session (or when `/health` is called, which checks the connection).

### Verifying the Database

- Open **`http://localhost:8000/health`**.
  - If the DB is reachable: `{"status":"ok","database":"connected"}`.
  - If not: `{"status":"degraded","database":"disconnected",...}`.
- Use **`http://localhost:8000/docs`** to call endpoints that read/write data (e.g. register, login); if they succeed, the database is in use.

---

## 6. How to Use the Database in Code

### In API Routes (FastAPI)

1. **Inject the session** with FastAPI’s **`Depends(get_db)`**.
2. Pass the **`db`** (session) object to your **service** or use it directly in the route.

**Example:**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()

@router.get("/example")
def example_route(db: Session = Depends(get_db)):
    # Use db to query or create records
    user = db.query(User).filter(User.email == "test@example.com").first()
    return {"user_id": str(user.id)}
```

- **`get_db`** is defined in **`app/db/session.py`**.
- Every route that needs the database should declare **`db: Session = Depends(get_db)`**.
- Do **not** create a new engine or session manually in routes; always use **`get_db`**.

### In Services

Services receive the **session** from the route (or from a dependency) and use it to run queries and persist changes:

```python
class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str):
        return self.db.query(User).filter(User.email == email).first()

    def create(self, email: str, ...):
        user = User(email=email, ...)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
```

- The **route** creates the service with **`UserService(db)`** and calls methods; the service uses **`self.db`** for all queries and **commit/rollback**.
- Transactions are committed (or rolled back) when **`get_db`** finishes (see “How the Connection Works” above). You can also call **`db.commit()`** or **`db.rollback()`** inside the request if needed.

### In Scripts (e.g. Seed CLI)

For one-off scripts (like the seed CLI), use **`SessionLocal()`** directly:

```python
from app.db.session import SessionLocal

db = SessionLocal()
try:
    # Do work
    db.commit()
finally:
    db.close()
```

The seed CLI in **`app/seed/cli.py`** does this pattern when running **`python -m app.seed.cli --auth`** etc.

---

## 7. Models and Tables

### Base and Imports

- Every model inherits from **`app.db.base.Base`** (SQLAlchemy **DeclarativeBase**).
- **All** models must be **imported** in **`app/db/base.py`** so that:
  - Alembic can see them when generating migrations.
  - The metadata (tables) is registered for migration scripts.

### Where Models Are Defined

| Location | Models (examples) |
|----------|--------------------|
| **`app/domains/auth/models.py`** | Tenant, User, Role, Permission, UserRole, RefreshToken, Institution, UserMembership, Invite, AuditLog, … |
| **`app/domains/chatbots/models.py`** | Chatbot, ChatbotConversation, ChatbotMessage, ChatbotCapability, … |
| **`app/domains/subscriptions/models.py`** | SubscriptionTierModel, UserSubscription, UserUsageQuota, … |
| **`app/models/`** | Template, TemplateVersion, TemplateExecution, TemplateFavorite |

### Table Names

- By default, SQLAlchemy uses the **class name in lowercase** for the table name (e.g. `User` → `users` in many setups).
- Explicit names are set with **`__tablename__ = "users"`** (or similar) in the model class.
- Migrations in **`alembic/versions/`** show the actual table names (e.g. `users`, `tenants`, `roles`, `refresh_tokens`).

### Relationships

Models use **`relationship()`** and **`ForeignKey()`** for associations (e.g. User → Tenant, User → UserRoles → Role). Queries can use **`db.query(User).options(joinedload(User.tenant)).first()`** etc. to load related rows.

---

## 8. Migrations (Alembic)

Alembic tracks schema changes in **revision scripts** under **`alembic/versions/`**. The app uses these to update the database when you run **`alembic upgrade head`**.

### Configuration

- **`alembic.ini`** — Alembic config; **`script_location = alembic`**; the URL in the file is overridden by **`app/core/config`** in **`alembic/env.py`**.
- **`alembic/env.py`** — Sets **`config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)`** so migrations use the same **`DATABASE_URL`** as the app. It also sets **`target_metadata = Base.metadata`** so Alembic knows about all models imported in **`app/db/base.py`**.

### Common Commands

| Command | Purpose |
|---------|--------|
| **`alembic upgrade head`** | Apply all pending migrations up to the latest revision. Use this to create/update tables. |
| **`alembic downgrade -1`** | Undo the last migration (one step back). |
| **`alembic downgrade base`** | Undo all migrations (empty schema; use with care). |
| **`alembic current`** | Show the current revision in the database. |
| **`alembic history`** | List revision IDs and descriptions. |

### Creating a New Migration (Schema Change)

1. **Change the models** in Python (e.g. add a column in **`app/domains/auth/models.py`**).
2. Generate a new revision:
   ```bash
   alembic revision --autogenerate -m "add_profile_picture_url_to_users"
   ```
   This creates a new file in **`alembic/versions/`** with **`upgrade()`** and **`downgrade()`**.
3. **Review** the generated file; fix or add operations if needed (especially for enums, indexes, or renames).
4. Apply it:
   ```bash
   alembic upgrade head
   ```

**Important:** All models that should be part of the schema must be imported in **`app/db/base.py`**; otherwise **autogenerate** will not see them.

---

## 9. Health Check

The app exposes **`GET /health`** (in **`app/main.py`**), which:

1. Creates a short-lived session with **`SessionLocal()`**.
2. Runs **`db.execute(text("SELECT 1"))`** to check connectivity.
3. Returns **`{"status":"ok","database":"connected"}`** if the query succeeds.
4. Returns **`{"status":"degraded","database":"disconnected",...}`** if the database is unreachable (e.g. wrong URL, network issue, DB down).

Use this to confirm the app can talk to PostgreSQL after setting **`DATABASE_URL`** and running migrations.

---

## 10. Cloud Database (Supabase)

When **`DATABASE_URL`** contains **`supabase.co`** or **`pooler.supabase.com`**, the app (in **`app/db/session.py`**):

- Uses **SSL** for the connection (**`sslmode=require`**).
- Keeps the same pool, timeout, and retry behavior.

No extra code is required in your routes or services; only **`DATABASE_URL`** and the session layer change. Use the **connection string** provided by your team (often from the Supabase project settings, “Connection string” or “Pooler”).

---

## 11. Troubleshooting

| Problem | What to check |
|--------|----------------|
| **Database connection failed** | Verify **`DATABASE_URL`** in `.env` (user, password, host, port, database name). Ensure PostgreSQL is running and reachable (firewall, VPN). For cloud, ensure IP/access is allowed and SSL is used. |
| **Import errors (e.g. “No module named 'app.db'”)** | Run from the **project root**; ensure the virtual environment is activated and **`pip install -r requirements.txt`** was run. |
| **Alembic “can’t find models” or empty autogenerate** | Ensure every model is **imported** in **`app/db/base.py`** (see the imports at the bottom of that file). |
| **Migration fails (e.g. “relation already exists”)** | The DB may already have the table. Check **`alembic current`** and **`alembic history`**; fix the migration or the DB state (do not drop production data without a backup). |
| **401 on protected routes** | This is auth/JWT-related, not the database. Use a valid token from **`/auth/login`** or **`/auth/register`** in the **`Authorization: Bearer <token>`** header. |
| **Slow or hanging queries** | The engine sets a **statement timeout** (e.g. 10 seconds). Check slow queries in logs (in dev, **`echo=True`** in the engine can log SQL). |

---

## Quick Reference

- **Set connection:** **`DATABASE_URL`** in **`.env`**.
- **Apply schema:** **`alembic upgrade head`**.
- **Seed data:** **`python -m app.seed.cli --auth`**, then **`--create-admin --interactive`** (and optionally **`--templates`**, **`--chatbots`**).
- **Use in routes:** **`db: Session = Depends(get_db)`** and pass **`db`** to services.
- **Use in scripts:** **`SessionLocal()`**, then **commit** / **close** in **try/finally**.
- **Check connectivity:** **`GET /health`**.
- **New schema change:** Edit models → **`alembic revision --autogenerate -m "description"`** → review → **`alembic upgrade head`**.

For overall project setup and architecture, see **PROJECT_GUIDE.md** and **SETUP.md**.
