"""
Office Management
-----------------
Admin can create, edit, and delete offices.
Admin + Manager can list offices and view staff per office.
All authenticated staff can fetch their own assigned office (/mine) —
this is what the GPS punch uses to get geo-fence coordinates.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime
from bson import ObjectId

from database import offices_col, users_col
from models.office import OfficeCreate, OfficeUpdate
from utils.auth_deps import require_auth, admin_only, admin_or_manager

router = APIRouter(prefix="/api/offices", tags=["offices"])


# ── Create office (admin only) ────────────────────────────────

@router.post("/", status_code=201)
async def create_office(
    body: OfficeCreate,
    current_user: dict = Depends(admin_only),
):
    doc = body.model_dump()
    doc["created_by"]      = current_user["id"]
    doc["created_by_name"] = current_user["name"]
    doc["created_at"]      = datetime.utcnow()

    result = await offices_col().insert_one(doc)
    doc["id"] = str(result.inserted_id)
    _fmt(doc)
    return doc


# ── List all offices (any authenticated staff) ────────────────

@router.get("/")
async def list_offices(current_user: dict = Depends(require_auth)):
    """
    Returns all offices with a live staff_count.
    Accessible to all roles — staff see it when the frontend
    needs to display their office name.
    """
    offices = []
    async for doc in offices_col().find({}).sort("name", 1):
        doc["id"] = str(doc.pop("_id"))
        # Count active staff assigned to this office
        doc["staff_count"] = await users_col().count_documents(
            {"office_id": doc["id"], "is_active": True}
        )
        _fmt(doc)
        offices.append(doc)
    return offices


# ── Get own assigned office (any authenticated staff) ─────────

@router.get("/mine")
async def my_office(current_user: dict = Depends(require_auth)):
    """
    Returns the office assigned to the current user.
    The GPS punch-in/out endpoints use this same lookup internally;
    this route is exposed so the frontend can display the office
    name and radius in the punch panel before the user taps punch.
    """
    office_id = current_user.get("office_id")
    if not office_id:
        raise HTTPException(
            status_code=404,
            detail="No office assigned to your account. Ask your admin to assign one.",
        )
    office = await offices_col().find_one({"_id": ObjectId(office_id)})
    if not office:
        raise HTTPException(
            status_code=404,
            detail="Your assigned office no longer exists. Contact admin.",
        )
    office["id"] = str(office.pop("_id"))
    _fmt(office)
    return office


# ── Get single office (admin / manager) ───────────────────────

@router.get("/{office_id}")
async def get_office(
    office_id: str,
    current_user: dict = Depends(admin_or_manager),
):
    office = await offices_col().find_one({"_id": ObjectId(office_id)})
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")
    office["id"] = str(office.pop("_id"))
    office["staff_count"] = await users_col().count_documents(
        {"office_id": office_id, "is_active": True}
    )
    _fmt(office)
    return office


# ── Update office (admin only) ────────────────────────────────

@router.patch("/{office_id}")
async def update_office(
    office_id: str,
    body: OfficeUpdate,
    current_user: dict = Depends(admin_only),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await offices_col().find_one_and_update(
        {"_id": ObjectId(office_id)},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Office not found")

    result["id"] = str(result.pop("_id"))
    _fmt(result)
    return result


# ── Delete office (admin only) ────────────────────────────────

@router.delete("/{office_id}")
async def delete_office(
    office_id: str,
    current_user: dict = Depends(admin_only),
):
    """
    Blocked if any staff (active or inactive) are still assigned.
    Admin must reassign or remove those employees first.
    """
    assigned = await users_col().count_documents({"office_id": office_id})
    if assigned > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot delete — {assigned} employee(s) are still assigned to this office. "
                "Reassign them to another office first."
            ),
        )

    result = await offices_col().delete_one({"_id": ObjectId(office_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Office not found")

    return {"success": True, "message": "Office deleted successfully"}


# ── List staff for a specific office (admin / manager) ────────

@router.get("/{office_id}/staff")
async def office_staff(
    office_id: str,
    current_user: dict = Depends(admin_or_manager),
):
    """All active employees assigned to the given office."""
    staff = []
    async for u in users_col().find(
        {"office_id": office_id, "is_active": True},
        {"hashed_password": 0},
    ):
        u["id"] = str(u.pop("_id"))
        staff.append(u)
    return staff


# ── Assign employee to office (admin only) ────────────────────

@router.patch("/{office_id}/assign/{user_id}")
async def assign_employee(
    office_id: str,
    user_id: str,
    current_user: dict = Depends(admin_only),
):
    """
    Move an employee to this office.
    Can also be done via PATCH /api/auth/users/{id} with office_id in the body,
    but this dedicated endpoint is cleaner for the offices UI.
    """
    # Verify office exists
    office = await offices_col().find_one({"_id": ObjectId(office_id)})
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")

    # Verify user exists
    user = await users_col().find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found")

    await users_col().update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"office_id": office_id}},
    )

    return {
        "success":     True,
        "employee":    user["name"],
        "assigned_to": office["name"],
    }


# ── Helper ─────────────────────────────────────────────────────

def _fmt(doc: dict):
    if isinstance(doc.get("created_at"), datetime):
        doc["created_at"] = doc["created_at"].isoformat() + "Z"