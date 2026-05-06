"""Assign teacher role to a user if they don't have it."""
import sys
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.auth.models import User, Role, UserRole, RoleName
from uuid import UUID

def assign_teacher_role(email: str):
    """Assign teacher role to user by email."""
    db: Session = SessionLocal()
    try:
        # Get user
        user = db.query(User).filter(User.email == email.lower()).first()
        if not user:
            print(f"❌ User not found: {email}")
            return False
        
        print(f"✅ Found user: {user.email} (ID: {user.id})")
        print(f"   Tenant ID: {user.tenant_id}")
        
        # Get teacher role
        teacher_role = db.query(Role).filter(Role.name == RoleName.TEACHER).first()
        if not teacher_role:
            print("❌ Teacher role not found in database!")
            print("   Run database migrations/seeds to create roles.")
            return False
        
        print(f"✅ Found teacher role: {teacher_role.name} (ID: {teacher_role.id})")
        
        # Check if user already has teacher role
        existing_role = db.query(UserRole).filter(
            UserRole.user_id == user.id,
            UserRole.role_id == teacher_role.id,
            UserRole.tenant_id == user.tenant_id
        ).first()
        
        if existing_role:
            print("✅ User already has teacher role assigned")
            return True
        
        # Assign teacher role
        user_role = UserRole(
            user_id=user.id,
            role_id=teacher_role.id,
            tenant_id=user.tenant_id,
            granted_by=None
        )
        db.add(user_role)
        db.commit()
        db.refresh(user_role)
        
        print("✅ Teacher role assigned successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        email = sys.argv[1]
    else:
        email = "owais.naseer.dev@gmail.com"  # Default email
    
    print("=" * 70)
    print("ASSIGN TEACHER ROLE")
    print("=" * 70)
    print()
    print(f"Assigning teacher role to: {email}")
    print()
    
    success = assign_teacher_role(email)
    
    print()
    print("=" * 70)
    if success:
        print("✅ DONE! User now has teacher role.")
        print("   Restart backend server and try accessing worksheet page again.")
    else:
        print("❌ FAILED! Check errors above.")
    print("=" * 70)
