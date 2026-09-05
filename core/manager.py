# -*- coding: utf-8 -*-
import asyncio
import os
import json
from datetime import datetime
import pytz
from pyrogram import Client
from config import API_ID, API_HASH, DB_NAME
import aiosqlite

ACTIVE_CLIENTS = {}
FONTS = {
    1: {"0": "𝟎", "1": "𝟏", "2": "𝟐", "3": "𝟑", "4": "𝟒", "5": "𝟓", "6": "𝟔", "7": "𝟕", "8": "𝟖", "9": "𝟗"},
    2: {"0": "𝟘", "1": "𝟙", "2": "𝟚", "3": "𝟛", "4": "𝟜", "5": "𝟝", "6": "𝟞", "7": "𝟟", "8": "𝟠", "9": "𝟡"},
    3: {"0": "⓪", "1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤", "6": "⑥", "7": "⑦", "8": "⑧", "9": "⑨"}
}

async def timename_loop(client: Client, base_name: str, font_id: int):
    """حلقه تغییر خودکار ساعت روی نام پروفایل"""
    tz = pytz.timezone("Asia/Tehran")
    last_t = ""
    while getattr(client, "timename_active", False):
        try:
            now_t = datetime.now(tz).strftime("%H:%M")
            if now_t != last_t:
                last_t = now_t
                f = FONTS.get(font_id, FONTS[1])
                clock_str = "".join(f.get(c, c) for c in now_t)
                await client.update_profile(first_name=f"{base_name} {clock_str}")
        except Exception:
            pass
        await asyncio.sleep(20)

async def start_single_client(user_id: int, session_str: str):
    """روشن کردن درجا و بدون قفل سلف در حافظه موقت (RAM)"""
    if user_id in ACTIVE_CLIENTS:
        try:
            await ACTIVE_CLIENTS[user_id].stop()
        except Exception:
            pass
        ACTIVE_CLIENTS.pop(user_id, None)

    for sf in [f"self_{user_id}.session", f"self_{user_id}.session-journal"]:
        if os.path.exists(sf):
            try:
                os.remove(sf)
            except Exception:
                pass

    user_prefix = "."
    prefix_on = True
    settings = {}
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("SELECT prefix, prefix_enabled, settings FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            if row:
                user_prefix = row[0] or "."
                prefix_on = bool(row[1])
                settings = json.loads(row[2]) if row[2] else {}
    except Exception:
        pass

    try:
        cli = Client(
            name=f"self_{user_id}",
            api_id=API_ID,
            api_hash=API_HASH,
            device_model="SelfSaz Pro",
            system_version="Linux x64",
            app_version="5.3.0",
            session_string=session_str,
            in_memory=True,
            plugins=dict(root="plugins")
        )
        await cli.start()

        cli.custom_prefix = user_prefix
        cli.prefix_enabled = prefix_on
        cli.settings = settings
        cli.cleaner_active = settings.get("cleaner_active", False)
        cli.cleaner_delay = settings.get("cleaner_delay", 20)
        cli.monshi_active = settings.get("monshi_active", False)
        cli.timename_active = settings.get("timename_active", False)
        cli.timename_task = None

        if cli.timename_active:
            name_base = settings.get("timename_base", "Self")
            font = settings.get("timename_font", 1)
            cli.timename_task = asyncio.create_task(timename_loop(cli, name_base, font))

        ACTIVE_CLIENTS[user_id] = cli
        print(f"[🔥 Hot-Reload] سلف {user_id} با موفقیت آنلاین شد!")
        return True, ""
    except Exception as e:
        err_msg = str(e)
        print(f"[!] خطا در استارت {user_id}: {err_msg}")
        return False, err_msg

async def stop_single_client(user_id: int):
    if user_id in ACTIVE_CLIENTS:
        try:
            cli = ACTIVE_CLIENTS[user_id]
            cli.timename_active = False
            if cli.timename_task:
                cli.timename_task.cancel()
            if cli.is_connected:
                await cli.stop()
        except Exception:
            pass
        finally:
            ACTIVE_CLIENTS.pop(user_id, None)
        return True
    return False

async def launch_all_existing_selfs():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, session_string FROM users WHERE session_string IS NOT NULL")
        rows = await cursor.fetchall()
    for uid, sess in rows:
        asyncio.create_task(start_single_client(uid, sess))
