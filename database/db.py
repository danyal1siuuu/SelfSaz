# -*- coding: utf-8 -*-
import aiosqlite
from config import DB_NAME


async def _ensure_column(db, table: str, column: str, definition: str):
    cursor = await db.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in await cursor.fetchall()}
    if column not in existing:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                session_string TEXT,
                prefix TEXT DEFAULT '.',
                prefix_enabled INTEGER DEFAULT 1,
                coins INTEGER DEFAULT 100,
                is_vip INTEGER DEFAULT 0,
                settings TEXT DEFAULT '{}',
                plan TEXT DEFAULT 'normal',
                activity_score INTEGER DEFAULT 0,
                last_daily_claim INTEGER DEFAULT 0,
                previous_plan TEXT DEFAULT 'normal'
            )
            """
        )

        # Safe migrations for existing databases.
        await _ensure_column(db, "users", "settings", "TEXT DEFAULT '{}'")
        await _ensure_column(db, "users", "prefix", "TEXT DEFAULT '.'")
        await _ensure_column(db, "users", "prefix_enabled", "INTEGER DEFAULT 1")
        await _ensure_column(db, "users", "coins", "INTEGER DEFAULT 100")
        await _ensure_column(db, "users", "is_vip", "INTEGER DEFAULT 0")
        await _ensure_column(db, "users", "plan", "TEXT DEFAULT 'normal'")
        await _ensure_column(db, "users", "activity_score", "INTEGER DEFAULT 0")
        await _ensure_column(db, "users", "last_daily_claim", "INTEGER DEFAULT 0")
        await _ensure_column(db, "users", "previous_plan", "TEXT DEFAULT 'normal'")

        # Normalize legacy rows. Existing VIP users become diamond; everyone
        # else gets the free normal plan unless they already have a valid plan.
        await db.execute("UPDATE users SET plan = 'diamond' WHERE COALESCE(is_vip, 0) = 1")
        await db.execute(
            "UPDATE users SET plan = 'normal' WHERE plan IS NULL OR plan NOT IN ('normal','iron','bronze','silver','gold','diamond')"
        )
        await db.execute("UPDATE users SET previous_plan = 'normal' WHERE previous_plan IS NULL OR previous_plan = ''")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS relations (
                owner_id INTEGER,
                target_id INTEGER,
                type TEXT,
                PRIMARY KEY (owner_id, target_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_replies (
                owner_id INTEGER,
                trigger TEXT,
                response TEXT,
                PRIMARY KEY (owner_id, trigger)
            )
            """
        )
        await db.commit()
