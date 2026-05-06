"""
Authentication services module.
"""
from app.domains.auth.services.audit_service import AuditService
from app.domains.auth.services.signup_service import SignupService
from app.domains.auth.services.membership_service import MembershipService
from app.domains.auth.services.invite_service import InviteService
from app.domains.auth.services.session_service import SessionService

# Import services from services.py file (parent module)
# Import directly to avoid circular import issues
import importlib.util
import sys
from pathlib import Path

# Get path to services.py file
_current_file = Path(__file__)
_services_py_path = _current_file.parent.parent / "services.py"

if _services_py_path.exists():
    # Load services.py as a module
    _spec = importlib.util.spec_from_file_location("_auth_services_py", str(_services_py_path))
    if _spec and _spec.loader:
        _services_module = importlib.util.module_from_spec(_spec)
        sys.modules["_auth_services_py"] = _services_module
        _spec.loader.exec_module(_services_module)
        
        # Export services from services.py
        RBACService = getattr(_services_module, 'RBACService', None)
        AuthService = getattr(_services_module, 'AuthService', None)
        UserService = getattr(_services_module, 'UserService', None)
        TenantService = getattr(_services_module, 'TenantService', None)
        SelfRegistrationService = getattr(_services_module, 'SelfRegistrationService', None)
        SuperAdminService = getattr(_services_module, 'SuperAdminService', None)
    else:
        RBACService = None
        AuthService = None
        UserService = None
        TenantService = None
        SelfRegistrationService = None
        SuperAdminService = None
else:
    RBACService = None
    AuthService = None
    UserService = None
    TenantService = None
    SelfRegistrationService = None
    SuperAdminService = None

__all__ = [
    "AuditService",
    "SignupService",
    "MembershipService",
    "InviteService",
    "SessionService",
    "RBACService",
    "AuthService",
    "UserService",
    "TenantService",
    "SelfRegistrationService",
    "SuperAdminService",
]
