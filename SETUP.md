# Setup Guide - 1ne.ai Backend

This guide provides detailed instructions for setting up the 1ne.ai backend development environment.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Virtual Environment Setup](#virtual-environment-setup)
3. [Database Setup](#database-setup)
4. [Environment Configuration](#environment-configuration)
5. [Installation](#installation)
6. [Running the Application](#running-the-application)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.11 or higher**
  - Check version: `python --version` or `python3 --version`
  - Download: https://www.python.org/downloads/

- **PostgreSQL 12+**
  - Download: https://www.postgresql.org/download/
  - Ensure PostgreSQL service is running

- **pip** (usually comes with Python)
  - Upgrade: `pip install --upgrade pip`

- **Git** (for cloning the repository)

## Virtual Environment Setup

### Why Use a Virtual Environment?

A virtual environment isolates your project dependencies from other Python projects, preventing conflicts and ensuring reproducible builds.

### Creating a Virtual Environment

#### Windows:
```powershell
# Navigate to project directory
cd D:\1ne\1ne_backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate
```

#### macOS/Linux:
```bash
# Navigate to project directory
cd /path/to/1ne_backend

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate
```

**Note:** When activated, your terminal prompt will show `(venv)` at the beginning.

### Deactivating Virtual Environment

When you're done working:
```bash
deactivate
```

## Database Setup

1. **Start PostgreSQL service:**
   ```bash
   # Windows (as Administrator)
   net start postgresql-x64-14
   
   # macOS (using Homebrew)
   brew services start postgresql
   
   # Linux
   sudo systemctl start postgresql
   ```

2. **Create database:**
   ```bash
   # Connect to PostgreSQL
   psql -U postgres
   
   # Create database
   CREATE DATABASE 1ne_db;
   
   # Create user (optional)
   CREATE USER your_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE 1ne_db TO your_user;
   
   # Exit psql
   \q
   ```

## Environment Configuration

1. **Copy the example environment file:**
   ```bash
   # Windows
   copy .env.example .env
   
   # macOS/Linux
   cp .env.example .env
   ```

2. **Edit `.env` file with your configuration:**
   ```env
   # Update database URL with your credentials
   DATABASE_URL=postgresql://your_user:your_password@localhost:5432/1ne_db
   
   # Set environment
   ENVIRONMENT=dev
   LOG_LEVEL=INFO
   
   # Add LLM API keys if using real LLM (optional)
   OPENAI_API_KEY=sk-your-key-here
   ```

**Important:** Never commit `.env` to version control. It's already in `.gitignore`.

## Installation

### Method 1: Using requirements.txt (Recommended)

1. **Upgrade pip:**
   ```bash
   pip install --upgrade pip
   ```

2. **Install production dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install development dependencies (for testing):**
   ```bash
   pip install -r requirements-dev.txt
   ```

### Method 2: Using Poetry (Alternative)

1. **Install Poetry:**
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

## Running the Application

1. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

2. **Seed auth data (roles, permissions, platform tenant):**
   ```bash
   python -m app.seed.cli --auth
   ```

3. **Create super admin account:**
   ```bash
   # Interactive mode (recommended for first-time setup)
   python -m app.seed.cli --create-admin --interactive
   
   # Or using environment variables (for CI/CD)
   # Add SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD to .env
   python -m app.seed.cli --create-admin
   ```
   
   **📖 For complete super admin guide, see:** [SUPER_ADMIN_GUIDE.md](SUPER_ADMIN_GUIDE.md)

4. **Seed initial templates (optional):**
   ```bash
   python -m app.seed.cli --templates
   ```

5. **Start the development server:**
   ```bash
   uvicorn app.main:app --reload
   ```

6. **Verify the application is running:**
   - API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health

## Troubleshooting

### Virtual Environment Issues

**Problem:** `python: command not found`
- **Solution:** Use `python3` instead of `python` on macOS/Linux

**Problem:** `venv\Scripts\activate: cannot be loaded`
- **Solution:** Run PowerShell as Administrator and execute: `Set-ExecutionPolicy RemoteSigned`

### Database Connection Issues

**Problem:** `could not connect to server`
- **Solution:** Ensure PostgreSQL service is running
- Check connection string in `.env` file
- Verify database exists: `psql -U postgres -l`

**Problem:** `password authentication failed`
- **Solution:** Verify username and password in `DATABASE_URL`
- Reset PostgreSQL password if needed

### Dependency Installation Issues

**Problem:** `pip install` fails with SSL errors
- **Solution:** Upgrade pip: `pip install --upgrade pip`
- Use trusted hosts: `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt`

**Problem:** `psycopg2-binary` installation fails
- **Solution:** Install PostgreSQL development libraries:
  - Windows: Install PostgreSQL client tools
  - macOS: `brew install postgresql`
  - Linux: `sudo apt-get install libpq-dev` (Ubuntu/Debian)

### Port Already in Use

**Problem:** `Address already in use`
- **Solution:** Change port: `uvicorn app.main:app --reload --port 8001`
- Or kill the process using port 8000

## Next Steps

- Read the [API Documentation](http://localhost:8000/docs) when server is running
- Check `tests/` directory for test examples
- Review `app/` directory structure for code organization
- See `alembic/versions/` for database migration history

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

