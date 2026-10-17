from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal
from datetime import datetime
from bson import ObjectId


RoleType = Literal["admin", "manager", "agent", "viewer"]


class PyObjectId(str):
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
    office_id: Optional[str] = None          # ← ObjectId string of assigned office
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


# ── API models ─────────────────────────────────────────────────

class UserCreate(BaseModel):
    """Admin uses this to create a new staff account."""
    name: str       = Field(..., min_length=2, max_length=80)
    email: EmailStr
    password: str   = Field(..., min_length=8)
    role: RoleType
    department: str = ""
    phone: str      = ""
    office_id: Optional[str] = None          # ← assign office at creation time


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
    office_id: Optional[str]   = None        # ← included so frontend can filter/display
    office_name: Optional[str] = None        # ← populated by list_users (join); None elsewhere


class UserUpdate(BaseModel):
    """Admin can patch any of these fields."""
    name: Optional[str]       = None
    role: Optional[RoleType]  = None
    department: Optional[str] = None
    phone: Optional[str]      = None
    is_active: Optional[bool] = None
    office_id: Optional[str]  = None         # ← allows reassigning office via PATCH /users/{id}


# ── Auth request / response models ────────────────────────────

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
    office_id: Optional[str] = None          # ← returned on login so frontend caches it


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"