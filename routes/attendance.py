from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime, date, timezone, timedelta
from bson import ObjectId
from pydantic import BaseModel
from typing import Optional

from database import attendance_col, users_col
from models.attendance import PunchInRequest, PunchOutRequest
from utils.geo import is_inside_geofence, office_coords
from utils.sheets import sync_attendance
from utils.auth_deps import require_auth, admin_or_manager

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

IST = timezone(timedelta(hours=5, minutes=30))
LATE_THRESHOLD_HOUR = 9
LATE_THRESHOLD_MIN  = 15
SHORT_DAY_HOURS     = 6.0


class AdminMarkRequest(BaseModel):
    employee_id: str
    date:        str
    punch_in:    str
    punch_out:   Optional[str] = None
    note:        Optional[str] = None


@router.post("/punch-in")
async def punch_in(body: PunchInRequest, current_user: dict = Depends(require_auth)):
    employee_id = current_user["id"]
    today = datetime.now(IST).date().isoformat()
    now   = datetime.utcnow()

    existing = await attendance_col().find_one({"employee_id": employee_id, "date": today})
    if existing and existing.get("punch_in"):
        raise HTTPException(status_code=400, detail="Already punched in today. Use punch-out to end your shift.")

    inside, distance_m = is_inside_geofence(body.gps.lat, body.gps.lng)
    if not inside:
        raise HTTPException(status_code=403, detail=(
            f"You are {distance_m:.0f}m from the office. "
            f"Punch-in only allowed within {office_coords()['radius_meters']:.0f}m."
        ))

    is_late = (now.hour > LATE_THRESHOLD_HOUR) or (now.hour == LATE_THRESHOLD_HOUR and now.minute > LATE_THRESHOLD_MIN)

    record = {
        "employee_id": employee_id, "employee_name": current_user["name"],
        "date": today, "punch_in": now, "punch_out": None,
        "punch_in_lat": body.gps.lat, "punch_in_lng": body.gps.lng,
        "punch_in_distance_m": distance_m,
        "punch_out_lat": None, "punch_out_lng": None, "punch_out_distance_m": None,
        "status": "present", "is_late": is_late, "early_departure": False,
        "working_hours": None, "geo_verified": True, "device_info": body.device_info,
        "manual_entry": False, "marked_by": None, "marked_by_id": None, "note": "",
    }

    if existing:
        await attendance_col().find_one_and_update({"_id": existing["_id"]}, {"$set": record})
        record_id = str(existing["_id"])
    else:
        result = await attendance_col().insert_one(record)
        record_id = str(result.inserted_id)

    return {
        "success": True, "punch_in": now.isoformat() + "Z",
        "is_late": is_late, "distance_from_office_m": distance_m,
        "geo_verified": True, "record_id": record_id,
        "message": "⚠️ Punch-in recorded but you are late today." if is_late else "✅ Punch-in successful. Have a great day!",
    }


@router.post("/punch-out")
async def punch_out(body: PunchOutRequest, current_user: dict = Depends(require_auth)):
    employee_id = current_user["id"]
    today = datetime.now(IST).date().isoformat()
    now   = datetime.utcnow()

    record = await attendance_col().find_one({"employee_id": employee_id, "date": today})
    if not record or not record.get("punch_in"):
        raise HTTPException(status_code=400, detail="No punch-in found for today. Please punch in first.")
    if record.get("punch_out"):
        raise HTTPException(status_code=400, detail="Already punched out for today.")

    inside, distance_m = is_inside_geofence(body.gps.lat, body.gps.lng)
    punch_in_time: datetime = record["punch_in"]
    working_seconds = (now - punch_in_time).total_seconds()
    working_hours   = round(working_seconds / 3600, 2)
    early_departure = working_hours < SHORT_DAY_HOURS

    updates = {
        "punch_out": now, "punch_out_lat": body.gps.lat, "punch_out_lng": body.gps.lng,
        "punch_out_distance_m": distance_m, "working_hours": working_hours,
        "early_departure": early_departure,
    }
    if record["is_late"] and working_hours >= SHORT_DAY_HOURS:
        updates["status"] = "late"
    elif early_departure:
        updates["status"] = "half-day"

    await attendance_col().update_one({"_id": record["_id"]}, {"$set": updates})

    final_record = {**record, **updates}
    final_record["punch_in"]  = punch_in_time.isoformat() + "Z"
    final_record["punch_out"] = now.isoformat() + "Z"
    await sync_attendance(final_record)

    return {
        "success": True, "punch_out": now.isoformat() + "Z",
        "working_hours": working_hours, "early_departure": early_departure,
        "distance_from_office_m": distance_m,
        "message": f"⚠️ Short day recorded ({working_hours:.1f} hrs)." if early_departure else f"✅ Punched out. You worked {working_hours:.1f} hours today.",
    }


@router.post("/admin-mark")
async def admin_mark_attendance(body: AdminMarkRequest, current_user: dict = Depends(admin_or_manager)):
    """
    Admin / Manager manually marks or corrects attendance for any employee.
    Times supplied in IST HH:MM, stored as UTC. Sets manual_entry=True
    so frontend can show a visual distinction (dashed border + pencil icon).
    """
    employee = await users_col().find_one({"_id": ObjectId(body.employee_id)})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    try:
        date_obj = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")

    try:
        h_in, m_in = map(int, body.punch_in.split(":"))
    except Exception:
        raise HTTPException(status_code=400, detail="punch_in must be HH:MM")

    punch_in_ist = datetime(date_obj.year, date_obj.month, date_obj.day, h_in, m_in, tzinfo=IST)
    punch_in_utc = punch_in_ist.astimezone(timezone.utc).replace(tzinfo=None)

    punch_out_utc = None
    if body.punch_out:
        try:
            h_out, m_out = map(int, body.punch_out.split(":"))
        except Exception:
            raise HTTPException(status_code=400, detail="punch_out must be HH:MM")
        punch_out_ist = datetime(date_obj.year, date_obj.month, date_obj.day, h_out, m_out, tzinfo=IST)
        punch_out_utc = punch_out_ist.astimezone(timezone.utc).replace(tzinfo=None)
        if punch_out_utc <= punch_in_utc:
            raise HTTPException(status_code=400, detail="Punch Out must be after Punch In")

    is_late = h_in > LATE_THRESHOLD_HOUR or (h_in == LATE_THRESHOLD_HOUR and m_in > LATE_THRESHOLD_MIN)

    working_hours   = None
    early_departure = False
    if punch_out_utc:
        working_hours   = round((punch_out_utc - punch_in_utc).total_seconds() / 3600, 2)
        early_departure = working_hours < SHORT_DAY_HOURS

    if is_late and working_hours and working_hours >= SHORT_DAY_HOURS:
        status = "late"
    elif working_hours and working_hours < SHORT_DAY_HOURS:
        status = "half-day"
    else:
        status = "present"

    record = {
        "employee_id": body.employee_id, "employee_name": employee["name"],
        "date": body.date, "punch_in": punch_in_utc, "punch_out": punch_out_utc,
        "punch_in_lat": None, "punch_in_lng": None, "punch_out_lat": None, "punch_out_lng": None,
        "punch_in_distance_m": None, "punch_out_distance_m": None,
        "status": status, "is_late": is_late, "early_departure": early_departure,
        "working_hours": working_hours, "geo_verified": False, "device_info": None,
        "manual_entry": True,
        "marked_by":    current_user["name"],
        "marked_by_id": current_user["id"],
        "note":         (body.note or "").strip(),
        "marked_at":    datetime.utcnow(),
    }

    existing = await attendance_col().find_one({"employee_id": body.employee_id, "date": body.date})
    if existing:
        await attendance_col().update_one({"_id": existing["_id"]}, {"$set": record})
        action = "updated"
    else:
        await attendance_col().insert_one(record)
        action = "marked"

    return {
        "success":   True, "action": action,
        "message":   f"Attendance {action} for {employee['name']} on {body.date}",
        "punch_in":  punch_in_utc.isoformat() + "Z",
        "punch_out": punch_out_utc.isoformat() + "Z" if punch_out_utc else None,
        "is_late":   is_late, "status": status, "marked_by": current_user["name"],
    }


@router.get("/today")
async def today_attendance(current_user: dict = Depends(admin_or_manager)):
    today = datetime.now(IST).date().isoformat()
    records = []
    async for doc in attendance_col().find({"date": today}):
        doc["id"] = str(doc.pop("_id"))
        _format_datetimes(doc)
        records.append(doc)

    all_users = []
    async for u in users_col().find({"is_active": True}):
        all_users.append({"id": str(u["_id"]), "name": u["name"], "role": u["role"]})

    punched_ids = {r["employee_id"] for r in records}
    absent = [u for u in all_users if u["id"] not in punched_ids]

    return {
        "date": today,
        "present":  len([r for r in records if r.get("punch_in")]),
        "absent":   len(absent),
        "late":     len([r for r in records if r.get("is_late")]),
        "on_leave": len([r for r in records if r.get("status") == "on-leave"]),
        "records":  records,
        "absent_employees": absent,
    }


@router.get("/me")
async def my_attendance(
    month: int = Query(default=None, ge=1, le=12),
    year:  int = Query(default=None),
    current_user: dict = Depends(require_auth),
):
    now = datetime.utcnow()
    y = year or now.year
    m = month or now.month
    prefix = f"{y}-{m:02d}"

    records = []
    async for doc in attendance_col().find(
        {"employee_id": current_user["id"], "date": {"$regex": f"^{prefix}"}}
    ).sort("date", -1):
        doc["id"] = str(doc.pop("_id"))
        _format_datetimes(doc)
        records.append(doc)

    return {
        "employee_id":   current_user["id"],
        "employee_name": current_user["name"],
        "month":         prefix,
        "total_records": len(records),
        "present_days":  len([r for r in records if r.get("punch_in")]),
        "late_days":     len([r for r in records if r.get("is_late")]),
        "records":       records,
    }


@router.get("/employee/{employee_id}")
async def employee_attendance(
    employee_id: str,
    month: int = Query(default=None, ge=1, le=12),
    year:  int = Query(default=None),
    current_user: dict = Depends(admin_or_manager),
):
    now = datetime.utcnow()
    y = year or now.year
    m = month or now.month
    prefix = f"{y}-{m:02d}"

    records = []
    async for doc in attendance_col().find(
        {"employee_id": employee_id, "date": {"$regex": f"^{prefix}"}}
    ).sort("date", -1):
        doc["id"] = str(doc.pop("_id"))
        _format_datetimes(doc)
        records.append(doc)

    return {"employee_id": employee_id, "month": prefix, "records": records}


@router.get("/geofence")
async def get_geofence(current_user: dict = Depends(require_auth)):
    return office_coords()


def _format_datetimes(doc: dict):
    for key in ("punch_in", "punch_out", "marked_at"):
        if isinstance(doc.get(key), datetime):
            doc[key] = doc[key].isoformat() + "Z"