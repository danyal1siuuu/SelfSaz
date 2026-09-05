# -*- coding: utf-8 -*-
import asyncio
import os
from pyrogram import Client
from config import API_ID, API_HASH, DB_NAME
import aiosqlite

ACTIVE_CLIENTS = {}

async def start_single_client(user_id: int, session_str: str):
    """روشن کردن درجا و بدون قفل سلف در حافظه موقت (RAM)"""
    # خاموش کردن و قطع اتصال قبلی در صورت وجود
    if user_id in ACTIVE_CLIENTS:
        try:
            await ACTIVE_CLIENTS[user_id].stop()
        except Exception:
            pass
        ACTIVE_CLIENTS.pop(user_id, None)

    # پاک کردن هرگونه فایل کش جا مانده برای جلوگیری از تداخل
    session_file = f"self_{user_id}.session"
    if os.path.exists(session_file):
        try:
            os.remove(session_file)
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
            in_memory=True,  # جلوگیری قطعی از قفل شدن سشن
            plugins=dict(root="plugins")
        )
        await cli.start()
        cli.custom_prefix = "."
        cli.prefix_enabled = True
        ACTIVE_CLIENTS[user_id] = cli
        print(f"[🔥 Hot-Reload] سلف کاربر {user_id} با موفقیت روشن شد!")
        return True, ""
    except Exception as e:
        err_msg = str(e)
        print(f"[!] خطا در اجرای سلف {user_id}: {err_msg}")
        return False, err_msg

async def stop_single_client(user_id: int):
    """قطع اتصال و خاموش کردن کامل سلف"""
    if user_id in ACTIVE_CLIENTS:
        try:
            cli = ACTIVE_CLIENTS[user_id]
            if cli.is_connected:
                await cli.stop()
        except Exception:
            pass
        finally:
            ACTIVE_CLIENTS.pop(user_id, None)
        return True
    return False

async def launch_all_existing_selfs():
    """لود خودکار تمام کاربران پس از بالا آمدن سرور"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, session_string FROM users WHERE session_string IS NOT NULL")
        rows = await cursor.fetchall()

    for uid, sess in rows:
        asyncio.create_task(start_single_client(uid, sess))
