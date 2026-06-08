from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime, date, timezone, timedelta
from bson import ObjectId

# India Standard Time — so "today" is always IST, not Render server time (Singapore UTC+8)
IST = timezone(timedelta(hours=5, minutes=30))

from database import leaves_col, leave_balances_col, users_col, attendance_col
from models.leave import LeaveApplyRequest, LeaveActionRequest, LEAVE_ENTITLEMENTS
from utils.sheets import sync_leave
from utils.auth_deps import require_auth, admin_or_manager

router = APIRouter(prefix="/api/leave", tags=["leave"])


# ── Employee: apply for leave ─────────────────────────────────

@router.post("/apply", status_code=201)
async def apply_leave(
    body: LeaveApplyRequest,
    current_user: dict = Depends(require_auth),
):
    try:
        start = date.fromisoformat(body.start_date)
        end   = date.fromisoformat(body.end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD format")

    if start > end:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    if start < datetime.now(IST).date():
        raise HTTPException(status_code=400, detail="Cannot apply leave for past dates")

    total_days = _count_working_days(start, end)
    if total_days == 0:
        raise HTTPException(status_code=400, detail="No working days in selected range")

    # Check balance for annual leave
    if body.leave_type == "annual":
        balance = await _get_or_create_balance(
            current_user["id"], current_user["name"]
        )
        available = balance.get("annual_total", 0) - balance.get("annual_used", 0)
        if total_days > available:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient annual leave. Available: {available} day(s), Requested: {total_days} day(s).",
            )

    # Check no overlapping pending/approved leave for same employee
    overlap = await leaves_col().find_one({
        "employee_id": current_user["id"],
        "status": {"$in": ["pending", "approved"]},
        "$or": [
            {"start_date": {"$lte": body.end_date}, "end_date": {"$gte": body.start_date}}
        ]
    })
    if overlap:
        raise HTTPException(
            status_code=400,
            detail=f"You already have a {overlap['status']} leave overlapping these dates."
        )

    doc = {
        "employee_id":    current_user["id"],
        "employee_name":  current_user["name"],
        "employee_email": current_user["email"],
        "leave_type":     body.leave_type,
        "start_date":     body.start_date,
        "end_date":       body.end_date,
        "total_days":     total_days,
        "reason":         body.reason,
        "status":         "pending",
        "applied_at":     datetime.utcnow(),
        "actioned_by":      None,
        "actioned_by_name": None,
        "actioned_at":      None,
        "rejection_reason": None,
    }
    result = await leaves_col().insert_one(doc)

    return {
        "success":   True,
        "leave_id":  str(result.inserted_id),
        "total_days": total_days,
        "message":   f"Leave application submitted. Pending approval ({total_days} working day(s)).",
    }


# ── Admin/Manager: approve or reject ─────────────────────────

@router.patch("/{leave_id}/action")
async def action_leave(
    leave_id: str,
    body: LeaveActionRequest,
    current_user: dict = Depends(admin_or_manager),
):
    leave = await leaves_col().find_one({"_id": ObjectId(leave_id)})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if leave["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"This leave is already {leave['status']}"
        )

    now = datetime.utcnow()
    new_status = "approved" if body.action == "approve" else "rejected"

    updates = {
        "status":           new_status,
        "actioned_by":      current_user["id"],
        "actioned_by_name": current_user["name"],
        "actioned_at":      now,
    }
    if body.rejection_reason:
        updates["rejection_reason"] = body.rejection_reason

    await leaves_col().update_one({"_id": ObjectId(leave_id)}, {"$set": updates})

    if body.action == "approve":
        await _deduct_balance(leave["employee_id"], leave["leave_type"], leave["total_days"])
        await _mark_attendance_on_leave(leave)

    final = {**leave, **updates}
    final["applied_at"] = leave["applied_at"].isoformat() + 'Z' if isinstance(leave.get("applied_at"), datetime) else ""
    await sync_leave(final)

    return {
        "success": True,
        "status":  new_status,
        "message": f"Leave {new_status} successfully.",
    }


# ── Admin/Manager: list all leaves ───────────────────────────

@router.get("/")
async def list_leaves(
    status:      str | None = Query(default=None),
    employee_id: str | None = Query(default=None),
    limit:       int        = Query(default=50, le=200),
    current_user: dict = Depends(admin_or_manager),
):
    query: dict = {}
    if status:      query["status"]      = status
    if employee_id: query["employee_id"] = employee_id

    results = []
    async for doc in leaves_col().find(query).sort("applied_at", -1).limit(limit):
        doc["id"] = str(doc.pop("_id"))
        _fmt(doc)
        results.append(doc)
    return results


# ── Employee: own leave history ───────────────────────────────

@router.get("/me")
async def my_leaves(current_user: dict = Depends(require_auth)):
    results = []
    async for doc in leaves_col().find(
        {"employee_id": current_user["id"]}
    ).sort("applied_at", -1):
        doc["id"] = str(doc.pop("_id"))
        _fmt(doc)
        results.append(doc)
    return results


# ── Balance: own ──────────────────────────────────────────────

@router.get("/balance/me")
async def my_balance(current_user: dict = Depends(require_auth)):
    return await _get_or_create_balance(current_user["id"], current_user["name"])


# ── Balance: specific employee (admin/manager) ────────────────

@router.get("/balance/{employee_id}")
async def employee_balance(
    employee_id: str,
    current_user: dict = Depends(admin_or_manager),
):
    user = await users_col().find_one({"_id": ObjectId(employee_id)})
    name = user["name"] if user else "Unknown"
    return await _get_or_create_balance(employee_id, name)


# ── Internal helpers ──────────────────────────────────────────

async def _get_or_create_balance(employee_id: str, employee_name: str) -> dict:
    year    = datetime.utcnow().year
    balance = await leave_balances_col().find_one(
        {"employee_id": employee_id, "year": year}
    )
    if not balance:
        doc = {
            "employee_id":   employee_id,
            "employee_name": employee_name,
            "year":          year,
            "annual_total":  LEAVE_ENTITLEMENTS["annual"],   # 6
            "annual_used":   0,
        }
        await leave_balances_col().insert_one(doc)
        return doc

    # Always enforce current entitlement (handles old docs with annual_total=24)
    if balance.get("annual_total") != LEAVE_ENTITLEMENTS["annual"]:
        await leave_balances_col().update_one(
            {"_id": balance["_id"]},
            {"$set": {"annual_total": LEAVE_ENTITLEMENTS["annual"]}}
        )
        balance["annual_total"] = LEAVE_ENTITLEMENTS["annual"]

    balance["id"] = str(balance.pop("_id"))
    return balance


async def _deduct_balance(employee_id: str, leave_type: str, days: int):
    if leave_type == "unpaid":
        return
    await leave_balances_col().update_one(
        {"employee_id": employee_id, "year": datetime.utcnow().year},
        {"$inc": {"annual_used": days}},
        upsert=True,
    )


async def _mark_attendance_on_leave(leave: dict):
    try:
        start   = date.fromisoformat(leave["start_date"])
        end     = date.fromisoformat(leave["end_date"])
        current = start
        while current <= end:
            if current.weekday() < 6:
                day_str = current.isoformat()
                await attendance_col().update_one(
                    {"employee_id": leave["employee_id"], "date": day_str},
                    {"$setOnInsert": {
                        "employee_id":   leave["employee_id"],
                        "employee_name": leave["employee_name"],
                        "date":          day_str,
                        "status":        "on-leave",
                        "is_late":       False,
                        "geo_verified":  False,
                    }},
                    upsert=True,
                )
            current = date.fromordinal(current.toordinal() + 1)
    except Exception:
        pass


def _count_working_days(start: date, end: date) -> int:
    count, current = 0, start
    while current <= end:
        if current.weekday() < 6:
            count += 1
        current = date.fromordinal(current.toordinal() + 1)
    return count


def _fmt(doc: dict):
    for key in ("applied_at", "actioned_at"):
        if isinstance(doc.get(key), datetime):
            doc[key] = doc[key].isoformat() + 'Z'