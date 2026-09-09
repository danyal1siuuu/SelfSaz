# -*- coding: utf-8 -*-
import asyncio
import os
import json
import glob
from datetime import datetime
import pytz
from pyrogram import Client
from config import API_ID, API_HASH, DB_NAME
from plugins.account_automations import start_account_automations, stop_account_automations
import aiosqlite

ACTIVE_CLIENTS = {}

FONTS = {
    1: dict(zip("0123456789:", "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗:")),
    2: dict(zip("0123456789:", "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡︰")),
    3: dict(zip("0123456789:", "⓪①②③④⑤⑥⑦⑧⑨﹕")),
    4: dict(zip("0123456789:", "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿：")),
    5: dict(zip("0123456789:", "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵꞉")),
    6: dict(zip("0123456789:", "⓿❶❷❸❹❺❻❼❽❾︓")),
    7: dict(zip("0123456789:", "𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫ː")),
    8: dict(zip("0123456789:", "۰۱۲۳۴۵۶۷۸۹⋮")),
    9: dict(zip("0123456789:", "٠١٢٣٤٥٦٧٨٩∙")),
    10: dict(zip("0123456789:", "⁰¹²³⁴⁵⁶⁷⁸⁹⸬")),
    11: dict(zip("0123456789:", "₀₁₂₃₄₅₆₇₈₉﹒")),
    12: dict(zip("0123456789:", "０１２３４５６７８９⸱")),
    13: dict(zip("0123456789:", "০১২৩৪৫৬৭৮৯⸮")),
    14: dict(zip("0123456789:", "०१२३४५६७८९ꞏ")),
    15: dict(zip("0123456789:", "๐๑๒๓๔๕๖๗๘๙∶")),
    16: dict(zip("0123456789:", "០១២៣៤៥៦៧៨៩⁝")),
    17: dict(zip("0123456789:", "၀၁၂၃၄၅၆၇၈၉⸴")),
    18: dict(zip("0123456789:", "໐໑໒໓໔໕໖໗໘໙⸺")),
    19: dict(zip("0123456789:", "૦૧૨૩૪૫૬૭૮૯﹡")),
    20: dict(zip("0123456789:", "೦೧೨೩೪೫೬೭೮೯⸰")),
    21: dict(zip("0123456789:", "౦౧౨౩౪౫౬౭౮౯⹉")),
    22: dict(zip("0123456789:", "൦൧൨൩൪൫൬൭൮൯⸪")),
    23: dict(zip("0123456789:", "௦௧௨௩௪௫௬௭௮௯⸫")),
    24: dict(zip("0123456789:", "୦୧୨୩୪୫୬୭୮୯᛬")),
    25: dict(zip("0123456789:", "੦੧੨੩੪੫੬੭੮੯⁚")),
}

def clean_profile_name(first_name: str) -> str:
    """پاکسازی ساعت قبلی از انتهای نام بدون رجکس خطرناک و بدون باگ یونیکد"""
    if not first_name:
        return "Self"
    all_time_chars = set("0123456789: ")
    for f in FONTS.values():
        for ch in f.values():
            all_time_chars.add(ch)

    parts = first_name.rsplit(" ", 1)
    if len(parts) == 2 and ":" in parts[1]:
        if all(c in all_time_chars for c in parts[1].strip()):
            return parts[0].strip() or "Self"
    return first_name.strip() or "Self"

async def timename_loop(client: Client, base_name: str, font_id: int):
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
        try:
            from core.plans import get_timename_interval
            interval = await get_timename_interval(client.me.id)
        except Exception:
            interval = 20
        await asyncio.sleep(interval)

async def restore_original_name(client: Client):
    orig = getattr(client, "original_name", None) or client.settings.get("original_name")
    if orig:
        try:
            await client.update_profile(first_name=orig)
            print(f"[⏰ Name Restored] نام اکانت به '{orig}' برگردانده شد.")
        except Exception:
            pass

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
            app_version="5.7.0",
            session_string=session_str,
            in_memory=True,
            plugins=dict(root="plugins")
        )
        await cli.start()

        me = await cli.get_me()
        clean_name = clean_profile_name(me.first_name)
        cli.original_name = settings.get("original_name") or clean_name
        settings["original_name"] = cli.original_name

        cli.custom_prefix = user_prefix
        cli.prefix_enabled = prefix_on
        cli.settings = settings
        cli.cleaner_active = settings.get("cleaner_active", False)
        cli.cleaner_delay = settings.get("cleaner_delay", 20)
        cli.monshi_active = settings.get("monshi_active", False)
        raw_font = settings.get("timename_font", 1)
        try:
            saved_font = int(raw_font)
        except (TypeError, ValueError):
            saved_font = 1
        cli.timename_font = min(25, max(1, saved_font))
        if cli.timename_font != saved_font:
            settings["timename_font"] = cli.timename_font
            try:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET settings=? WHERE user_id=?", (json.dumps(settings, ensure_ascii=False), user_id))
                    await db.commit()
            except Exception:
                pass
        cli.timename_active = bool(settings.get("timename_active", False))
        cli.auto_read_active = settings.get("auto_read_active", False)
        cli.auto_reply_active = settings.get("auto_reply_active", False)
        cli.away_active = settings.get("away_active", False)
        cli.monshi_replied_users = {}
        cli.auto_reply_users = {}
        cli.timename_task = None

        if cli.timename_active:
            font = cli.timename_font
            cli.timename_task = asyncio.create_task(timename_loop(cli, cli.original_name, font))

        await start_account_automations(cli)
        ACTIVE_CLIENTS[user_id] = cli
        print(f"[🔥 Hot-Reload] سلف {user_id} آنلاین شد!")
        return True, ""
    except Exception as e:
        err_msg = str(e)
        print(f"[!] خطا در اجرای سلف {user_id}: {err_msg}")
        return False, err_msg

async def stop_single_client(user_id: int):
    if user_id in ACTIVE_CLIENTS:
        try:
            cli = ACTIVE_CLIENTS[user_id]
            await stop_account_automations(cli)
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

async def stop_all_clients():
    """خاموش‌سازی همگانی توسط ادمین"""
    count = len(ACTIVE_CLIENTS)
    for uid in list(ACTIVE_CLIENTS.keys()):
        await stop_single_client(uid)
    return count

async def restart_all_clients():
    """ریستارت همگانی سلف‌ها توسط ادمین"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, session_string FROM users WHERE session_string IS NOT NULL")
        rows = await cursor.fetchall()
    count = 0
    for uid, sess in rows:
        await stop_single_client(uid)
        await asyncio.sleep(0.5)
        ok, _ = await start_single_client(uid, sess)
        if ok:
            count += 1
    return count

def clean_server_temp_files():
    """پاکسازی فایل‌های بی‌استفاده و کش‌ها"""
    deleted = 0
    for pattern in ["*.session", "*.session-journal", "downloads/*"]:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
                deleted += 1
            except Exception:
                pass
    return deleted

async def launch_all_existing_selfs():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, session_string FROM users WHERE session_string IS NOT NULL")
        rows = await cursor.fetchall()
    for uid, sess in rows:
        asyncio.create_task(start_single_client(uid, sess))
