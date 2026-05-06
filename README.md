# 1ne.ai Backend

Backend API for 1ne.ai - an AI-powered teacher assistant.

## Tech Stack

- **Python 3.11+**
- **FastAPI** - Modern web framework
- **SQLAlchemy 2.0** - ORM for database operations
- **PostgreSQL** - Relational database
- **Alembic** - Database migrations
- **Pydantic v2** - Data validation
- **Uvicorn** - ASGI server
- **pytest** - Testing framework
- **OpenAI/Anthropic/Google** - LLM providers
- **Redis** - Caching (optional)

## Setup

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 12+ (installed and running)
- pip (Python package manager)

### Installation Steps

#### Option 1: Using Virtual Environment (Recommended)

1. **Create a virtual environment:**
   ```bash
   # Windows
   python -m venv venv
   
   # macOS/Linux
   python3 -m venv venv
   ```

2. **Activate the virtual environment:**
   ```bash
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Upgrade pip:**
   ```bash
   pip install --upgrade pip
   ```

4. **Install dependencies:**
   ```bash
   # For production
   pip install -r requirements.txt
   
   # For development (includes testing tools)
   pip install -r requirements-dev.txt
   ```

5. **Create a `.env` file:**
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env with your actual database credentials and API keys
   ```

6. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

7. **Seed initial data and create super admin:**
   ```bash
   # Seed auth data (roles, permissions, platform tenant)
   python -m app.seed.cli --auth
   
   # Create super admin (interactive - recommended for first-time setup)
   python -m app.seed.cli --create-admin --interactive
   ```
   
   **📖 For detailed super admin guide, see:** [SUPER_ADMIN_GUIDE.md](SUPER_ADMIN_GUIDE.md)

8. **Start the development server:**
   ```bash
   # Option 1: Using PowerShell script (recommended)
   .\start_server.ps1
   
   # Option 2: Manual start
   uvicorn app.main:app --reload
   ```

9. **Test the endpoints:**
   ```bash
   # Run comprehensive tests (in a new terminal)
   .\run_tests.ps1
   
   # Or run Python test script directly
   python test_api_endpoints.py
   ```

#### Option 2: Using Poetry (Alternative)

1. **Install Poetry** (if not already installed):
   ```bash
   # Windows (PowerShell)
   (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
   
   # macOS/Linux
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. **Install dependencies:**
   ```bash
   poetry install
   ```

3. **Activate Poetry shell:**
   ```bash
   poetry shell
   ```

4. **Follow steps 5-8 from Option 1 above**

### Deactivating Virtual Environment

When you're done working:
```bash
deactivate
```

The API will be available at `http://localhost:8000` with documentation at `http://localhost:8000/docs`.

## Project Structure

```
app/
  main.py              # FastAPI app factory
  core/                # Core configuration and utilities
    config.py          # Application settings
    logging.py         # Logging configuration
  db/                  # Database configuration
    base.py            # SQLAlchemy base class
    session.py         # Database session management
  models/              # SQLAlchemy models
  schemas/             # Pydantic schemas
  api/                 # API routes
    v1/                # API version 1
    deps/              # API dependencies
  services/            # Business logic services
  llm/                 # LLM abstraction layer
  seed/                # Database seeding scripts
alembic/               # Alembic migrations
tests/                 # Test suite
```

## Health Check

```bash
curl http://localhost:8000/health
```

Response: `{"status": "ok"}`

# 1ne_backend
