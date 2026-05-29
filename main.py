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

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from database import create_indexes, close_connection
from routes import auth, enquiry, attendance, leave

settings = get_settings()


# ── Lifespan (startup / shutdown) ─────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_indexes()
    yield
    # Shutdown
    await close_connection()


# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="Insurance Zone API",
    description="Backend for Insurance Zone — auth, leads, attendance, leaves",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── CORS ──────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(enquiry.router)
app.include_router(attendance.router)
app.include_router(leave.router)


# ── Health check ──────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health():
    return {
        "status": "ok",
        "service": "Insurance Zone API",
        "env": settings.app_env,
    }


@app.get("/", tags=["system"])
async def root():
    return JSONResponse({
        "message": "Insurance Zone API is running.",
        "docs": "/docs",
        "health": "/health",
    })