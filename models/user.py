from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal
from datetime import datetime
from bson import ObjectId


# Roles available in the system
RoleType = Literal["admin", "manager", "agent", "viewer"]


class PyObjectId(str):
    """Helper so Pydantic can handle MongoDB ObjectIds."""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return str(v)


# ── DB Document ────────────────────────────────────────────────
class UserInDB(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    name: str
    email: EmailStr
    hashed_password: str
    role: RoleType
    department: str = ""
    phone: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None   # admin user id who created this account

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


# ── API Request / Response models ─────────────────────────────

class UserCreate(BaseModel):
    """Admin uses this to create a new staff account."""
    name: str = Field(..., min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: RoleType
    department: str = ""
    phone: str = ""


class UserOut(BaseModel):
    """Safe version returned to the client — no password hash."""
    id: str
    name: str
    email: EmailStr
    role: RoleType
    department: str
    phone: str
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    """Admin can patch any of these fields."""
    name: Optional[str] = None
    role: Optional[RoleType] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


# ── Auth request/response models ──────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: RoleType
    name: str
    user_id: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"