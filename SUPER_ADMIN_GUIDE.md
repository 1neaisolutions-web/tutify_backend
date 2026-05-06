# Super Admin Creation Guide

Complete guide for creating and managing super admin accounts in the 1ne.ai backend.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Method 1: Interactive Creation](#method-1-interactive-creation-recommended)
4. [Method 2: Environment Variables](#method-2-environment-variables-cicd)
5. [Method 3: Complete Setup](#method-3-complete-setup-all-in-one)
6. [Managing Super Admins](#managing-super-admins)
7. [Password Requirements](#password-requirements)
8. [Troubleshooting](#troubleshooting)
9. [After Creating Super Admin](#after-creating-super-admin)
10. [Security Best Practices](#security-best-practices)

---

## Prerequisites

Before creating a super admin, ensure:

1. **Database is set up and migrations are run:**
   ```bash
   alembic upgrade head
   ```

2. **Auth data is seeded** (roles, permissions, platform tenant):
   ```bash
   python -m app.seed.cli --auth
   ```

---

## Quick Start

### For First-Time Setup:

```bash
# Step 1: Run migrations
alembic upgrade head

# Step 2: Seed auth data
python -m app.seed.cli --auth

# Step 3: Create super admin (interactive)
python -m app.seed.cli --create-admin --interactive
```

---

## Method 1: Interactive Creation (Recommended)

**Best for:** Local development, first super admin creation

### Steps:

1. **Run the interactive command:**
   ```bash
   python -m app.seed.cli --create-admin --interactive
   ```

2. **Follow the prompts:**
   ```
   ============================================================
   Creating Super Admin User
   ============================================================

   Email address: admin@1ne.ai
   Password: ******** (hidden, min 10 characters)
   Password (again): ********
   First name (default: Super): Super
   Last name (default: Admin): Admin
   Phone (optional): +1234567890
   ```

3. **Success message:**
   ```
   ✅ Super admin created successfully!
      Email: admin@1ne.ai
      User ID: 123e4567-e89b-12d3-a456-426614174000
   
   ⚠️  IMPORTANT: Change password after first login!
   ```

---

## Method 2: Environment Variables (CI/CD)

**Best for:** Production deployments, CI/CD pipelines, Docker containers

### Steps:

1. **Add to `.env` file:**
   ```env
   SUPER_ADMIN_EMAIL=admin@1ne.ai
   SUPER_ADMIN_PASSWORD=SecurePassword123!@#
   SUPER_ADMIN_FIRST_NAME=Super
   SUPER_ADMIN_LAST_NAME=Admin
   ```

2. **Run the command:**
   ```bash
   python -m app.seed.cli --auth --create-admin
   ```

3. **Output:**
   ```
   Seeding auth data (roles, permissions, platform tenant)...
   Auth seeding complete!
     Platform tenant created: True
     Roles created: 6
     Permissions created: 20
     Role-permission mappings: 45

   Creating super admin user...
   ✅ Super admin created successfully!
      Email: admin@1ne.ai
      User ID: 123e4567-e89b-12d3-a456-426614174000
   ```

---

## Method 3: Complete Setup (All-in-One)

**Best for:** Fresh installation, new developer onboarding

### Steps:

```bash
# Step 1: Run migrations
alembic upgrade head

# Step 2: Seed everything + create super admin
python -m app.seed.cli --auth --create-admin --interactive --templates
```

This will:
- ✅ Create platform tenant
- ✅ Seed roles and permissions
- ✅ Create super admin (interactive)
- ✅ Seed templates

---

## Managing Super Admins

### List All Super Admins

```bash
python -m app.seed.cli --list-admins
```

**Output:**
```
============================================================
Super Admins (2 total)
============================================================
✅ admin1@1ne.ai
   Name: Super Admin
   Status: active
   User ID: 123e4567-e89b-12d3-a456-426614174000
   Last Login: 2024-01-15 10:30:00

✅ admin2@1ne.ai
   Name: Admin Two
   Status: active
   User ID: 456e7890-e89b-12d3-a456-426614174001
   Last Login: Never
```

### Update Super Admin

```bash
python -m app.seed.cli --update-admin <user_id>
```

**Example:**
```bash
python -m app.seed.cli --update-admin 123e4567-e89b-12d3-a456-426614174000
```

### Deactivate Super Admin

```bash
python -m app.seed.cli --delete-admin <user_id>
```

**Example:**
```bash
python -m app.seed.cli --delete-admin 123e4567-e89b-12d3-a456-426614174000
```

**Note:** Cannot deactivate the last active super admin. Create another super admin first.

---

## Password Requirements

When creating a super admin, password must meet:

- ✅ Minimum 10 characters
- ✅ At least one uppercase letter
- ✅ At least one lowercase letter
- ✅ At least one number
- ✅ At least one special character (!@#$%^&*(),.?":{}|<>)

**Example valid passwords:**
- `SecurePass123!@#`
- `MyPassword2024!`
- `Admin@123Secure`

---

## Troubleshooting

### Error: "Platform tenant not found"

**Solution:**
```bash
# Seed auth data first
python -m app.seed.cli --auth
```

### Error: "Super admin role not found"

**Solution:**
```bash
# Seed auth data first
python -m app.seed.cli --auth
```

### Error: "Super admin already exists"

**Solution:**
- Use `--force` flag to recreate:
  ```bash
  python -m app.seed.cli --create-admin --force
  ```
- Or use a different email address

### Error: "Password must be at least 10 characters"

**Solution:** Use a password that meets all requirements (see [Password Requirements](#password-requirements))

### Error: "Email and password required"

**Solution:**
- For interactive mode: Make sure you enter both email and password
- For env vars: Add `SUPER_ADMIN_EMAIL` and `SUPER_ADMIN_PASSWORD` to `.env` file

### Error: "Cannot deactivate the last active super admin"

**Solution:**
- Create another super admin first
- Then you can deactivate the previous one

---

## After Creating Super Admin

### 1. Login

**Using curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@1ne.ai",
    "password": "SecurePassword123!@#"
  }'
```

**Using API docs:**
- Visit: http://localhost:8000/docs
- Navigate to: `POST /api/v1/auth/login`
- Click "Try it out" and enter credentials

### 2. Get Access Token

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "email": "admin@1ne.ai",
    "roles": ["super_admin"]
  }
}
```

### 3. Use Token for Admin Operations

**Create another super admin:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/super-admins" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin2@1ne.ai",
    "password": "SecurePassword123!@#",
    "first_name": "Admin",
    "last_name": "Two",
    "role_name": "super_admin"
  }'
```

**List all super admins:**
```bash
curl -X GET "http://localhost:8000/api/v1/admin/super-admins" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

---

## Security Best Practices

1. ✅ **Change password after first login**
2. ✅ **Use strong passwords** (see [Password Requirements](#password-requirements))
3. ✅ **Never commit `.env` file** to version control
4. ✅ **In production**, use environment variables, not interactive mode
5. ✅ **Keep super admin credentials secure**
6. ✅ **Limit number of super admins** (recommended: 2-4)
7. ✅ **Regular access reviews** (quarterly)
8. ✅ **Use MFA** when available (future enhancement)

---

## Quick Reference

| Task | Command |
|------|---------|
| **Create super admin (interactive)** | `python -m app.seed.cli --create-admin --interactive` |
| **Create super admin (env vars)** | `python -m app.seed.cli --create-admin` |
| **List super admins** | `python -m app.seed.cli --list-admins` |
| **Update super admin** | `python -m app.seed.cli --update-admin <user_id>` |
| **Deactivate super admin** | `python -m app.seed.cli --delete-admin <user_id>` |
| **Seed auth data** | `python -m app.seed.cli --auth` |
| **Seed templates** | `python -m app.seed.cli --templates` |
| **Full setup** | `python -m app.seed.cli --auth --create-admin --interactive --templates` |
| **Show help** | `python -m app.seed.cli --help` |

---

## For New Developers

### First-Time Setup Checklist

- [ ] Database created and running
- [ ] `.env` file configured
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Migrations run (`alembic upgrade head`)
- [ ] Auth data seeded (`python -m app.seed.cli --auth`)
- [ ] Super admin created (`python -m app.seed.cli --create-admin --interactive`)
- [ ] Server started (`uvicorn app.main:app --reload`)
- [ ] Login tested (`POST /api/v1/auth/login`)

---

## Additional Resources

- [API Documentation](http://localhost:8000/docs) - Full API reference
- [Setup Guide](SETUP.md) - Complete setup instructions
- [README](README.md) - Project overview

---

## Need Help?

If you encounter issues:

1. Check [Troubleshooting](#troubleshooting) section
2. Verify all [Prerequisites](#prerequisites) are met
3. Check database connection and migrations
4. Review error messages carefully
5. Contact the development team

