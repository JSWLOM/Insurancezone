from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class OfficeCreate(BaseModel):
    name:           str   = Field(..., min_length=2,  max_length=100)
    address:        str   = Field(..., min_length=5)
    city:           str   = Field(..., min_length=2)
    lat:            float = Field(..., ge=-90,  le=90)
    lng:            float = Field(..., ge=-180, le=180)
    radius_meters:  float = Field(default=200.0, ge=50, le=1000)
    is_active:      bool  = True


class OfficeOut(OfficeCreate):
    id:           str
    created_by:   Optional[str]      = None
    created_at:   datetime
    staff_count:  int                = 0   # populated at query time


class OfficeUpdate(BaseModel):
    name:          Optional[str]   = None
    address:       Optional[str]   = None
    city:          Optional[str]   = None
    lat:           Optional[float] = None
    lng:           Optional[float] = None
    radius_meters: Optional[float] = None
    is_active:     Optional[bool]  = None