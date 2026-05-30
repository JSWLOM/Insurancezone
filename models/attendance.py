from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class GPSCoord(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy_meters: Optional[float] = None


class PunchInRequest(BaseModel):
    gps: GPSCoord
    device_info: Optional[str] = None


class PunchOutRequest(BaseModel):
    gps: GPSCoord


class AttendanceRecord(BaseModel):
    employee_id: str
    employee_name: str
    date: str
    punch_in: Optional[datetime] = None
    punch_out: Optional[datetime] = None
    punch_in_lat: Optional[float] = None
    punch_in_lng: Optional[float] = None
    punch_out_lat: Optional[float] = None
    punch_out_lng: Optional[float] = None
    punch_in_distance_m: Optional[float] = None
    punch_out_distance_m: Optional[float] = None
    status: str = "absent"
    is_late: bool = False
    early_departure: bool = False
    working_hours: Optional[float] = None
    device_info: Optional[str] = None
    geo_verified: bool = False