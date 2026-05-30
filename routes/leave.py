from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime, date
from bson import ObjectId

from database import leaves_col, leave_balances_col, users_col, attendance_col
from models.leave import LeaveApplyRequest, LeaveActionRequest, LEAVE_ENTITLEMENTS
from utils.sheets import sync_leave
from utils.auth_deps import require_auth, admin_or_manager

router = APIRouter(prefix="/api/leave", tags=["leave"])


@router.post("/apply", status_code=201)
async def apply_leave(
    body: LeaveApplyRequest,
    current_user: dict = Depends(require_auth),
):
    try:
        start = date.fromisoformat(body.start_date)
        end = date.fromisoformat(body.end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD format")

    if start > end:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    total_days = _count_working_days(start, end)
    if total_days == 0:
        raise HTTPException(status_code=400, detail="No working days in selected range")

    if body.leave_type != "unpaid":
        balance = await _get_or_create_balance(current_user["id"], current_user["name"])
        used_key = f"{body.leave_type}_used"
        total_key = f"{body.leave_type}_total"
        available = balance.get(total_key, 0) - balance.get(used_key, 0)
        if total_days > available:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient {body.leave_type} leave. Available: {available} days, Requested: {total_days} days.",
            )

    doc = {
        "employee_id": current_user["id"],
        "employee_name": current_user["name"],
        "employee_email": current_user["email"],
        "leave_type": body.leave_type,
        "start_date": body.start_date,
        "end_date": body.end_date,
        "total_days": total_days,
        "reason": body.reason,
        "status": "pending",
        "applied_at": datetime.utcnow(),
        "actioned_by": None,
        "actioned_by_name": None,
        "actioned_at": None,
        "rejection_reason": None,
    }
    result = await leaves_col().insert_one(doc)

    return {
        "success": True,
        "leave_id": str(result.inserted_id),
        "total_days": total_days,
        "message": f"Leave application submitted. Pending approval ({total_days} working days).",
    }


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
        raise HTTPException(status_code=400, detail=f"Leave is already {leave['status']}")

    now = datetime.utcnow()
    updates = {
        "status": "approved" if body.action == "approve" else "rejected",
        "actioned_by": current_user["id"],
        "actioned_by_name": current_user["name"],
        "actioned_at": now,
    }
    if body.rejection_reason:
        updates["rejection_reason"] = body.rejection_reason

    await leaves_col().update_one({"_id": ObjectId(leave_id)}, {"$set": updates})

    if body.action == "approve":
        await _deduct_balance(leave["employee_id"], leave["leave_type"], leave["total_days"])
        await _mark_attendance_on_leave(leave)

    final = {**leave, **updates}
    final["applied_at"] = leave["applied_at"].isoformat() if isinstance(leave.get("applied_at"), datetime) else ""
    await sync_leave(final)

    return {"success": True, "status": updates["status"], "message": f"Leave {updates['status']} successfully."}


@router.get("/")
async def list_leaves(
    status: str | None = Query(default=None),
    employee_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    current_user: dict = Depends(admin_or_manager),
):
    query: dict = {}
    if status:
        query["status"] = status
    if employee_id:
        query["employee_id"] = employee_id

    results = []
    async for doc in leaves_col().find(query).sort("applied_at", -1).limit(limit):
        doc["id"] = str(doc.pop("_id"))
        _fmt(doc)
        results.append(doc)
    return results


@router.get("/me")
async def my_leaves(current_user: dict = Depends(require_auth)):
    results = []
    async for doc in leaves_col().find({"employee_id": current_user["id"]}).sort("applied_at", -1):
        doc["id"] = str(doc.pop("_id"))
        _fmt(doc)
        results.append(doc)
    return results


@router.get("/balance/me")
async def my_balance(current_user: dict = Depends(require_auth)):
    return await _get_or_create_balance(current_user["id"], current_user["name"])


@router.get("/balance/{employee_id}")
async def employee_balance(
    employee_id: str,
    current_user: dict = Depends(admin_or_manager),
):
    user = await users_col().find_one({"_id": ObjectId(employee_id)})
    name = user["name"] if user else "Unknown"
    return await _get_or_create_balance(employee_id, name)


async def _get_or_create_balance(employee_id: str, employee_name: str) -> dict:
    year = datetime.utcnow().year
    balance = await leave_balances_col().find_one({"employee_id": employee_id, "year": year})
    if not balance:
        doc = {
            "employee_id": employee_id,
            "employee_name": employee_name,
            "year": year,
            "annual_total": LEAVE_ENTITLEMENTS["annual"],
            "annual_used": 0,
            "sick_total": LEAVE_ENTITLEMENTS["sick"],
            "sick_used": 0,
            "casual_total": LEAVE_ENTITLEMENTS["casual"],
            "casual_used": 0,
            "maternity_total": LEAVE_ENTITLEMENTS["maternity"],
            "maternity_used": 0,
            "paternity_total": LEAVE_ENTITLEMENTS["paternity"],
            "paternity_used": 0,
        }
        await leave_balances_col().insert_one(doc)
        return doc
    balance["id"] = str(balance.pop("_id"))
    return balance


async def _deduct_balance(employee_id: str, leave_type: str, days: int):
    if leave_type == "unpaid":
        return
    await leave_balances_col().update_one(
        {"employee_id": employee_id, "year": datetime.utcnow().year},
        {"$inc": {f"{leave_type}_used": days}},
        upsert=True,
    )


async def _mark_attendance_on_leave(leave: dict):
    try:
        start = date.fromisoformat(leave["start_date"])
        end = date.fromisoformat(leave["end_date"])
        current = start
        while current <= end:
            if current.weekday() < 6:
                day_str = current.isoformat()
                await attendance_col().update_one(
                    {"employee_id": leave["employee_id"], "date": day_str},
                    {"$setOnInsert": {
                        "employee_id": leave["employee_id"],
                        "employee_name": leave["employee_name"],
                        "date": day_str,
                        "status": "on-leave",
                        "is_late": False,
                        "geo_verified": False,
                    }},
                    upsert=True,
                )
            current = date.fromordinal(current.toordinal() + 1)
    except Exception:
        pass


def _count_working_days(start: date, end: date) -> int:
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 6:
            count += 1
        current = date.fromordinal(current.toordinal() + 1)
    return count


def _fmt(doc: dict):
    for key in ("applied_at", "actioned_at"):
        if isinstance(doc.get(key), datetime):
            doc[key] = doc[key].isoformat()