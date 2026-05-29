from motor.motor_asyncio import AsyncIOMotorClient
from config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

# Single client instance reused across requests
_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_url)
    return _client


def get_db():
    return get_client()[settings.db_name]


# Collections — typed accessors
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


async def create_indexes():
    """
    Run once on startup to ensure all performance-critical indexes exist.
    Idempotent — safe to call multiple times.
    """
    try:
        # Users
        await users_col().create_index("email", unique=True)
        await users_col().create_index("role")

        # Refresh tokens
        await refresh_tokens_col().create_index("token", unique=True)
        await refresh_tokens_col().create_index("user_id")
        # Auto-expire stale tokens from MongoDB after 8 days
        await refresh_tokens_col().create_index(
            "expires_at", expireAfterSeconds=0
        )

        # Enquiries
        await enquiries_col().create_index("timestamp")
        await enquiries_col().create_index("status")
        await enquiries_col().create_index("phone")

        # Attendance — compound index so lookups by employee+date are fast
        await attendance_col().create_index([("employee_id", 1), ("date", -1)])
        await attendance_col().create_index("date")

        # Leaves
        await leaves_col().create_index([("employee_id", 1), ("status", 1)])
        await leaves_col().create_index("status")

        # Leave balances
        await leave_balances_col().create_index(
            [("employee_id", 1), ("year", 1)], unique=True
        )

        logger.info("MongoDB indexes verified ✓")
    except Exception as e:
        logger.error(f"Index creation failed: {e}")
        raise


async def close_connection():
    global _client
    if _client:
        _client.close()
        _client = None