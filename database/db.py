# -*- coding: utf-8 -*-
import aiosqlite
import json
from config import DB_NAME

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                session_string TEXT,
                prefix TEXT DEFAULT '.',
                prefix_enabled INTEGER DEFAULT 1,
                coins INTEGER DEFAULT 100,
                is_vip INTEGER DEFAULT 0,
                settings TEXT DEFAULT '{}'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS relations (
                owner_id INTEGER,
                target_id INTEGER,
                type TEXT,
                PRIMARY KEY (owner_id, target_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auto_replies (
                owner_id INTEGER,
                trigger TEXT,
                response TEXT,
                PRIMARY KEY (owner_id, trigger)
            )
        """)
        await db.commit()
