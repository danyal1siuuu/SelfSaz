# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import aiosqlite
import json
import os
import time
import yt_dlp
from config import BOT_TOKEN, DB_NAME, ADMIN_ID
from core.manager import (
    start_single_client, stop_single_client, ACTIVE_CLIENTS, 
    timename_loop, restore_original_name, stop_all_clients, 
    restart_all_clients, clean_server_temp_files
)
from plugins.fun_crypto import fetch_live_market_data, format_market_display

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
CHANNEL_URL = "https://t.me/Vip_Viro"
USER_STATES = {}
TARGET_USER_ADMIN = {}
REGISTRATION_OPEN = True
START_TIME = time.time()

class HttpBot:
    def __init__(self):
        self.running = False

    async def send_message(self, chat_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{API_URL}/sendMessage", json=payload) as resp:
                    return await resp.json()
        except Exception:
            pass

    async def edit_message(self, chat_id, message_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{API_URL}/editMessageText", json=payload) as resp:
                    return await resp.json()
        except Exception:
            pass

    async def answer_callback(self, callback_query_id, text=None, alert=False):
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = alert
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(f"{API_URL}/answerCallbackQuery", json=payload)
        except Exception:
            pass

    async def send_document(self, chat_id, file_path, caption=None):
        data = aiohttp.FormData()
        data.add_field("chat_id", str(chat_id))
        if caption:
            data.add_field("caption", caption)
        data.add_field("document", open(file_path, "rb"))
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{API_URL}/sendDocument", data=data) as resp:
                    return await resp.json()
        except Exception:
            pass

    async def send_video_file(self, chat_id, file_path, caption=None):
        data = aiohttp.FormData()
        data.add_field("chat_id", str(chat_id))
        if caption:
            data.add_field("caption", caption)
        data.add_field("video", open(file_path, "rb"))
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{API_URL}/sendVideo", data=data) as resp:
                    return await resp.json()
        except Exception:
            pass

    async def get_user_db(self, user_id):
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("SELECT session_string, coins, is_vip, prefix, prefix_enabled, settings FROM users WHERE user_id = ?", (user_id,))
            return await cursor.fetchone()

    async def update_setting_db(self, user_id, key, val):
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("SELECT settings FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            st = json.loads(row[0]) if row and row[0] else {}
            st[key] = val
            await db.execute("UPDATE users SET settings = ? WHERE user_id = ?", (json.dumps(st), user_id))
            await db.commit()
            if user_id in ACTIVE_CLIENTS:
                ACTIVE_CLIENTS[user_id].settings = st
                setattr(ACTIVE_CLIENTS[user_id], key, val)

    def get_main_dashboard_kb(self, is_online, is_admin=False):
        status_btn = "🟢 وضعیت سلف: روشن (خاموش کردن)" if is_online else "🔴 وضعیت سلف: خاموش (روشن کردن)"
        toggle_cb = "btn_turn_off" if is_online else "btn_turn_on"
        kb = [
            [{"text": status_btn, "callback_data": toggle_cb}],
            [{"text": "🔄 راه‌اندازی مجدد سلف", "callback_data": "btn_restart"}, {"text": "📈 نرخ لحظه‌ای ارز و طلا", "callback_data": "menu_rates"}],
            [{"text": "⏰ ساعت روی اسم (۱۰ فونت)", "callback_data": "menu_timename"}, {"text": "🤖 منشی هوشمند", "callback_data": "menu_monshi"}],
            [{"text": "🗑 پاکسازی خودکار پیام‌ها", "callback_data": "menu_cleaner"}, {"text": "🛡 لیست دوستان و دشمنان", "callback_data": "menu_relations"}],
            [{"text": "⚡️ تغییر پیشوند (.)", "callback_data": "menu_prefix"}, {"text": "🛠 جعبه ابزارها و دانلودر", "callback_data": "menu_tools"}]
        ]
        if is_admin:
            kb.append([{"text": "👑 سوپر پنل مدیریت ادمین (۶۰ قابلیت)", "callback_data": "menu_admin"}])
        kb.append([{"text": "🛑 خروج و پاک کردن اکانت", "callback_data": "btn_delete_account"}, {"text": "📢 کانال پشتیبانی", "url": CHANNEL_URL}])
        return {"inline_keyboard": kb}

    async def start(self):
        self.running = True
        offset = 0
        print("[+] Ultimate HTTP Bot Online.")
        async with aiohttp.ClientSession() as session:
            while self.running:
                try:
                    url = f"{API_URL}/getUpdates?offset={offset}&timeout=20"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for update in data.get("result", []):
                                offset = update["update_id"] + 1
                                asyncio.create_task(self.handle_update(update))
                except Exception:
                    await asyncio.sleep(2)

    async def handle_update(self, update):
        global REGISTRATION_OPEN
        # ----------------- پیام‌های ورودی متنی -----------------
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg.get("from", {}).get("id", chat_id)
            text = msg.get("text", "").strip()
            is_admin = (user_id == ADMIN_ID)

            if text in ["/start", "/panel"]:
                USER_STATES.pop(user_id, None)
                u = await self.get_user_db(user_id)
                if u:
                    is_online = user_id in ACTIVE_CLIENTS
                    p_text = (
                        "👑 **داشبورد مدیریت یکپارچه سلف‌بات**\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🆔 شناسه شما: `{user_id}`\n"
                        f"⚡️ وضعیت اتصال: {'فعال و روشن 🟢' if is_online else 'خاموش 🔴'}\n"
                        f"💰 موجودی: `{u[1]}` سکه | پلن: {'VIP 💎 (نامحدود)' if u[2] else 'عادی 👤'}\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        "👇 کنترل تمام قابلیت‌ها ۱۰۰٪ دکمه‌ای است؛ انتخاب کنید:"
                    )
                    return await self.send_message(chat_id, p_text, reply_markup=self.get_main_dashboard_kb(is_online, is_admin))
                else:
                    kb = {
                        "inline_keyboard": [
                            [{"text": "🔑 اتصال اکانت (ارسال سشن)", "callback_data": "btn_submit_session"}],
                            [{"text": "📢 کانال پشتیبانی", "url": CHANNEL_URL}]
                        ]
                    }
                    return await self.send_message(chat_id, "👋 **به سیستم مدیریت سلف‌ساز خوش آمدید!**\n\nجهت راه‌اندازی و اتصال سلف روی دکمه زیر کلیک کنید:", reply_markup=kb)

            if text == "/admin" and is_admin:
                USER_STATES.pop(user_id, None)
                return await self.show_admin_hub(chat_id)

            # ۱. دانلود از یوتیوب داخل خود بات (بدون ارور شناسه عددی)
            if USER_STATES.get(user_id) == "WAITING_YOUTUBE":
                USER_STATES.pop(user_id, None)
                if "http" in text and ("youtube.com" in text or "youtu.be" in text):
                    wait_m = await self.send_message(chat_id, "⏳ در حال استخراج و دانلود ویدیو از یوتیوب...")
                    opts = {
                        'format': 'best[ext=mp4]/best',
                        'outtmpl': f'downloads/yt_{user_id}_%(id)s.%(ext)s',
                        'max_filesize': 45 * 1024 * 1024
                    }
                    try:
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(text, download=True)
                            fname = ydl.prepare_filename(info)
                        await self.send_message(chat_id, "📤 ویدیو با موفقیت دانلود شد؛ در حال آپلود...")
                        await self.send_video_file(chat_id, fname, caption=f"🎬 **{info.get('title', 'YouTube Video')}**")
                        if os.path.exists(fname):
                            os.remove(fname)
                    except Exception as e:
                        await self.send_message(chat_id, f"❌ خطا در دانلود یوتیوب:\n`{e}`")
                else:
                    await self.send_message(chat_id, "❌ لینک ارسال شده معتبر نمی‌باشد.")
                return

            # دریافت سشن
            if USER_STATES.get(user_id) == "WAITING_SESSION":
                if not REGISTRATION_OPEN and not is_admin:
                    USER_STATES.pop(user_id, None)
                    return await self.send_message(chat_id, "🔒 در حال حاضر ثبت‌نام و اتصال کاربران جدید توسط مدیریت موقتاً بسته شده است.")
                if len(text) > 40:
                    await self.send_message(chat_id, "⏳ در حال اتصال آنی سلف به سرور...")
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT OR REPLACE INTO users (user_id, session_string, coins, prefix, prefix_enabled, settings) VALUES (?, ?, 100, '.', 1, '{}')", (user_id, text))
                        await db.commit()

                    started, err = await start_single_client(user_id, text)
                    USER_STATES.pop(user_id, None)

                    if started:
                        await self.send_message(chat_id, "🎉 **سلف شما روشن شد!** اکنون همه قابلیت‌ها را با دکمه‌ها کنترل کنید:", reply_markup=self.get_main_dashboard_kb(True, is_admin))
                    else:
                        await self.send_message(chat_id, f"❌ خطا در روشن شدن:\n`{err}`")
                else:
                    await self.send_message(chat_id, "❌ استرینگ سشن ارسالی نامعتبر است.")

            # دریافت پیام همگانی ادمین
            elif USER_STATES.get(user_id) == "WAITING_BROADCAST" and is_admin:
                USER_STATES.pop(user_id, None)
                await self.send_message(chat_id, "⏳ در حال ارسال همگانی...")
                cnt = 0
                async with aiosqlite.connect(DB_NAME) as db:
                    cursor = await db.execute("SELECT user_id FROM users")
                    rows = await cursor.fetchall()
                for r in rows:
                    try:
                        await self.send_message(r[0], f"📢 **اطلاعیه رسمی مدیریت:**\n\n{text}")
                        cnt += 1
                        await asyncio.sleep(0.08)
                    except Exception:
                        pass
                return await self.send_message(chat_id, f"✅ پیام با موفقیت به {cnt} کاربر ارسال شد.")

            # دریافت آیدی کاربر توسط ادمین
            elif USER_STATES.get(user_id) == "WAITING_TARGET_USER" and is_admin:
                USER_STATES.pop(user_id, None)
                if text.isdigit():
                    t_uid = int(text)
                    t_data = await self.get_user_db(t_uid)
                    if t_data:
                        TARGET_USER_ADMIN[user_id] = t_uid
                        return await self.show_target_user_card(chat_id, t_uid, t_data)
                    else:
                        return await self.send_message(chat_id, f"❌ کاربری با شناسه `{t_uid}` یافت نشد.")
                else:
                    return await self.send_message(chat_id, "❌ شناسه عددی نامعتبر است.")

            # ارسال پیام اختصاصی به کاربر توسط ادمین
            elif USER_STATES.get(user_id) == "WAITING_DM_USER" and is_admin:
                USER_STATES.pop(user_id, None)
                t_uid = TARGET_USER_ADMIN.get(user_id)
                if t_uid:
                    await self.send_message(t_uid, f"📩 **پیام ویژه از طرف مدیریت:**\n\n{text}")
                    return await self.send_message(chat_id, f"✅ پیام به کاربر `{t_uid}` ارسال شد.")

        # ----------------- دکمه‌ها و کلیک‌ها -----------------
        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            user_id = cq.get("from", {}).get("id", chat_id)
            msg_id = cq["message"]["message_id"]
            data = cq.get("data")
            is_admin = (user_id == ADMIN_ID)

            # امنیت: اگر سلف حذف شده بود تمام دکمه‌های پیام‌های قبلی قفل شوند
            allowed_unregistered = ["btn_submit_session", "back_home"]
            is_admin_action = is_admin and (data.startswith("ad_") or data == "menu_admin")
            if not is_admin_action and data not in allowed_unregistered:
                u_check = await self.get_user_db(user_id)
                if not u_check:
                    await self.answer_callback(cq["id"], "❌ سلف شما حذف شده و این دکمه‌ها منقضی شده‌اند!", alert=True)
                    kb_reconnect = {"inline_keyboard": [[{"text": "🔑 اتصال مجدد سلف", "callback_data": "btn_submit_session"}]]}
                    return await self.edit_message(chat_id, msg_id, "🛑 این پنل منقضی شده است. برای فعال‌سازی مجدد روی دکمه زیر بزنید:", reply_markup=kb_reconnect)

            if data == "btn_submit_session":
                USER_STATES[user_id] = "WAITING_SESSION"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "back_home"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📱 کد استرینگ سشن را ارسال کنید:", reply_markup=kb)

            # خاموش / روشن / ریستارت
            elif data == "btn_turn_off":
                await stop_single_client(user_id)
                await self.answer_callback(cq["id"], "🛑 سلف خاموش شد و نام قبلی شما بازگشت.")
                return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (خاموش 🔴)**", reply_markup=self.get_main_dashboard_kb(False, is_admin))

            elif data == "btn_turn_on":
                u = await self.get_user_db(user_id)
                if u:
                    ok, err = await start_single_client(user_id, u[0])
                    if ok:
                        await self.answer_callback(cq["id"], "🟢 سلف روشن شد!")
                        return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (روشن 🟢)**", reply_markup=self.get_main_dashboard_kb(True, is_admin))
                    else:
                        await self.answer_callback(cq["id"], f"خطا در روشن شدن:\n{err}", alert=True)

            elif data == "btn_restart":
                u = await self.get_user_db(user_id)
                if u:
                    await stop_single_client(user_id)
                    await asyncio.sleep(1)
                    await start_single_client(user_id, u[0])
                    await self.answer_callback(cq["id"], "🔄 سلف ریستارت شد!", alert=True)
                    return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (روشن 🟢)**", reply_markup=self.get_main_dashboard_kb(True, is_admin))

            elif data == "btn_delete_account":
                await stop_single_client(user_id)
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                    await db.execute("DELETE FROM relations WHERE owner_id = ?", (user_id,))
                    await db.commit()
                await self.answer_callback(cq["id"], "اکانت و سلف شما پاک شد.", alert=True)
                kb = {"inline_keyboard": [[{"text": "🔑 اتصال مجدد سلف", "callback_data": "btn_submit_session"}]]}
                return await self.edit_message(chat_id, msg_id, "🛑 سلف شما متوقف و حذف شد.", reply_markup=kb)

            # نرخ لحظه‌ای ارز، طلا و رمزارز
            elif data in ["menu_rates", "refresh_rates"]:
                await self.answer_callback(cq["id"], "🔄 درحال استعلام مظنه زنده...")
                rates_data = await fetch_live_market_data()
                market_text = format_market_display(rates_data)
                kb = {
                    "inline_keyboard": [
                        [{"text": "🔄 به‌روزرسانی لحظه‌ای نرخ‌ها", "callback_data": "refresh_rates"}],
                        [{"text": "🔙 بازگشت به منوی اصلی", "callback_data": "back_dashboard"}]
                    ]
                }
                return await self.edit_message(chat_id, msg_id, market_text, reply_markup=kb)

            # ساعت روی اسم (۱۰ فونت)
            elif data == "menu_timename":
                cli = ACTIVE_CLIENTS.get(user_id)
                t_on = getattr(cli, "timename_active", False) if cli else False
                st_text = "خاموش کردن ساعت 🔴 (برگشت به اسم قبلی)" if t_on else "روشن کردن ساعت 🟢"
                kb = {
                    "inline_keyboard": [
                        [{"text": st_text, "callback_data": "toggle_timename"}],
                        [{"text": "فونت ۱ (𝟎𝟎:𝟎𝟎)", "callback_data": "font_1"}, {"text": "فونت ۲ (𝟘𝟘:𝟘𝟘)", "callback_data": "font_2"}],
                        [{"text": "فونت ۳ (⓪⓪:⓪⓪)", "callback_data": "font_3"}, {"text": "فونت ۴ (𝟶𝟶:𝟶𝟶)", "callback_data": "font_4"}],
                        [{"text": "فونت ۵ (𝟬𝟬:𝟬𝟬)", "callback_data": "font_5"}, {"text": "فونت ۶ (⓿⓿:⓿⓿)", "callback_data": "font_6"}],
                        [{"text": "فونت ۷ (𝟢𝟢:𝟢𝟢)", "callback_data": "font_7"}, {"text": "فونت ۸ (۰۰:۰۰)", "callback_data": "font_8"}],
                        [{"text": "فونت ۹ (⁰⁰:⁰⁰)", "callback_data": "font_9"}, {"text": "فونت ۱۰ (₀₀:₀₀)", "callback_data": "font_10"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = f"⏰ **ساعت خودکار روی اسم (۱۰ فونت متنوع)**\nوضعیت فعلی: `{'روشن 🟢' if t_on else 'خاموش 🔴'}`"
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "toggle_timename":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ ابتدا سلف را روشن کنید.", alert=True)
                if cli.timename_active:
                    cli.timename_active = False
                    if cli.timename_task:
                        cli.timename_task.cancel()
                    await restore_original_name(cli)
                    await self.update_setting_db(user_id, "timename_active", False)
                    await self.answer_callback(cq["id"], "🛑 ساعت خاموش شد و نام قبلی شما بازگشت.")
                else:
                    cli.timename_active = True
                    await self.update_setting_db(user_id, "timename_active", True)
                    cli.timename_task = asyncio.create_task(timename_loop(cli, cli.original_name, cli.settings.get("timename_font", 1)))
                    await self.answer_callback(cq["id"], "🟢 ساعت با موفقیت روشن شد
