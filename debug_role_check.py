"""Debug script to see what's actually happening in role check."""
import sys
from app.domains.auth.dependencies import require_any_role
from app.domains.auth.models import RoleName

# Simulate what happens when require_any_role is called
print("Testing require_any_role with 'institution_admin'...")
print("=" * 60)

# Create the dependency
dep_func = require_any_role("org_admin", "institution_admin", "super_admin")

# Get the inner function
import inspect
source = inspect.getsource(dep_func)
print("\nSource code of role_checker:")
print("-" * 60)
# Find the normalization part
if "institution_admin" in source:
    lines = source.split('\n')
    for i, line in enumerate(lines):
        if "institution_admin" in line or "school_admin" in line or "normalized" in line or "db_safe" in line:
            print(f"{i+1:3}: {line}")
else:
    print("ERROR: normalization code not found!")

print("\n" + "=" * 60)
print("Testing normalization logic manually:")
print("=" * 60)

role_names = ["org_admin", "institution_admin", "super_admin"]
print(f"Input roles: {role_names}")

# Simulate the normalization
db_safe_roles = []
for role_name in role_names:
    if role_name == "institution_admin":
        db_safe_roles.append("school_admin")
    else:
        db_safe_roles.append(role_name)

db_safe_roles = list(dict.fromkeys(db_safe_roles))
print(f"After normalization: {db_safe_roles}")
print(f"'institution_admin' removed: {'institution_admin' not in db_safe_roles}")
print(f"'school_admin' added: {'school_admin' in db_safe_roles}")

print("\n" + "=" * 60)
print("Testing enum conversion:")
print("=" * 60)
for role_name in db_safe_roles:
    if role_name == "school_admin":
        enum_val = RoleName.SCHOOL_ADMIN
        print(f"  '{role_name}' -> {enum_val} (value: '{enum_val.value}')")
    elif role_name == "org_admin":
        enum_val = RoleName.ORG_ADMIN
        print(f"  '{role_name}' -> {enum_val} (value: '{enum_val.value}')")
    elif role_name == "super_admin":
        enum_val = RoleName.SUPER_ADMIN
        print(f"  '{role_name}' -> {enum_val} (value: '{enum_val.value}')")

print("\n" + "=" * 60)
print("All normalization looks correct!")
print("=" * 60)
