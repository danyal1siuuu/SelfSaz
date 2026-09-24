# -*- coding: utf-8 -*-
"""Persistent system settings and small admin-audit helpers for SelfSaz."""
from __future__ import annotations

import json
import time
from typing import Any

import aiosqlite

from config import DB_NAME


async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
        row = await cur.fetchone()
    return row[0] if row else default


async def set_setting(key: str, value: Any) -> None:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO system_settings(key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, int(time.time())),
        )
        await db.commit()


async def delete_setting(key: str) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM system_settings WHERE key = ?", (key,))
        await db.commit()


async def get_json_setting(key: str, default: Any = None) -> Any:
    raw = await get_setting(key, "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


async def audit_log(actor_id: int, action: str, target_id: int | None = None, detail: str = "") -> None:
    # Global audit switch is persistent and enforced here, so the admin toggle is real.
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("SELECT value FROM system_settings WHERE key = ?", ("audit_enabled",))
        row = await cur.fetchone()
        if row and str(row[0]).strip() == "0":
            return
        await db.execute(
            "INSERT INTO audit_logs(actor_id, target_id, action, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (actor_id, target_id, action, detail[:2000], int(time.time())),
        )
        await db.commit()
