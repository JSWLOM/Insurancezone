from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


LeaveType = Literal["annual", "sick", "casual", "maternity", "paternity", "unpaid"]
LeaveStatus = Literal["pending", "approved", "rejected", "cancelled"]

LEAVE_ENTITLEMENTS: dict[str, int] = {
    "annual": 24,
    "sick": 12,
    "casual": 8,
    "maternity": 180,
    "paternity": 15,
    "unpaid": 0,
}


class LeaveApplyRequest(BaseModel):
    leave_type: LeaveType
    start_date: str
    end_date: str
    reason: str = Field(..., min_length=5, max_length=300)


class LeaveActionRequest(BaseModel):
    action: Literal["approve", "reject"]
    rejection_reason: Optional[str] = None


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