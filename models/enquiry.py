from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime
from bson import ObjectId

from database import enquiries_col
from models.enquiry import EnquiryCreate, EnquiryOut, EnquiryStatusUpdate
from utils.sheets import sync_enquiry
from utils.auth_deps import require_auth, admin_or_manager

router = APIRouter(prefix="/api/enquiry", tags=["enquiry"])


# ── Public: submit lead form ──────────────────────────────────

@router.post("/", status_code=201)
async def submit_enquiry(body: EnquiryCreate):
    """
    Public endpoint — no auth required.
    1. Saves to MongoDB.
    2. Fires-and-forgets sync to Google Sheets.
    """
    now = datetime.utcnow()
    doc = body.model_dump()
    doc["timestamp"] = now
    doc["status"] = "new"
    doc["sheets_synced"] = False

    result = await enquiries_col().insert_one(doc)
    inserted_id = str(result.inserted_id)

    # Sync to Sheets asynchronously — never block the response
    doc["timestamp"] = now.isoformat()
    synced = await sync_enquiry(doc)

    # Mark synced in DB
    if synced:
        await enquiries_col().update_one(
            {"_id": result.inserted_id},
            {"$set": {"sheets_synced": True}},
        )

    return {
        "success": True,
        "message": "Enquiry received. Our advisor will contact you within 2 hours.",
        "enquiry_id": inserted_id,
    }


# ── Admin/Manager: list all enquiries ────────────────────────

@router.get("/")
async def list_enquiries(
    status: str | None = Query(default=None),
    insurance_type: str | None = Query(default=None),
    city: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    skip: int = Query(default=0),
    current_user: dict = Depends(admin_or_manager),
):
    query: dict = {}
    if status:
        query["status"] = status
    if insurance_type:
        query["insurance_type"] = insurance_type
    if city:
        query["city"] = {"$regex": city, "$options": "i"}

    cursor = (
        enquiries_col()
        .find(query)
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
    )
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        if isinstance(doc.get("timestamp"), datetime):
            doc["timestamp"] = doc["timestamp"].isoformat()
        results.append(doc)

    total = await enquiries_col().count_documents(query)
    return {"total": total, "enquiries": results}


# ── Admin/Manager: single enquiry ─────────────────────────────

@router.get("/{enquiry_id}")
async def get_enquiry(
    enquiry_id: str,
    current_user: dict = Depends(admin_or_manager),
):
    doc = await enquiries_col().find_one({"_id": ObjectId(enquiry_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    doc["id"] = str(doc.pop("_id"))
    return doc


# ── Admin/Manager: update status / notes ─────────────────────

@router.patch("/{enquiry_id}")
async def update_enquiry_status(
    enquiry_id: str,
    body: EnquiryStatusUpdate,
    current_user: dict = Depends(admin_or_manager),
):
    updates: dict = {"status": body.status}
    if body.notes is not None:
        updates["notes"] = body.notes
    if body.assigned_to is not None:
        updates["assigned_to"] = body.assigned_to
    updates["last_updated"] = datetime.utcnow()
    updates["last_updated_by"] = current_user["id"]

    result = await enquiries_col().find_one_and_update(
        {"_id": ObjectId(enquiry_id)},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    result["id"] = str(result.pop("_id"))
    return result


# ── Admin: summary stats ──────────────────────────────────────

@router.get("/stats/summary")
async def enquiry_stats(current_user: dict = Depends(admin_or_manager)):
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    status_counts: dict = {}
    async for doc in enquiries_col().aggregate(pipeline):
        status_counts[doc["_id"]] = doc["count"]

    total = await enquiries_col().count_documents({})

    # Today's count
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await enquiries_col().count_documents(
        {"timestamp": {"$gte": today_start}}
    )

    return {
        "total": total,
        "today": today_count,
        "by_status": status_counts,
    }