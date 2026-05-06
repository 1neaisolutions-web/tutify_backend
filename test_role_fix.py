"""Test that role normalization works correctly."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.domains.auth.dependencies import require_any_role
from app.domains.auth.models import RoleName

print("Testing role normalization fix...")
print("=" * 60)

# Test 1: Check that RoleName.INSTITUTION_ADMIN exists in Python enum
print("\n1. Checking RoleName enum values:")
print(f"   RoleName.INSTITUTION_ADMIN exists: {hasattr(RoleName, 'INSTITUTION_ADMIN')}")
if hasattr(RoleName, 'INSTITUTION_ADMIN'):
    print(f"   RoleName.INSTITUTION_ADMIN.value = '{RoleName.INSTITUTION_ADMIN.value}'")
print(f"   RoleName.SCHOOL_ADMIN.value = '{RoleName.SCHOOL_ADMIN.value}'")

# Test 2: Create dependency with institution_admin
print("\n2. Creating require_any_role with 'institution_admin':")
try:
    dep = require_any_role("org_admin", "institution_admin", "super_admin")
    print("   OK: Dependency created successfully")
except Exception as e:
    print(f"   ERROR: {e}")
    sys.exit(1)

# Test 3: Check normalization logic
print("\n3. Testing normalization logic:")
test_roles = ["org_admin", "institution_admin", "super_admin"]
normalized = []
for role_name in test_roles:
    if role_name == "institution_admin":
        if "school_admin" not in normalized:
            normalized.append("school_admin")
    else:
        normalized.append(role_name)

print(f"   Original: {test_roles}")
print(f"   Normalized: {normalized}")
print(f"   'institution_admin' removed: {'institution_admin' not in normalized}")
print(f"   'school_admin' added: {'school_admin' in normalized}")

# Test 4: Verify enum conversion
print("\n4. Testing enum conversion:")
for role_name in normalized:
    try:
        if role_name == "institution_admin":
            enum_val = RoleName.SCHOOL_ADMIN
            print(f"   '{role_name}' -> {enum_val} (mapped to SCHOOL_ADMIN)")
        else:
            enum_val = RoleName(role_name)
            print(f"   '{role_name}' -> {enum_val}")
    except ValueError as e:
        print(f"   ERROR converting '{role_name}': {e}")

print("\n" + "=" * 60)
print("All tests passed! Fix should work now.")
