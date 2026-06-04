"""
Metrics — stores editable business KPIs in MongoDB.
Admin and Manager can update policy count and monthly revenue.
All authenticated staff can read.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
from database import get_db
from utils.auth_deps import require_auth, admin_or_manager

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


# ── Pydantic models ───────────────────────────────────────────

class MetricUpdate(BaseModel):
    value: float   # policies = integer count, revenue = float in lakhs


# ── Helper: get or create metric document ────────────────────

async def _get_metric(key: str) -> dict:
    doc = await get_db()["metrics"].find_one({"key": key})
    if not doc:
        defaults = {
            "policies_issued": 0.0,
            "monthly_revenue": 0.0,
        }
        doc = {
            "key":        key,
            "value":      defaults.get(key, 0.0),
            "updated_at": datetime.utcnow(),
            "updated_by": "system",
        }
        await get_db()["metrics"].insert_one(doc)
    return doc


# ── GET: all metrics (any authenticated staff) ────────────────

@router.get("/")
async def get_all_metrics(current_user: dict = Depends(require_auth)):
    keys = ["policies_issued", "monthly_revenue"]
    result = {}
    for key in keys:
        doc = await _get_metric(key)
        result[key] = doc["value"]
    return result


# ── PATCH: update a metric (admin/manager only) ───────────────

@router.patch("/{key}")
async def update_metric(
    key:  str,
    body: MetricUpdate,
    current_user: dict = Depends(admin_or_manager),
):
    allowed_keys = {"policies_issued", "monthly_revenue"}
    if key not in allowed_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown metric key '{key}'. Allowed: {', '.join(allowed_keys)}"
        )

    if body.value < 0:
        raise HTTPException(status_code=400, detail="Value cannot be negative")

    await get_db()["metrics"].update_one(
        {"key": key},
        {"$set": {
            "value":      body.value,
            "updated_at": datetime.utcnow(),
            "updated_by": current_user["name"],
        }},
        upsert=True,
    )

    return {
        "success": True,
        "key":     key,
        "value":   body.value,
        "updated_by": current_user["name"],
    }