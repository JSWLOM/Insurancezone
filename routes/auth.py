from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from bson import ObjectId

from database import users_col, refresh_tokens_col, offices_col
from models.user import (
    UserCreate, UserOut, UserUpdate,
    LoginRequest, TokenResponse, RefreshRequest, AccessTokenResponse,
)
from utils.jwt_handler import (
    hash_password, verify_password,
    create_access_token,
    generate_refresh_token, refresh_token_expiry,
)
from utils.auth_deps import require_auth, admin_only

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Register (admin only) ─────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    body: UserCreate,
    current_user: dict = Depends(admin_only),
):
    existing = await users_col().find_one({"email": body.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email {body.email} is already registered",
        )

    # Validate office_id if provided
    if body.office_id:
        office = await offices_col().find_one({"_id": ObjectId(body.office_id)})
        if not office:
            raise HTTPException(status_code=400, detail="office_id does not match any existing office")

    doc = {
        "name":            body.name,
        "email":           body.email,
        "hashed_password": hash_password(body.password),
        "role":            body.role,
        "department":      body.department,
        "phone":           body.phone,
        "is_active":       True,
        "office_id":       body.office_id or None,    # ← store office assignment
        "created_at":      datetime.utcnow(),
        "created_by":      current_user["id"],
    }
    result = await users_col().insert_one(doc)
    doc["id"] = str(result.inserted_id)

    # Attach office_name for the response
    doc["office_name"] = office["name"] if body.office_id else None
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

    refresh_token = generate_refresh_token()
    await refresh_tokens_col().insert_one({
        "token":      refresh_token,
        "user_id":    user_id,
        "expires_at": refresh_token_expiry(),
        "created_at": datetime.utcnow(),
    })

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=user["role"],
        name=user["name"],
        user_id=user_id,
        office_id=user.get("office_id"),              # ← included in login response
    )


# ── Refresh access token ──────────────────────────────────────

@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_access_token(body: RefreshRequest):
    stored = await refresh_tokens_col().find_one({"token": body.refresh_token})
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token. Please log in again.",
        )

    if datetime.utcnow() > stored["expires_at"]:
        await refresh_tokens_col().delete_one({"token": body.refresh_token})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired. Please log in again.",
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
    await refresh_tokens_col().delete_one({"token": body.refresh_token})


# ── Current user ──────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
async def get_me(current_user: dict = Depends(require_auth)):
    # Optionally enrich with office_name
    if current_user.get("office_id"):
        office = await offices_col().find_one({"_id": ObjectId(current_user["office_id"])})
        current_user["office_name"] = office["name"] if office else None
    return _format_user(current_user)


# ── List all staff (admin / manager) ─────────────────────────

@router.get("/users")
async def list_users(current_user: dict = Depends(require_auth)):
    if current_user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Collect all users first
    user_list = []
    async for u in users_col().find({}, {"hashed_password": 0}):
        user_list.append(u)

    # Batch-fetch office names in one query (avoid N+1)
    office_ids = list({u["office_id"] for u in user_list if u.get("office_id")})
    office_map: dict[str, str] = {}
    if office_ids:
        async for o in offices_col().find(
            {"_id": {"$in": [ObjectId(oid) for oid in office_ids]}}
        ):
            office_map[str(o["_id"])] = o["name"]

    # Attach office_name to each user dict before formatting
    result = []
    for u in user_list:
        u["office_name"] = office_map.get(u.get("office_id") or "", None)
        result.append(_format_user(u))

    return result


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

    # ── Password reset: hash before storing, never save plaintext ──
    if "password" in updates:
        updates["hashed_password"] = hash_password(updates.pop("password"))

    # If reassigning office, validate it exists
    if "office_id" in updates and updates["office_id"]:
        office = await offices_col().find_one({"_id": ObjectId(updates["office_id"])})
        if not office:
            raise HTTPException(status_code=400, detail="office_id does not match any existing office")

    result = await users_col().find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="User not found")

    # Attach office_name
    if result.get("office_id"):
        office = await offices_col().find_one({"_id": ObjectId(result["office_id"])})
        result["office_name"] = office["name"] if office else None

    return _format_user(result)


# ── Delete user (admin only) ──────────────────────────────────

@router.delete("/users/{user_id}", status_code=200)
async def delete_user(
    user_id: str,
    current_user: dict = Depends(admin_only),
):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    user = await users_col().find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await users_col().delete_one({"_id": ObjectId(user_id)})
    await refresh_tokens_col().delete_many({"user_id": user_id})

    return {
        "success": True,
        "message": f"{user['name']} has been permanently removed.",
    }


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
        office_id=u.get("office_id"),
        office_name=u.get("office_name"),              # only populated by list_users / get_me
    )