from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date


# ── GPS coordinate payload ─────────────────────────────────────

class GPSCoord(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy_meters: Optional[float] = None   # from browser GPS API


# ── Punch-in request ──────────────────────────────────────────

class PunchInRequest(BaseModel):
    gps: GPSCoord
    device_info: Optional[str] = None   # browser user-agent snippet


class PunchOutRequest(BaseModel):
    gps: GPSCoord


# ── Stored attendance record ──────────────────────────────────

class AttendanceRecord(BaseModel):
    employee_id: str
    employee_name: str
    date: str                   # ISO date string "YYYY-MM-DD" — easier querying
    punch_in: Optional[datetime] = None
    punch_out: Optional[datetime] = None
    punch_in_lat: Optional[float] = None
    punch_in_lng: Optional[float] = None
    punch_out_lat: Optional[float] = None
    punch_out_lng: Optional[float] = None
    punch_in_distance_m: Optional[float] = None   # distance from office at punch-in
    punch_out_distance_m: Optional[float] = None
    status: str = "absent"      # present / absent / late / half-day / on-leave
    is_late: bool = False
    early_departure: bool = False
    working_hours: Optional[float] = None
    device_info: Optional[str] = None
    geo_verified: bool = False  # True if inside geo-fence


# ── API Response ──────────────────────────────────────────────

class AttendanceOut(AttendanceRecord):
    id: str


# ── Admin daily overview item ─────────────────────────────────

class DailyAttendanceSummary(BaseModel):
    date: str
    total_employees: int
    present: int
    absent: int
    late: int
    on_leave: int
    records: list[AttendanceOut]