from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from bson import ObjectId

from database import users_col, refresh_tokens_col
from models.user import (
    UserCreate, UserOut, UserUpdate,
    LoginRequest, TokenResponse, RefreshRequest, AccessTokenResponse,
)
from utils.jwt_handler import (
    hash_password, verify_password,
    create_access_token, decode_access_token,
    generate_refresh_token, refresh_token_expiry,
)
from utils.auth_deps import require_auth, admin_only

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Register (admin-only) ─────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    body: UserCreate,
    current_user: dict = Depends(admin_only),
):
    """
    Create a new staff account.  Only admins can do this.
    """
    existing = await users_col().find_one({"email": body.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email {body.email} is already registered",
        )

    doc = {
        "name": body.name,
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "role": body.role,
        "department": body.department,
        "phone": body.phone,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "created_by": current_user["id"],
    }
    result = await users_col().insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return _format_user(doc)


# ── Login ─────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    user = await users_col().find_one({"email": body.email})

    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact admin.",
        )

    user_id = str(user["_id"])

    access_token = create_access_token(
        user_id=user_id,
        email=user["email"],
        role=user["role"],
        name=user["name"],
    )

    # Generate opaque refresh token and store in DB
    refresh_token = generate_refresh_token()
    await refresh_tokens_col().insert_one({
        "token": refresh_token,
        "user_id": user_id,
        "expires_at": refresh_token_expiry(),
        "created_at": datetime.utcnow(),
    })

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=user["role"],
        name=user["name"],
        user_id=user_id,
    )


# ── Refresh access token ──────────────────────────────────────

@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_access_token(body: RefreshRequest):
    """
    Exchange a valid refresh token for a new short-lived access token.
    The refresh token itself is NOT rotated here (keep it simple for small team).
    """
    stored = await refresh_tokens_col().find_one({"token": body.refresh_token})
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token. Please log in again.",
        )

    # Check expiry manually (TTL index removes it from DB eventually,
    # but let's be explicit)
    if datetime.utcnow() > stored["expires_at"]:
        await refresh_tokens_col().delete_one({"token": body.refresh_token})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please log in again.",
        )

    user = await users_col().find_one({"_id": ObjectId(stored["user_id"])})
    if not user or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )

    access_token = create_access_token(
        user_id=str(user["_id"]),
        email=user["email"],
        role=user["role"],
        name=user["name"],
    )
    return AccessTokenResponse(access_token=access_token)


# ── Logout ────────────────────────────────────────────────────

@router.post("/logout", status_code=204)
async def logout(body: RefreshRequest):
    """Revoke the refresh token — client should also discard the access token."""
    await refresh_tokens_col().delete_one({"token": body.refresh_token})
    # Always return 204 regardless — don't leak whether token existed


# ── Current user ──────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
async def get_me(current_user: dict = Depends(require_auth)):
    return _format_user(current_user)


# ── List all staff (admin/manager) ────────────────────────────

@router.get("/users")
async def list_users(current_user: dict = Depends(require_auth)):
    if current_user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    cursor = users_col().find({}, {"hashed_password": 0})
    users = []
    async for u in cursor:
        users.append(_format_user(u))
    return users


# ── Update user (admin only) ──────────────────────────────────

@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdate,
    current_user: dict = Depends(admin_only),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await users_col().find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return _format_user(result)


# ── Helper ────────────────────────────────────────────────────

def _format_user(u: dict) -> UserOut:
    return UserOut(
        id=str(u.get("_id", u.get("id", ""))),
        name=u["name"],
        email=u["email"],
        role=u["role"],
        department=u.get("department", ""),
        phone=u.get("phone", ""),
        is_active=u.get("is_active", True),
        created_at=u.get("created_at", datetime.utcnow()),
    )