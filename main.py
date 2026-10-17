"""
Insurance Zone API
==================
FastAPI backend for Insurance Zone (insurancezone.co.in)

Tech stack:
  - FastAPI + Uvicorn
  - MongoDB Atlas via Motor (async)
  - JWT auth (access + refresh tokens)
  - bcrypt password hashing
  - Google Apps Script → Google Sheets sync
  - Haversine geo-fence for GPS attendance
"""

"""
Insurance Zone API v2.0
=======================
Added in v2.0: Multi-office support (routes/offices.py)
Each employee is assigned to one office. Punch-in/out validates
against that employee's specific office geo-fence, not a global .env value.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from database import create_indexes, close_connection
from routes import auth, enquiry, attendance, leave, metrics, holidays, offices   # ← offices added

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_indexes()
    yield
    await close_connection()


app = FastAPI(
    title="Insurance Zone API",
    description="Backend for Insurance Zone — auth, leads, attendance, leaves, multi-office",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(enquiry.router)
app.include_router(attendance.router)
app.include_router(leave.router)
app.include_router(metrics.router)
app.include_router(holidays.router)
app.include_router(offices.router)       # ← NEW


@app.get("/health", tags=["system"])
async def health():
    return {
        "status":  "ok",
        "service": "Insurance Zone API",
        "version": "2.0.0",
        "env":     settings.app_env,
    }


@app.get("/", tags=["system"])
async def root():
    return JSONResponse({
        "message": "Insurance Zone API v2.0 is running.",
        "docs":    "/docs",
        "health":  "/health",
    })