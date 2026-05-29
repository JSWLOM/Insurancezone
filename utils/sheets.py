"""
Google Sheets integration via Google Apps Script Web App.

How to set up (one-time):
1. Open your Google Sheet.
2. Extensions → Apps Script → paste the code from SETUP.md.
3. Deploy → New deployment → Web App.
   - Execute as: Me
   - Who has access: Anyone
4. Copy the deployment URL into your .env as GOOGLE_SHEETS_URL.
"""

import httpx
import logging
from datetime import datetime
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def post_to_sheet(sheet_name: str, row_data: dict) -> bool:
    """
    POST a row of data to the Google Apps Script endpoint.

    Args:
        sheet_name: The name of the tab/sheet to append to.
                    E.g. "Enquiries", "Attendance", "Leaves"
        row_data:   Dict of column → value pairs.

    Returns:
        True if successful, False otherwise.
        Never raises — failures are logged and swallowed so the
        main request never fails because of a Sheets sync issue.
    """
    if not settings.google_sheets_url:
        logger.warning("GOOGLE_SHEETS_URL not configured — skipping Sheets sync")
        return False

    payload = {
        "sheet": sheet_name,
        "data": row_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                settings.google_sheets_url,
                json=payload,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                logger.info(f"Sheets sync OK → {sheet_name}")
                return True
            else:
                logger.warning(
                    f"Sheets sync failed [{resp.status_code}] → {sheet_name}: {resp.text[:200]}"
                )
                return False
    except httpx.TimeoutException:
        logger.warning(f"Sheets sync timed out → {sheet_name}")
        return False
    except Exception as e:
        logger.error(f"Sheets sync error → {sheet_name}: {e}")
        return False


# ── Typed helpers for each sheet tab ─────────────────────────

async def sync_enquiry(enquiry: dict) -> bool:
    row = {
        "Name": enquiry.get("name", ""),
        "Phone": enquiry.get("phone", ""),
        "Email": enquiry.get("email", ""),
        "Insurance Type": enquiry.get("insurance_type", ""),
        "City": enquiry.get("city", ""),
        "Message": enquiry.get("message", ""),
        "Source": enquiry.get("source", "website"),
        "Status": enquiry.get("status", "new"),
        "Timestamp": enquiry.get("timestamp", datetime.utcnow().isoformat()),
    }
    return await post_to_sheet("Enquiries", row)


async def sync_attendance(record: dict) -> bool:
    row = {
        "Employee": record.get("employee_name", ""),
        "Date": record.get("date", ""),
        "Punch In": str(record.get("punch_in", "")),
        "Punch Out": str(record.get("punch_out", "")),
        "Status": record.get("status", ""),
        "Is Late": "Yes" if record.get("is_late") else "No",
        "Working Hours": record.get("working_hours", ""),
        "Geo Verified": "Yes" if record.get("geo_verified") else "No",
        "Distance (m)": record.get("punch_in_distance_m", ""),
    }
    return await post_to_sheet("Attendance", row)


async def sync_leave(leave: dict) -> bool:
    row = {
        "Employee": leave.get("employee_name", ""),
        "Email": leave.get("employee_email", ""),
        "Leave Type": leave.get("leave_type", ""),
        "Start Date": leave.get("start_date", ""),
        "End Date": leave.get("end_date", ""),
        "Total Days": leave.get("total_days", ""),
        "Reason": leave.get("reason", ""),
        "Status": leave.get("status", "pending"),
        "Applied At": str(leave.get("applied_at", "")),
        "Actioned By": leave.get("actioned_by_name", ""),
    }
    return await post_to_sheet("Leaves", row)