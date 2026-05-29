from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal
from datetime import datetime


StatusType = Literal["new", "contacted", "converted", "closed"]
InsuranceType = Literal[
    "Life Insurance",
    "Health Insurance",
    "Vehicle Insurance",
    "Business Insurance",
    "Finance / Refinance",
    "Property Insurance",
    "Machine Insurance",
    "Factory Insurance",
    "Other",
]


# ── Public submission form ─────────────────────────────────────

class EnquiryCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=10, max_length=15)
    email: Optional[EmailStr] = None
    insurance_type: Optional[InsuranceType] = None
    city: Optional[str] = None
    message: Optional[str] = Field(default=None, max_length=500)
    source: str = "website"      # website / whatsapp / walk-in / referral


# ── DB Document ───────────────────────────────────────────────

class EnquiryInDB(EnquiryCreate):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: StatusType = "new"
    assigned_to: Optional[str] = None   # employee ObjectId string
    notes: Optional[str] = None
    sheets_synced: bool = False


# ── API Response ──────────────────────────────────────────────

class EnquiryOut(EnquiryInDB):
    id: str


# ── Staff update ──────────────────────────────────────────────

class EnquiryStatusUpdate(BaseModel):
    status: StatusType
    notes: Optional[str] = None
    assigned_to: Optional[str] = None