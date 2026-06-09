# Insurance Zone API — Setup Guide

## 1. Clone and install locally

```bash
git clone <your-repo>
cd api
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in your `.env` with real values (MongoDB URL, office coordinates, etc).

```bash
uvicorn main:app --reload
# API now running at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

---

## 2. Google Apps Script (Google Sheets sync)

### Step 1 — Create the Google Sheet
1. Go to [sheets.google.com](https://sheets.google.com) and create a new sheet.
2. Rename it **"Insurance Zone Data"**.
3. Add three tabs at the bottom: **Enquiries**, **Attendance**, **Leaves**.

### Step 2 — Add headers to each tab

**Enquiries tab** — Row 1:
`Name | Phone | Email | Insurance Type | City | Message | Source | Status | Timestamp`

**Attendance tab** — Row 1:
`Employee | Date | Punch In | Punch Out | Status | Is Late | Working Hours | Geo Verified | Distance (m)`

**Leaves tab** — Row 1:
`Employee | Email | Leave Type | Start Date | End Date | Total Days | Reason | Status | Applied At | Actioned By`

### Step 3 — Add the Apps Script

1. In your Google Sheet: **Extensions → Apps Script**.
2. Delete any existing code and paste the following:

```javascript
function doPost(e) {
  try {
    var payload = JSON.parse(e.postData.contents);
    var sheetName = payload.sheet;
    var data = payload.data;

    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName(sheetName);

    if (!sheet) {
      return ContentService
        .createTextOutput(JSON.stringify({ error: "Sheet not found: " + sheetName }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // Get headers from row 1
    var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];

    // Build row matching headers order
    var row = headers.map(function(header) {
      return data[header] !== undefined ? data[header] : "";
    });

    sheet.appendRow(row);

    return ContentService
      .createTextOutput(JSON.stringify({ success: true }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService
    .createTextOutput(JSON.stringify({ status: "Insurance Zone Sheets API is running" }))
    .setMimeType(ContentService.MimeType.JSON);
}
```

3. Click **Save** (Ctrl+S).

### Step 4 — Deploy

1. Click **Deploy → New Deployment**.
2. Click the gear icon → **Web App**.
3. Set:
   - Description: `Insurance Zone API`
   - Execute as: **Me**
   - Who has access: **Anyone**
4. Click **Deploy**.
5. Copy the **Web App URL** — it looks like:
   `https://script.google.com/macros/s/AKfycb.../exec`
6. Paste it into your `.env` as `GOOGLE_SHEETS_URL=...`

> ⚠️ Every time you edit the script, you must create a **New Deployment** to get an updated URL.

---

## 3. Create the first Admin user

Since the `/api/auth/register` endpoint requires admin auth, you need to seed the first admin manually.

Run this Python script once (with your `.env` populated):

```python
# seed_admin.py
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def seed():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL"))
    db = client[os.getenv("DB_NAME", "insurance_zone")]

    admin = {
        "name": "Admin",
        "email": "admin@insurancezone.co.in",
        "hashed_password": pwd.hash("Change@Me123"),   # ← change this!
        "role": "admin",
        "department": "Management",
        "phone": "+91 9473663757",
        "is_active": True,
        "created_at": datetime.utcnow(),
    }

    existing = await db["users"].find_one({"email": admin["email"]})
    if existing:
        print("Admin already exists.")
    else:
        await db["users"].insert_one(admin)
        print("✅ Admin created. Login with admin@insurancezone.co.in / Change@Me123")
        print("⚠️  Change the password immediately after first login!")

    client.close()

asyncio.run(seed())
```

```bash
python seed_admin.py
```

---

## 4. Deploy to Render.com

1. Push your code to a GitHub repo (make sure `.env` is in `.gitignore`!).
2. Go to [render.com](https://render.com) → **New Web Service** → connect your repo.
3. Render detects `render.yaml` automatically.
4. Under **Environment**, click each `sync: false` variable and fill in real values:
   - `MONGODB_URL` → your Atlas connection string
   - `GOOGLE_SHEETS_URL` → your Apps Script URL
   - `OFFICE_LAT` / `OFFICE_LNG` → your office GPS coordinates
   - `ALLOWED_ORIGINS` → `https://insurancezone.co.in`
5. Click **Deploy**. Your API will be live at:
   `https://insurance-zone-api.onrender.com`

---

## 5. API Endpoints Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/login` | Public | Login, get JWT tokens |
| POST | `/api/auth/register` | Admin | Create staff account |
| POST | `/api/auth/refresh` | Public | Refresh access token |
| POST | `/api/auth/logout` | Public | Revoke refresh token |
| GET | `/api/auth/me` | Any staff | Get own profile |
| GET | `/api/auth/users` | Admin/Mgr | List all staff |
| POST | `/api/enquiry/` | Public | Submit enquiry form |
| GET | `/api/enquiry/` | Admin/Mgr | List all enquiries |
| PATCH | `/api/enquiry/{id}` | Admin/Mgr | Update enquiry status |
| GET | `/api/enquiry/stats/summary` | Admin/Mgr | Enquiry stats |
| POST | `/api/attendance/punch-in` | Any staff | GPS punch in |
| POST | `/api/attendance/punch-out` | Any staff | GPS punch out |
| GET | `/api/attendance/today` | Admin/Mgr | Today's full attendance |
| GET | `/api/attendance/me` | Any staff | Own attendance history |
| GET | `/api/attendance/geofence` | Any staff | Office GPS + radius |
| POST | `/api/leave/apply` | Any staff | Apply for leave |
| PATCH | `/api/leave/{id}/action` | Admin/Mgr | Approve or reject |
| GET | `/api/leave/` | Admin/Mgr | All leave requests |
| GET | `/api/leave/me` | Any staff | Own leave history |
| GET | `/api/leave/balance/me` | Any staff | Own leave balance |

Full interactive docs: `/docs` (Swagger UI)




izonejai@gmail.com   Staff   jai@9044
Jaiswalsristi007@gmail.com  Manager  8808409192
jaiswalom435@gmail.com   Superadmin  Izone@123



.\venv\Scripts\Activate.ps1







