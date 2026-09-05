# -*- coding: utf-8 -*-
import asyncio
import os
import json
import re
from datetime import datetime
import pytz
from pyrogram import Client
from config import API_ID, API_HASH, DB_NAME
import aiosqlite

ACTIVE_CLIENTS = {}

# ۱۰ مدل فونت جذاب و متنوع
FONTS = {
    1: {"0": "𝟎", "1": "𝟏", "2": "𝟐", "3": "𝟑", "4": "𝟒", "5": "𝟓", "6": "𝟔", "7": "𝟕", "8": "𝟖", "9": "𝟗"}, # ضخیم سِریف
    2: {"0": "𝟘", "1": "𝟙", "2": "𝟚", "3": "𝟛", "4": "𝟜", "5": "𝟝", "6": "𝟞", "7": "𝟟", "8": "𝟠", "9": "𝟡"}, # دابل توخالی
    3: {"0": "⓪", "1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤", "6": "⑥", "7": "⑦", "8": "⑧", "9": "⑨"}, # دایره‌ای
    4: {"0": "𝟶", "1": "𝟷", "2": "𝟸", "3": "𝟹", "4": "𝟺", "5": "𝟻", "6": "𝟼", "7": "𝟽", "8": "𝟾", "9": "𝟿"}, # مونو / ترمینال
    5: {"0": "𝟬", "1": "𝟭", "2": "𝟮", "3": "𝟯", "4": "𝟰", "5": "𝟱", "6": "𝟲", "7": "𝟳", "8": "𝟴", "9": "𝟵"}, # ضخیم مدرن
    6: {"0": "⓿", "1": "❶", "2": "❷", "3": "❸", "4": "❹", "5": "❺", "6": "❻", "7": "❼", "8": "❽", "9": "❾"}, # دایره مشکی
    7: {"0": "𝟢", "1": "𝟣", "2": "𝟤", "3": "𝟥", "4": "𝟦", "5": "𝟧", "6": "𝟨", "7": "𝟩", "8": "𝟪", "9": "𝟫"}, # فانتزی
    8: {"0": "۰", "1": "۱", "2": "۲", "3": "۳", "4": "۴", "5": "۵", "6": "۶", "7": "۷", "8": "۸", "9": "۹"}, # فارسی اصیل
    9: {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹"}, # بالانویس
    10: {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉"} # زیرنویس
}

async def timename_loop(client: Client, base_name: str, font_id: int):
    """حلقه تغییر خودکار ساعت روی نام اکانت"""
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

async def restore_original_name(client: Client):
    """بازگرداندن نام اصلی کاربر به محض خاموش شدن ساعت"""
    orig = getattr(client, "original_name", None) or client.settings.get("original_name")
    if orig:
        try:
            await client.update_profile(first_name=orig)
            print(f"[⏰ Name Restored] نام اکانت به '{orig}' برگردانده شد.")
        except Exception as e:
            print(f"[!] خطا در بازگرداندن نام: {e}")

async def start_single_client(user_id: int, session_str: str):
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
            app_version="5.5.0",
            session_string=session_str,
            in_memory=True,
            plugins=dict(root="plugins")
        )
        await cli.start()

        # ذخیره نام واقعی اکانت در اولین اجرا
        me = await cli.get_me()
        clean_name = re.sub(r'\s+[\d\:\s٠-۹۰-۹⓪-⑨𝟎-𝟿⁰-⁹₀-₉❶-❾]+$', '', me.first_name).strip() or "Self"
        cli.original_name = settings.get("original_name") or clean_name
        settings["original_name"] = cli.original_name

        cli.custom_prefix = user_prefix
        cli.prefix_enabled = prefix_on
        cli.settings = settings
        cli.cleaner_active = settings.get("cleaner_active", False)
        cli.cleaner_delay = settings.get("cleaner_delay", 20)
        cli.monshi_active = settings.get("monshi_active", False)
        cli.timename_active = settings.get("timename_active", False)
        cli.timename_task = None

        if cli.timename_active:
            font = settings.get("timename_font", 1)
            cli.timename_task = asyncio.create_task(timename_loop(cli, cli.original_name, font))

        ACTIVE_CLIENTS[user_id] = cli
        print(f"[🔥 Hot-Reload] سلف {user_id} آنلاین شد!")
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
            await restore_original_name(cli)
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
