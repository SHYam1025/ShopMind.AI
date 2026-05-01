"""
Storage — SQLite-based persistent store for delivery profiles and order history.
Uses aiosqlite for fully async I/O.
"""

import aiosqlite
import json
import logging
from datetime import datetime

from models.schemas import DeliveryProfile, OrderConfirmation

logger = logging.getLogger(__name__)
DB_PATH = "shopmind.db"


async def init_db():
    """Create tables if they don't exist. Call on app startup."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS delivery_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                profile_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                order_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()
    logger.info("Database initialized")


async def save_profile(profile: DeliveryProfile) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO delivery_profiles (email, profile_json, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                profile_json = excluded.profile_json,
                updated_at = excluded.updated_at
            """,
            (profile.email, profile.model_dump_json(), now, now),
        )
        await db.commit()
    logger.info("Profile saved | email=%s", profile.email)


async def get_profile(email: str) -> DeliveryProfile | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT profile_json FROM delivery_profiles WHERE email = ?", (email,)
        ) as cursor:
            row = await cursor.fetchone()
    if row:
        return DeliveryProfile.model_validate_json(row[0])
    return None


async def save_order(order: OrderConfirmation) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO orders (order_id, email, order_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (order.order_id, order.email_sent_to, order.model_dump_json(), now),
        )
        await db.commit()
    logger.info("Order saved | order_id=%s", order.order_id)


async def get_orders(email: str) -> list[OrderConfirmation]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT order_json FROM orders WHERE email = ? ORDER BY created_at DESC",
            (email,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [OrderConfirmation.model_validate_json(r[0]) for r in rows]
