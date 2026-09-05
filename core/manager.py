# -*- coding: utf-8 -*-
import asyncio
from pyrogram import Client
from config import API_ID, API_HASH, DB_NAME
import aiosqlite

ACTIVE_CLIENTS = {}

async def start_single_client(user_id: int, session_str: str):
    """روشن کردن آنی سلف یک کاربر در لحظه بدون نیاز به ریستارت سرور"""
    if user_id in ACTIVE_CLIENTS:
        try:
            await ACTIVE_CLIENTS[user_id].stop()
        except Exception:
            pass

    try:
        cli = Client(
            name=f"self_{user_id}",
            api_id=API_ID,
            api_hash=API_HASH,
            device_model="Desktop",
            system_version="Windows 10",
            app_version="4.16.8 x64",
            lang_code="en",
            session_string=session_str,
            plugins=dict(root="plugins")
        )
        await cli.start()
        cli.custom_prefix = "."
        cli.prefix_enabled = True
        ACTIVE_CLIENTS[user_id] = cli
        print(f"[🔥 Hot-Reload] سلف کاربر {user_id} با موفقیت در لحظه روشن شد!")
        return True
    except Exception as e:
        print(f"[!] خطا در ران کردن سلف {user_id}: {e}")
        return False

async def stop_single_client(user_id: int):
    """خاموش کردن سلف کاربر"""
    if user_id in ACTIVE_CLIENTS:
        try:
            await ACTIVE_CLIENTS[user_id].stop()
            del ACTIVE_CLIENTS[user_id]
            return True
        except Exception:
            pass
    return False

async def launch_all_existing_selfs():
    """لود تمام کاربران ثبت شده در هنگام روشن شدن اولیه سرور"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, session_string FROM users WHERE session_string IS NOT NULL")
        rows = await cursor.fetchall()

    for uid, sess in rows:
        asyncio.create_task(start_single_client(uid, sess))
