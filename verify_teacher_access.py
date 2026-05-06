"""Verify teacher role and test access."""
import sys
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.auth.models import User, Role, UserRole, RoleName

def verify_teacher_access(email: str):
    """Verify user has teacher role and show details."""
    db: Session = SessionLocal()
    try:
        # Get user
        user = db.query(User).filter(User.email == email.lower()).first()
        if not user:
            print(f"❌ User not found: {email}")
            return False
        
        print(f"✅ User found: {user.email}")
        print(f"   User ID: {user.id}")
        print(f"   Tenant ID: {user.tenant_id}")
        print()
        
        # Get all user roles
        user_roles = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user.id,
            UserRole.tenant_id == user.tenant_id
        ).all()
        
        print(f"User Roles ({len(user_roles)} total):")
        has_teacher = False
        for ur in user_roles:
            role_name = ur.role.name if ur.role else "Unknown"
            print(f"   - {role_name} (Role ID: {ur.role_id}, Tenant: {ur.tenant_id})")
            if role_name == RoleName.TEACHER or str(role_name) == "teacher":
                has_teacher = True
        
        print()
        
        if not has_teacher:
            print("❌ User does NOT have teacher role!")
            print()
            print("Assigning teacher role now...")
            
            # Get teacher role
            teacher_role = db.query(Role).filter(Role.name == RoleName.TEACHER).first()
            if not teacher_role:
                print("❌ Teacher role not found in database!")
                return False
            
            # Assign teacher role
            new_user_role = UserRole(
                user_id=user.id,
                role_id=teacher_role.id,
                tenant_id=user.tenant_id,
                granted_by=None
            )
            db.add(new_user_role)
            db.commit()
            print("✅ Teacher role assigned!")
        else:
            print("✅ User HAS teacher role!")
        
        # Verify the role check query that require_any_role uses
        print()
        print("Testing role check query (same as require_any_role)...")
        from sqlalchemy import or_
        
        role_filters = [
            Role.name == RoleName.ORG_ADMIN,
            Role.name == RoleName.SCHOOL_ADMIN,
            Role.name == RoleName.SUPER_ADMIN,
            Role.name == RoleName.TEACHER,
        ]
        combined_filter = or_(*role_filters)
        
        matching_role = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user.id,
            UserRole.tenant_id == user.tenant_id,
            combined_filter,
        ).first()
        
        if matching_role:
            print(f"✅ Role check query SUCCESS!")
            print(f"   Found matching role: {matching_role.role.name}")
        else:
            print("❌ Role check query FAILED!")
            print("   This means require_any_role will fail!")
            print()
            print("   Debugging info:")
            print(f"   - User ID: {user.id}")
            print(f"   - Tenant ID: {user.tenant_id}")
            print(f"   - Looking for roles: org_admin, school_admin, super_admin, teacher")
            
            # Check if tenant_id is the issue
            all_user_roles = db.query(UserRole).filter(UserRole.user_id == user.id).all()
            print(f"   - User has {len(all_user_roles)} role assignments total")
            for ur in all_user_roles:
                role = db.query(Role).filter(Role.id == ur.role_id).first()
                print(f"     * {role.name if role else 'Unknown'} (Tenant: {ur.tenant_id})")
        
        return matching_role is not None
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    email = "owais.naseer.dev@gmail.com"
    
    print("=" * 70)
    print("VERIFY TEACHER ACCESS")
    print("=" * 70)
    print()
    
    success = verify_teacher_access(email)
    
    print()
    print("=" * 70)
    if success:
        print("✅ User should have access to content packs!")
        print("   If still getting errors, RESTART the backend server.")
    else:
        print("❌ User does NOT have proper access!")
        print("   Check the errors above.")
    print("=" * 70)
