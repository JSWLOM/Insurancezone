"""
Run once to create the first admin account in MongoDB.

Usage:
    python seed_admin.py

Requirements:
    - .env file populated with MONGODB_URL and DB_NAME
    - pip install motor passlib[bcrypt] python-dotenv
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from datetime import datetime
from dotenv import load_dotenv
import os
import sys

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_EMAIL = "jaiswalom435@gmail.com"
ADMIN_PASSWORD = "Izone@123"   # ← CHANGE THIS before running!


async def seed():
    mongodb_url = os.getenv("MONGODB_URL")
    db_name = os.getenv("DB_NAME", "insurancezone")

    if not mongodb_url:
        print("❌ MONGODB_URL not set in .env")
        sys.exit(1)

    client = AsyncIOMotorClient(mongodb_url)
    db = client[db_name]

    existing = await db["users"].find_one({"email": ADMIN_EMAIL})
    if existing:
        print(f"⚠️  Admin with email {ADMIN_EMAIL} already exists.")
        print("    To reset password, delete the user from Atlas and re-run.")
        client.close()
        return

    admin = {
        "name": "Super Admin",
        "email": ADMIN_EMAIL,
        "hashed_password": pwd_context.hash(ADMIN_PASSWORD[:72]),
        "role": "admin",
        "department": "Management",
        "phone": "+91 7233013806",
        "is_active": True,
        "created_at": datetime.utcnow(),
        "created_by": "seed_script",
    }

    await db["users"].insert_one(admin)
    print("=" * 55)
    print("✅  Admin account created successfully!")
    print(f"    Email   : {ADMIN_EMAIL}")
    print(f"    Password: {ADMIN_PASSWORD}")
    print("=" * 55)
    print("⚠️  IMPORTANT: Change this password immediately after first login.")
    print("    Use POST /api/auth/login to get a token,")
    print("    then PATCH /api/auth/users/<id> to update the password.")

    client.close()


if __name__ == "__main__":
    asyncio.run(seed())