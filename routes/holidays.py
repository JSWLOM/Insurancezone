"""
Holiday Management
Admin and Manager can declare / remove public holidays.
All authenticated staff can read holidays (needed for calendar display).
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime
from pydantic import BaseModel

from database import get_db
from utils.auth_deps import require_auth, admin_or_manager

router = APIRouter(prefix="/api/holidays", tags=["holidays"])


class HolidayCreate(BaseModel):
    date: str   # "YYYY-MM-DD"
    name: str   # "Diwali", "Eid", etc.


# ── Declare a holiday (admin / manager only) ──────────────────

@router.post("/", status_code=201)
async def declare_holiday(
    body: HolidayCreate,
    current_user: dict = Depends(admin_or_manager),
):
    body.name = body.name.strip()
    if not body.name:
        raise HTTPException(status_code=400, detail="Holiday name cannot be empty")

    # Validate date format loosely
    try:
        datetime.strptime(body.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must be in YYYY-MM-DD format")

    existing = await get_db()["holidays"].find_one({"date": body.date})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"'{existing['name']}' is already declared as a holiday on {body.date}",
        )

    doc = {
        "date":             body.date,
        "name":             body.name,
        "created_by":       current_user["id"],
        "created_by_name":  current_user["name"],
        "created_at":       datetime.utcnow(),
    }
    await get_db()["holidays"].insert_one(doc)
    return {"success": True, "date": body.date, "name": body.name}


# ── List holidays (any authenticated staff) ───────────────────

@router.get("/")
async def list_holidays(
    month: int = Query(default=None, ge=1, le=12),
    year:  int = Query(default=None),
    current_user: dict = Depends(require_auth),
):
    query: dict = {}
    if month and year:
        prefix = f"{year}-{month:02d}"
        query["date"] = {"$regex": f"^{prefix}"}

    holidays = []
    async for doc in get_db()["holidays"].find(query).sort("date", 1):
        doc["id"] = str(doc.pop("_id"))
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat() + "Z"
        holidays.append(doc)
    return holidays


# ── Remove a holiday (admin / manager only) ───────────────────

@router.delete("/{date}", status_code=200)
async def remove_holiday(
    date: str,
    current_user: dict = Depends(admin_or_manager),
):
    result = await get_db()["holidays"].delete_one({"date": date})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"No holiday found on {date}")
    return {"success": True, "message": f"Holiday on {date} has been removed"}