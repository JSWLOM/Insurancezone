"""
FastAPI dependency functions for authentication and role-based access control.

Usage in routes:
    from utils.auth_deps import require_auth, require_roles

    @router.get("/admin-only")
    async def admin_endpoint(current_user = Depends(require_roles("admin"))):
        ...

    @router.get("/any-staff")
    async def staff_endpoint(current_user = Depends(require_auth)):
        ...
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from utils.jwt_handler import decode_access_token
from database import users_col
from bson import ObjectId

security = HTTPBearer()


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Validates the Bearer token and returns the current user dict from MongoDB.
    Raises 401 if token is missing, invalid, or expired.
    Raises 403 if the user account has been deactivated.
    """
    token = credentials.credentials
    payload = decode_access_token(token)   # raises 401 on failure

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token — missing subject",
        )

    # Re-fetch from DB on every request so deactivation takes immediate effect.
    # For a team of < 10 this is negligible overhead.
    user = await users_col().find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
        )
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been deactivated. Contact your admin.",
        )

    # Attach string id for downstream use
    user["id"] = str(user["_id"])
    return user


def require_roles(*roles: str):
    """
    Factory that returns a dependency checking the user has one of the given roles.

    Example:
        Depends(require_roles("admin", "manager"))
    """
    async def _check(current_user: dict = Depends(require_auth)) -> dict:
        if current_user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(roles)}",
            )
        return current_user
    return _check


# ── Convenience aliases ───────────────────────────────────────
admin_only       = require_roles("admin")
admin_or_manager = require_roles("admin", "manager")
all_staff        = require_auth          # any authenticated user