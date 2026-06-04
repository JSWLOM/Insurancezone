from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


# ── Only two leave types now ──────────────────────────────────
LeaveType   = Literal["annual", "unpaid"]
LeaveStatus = Literal["pending", "approved", "rejected", "cancelled"]

# Annual entitlement changed to 6 days
LEAVE_ENTITLEMENTS: dict[str, int] = {
    "annual": 6,
    "unpaid": 0,   # unlimited unpaid, no balance tracked
}


class LeaveApplyRequest(BaseModel):
    leave_type: LeaveType
    start_date: str   # "YYYY-MM-DD"
    end_date:   str   # "YYYY-MM-DD"
    reason:     str = Field(..., min_length=5, max_length=300)


class LeaveActionRequest(BaseModel):
    action:           Literal["approve", "reject"]
    rejection_reason: Optional[str] = None


class LeaveBalance(BaseModel):
    employee_id:    str
    employee_name:  str
    year:           int
    annual_total:   int = LEAVE_ENTITLEMENTS["annual"]
    annual_used:    int = 0