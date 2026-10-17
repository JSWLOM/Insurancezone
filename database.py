from motor.motor_asyncio import AsyncIOMotorClient
from config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_url)
    return _client


def get_db():
    return get_client()[settings.db_name]


# ── Collection accessors ───────────────────────────────────────
def users_col():
    return get_db()["users"]

def refresh_tokens_col():
    return get_db()["refresh_tokens"]

def enquiries_col():
    return get_db()["enquiries"]

def attendance_col():
    return get_db()["attendance"]

def leaves_col():
    return get_db()["leaves"]

def leave_balances_col():
    return get_db()["leave_balances"]

def offices_col():                          # ← NEW
    return get_db()["offices"]


async def create_indexes():
    """
    Idempotent — safe to call on every startup.
    Only creates indexes that don't already exist.
    """
    try:
        # ── Users ──────────────────────────────────────────────
        await users_col().create_index("email", unique=True)
        await users_col().create_index("role")
        await users_col().create_index("office_id")          # ← NEW: filter users by office

        # ── Refresh tokens ─────────────────────────────────────
        await refresh_tokens_col().create_index("token", unique=True)
        await refresh_tokens_col().create_index("user_id")
        # Auto-expire stale tokens from MongoDB after 8 days
        await refresh_tokens_col().create_index(
            "expires_at", expireAfterSeconds=0
        )

        # ── Enquiries ──────────────────────────────────────────
        await enquiries_col().create_index("timestamp")
        await enquiries_col().create_index("status")
        await enquiries_col().create_index("phone")

        # ── Attendance ─────────────────────────────────────────
        # Compound index: employee + date is the primary lookup pattern
        await attendance_col().create_index([("employee_id", 1), ("date", -1)])
        await attendance_col().create_index("date")
        await attendance_col().create_index("office_id")     # ← NEW: filter log by office

        # ── Leaves ─────────────────────────────────────────────
        await leaves_col().create_index([("employee_id", 1), ("status", 1)])
        await leaves_col().create_index("status")

        # ── Leave balances ─────────────────────────────────────
        await leave_balances_col().create_index(
            [("employee_id", 1), ("year", 1)], unique=True
        )

        # ── Offices (NEW) ──────────────────────────────────────
        await offices_col().create_index("name")
        await offices_col().create_index("is_active")

        # ── Holidays ───────────────────────────────────────────
        # unique=True matches the existing Atlas index — keeps startup idempotent
        await get_db()["holidays"].create_index("date", unique=True)

        # ── Metrics ────────────────────────────────────────────
        await get_db()["metrics"].create_index("key", unique=True)

        logger.info("MongoDB indexes verified ✓")

    except Exception as e:
        logger.error(f"Index creation failed: {e}")
        raise


async def close_connection():
    global _client
    if _client:
        _client.close()
        _client = None