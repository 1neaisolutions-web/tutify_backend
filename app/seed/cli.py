"""
CLI script for seeding templates and auth data.
"""
import sys
import getpass
from typing import Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.seed.seed_templates import seed_templates
from app.seed.seeders.auth_seeder import seed_auth_data
from app.seed.seeders.subscription_seeder import seed_subscription_tiers
from app.seed.seeders.chatbot_seeder import seed_chatbots
from app.domains.auth.models import UserStatus


def create_super_admin_interactive(db: Session, created_by: Optional[str] = None):
    """Interactive super admin creation."""
    from app.domains.auth.services import SuperAdminService
    from app.domains.auth.models import Tenant, TenantType
    
    print("=" * 60)
    print("Creating Super Admin User")
    print("=" * 60)
    print()
    
    email = input("Email address: ").strip()
    if not email:
        print("[ERROR] Email is required")
        sys.exit(1)
    
    password = getpass.getpass("Password: ")
    if len(password) < 10:
        print("[ERROR] Password must be at least 10 characters")
        sys.exit(1)
    
    password_confirm = getpass.getpass("Password (again): ")
    if password != password_confirm:
        print("[ERROR] Passwords do not match")
        sys.exit(1)
    
    first_name = input("First name (default: Super): ").strip() or "Super"
    last_name = input("Last name (default: Admin): ").strip() or "Admin"
    phone = input("Phone (optional): ").strip() or None
    
    # Get creator ID (use None for first admin since no user exists yet)
    if created_by:
        from uuid import UUID
        creator_id = UUID(created_by)
    else:
        # For first admin, use None since granted_by is nullable
        creator_id = None
    
    super_admin_service = SuperAdminService(db)
    try:
        user = super_admin_service.create_super_admin(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            created_by=creator_id,
        )
        print()
        print("[SUCCESS] Super admin created successfully!")
        print(f"   Email: {user.email}")
        print(f"   User ID: {user.id}")
        print()
        print("[WARNING] IMPORTANT: Change password after first login!")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        print(f"\nFull error details:")
        traceback.print_exc()
        sys.exit(1)


def list_super_admins(db: Session):
    """List all super admins."""
    from app.domains.auth.services import SuperAdminService
    
    super_admin_service = SuperAdminService(db)
    users, total = super_admin_service.list_super_admins(include_inactive=True)
    
    print("=" * 60)
    print(f"Super Admins ({total} total)")
    print("=" * 60)
    
    if not users:
        print("No super admins found.")
        return
    
    for user in users:
        status_icon = "[ACTIVE]" if user.status == UserStatus.ACTIVE else "[INACTIVE]"
        print(f"{status_icon} {user.email}")
        print(f"   Name: {user.full_name}")
        print(f"   Status: {user.status}")
        print(f"   User ID: {user.id}")
        print(f"   Last Login: {user.last_login_at or 'Never'}")
        print()


def update_super_admin_interactive(db: Session, user_id: str):
    """Interactive super admin update."""
    from app.domains.auth.services import SuperAdminService
    from app.domains.auth.schemas import UserUpdate
    from uuid import UUID
    
    super_admin_service = SuperAdminService(db)
    user = super_admin_service.get_super_admin(UUID(user_id))
    
    if not user:
        print(f"[ERROR] Super admin not found: {user_id}")
        sys.exit(1)
    
    print("=" * 60)
    print(f"Updating Super Admin: {user.email}")
    print("=" * 60)
    print()
    print("Press Enter to keep current value")
    print()
    
    # Ask if user wants to change password
    change_password = input("Change password? (y/n) [n]: ").strip().lower()
    if change_password == 'y':
        password = getpass.getpass("New password: ")
        if len(password) < 10:
            print("[ERROR] Password must be at least 10 characters")
            sys.exit(1)
        
        password_confirm = getpass.getpass("Password (again): ")
        if password != password_confirm:
            print("[ERROR] Passwords do not match")
            sys.exit(1)
        
        try:
            super_admin_service.change_super_admin_password(
                user_id=user.id,
                new_password=password,
                changed_by=user.id,  # Self-update for CLI
            )
            print()
            print("[SUCCESS] Password changed successfully!")
        except Exception as e:
            print(f"[ERROR] Error changing password: {e}")
            sys.exit(1)
    
    first_name = input(f"First name [{user.first_name}]: ").strip() or user.first_name
    last_name = input(f"Last name [{user.last_name}]: ").strip() or user.last_name
    phone = input(f"Phone [{user.phone or 'None'}]: ").strip() or user.phone
    
    update_request = UserUpdate(
        first_name=first_name if first_name != user.first_name else None,
        last_name=last_name if last_name != user.last_name else None,
        phone=phone if phone != user.phone else None,
    )
    
    try:
        updated_user = super_admin_service.update_super_admin(
            user_id=user.id,
            request=update_request,
            updated_by=user.id,  # Self-update for CLI
        )
        print()
        print("[SUCCESS] Super admin updated successfully!")
        print(f"   Email: {updated_user.email}")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        sys.exit(1)


def delete_super_admin_interactive(db: Session, user_id: str):
    """Interactive super admin deletion."""
    from app.domains.auth.services import SuperAdminService
    from app.domains.auth.models import Tenant, TenantType
    from uuid import UUID
    
    super_admin_service = SuperAdminService(db)
    user = super_admin_service.get_super_admin(UUID(user_id))
    
    if not user:
        print(f"[ERROR] Super admin not found: {user_id}")
        sys.exit(1)
    
    print("=" * 60)
    print(f"Deactivating Super Admin: {user.email}")
    print("=" * 60)
    print()
    print("[WARNING] WARNING: This will deactivate the super admin account.")
    
    # Check if last admin
    active_admins, count = super_admin_service.list_super_admins(include_inactive=False)
    if count <= 1:
        print("[ERROR] ERROR: Cannot deactivate the last active super admin!")
        print("   Create another super admin first.")
        sys.exit(1)
    
    confirm = input("Are you sure? (type 'yes' to confirm): ").strip().lower()
    if confirm != 'yes':
        print("Cancelled.")
        return
    
    reason = input("Reason (optional): ").strip() or None
    
    # Use platform tenant ID as deactivated_by for CLI operations
    platform = db.query(Tenant).filter(Tenant.type == TenantType.PLATFORM).first()
    deactivated_by = platform.id if platform else user.id
    
    try:
        super_admin_service.deactivate_super_admin(
            user_id=user.id,
            deactivated_by=deactivated_by,
            reason=reason,
        )
        print()
        print("[SUCCESS] Super admin deactivated successfully!")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    # Show help if requested
    if "--help" in sys.argv or "-h" in sys.argv:
        help_text = """
================================================================================
          1ne.ai Backend - Database Seeding CLI
================================================================================

USAGE:
    python -m app.seed.cli [OPTIONS]

OPTIONS:
    --auth                    Seed auth data (roles, permissions, platform tenant)
    --templates               Seed templates
    --subscriptions           Seed subscription tiers and features
    --chatbots                Seed chatbots, models, and capabilities
    --create-admin            Create super admin from environment variables
    --create-admin --interactive    Create super admin interactively (recommended)
    --list-admins             List all super admins
    --update-admin <user_id>  Update super admin information
    --delete-admin <user_id>  Deactivate super admin
    --force                   Force recreate existing data
    --help, -h                Show this help message

EXAMPLES:
    # First-time setup (recommended)
    python -m app.seed.cli --auth --create-admin --interactive

    # Create super admin interactively
    python -m app.seed.cli --create-admin --interactive

    # Create super admin from .env variables
    python -m app.seed.cli --create-admin

    # List all super admins
    python -m app.seed.cli --list-admins

    # Update super admin
    python -m app.seed.cli --update-admin <user_id>

    # Deactivate super admin
    python -m app.seed.cli --delete-admin <user_id>

    # Seed everything
    python -m app.seed.cli --auth --templates

    # Full setup with super admin
    python -m app.seed.cli --auth --create-admin --interactive --templates

DOCUMENTATION:
    For detailed super admin guide, see: SUPER_ADMIN_GUIDE.md
    For setup instructions, see: SETUP.md
    For project overview, see: README.md
        """
        print(help_text)
        sys.exit(0)
    
    force = "--force" in sys.argv
    create_admin = "--create-admin" in sys.argv
    list_admins = "--list-admins" in sys.argv
    update_admin = "--update-admin" in sys.argv
    delete_admin = "--delete-admin" in sys.argv
    
    interactive = "--interactive" in sys.argv or (create_admin and len(sys.argv) == 2)
    
    # Determine what to seed
    seed_auth = "--auth" in sys.argv
    seed_templates_flag = "--templates" in sys.argv
    seed_subscriptions = "--subscriptions" in sys.argv
    seed_chatbots_flag = "--chatbots" in sys.argv
    
    db: Session = SessionLocal()
    try:
        if seed_auth:
            print("Seeding auth data (roles, permissions, platform tenant)...")
            auth_result = seed_auth_data(db, force=force)
            print(f"Auth seeding complete!")
            print(f"  Platform tenant created: {auth_result['platform_tenant_created']}")
            print(f"  Roles created: {auth_result['roles_created']}")
            print(f"  Permissions created: {auth_result['permissions_created']}")
            print(f"  Role-permission mappings: {auth_result['role_permissions_created']}")
            print()
        
        if list_admins:
            list_super_admins(db)
        
        if create_admin:
            if interactive:
                create_super_admin_interactive(db)
            else:
                from app.seed.seeders.admin_seeder import seed_super_admin
                from app.core.config import settings
                
                print("Creating super admin user...")
                admin_result = seed_super_admin(db, force=force)
                
                if admin_result["created"]:
                    print(f"✅ Super admin created successfully!")
                    print(f"   Email: {admin_result['email']}")
                    print(f"   User ID: {admin_result['user_id']}")
                elif admin_result["skipped"]:
                    print(f"[WARNING] Super admin already exists: {admin_result.get('email', 'N/A')}")
                    print("   Use --force to recreate")
                elif admin_result["error"]:
                    print(f"❌ Error: {admin_result['error']}")
                    sys.exit(1)
                print()
        
        if update_admin:
            if len(sys.argv) < 3:
                print("[ERROR] Usage: python -m app.seed.cli --update-admin <user_id>")
                sys.exit(1)
            update_super_admin_interactive(db, sys.argv[2])
        
        if delete_admin:
            if len(sys.argv) < 3:
                print("[ERROR] Usage: python -m app.seed.cli --delete-admin <user_id>")
                sys.exit(1)
            delete_super_admin_interactive(db, sys.argv[2])
        
        if seed_templates_flag and not any([list_admins, update_admin, delete_admin]):
            print("Seeding templates...")
            template_result = seed_templates(db, force=force)
            print(f"Template seeding complete!")
            print(f"  Templates created: {template_result['templates_created']}")
            print(f"  Templates skipped: {template_result['templates_skipped']}")
            print(f"  Versions created: {template_result['versions_created']}")
            print(f"  Versions skipped: {template_result['versions_skipped']}")
            print()

        if seed_subscriptions and not any([list_admins, update_admin, delete_admin]):
            print("Seeding subscription tiers and features...")
            subscription_result = seed_subscription_tiers(db, force=force)
            print(f"Subscription seeding complete!")
            print(f"  Tiers created: {subscription_result['tiers_created']}")
            print(f"  Tiers skipped: {subscription_result['tiers_skipped']}")
            print(f"  Features created: {subscription_result['features_created']}")
            print(f"  Features skipped: {subscription_result['features_skipped']}")
            print()

        if seed_chatbots_flag and not any([list_admins, update_admin, delete_admin]):
            print("Seeding chatbots...")
            chatbot_result = seed_chatbots(db, force=force)
            print(f"Chatbot seeding complete!")
            print(f"  Chatbots created: {chatbot_result['chatbots_created']}")
            print(f"  Chatbots skipped: {chatbot_result['chatbots_skipped']}")
            print(f"  Models assigned: {chatbot_result['models_created']}")
            print(f"  Capabilities created: {chatbot_result['capabilities_created']}")
            print()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
