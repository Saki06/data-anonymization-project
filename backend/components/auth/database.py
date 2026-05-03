"""
MongoDB Database Connection
Async MongoDB connection using Motor driver.
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

# MongoDB connection settings
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "anonymization_system")

# Global client & db references
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None
_connected: bool = False


async def connect_db() -> AsyncIOMotorDatabase | None:
    """
    Initialize the MongoDB connection and return the database instance.
    Returns None if MongoDB is unreachable (app continues without auth).
    """
    global _client, _db, _connected
    try:
        _client = AsyncIOMotorClient(
            MONGO_URL,
            serverSelectionTimeoutMS=5000,  # 5-second timeout
            connectTimeoutMS=5000,
        )
        # Test the connection
        await _client.admin.command("ping")

        _db = _client[MONGO_DB_NAME]

        # Ensure unique index on email
        await _db.users.create_index("email", unique=True)

        _connected = True
        print(f"[AUTH] Connected to MongoDB: {MONGO_DB_NAME}")
        return _db
    except Exception as e:
        _connected = False
        print(f"[AUTH] MongoDB unavailable: {e}")
        print("[AUTH]   Auth endpoints will return 503. Start MongoDB to enable login/signup.")
        return None


async def close_db() -> None:
    """Close the MongoDB connection."""
    global _client, _connected
    if _client:
        _client.close()
        _connected = False
        print("[AUTH] MongoDB connection closed")


def get_db() -> AsyncIOMotorDatabase:
    """Return the current database instance. Raises if not connected."""
    if not _connected or _db is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please ensure MongoDB is running."
        )
    return _db


def is_db_connected() -> bool:
    """Check whether MongoDB is connected."""
    return _connected
