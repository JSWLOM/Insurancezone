from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


LeaveType = Literal["annual", "sick", "casual", "maternity", "paternity", "unpaid"]
LeaveStatus = Literal["pending", "approved", "rejected", "cancelled"]

# Default yearly entitlements per leave type
LEAVE_ENTITLEMENTS: dict[str, int] = {
    "annual": 24,
    "sick": 12,
    "casual": 8,
    "maternity": 180,
    "paternity": 15,
    "unpaid": 0,   # unlimited unpaid — no balance tracked
}


# ── Application ───────────────────────────────────────────────

class LeaveApplyRequest(BaseModel):
    leave_type: LeaveType
    start_date: str   # "YYYY-MM-DD"
    end_date: str     # "YYYY-MM-DD"
    reason: str = Field(..., min_length=5, max_length=300)


# ── DB Document ───────────────────────────────────────────────

class LeaveInDB(LeaveApplyRequest):
    employee_id: str
    employee_name: str
    employee_email: str
    total_days: int
    status: LeaveStatus = "pending"
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    actioned_by: Optional[str] = None    # manager/admin id
    actioned_by_name: Optional[str] = None
    actioned_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


# ── API response ──────────────────────────────────────────────

class LeaveOut(LeaveInDB):
    id: str


# ── Action by manager / admin ─────────────────────────────────

class LeaveActionRequest(BaseModel):
    action: Literal["approve", "reject"]
    rejection_reason: Optional[str] = None


# ── Balance record ────────────────────────────────────────────

class LeaveBalance(BaseModel):
    employee_id: str
    employee_name: str
    year: int
    annual_total: int = LEAVE_ENTITLEMENTS["annual"]
    annual_used: int = 0
    sick_total: int = LEAVE_ENTITLEMENTS["sick"]
    sick_used: int = 0
    casual_total: int = LEAVE_ENTITLEMENTS["casual"]
    casual_used: int = 0
    maternity_total: int = LEAVE_ENTITLEMENTS["maternity"]
    maternity_used: int = 0
    paternity_total: int = LEAVE_ENTITLEMENTS["paternity"]
    paternity_used: int = 0

    @property
    def annual_remaining(self) -> int:
        return self.annual_total - self.annual_used

    @property
    def sick_remaining(self) -> int:
        return self.sick_total - self.sick_used

    @property
    def casual_remaining(self) -> int:
        return self.casual_total - self.casual_used