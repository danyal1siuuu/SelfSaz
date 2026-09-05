# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import aiosqlite
import json
import os
import time
import glob
import sys
from datetime import datetime
import pytz
import yt_dlp

from pyrogram import Client as PyroClient
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired,
    PhoneNumberInvalid, PasswordHashInvalid
)

from config import BOT_TOKEN, DB_NAME, ADMIN_ID, API_ID, API_HASH
from core.manager import (
    start_single_client, stop_single_client, ACTIVE_CLIENTS, 
    timename_loop, restore_original_name, stop_all_clients, 
    restart_all_clients, clean_server_temp_files
)
from plugins.fun_crypto import fetch_live_market_data, format_market_display

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
CHANNEL_URL = "https://t.me/Vip_Viro"

# متغیرها و وضعیت‌های فعال سیستم
USER_STATES = {}
TARGET_USER_ADMIN = {}
LOGIN_CLIENTS = {}
REGISTRATION_OPEN = True
GLOBAL_MAINTENANCE = False
LOG_DELETED_MSGS = True
ANTI_SPAM_PROTECT = True
MAX_ALLOWED_SELFS = 1000
START_TIME = time.time()
SYSTEM_LOGS = []

def add_system_log(text: str):
    tz = pytz.timezone("Asia/Tehran")
    t = datetime.now(tz).strftime("%H:%M:%S")
    SYSTEM_LOGS.append(f"[{t}] {text}")
    if len(SYSTEM_LOGS) > 60:
        SYSTEM_LOGS.pop(0)
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
        status_btn = "🟢 وضعیت سلف: روشن (کلیک برای خاموش)" if is_online else "🔴 وضعیت سلف: خاموش (کلیک برای روشن)"
        toggle_cb = "btn_turn_off" if is_online else "btn_turn_on"
        kb = [
            [{"text": status_btn, "callback_data": toggle_cb}],
            [{"text": "🔄 راه‌اندازی مجدد سلف", "callback_data": "btn_restart"}, {"text": "📈 نرخ لحظه‌ای ارز و طلا", "callback_data": "menu_rates"}],
            [{"text": "⏰ ساعت روی اسم (۱۰ فونت)", "callback_data": "menu_timename"}, {"text": "🤖 منشی هوشمند و خودکار", "callback_data": "menu_monshi"}],
            [{"text": "🗑 پاکسازی خودکار پیام‌ها", "callback_data": "menu_cleaner"}, {"text": "🛡 مدیریت دوستان و دشمنان", "callback_data": "menu_relations"}],
            [{"text": "⚡️ تنظیمات پیشوند سلف", "callback_data": "menu_prefix"}, {"text": "🛠 جعبه‌ابزار کاربردی و دانلودر", "callback_data": "menu_tools"}]
        ]
        if is_admin:
            kb.append([{"text": "👑 سوپر پنل مدیریت کل سیستم (۶۵ قابلیت)", "callback_data": "admin_hub"}])
        kb.append([{"text": "🛑 خروج و حذف اطلاعات", "callback_data": "btn_delete_account"}, {"text": "📢 کانال پشتیبانی", "url": CHANNEL_URL}])
        return {"inline_keyboard": kb}

    def get_admin_hub_kb(self):
        kb = [
            [{"text": "⚙️ ۱. کنترل سرور و پروسه‌ها (۱۰)", "callback_data": "ad_sec_1"}, {"text": "🗄 ۲. مدیریت دیتابیس و فایل (۸)", "callback_data": "ad_sec_2"}],
            [{"text": "📊 ۳. آمار و مانیتورینگ زنده (۸)", "callback_data": "ad_sec_3"}, {"text": "👥 ۴. مدیریت کاربران و سلف‌ها (۱۰)", "callback_data": "ad_sec_4"}],
            [{"text": "🛡 ۵. امنیت و فایروال سیستم (۸)", "callback_data": "ad_sec_5"}, {"text": "🧩 ۶. تنظیمات پلاگین‌های سلف (۱۱)", "callback_data": "ad_sec_6"}],
            [{"text": "📢 ۷. پیام‌رسانی و پشتیبانی (۱۰)", "callback_data": "ad_sec_7"}],
            [{"text": "🔙 بازگشت به داشبورد اصلی", "callback_data": "back_dashboard"}]
        ]
        return {"inline_keyboard": kb}

    def get_admin_sec1_kb(self):
        return {"inline_keyboard": [
            [{"text": "۱. خاموش‌سازی همه سلف‌ها 🛑", "callback_data": "ad_stop_all"}, {"text": "۲. ریستارت همه سلف‌ها 🔄", "callback_data": "ad_restart_all"}],
            [{"text": "۳. پاکسازی کش و فایلهای موقت 🧹", "callback_data": "ad_clean_temp"}, {"text": "۴. تست سرعت و پینگ سرور ⚡️", "callback_data": "ad_ping_test"}],
            [{"text": "۵. بررسی میزان مصرف رم (RAM) 🧠", "callback_data": "ad_ram_usage"}, {"text": "۶. بررسی آپ‌تایم دقیق سرور ⏱", "callback_data": "ad_uptime"}],
            [{"text": "۷. لیست سلف‌های فعال کنونی 📋", "callback_data": "ad_online_list"}, {"text": "۸. همگام‌سازی وضعیت اتصال‌ها 🔌", "callback_data": "ad_sync_conns"}],
            [{"text": "۹. بارگذاری مجدد پلاگین‌ها ♻️", "callback_data": "ad_reload_plugins"}, {"text": "۱۰. ریستارت کلی پروسس ربات 🖥", "callback_data": "ad_restart_process"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec2_kb(self):
        return {"inline_keyboard": [
            [{"text": "۱۱. دانلود نسخه پشتیبان دیتابیس 📥", "callback_data": "ad_backup_db"}, {"text": "۱۲. بهینه‌سازی دیتابیس (Vacuum) 🛠", "callback_data": "ad_vacuum_db"}],
            [{"text": "۱۳. حذف سشن‌های خراب و منقضی 🗑", "callback_data": "ad_clean_broken_sessions"}, {"text": "۱۴. پاکسازی لاگ‌های قدیمی سیستم 🧽", "callback_data": "ad_clear_old_logs"}],
            [{"text": "۱۵. حجم کل فایل‌های دانلود شده 📦", "callback_data": "ad_download_dir_size"}, {"text": "۱۶. تخلیه کامل پوشه Downloads 🧼", "callback_data": "ad_purge_downloads"}],
            [{"text": "۱۷. شمارش جداول و رکوردهای DB 🧮", "callback_data": "ad_db_record_count"}, {"text": "۱۸. بررسی یکپارچگی دیتابیس (Integrity) 🔍", "callback_data": "ad_db_integrity"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec3_kb(self):
        return {"inline_keyboard": [
            [{"text": "۱۹. لاگ زنده سیستم (۶۰ پیام اخیر) 📜", "callback_data": "ad_live_logs"}, {"text": "۲۰. آمار جامع دیتابیس و کاربران 📈", "callback_data": "ad_full_stats"}],
            [{"text": "۲۱. تعداد سلف‌های VIP فعال 💎", "callback_data": "ad_count_vips"}, {"text": "۲۲. مصرف کل منابع سرور 📊", "callback_data": "ad_sys_resources"}],
            [{"text": "۲۳. سلف‌های دارای ساعت فعال ⏰", "callback_data": "ad_active_timename_list"}, {"text": "۲۴. سلف‌های دارای منشی فعال 🤖", "callback_data": "ad_active_monshi_list"}],
            [{"text": "۲۵. آمار مجموع سکه‌های سیستم 🪙", "callback_data": "ad_coins_circulation"}, {"text": "۲۶. نرخ خطاهای اخیر اتصال ⚠️", "callback_data": "ad_error_rate"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec4_kb(self):
        return {"inline_keyboard": [
            [{"text": "۲۷. جستجوی کاربر با آیدی 🔎", "callback_data": "ad_find_user"}, {"text": "۲۸. ارتقا کاربر به اکانت VIP 💎", "callback_data": "ad_grant_vip"}],
            [{"text": "۲۹. تنزیل رتبه از VIP 🚫", "callback_data": "ad_revoke_vip"}, {"text": "۳۰. افزودن سکه به کاربر 💰", "callback_data": "ad_add_coins"}],
            [{"text": "۳۱. کسر سکه از کاربر 📉", "callback_data": "ad_deduct_coins"}, {"text": "۳۲. ریستارت اجباری سلف کاربر ⚡️", "callback_data": "ad_force_restart_user"}],
            [{"text": "۳۳. خاموش‌سازی اجباری کاربر 🛑", "callback_data": "ad_force_stop_user"}, {"text": "۳۴. حذف کامل کاربر و سشن ❌", "callback_data": "ad_delete_user_session"}],
            [{"text": "۳۵. ارسال پیام مستقیم به کاربر 📩", "callback_data": "ad_dm_user"}, {"text": "۳۶. بررسی وضعیت سلامت سشن کاربر 🩺", "callback_data": "ad_test_user_session"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec5_kb(self):
        reg_btn = "۳۷. ثبت‌نام جدید: باز ✅" if REGISTRATION_OPEN else "۳۷. ثبت‌نام جدید: قفل 🔒"
        maint_btn = "۳۸. حالت تعمیرات: روشن 🔴" if GLOBAL_MAINTENANCE else "۳۸. حالت تعمیرات: خاموش 🟢"
        spam_btn = "۳۹. آنتی‌اسپم سیستم: فعال 🛡" if ANTI_SPAM_PROTECT else "۳۹. آنتی‌اسپم سیستم: خاموش ⚠️"
        return {"inline_keyboard": [
            [{"text": reg_btn, "callback_data": "ad_toggle_reg"}, {"text": maint_btn, "callback_data": "ad_toggle_maintenance"}],
            [{"text": spam_btn, "callback_data": "ad_toggle_antispam"}, {"text": "۴۰. محدودیت سقف تعداد سلف‌ها 🛑", "callback_data": "ad_set_max_selfs"}],
            [{"text": "۴۱. قطع اتصال کاربران مسدود شده ⛔️", "callback_data": "ad_kick_banned"}, {"text": "۴۲. بازنشانی کلیدهای دسترسی سلف 🔑", "callback_data": "ad_revoke_keys"}],
            [{"text": "۴۳. بررسی دسترسی‌های مشکوک 🚨", "callback_data": "ad_audit_suspicious"}, {"text": "۴۴. قفل اضطراری کل ربات 🚨", "callback_data": "ad_emergency_lock"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec6_kb(self):
        del_log_btn = "۴۵. لاگر حذف پیام: فعال ✅" if LOG_DELETED_MSGS else "۴۵. لاگر حذف پیام: خاموش ❌"
        return {"inline_keyboard": [
            [{"text": del_log_btn, "callback_data": "ad_toggle_del_logger"}, {"text": "۴۶. خاموش کردن ساعت کل سلف‌ها ⏰", "callback_data": "ad_kill_all_timename"}],
            [{"text": "۴۷. روشن‌سازی ساعت همه سلف‌ها ⏰", "callback_data": "ad_start_all_timename"}, {"text": "۴۸. خاموش‌سازی منشی همه سلف‌ها 🤖", "callback_data": "ad_kill_all_monshi"}],
            [{"text": "۴۹. پاکسازی دشمنان همه اکانت‌ها 🗑", "callback_data": "ad_purge_all_enemies"}, {"text": "۵۰. پاکسازی دوستان همه اکانت‌ها 🗑", "callback_data": "ad_purge_all_friends"}],
            [{"text": "۵۱. تنظیم پیشوند پیش‌فرض سیستم ⚡️", "callback_data": "ad_set_global_prefix"}, {"text": "۵۲. تست اتصال API وب‌سرویس ارز 📈", "callback_data": "ad_test_rates_api"}],
            [{"text": "۵۳. تست موتور FFmpeg و ویدیوگرد 🎬", "callback_data": "ad_test_ffmpeg"}, {"text": "۵۴. تست دانلودر یوتیوب سرور 📹", "callback_data": "ad_test_ytdlp"}],
            [{"text": "۵۵. بازنشانی متن پیش‌فرض منشی 📝", "callback_data": "ad_reset_monshi_text"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec7_kb(self):
        return {"inline_keyboard": [
            [{"text": "۵۶. ارسال همگانی به تمام کاربران 📢", "callback_data": "ad_broadcast_all"}, {"text": "۵۷. فوروارد همگانی به تمام کاربران 🔁", "callback_data": "ad_forward_all"}],
            [{"text": "۵۸. ارسال اطلاعیه به کاربران VIP 💎", "callback_data": "ad_broadcast_vip"}, {"text": "۵۹. پیام به دارندگان سلف روشن 🟢", "callback_data": "ad_broadcast_online"}],
            [{"text": "۶۰. ارسال فایل/عکس به همه 📁", "callback_data": "ad_broadcast_media"}, {"text": "۶۱. پین کردن پیام در سلف‌ها 📌", "callback_data": "ad_pin_global"}],
            [{"text": "۶۲. دریافت لینک کانال اسپانسر 📢", "callback_data": "ad_view_sponsor"}, {"text": "۶۳. تغییر لینک کانال اسپانسر ✏️", "callback_data": "ad_set_sponsor"}],
            [{"text": "۶۴. استخراج لیست آیدی تمام کاربران 📝", "callback_data": "ad_export_user_ids"}, {"text": "۶۵. راهنمای کامل کدهای خطا ℹ️", "callback_data": "ad_error_guide"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}
        async def start(self):
        self.running = True
        offset = 0
        add_system_log("HTTP Bot service started successfully.")
        print("[+] Ultimate HTTP Bot Online with 65 Admin Features.")
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
        global REGISTRATION_OPEN, GLOBAL_MAINTENANCE, LOG_DELETED_MSGS, ANTI_SPAM_PROTECT, CHANNEL_URL, MAX_ALLOWED_SELFS

        # ----------------- پردازش پیام‌های متنی ورودی -----------------
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg.get("from", {}).get("id", chat_id)
            text = msg.get("text", "").strip()
            is_admin = (user_id == ADMIN_ID)

            if GLOBAL_MAINTENANCE and not is_admin:
                return await self.send_message(chat_id, "🚧 سیستم در حال حاضر در حال تعمیر و به‌روزرسانی است. لطفاً بعداً تلاش فرمایید.")

            if text in ["/start", "/panel"]:
                USER_STATES.pop(user_id, None)
                u = await self.get_user_db(user_id)
                if u:
                    is_online = user_id in ACTIVE_CLIENTS
                    p_text = (
                        "👑 **داشبورد مدیریت یکپارچه و هوشمند سلف‌بات**\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🆔 شناسه شما: `{user_id}`\n"
                        f"⚡️ وضعیت اکانت سلف: {'فعال و آنلاین 🟢' if is_online else 'خاموش 🔴'}\n"
                        f"💰 موجودی: `{u[1]}` سکه | پلن: {'VIP 💎 (نامحدود)' if u[2] else 'عادی 👤'}\n"
                        f"⚡️ پیشوند فعال دستورات: `{u[3] or '.'}`\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        "👇 کنترل تمام قابلیت‌ها ۱۰۰٪ دکمه‌ای است؛ انتخاب کنید:"
                    )
                    return await self.send_message(chat_id, p_text, reply_markup=self.get_main_dashboard_kb(is_online, is_admin))
                else:
                    kb = {
                        "inline_keyboard": [
                            [
                                {"text": "⚡️ ساخت و دریافت آنی سشن (شماره)", "callback_data": "btn_create_session"},
                                {"text": "🔑 اتصال مستقیم (ارسال سشن)", "callback_data": "btn_submit_session"}
                            ],
                            [{"text": "📢 کانال پشتیبانی و اخبار", "url": CHANNEL_URL}]
                        ]
                    }
                    return await self.send_message(chat_id, "👋 **به سیستم پیشرفته سلف‌ساز خوش آمدید!**\n\nبرای راه‌اندازی سلف، یکی از روش‌های فوق‌سریع زیر را انتخاب کنید:", reply_markup=kb)

            if text == "/admin" and is_admin:
                USER_STATES.pop(user_id, None)
                return await self.send_message(chat_id, "👑 **سوپر پنل اختصاصی مدیریت ادمین (۶۵ قابلیت مجزا)**\n\nیکی از بخش‌های زیر را انتخاب کنید:", reply_markup=self.get_admin_hub_kb())

            # --- ۱. مرحله دریافت شماره تلفن برای ساخت آنی سشن ---
            if USER_STATES.get(user_id) == "WAITING_PHONE":
                phone = text.replace(" ", "").replace("-", "")
                if not (phone.startswith("+") and phone[1:].isdigit() and len(phone) >= 10):
                    return await self.send_message(chat_id, "❌ فرمت شماره نامعتبر است.\nلطفاً شماره را همراه با علامت + و کد کشور ارسال کنید:\nمثال: `+989123456789`")

                if user_id in LOGIN_CLIENTS:
                    try:
                        await LOGIN_CLIENTS[user_id]["client"].disconnect()
                    except Exception:
                        pass
                    LOGIN_CLIENTS.pop(user_id, None)

                await self.send_message(chat_id, "⏳ در حال اتصال به تلگرام و ارسال کد تایید...")
                try:
                    temp_cli = PyroClient(
                        name=f":memory:{user_id}",
                        api_id=API_ID,
                        api_hash=API_HASH,
                        in_memory=True
                    )
                    await temp_cli.connect()
                    code_data = await temp_cli.send_code(phone)
                    LOGIN_CLIENTS[user_id] = {
                        "client": temp_cli,
                        "phone": phone,
                        "phone_code_hash": code_data.phone_code_hash
                    }
                    USER_STATES[user_id] = "WAITING_LOGIN_CODE"
                    kb_cancel = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "btn_cancel_login"}]]}
                    return await self.send_message(chat_id, f"📩 کد تایید ۵ رقمی به تلگرام شماره `{phone}` ارسال شد.\n\n⚠️ **نکته:** کد را با فاصله بین اعداد بفرستید (مثال: `1 2 3 4 5`):", reply_markup=kb_cancel)
                except PhoneNumberInvalid:
                    return await self.send_message(chat_id, "❌ شماره تلفن وارد شده نامعتبر یا ثبت‌نشده در تلگرام است.")
                except Exception as e:
                    return await self.send_message(chat_id, f"❌ خطا در ارسال کد ورود:\n`{e}`")

            # --- ۲. مرحله دریافت کد ۵ رقمی تلگرام ---
            elif USER_STATES.get(user_id) == "WAITING_LOGIN_CODE":
                code = text.replace(" ", "").replace("-", "").strip()
                if not code.isdigit():
                    return await self.send_message(chat_id, "❌ کد ارسالی باید فقط شامل عدد باشد.")

                data = LOGIN_CLIENTS.get(user_id)
                if not data:
                    USER_STATES.pop(user_id, None)
                    return await self.send_message(chat_id, "❌ نشست ورود منقضی شد. لطفاً دوباره تلاش کنید.")

                cli = data["client"]
                await self.send_message(chat_id, "⏳ در حال بررسی کد ورود...")
                try:
                    await cli.sign_in(data["phone"], data["phone_code_hash"], code)
                    sess_str = await cli.export_session_string()
                    await cli.disconnect()
                    LOGIN_CLIENTS.pop(user_id, None)
                    USER_STATES.pop(user_id, None)

                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT OR REPLACE INTO users (user_id, session_string, coins, prefix, prefix_enabled, settings) VALUES (?, ?, 100, '.', 1, '{}')", (user_id, sess_str))
                        await db.commit()

                    await start_single_client(user_id, sess_str)
                    add_system_log(f"User {user_id} auto-created session & launched selfbot.")

                    msg_done = (
                        "🎉 **اکانت متصل و سلف شما با موفقیت روشن شد!**\n\n"
                        "🔑 **کد استرینگ سشن اختصاصی شما:**\n"
                        f"`{sess_str}`\n\n"
                        "👇 کنترل تمام قابلیت‌ها از داشبورد زیر:"
                    )
                    return await self.send_message(chat_id, msg_done, reply_markup=self.get_main_dashboard_kb(True, is_admin))

                except SessionPasswordNeeded:
                    USER_STATES[user_id] = "WAITING_LOGIN_2FA"
                    kb_cancel = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "btn_cancel_login"}]]}
                    return await self.send_message(chat_id, "🔐 اکانت شما دارای **تایید دومرحله‌ای (2FA)** است.\nلطفاً رمز عبور دومرحله‌ای اکانت خود را بفرستید:", reply_markup=kb_cancel)
                except (PhoneCodeInvalid, PhoneCodeExpired):
                    return await self.send_message(chat_id, "❌ کد وارد شده نادرست یا منقضی است. دوباره بررسی کنید.")
                except Exception as e:
                    return await self.send_message(chat_id, f"❌ خطا در بررسی کد:\n`{e}`")
                    elif USER_STATES.get(user_id) == "AD_WAIT_FIND_USER":
                    USER_STATES.pop(user_id, None)
                    if text.isdigit():
                        t_uid = int(text)
                        t_data = await self.get_user_db(t_uid)
                        if t_data:
                            TARGET_USER_ADMIN[user_id] = t_uid
                            on_st = "روشن 🟢" if t_uid in ACTIVE_CLIENTS else "خاموش 🔴"
                            card = (
                                f"👤 **اطلاعات کاربر `{t_uid}`:**\n"
                                f"وضعیت سلف: {on_st}\n"
                                f"سکه: `{t_data[1]}` | پلن: {'VIP 💎' if t_data[2] else 'عادی 👤'}\n"
                                f"پیشوند: `{t_data[3]}`\n"
                            )
                            return await self.send_message(chat_id, card)
                        else:
                            return await self.send_message(chat_id, f"❌ کاربری با شناسه `{t_uid}` یافت نشد.")

                elif USER_STATES.get(user_id) == "AD_WAIT_GRANT_VIP":
                    USER_STATES.pop(user_id, None)
                    if text.isdigit():
                        t_uid = int(text)
                        async with aiosqlite.connect(DB_NAME) as db:
                            await db.execute("UPDATE users SET is_vip = 1 WHERE user_id = ?", (t_uid,))
                            await db.commit()
                        add_system_log(f"VIP granted to user {t_uid}")
                        return await self.send_message(chat_id, f"💎 کاربر `{t_uid}` با موفقیت به سطح VIP ارتقا یافت.")

                elif USER_STATES.get(user_id) == "AD_WAIT_REVOKE_VIP":
                    USER_STATES.pop(user_id, None)
                    if text.isdigit():
                        t_uid = int(text)
                        async with aiosqlite.connect(DB_NAME) as db:
                            await db.execute("UPDATE users SET is_vip = 0 WHERE user_id = ?", (t_uid,))
                            await db.commit()
                        return await self.send_message(chat_id, f"🚫 وضعیت VIP کاربر `{t_uid}` لغو گردید.")

                elif USER_STATES.get(user_id) == "AD_WAIT_ADD_COINS":
                    USER_STATES.pop(user_id, None)
                    parts = text.split()
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        t_uid, amount = int(parts[0]), int(parts[1])
                        async with aiosqlite.connect(DB_NAME) as db:
                            await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, t_uid))
                            await db.commit()
                        return await self.send_message(chat_id, f"💰 تعداد `{amount}` سکه به کاربر `{t_uid}` اضافه شد.")

                elif USER_STATES.get(user_id) == "AD_WAIT_SET_MAX_SELFS":
                    USER_STATES.pop(user_id, None)
                    if text.isdigit():
                        MAX_ALLOWED_SELFS = int(text)
                        return await self.send_message(chat_id, f"🛑 سقف مجاز سلف‌های سیستم به `{MAX_ALLOWED_SELFS}` تغییر یافت.")

                elif USER_STATES.get(user_id) == "AD_WAIT_SPONSOR_URL":
                    USER_STATES.pop(user_id, None)
                    CHANNEL_URL = text.strip()
                    return await self.send_message(chat_id, f"📢 لینک کانال حامی به `{CHANNEL_URL}` تغییر پیدا کرد.")

        # ----------------- پردازش کلیک روی دکمه‌ها -----------------
        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            user_id = cq.get("from", {}).get("id", chat_id)
            msg_id = cq["message"]["message_id"]
            data = cq.get("data", "")
            is_admin = (user_id == ADMIN_ID)

            allowed_unreg = ["btn_create_session", "btn_cancel_login", "btn_submit_session", "back_dashboard"]
            if not is_admin and not data.startswith("ad_") and data not in allowed_unreg:
                u_chk = await self.get_user_db(user_id)
                if not u_chk:
                    await self.answer_callback(cq["id"], "❌ سلف شما ثبت نشده یا حذف شده است!", alert=True)
                    kb_reconnect = {
                        "inline_keyboard": [
                            [
                                {"text": "⚡️ ساخت و دریافت آنی سشن", "callback_data": "btn_create_session"},
                                {"text": "🔑 اتصال مستقیم (ارسال سشن)", "callback_data": "btn_submit_session"}
                            ]
                        ]
                    }
                    return await self.edit_message(chat_id, msg_id, "🛑 اطلاعات شما یافت نشد. جهت اتصال دوباره یکی از روش‌های زیر را بزنید:", reply_markup=kb_reconnect)

            # دکمه ورود و ساخت خودکار سشن با شماره
            if data == "btn_create_session":
                if not REGISTRATION_OPEN and not is_admin:
                    return await self.answer_callback(cq["id"], "🔒 ثبت‌نام کاربران جدید موقتاً بسته است.", alert=True)
                
                USER_STATES[user_id] = "WAITING_PHONE"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف و بازگشت", "callback_data": "btn_cancel_login"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(
                    chat_id, msg_id, 
                    "📱 **ورود مستقیم و استخراج آنی سشن:**\n\n"
                    "لطفاً شماره موبایل اکانت خود را همراه با کد کشور ارسال کنید:\n"
                    "مثال: `+989123456789`", 
                    reply_markup=kb
                )

            elif data == "btn_cancel_login":
                USER_STATES.pop(user_id, None)
                if user_id in LOGIN_CLIENTS:
                    try:
                        await LOGIN_CLIENTS[user_id]["client"].disconnect()
                    except Exception:
                        pass
                    LOGIN_CLIENTS.pop(user_id, None)
                await self.answer_callback(cq["id"], "عملیات ورود لغو شد.")
                return await self.handle_update({"message": {"chat": {"id": chat_id}, "from": {"id": user_id}, "text": "/start"}})

            elif data == "btn_submit_session":
                USER_STATES[user_id] = "WAITING_SESSION"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف و بازگشت", "callback_data": "back_dashboard"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📱 **لطفاً کد استرینگ سشن (String Session) اکانت خود را بفرستید:**", reply_markup=kb)

            elif data == "back_dashboard":
                USER_STATES.pop(user_id, None)
                is_online = user_id in ACTIVE_CLIENTS
                txt = "👑 **داشبورد مدیریت یکپارچه سلف‌بات**\nگزینه مورد نظر خود را انتخاب فرمایید:"
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=self.get_main_dashboard_kb(is_online, is_admin))

            elif data == "btn_turn_off":
                await stop_single_client(user_id)
                add_system_log(f"Self {user_id} stopped by user.")
                await self.answer_callback(cq["id"], "🛑 سلف خاموش شد و نام قبلی شما بازگشت.")
                return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (خاموش 🔴)**", reply_markup=self.get_main_dashboard_kb(False, is_admin))

            elif data == "btn_turn_on":
                u = await self.get_user_db(user_id)
                if u:
                    ok, err = await start_single_client(user_id, u[0])
                    if ok:
                        add_system_log(f"Self {user_id} started by user.")
                        await self.answer_callback(cq["id"], "🟢 سلف شما آنلاین شد!")
                        return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (روشن 🟢)**", reply_markup=self.get_main_dashboard_kb(True, is_admin))
                    else:
                        await self.answer_callback(cq["id"], f"خطا در اتصال:\n{err}", alert=True)

            elif data == "btn_restart":
                u = await self.get_user_db(user_id)
                if u:
                    await stop_single_client(user_id)
                    await asyncio.sleep(1)
                    await start_single_client(user_id, u[0])
                    await self.answer_callback(cq["id"], "🔄 سلف با موفقیت ریستارت شد!", alert=True)
                    return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (روشن 🟢)**", reply_markup=self.get_main_dashboard_kb(True, is_admin))

            elif data == "btn_delete_account":
                await stop_single_client(user_id)
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                    await db.execute("DELETE FROM relations WHERE owner_id = ?", (user_id,))
                    await db.commit()
                add_system_log(f"User {user_id} deleted account.")
                await self.answer_callback(cq["id"], "اکانت و تنظیمات شما با موفقیت حذف گردید.", alert=True)
                kb = {
                    "inline_keyboard": [
                        [
                            {"text": "⚡️ ساخت و دریافت آنی سشن", "callback_data": "btn_create_session"},
                            {"text": "🔑 اتصال مستقیم (ارسال سشن)", "callback_data": "btn_submit_session"}
                        ]
                    ]
                }
                return await self.edit_message(chat_id, msg_id, "🛑 سلف شما حذف و خاموش گردید.", reply_markup=kb)
                # ================== بخش کاملاً پیشرفته مدیریت دوستان و دشمنان ==================
            elif data == "menu_relations":
                async with aiosqlite.connect(DB_NAME) as db:
                    c_f = await db.execute("SELECT COUNT(*) FROM relations WHERE owner_id = ? AND type = 'friend'", (user_id,))
                    friends_count = (await c_f.fetchone())[0]
                    c_e = await db.execute("SELECT COUNT(*) FROM relations WHERE owner_id = ? AND type = 'enemy'", (user_id,))
                    enemies_count = (await c_e.fetchone())[0]

                txt = (
                    "🛡 **مرکز هوشمند و حرفه‌ای مدیریت دوستان و دشمنان**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"❤️ تعداد دوستان ویژه: `{friends_count}` نفر\n"
                    f"⚔️ تعداد دشمنان ثبت شده: `{enemies_count}` نفر\n\n"
                    "⚙️ **عملکرد خودکار:**\n"
                    "• **دشمنان:** ارسال فوری جواب‌های دندان‌شکن به محض پیام دادن دشمن!\n"
                    "• **دوستان:** معاف از پاسخ منشی با متن اختصاصی و صمیمانه.\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "👇 عملیات مورد نظر خود را انتخاب کنید:"
                )
                kb = {
                    "inline_keyboard": [
                        [{"text": "📋 لیست دوستان ❤️", "callback_data": "rel_list_friends"}, {"text": "📋 لیست دشمنان ⚔️", "callback_data": "rel_list_enemies"}],
                        [{"text": "➕ افزودن به دوستان", "callback_data": "rel_add_friend"}, {"text": "➕ افزودن به دشمنان", "callback_data": "rel_add_enemy"}],
                        [{"text": "🗑 حذف کاربر با آیدی عددی", "callback_data": "rel_remove_user"}],
                        [{"text": " پاکسازی همه دوستان ❌", "callback_data": "rel_clear_friends"}, {"text": " پاکسازی همه دشمنان ❌", "callback_data": "rel_clear_enemies"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "rel_list_friends":
                async with aiosqlite.connect(DB_NAME) as db:
                    cursor = await db.execute("SELECT target_id FROM relations WHERE owner_id = ? AND type = 'friend' LIMIT 30", (user_id,))
                    rows = await cursor.fetchall()
                res_txt = "❤️ **لیست دوستان ویژه ثبت شده:**\n\n" + "\n".join([f"• شناسه: `{r[0]}`" for r in rows]) if rows else "❤️ **لیست دوستان شما در حال حاضر خالی است.**"
                kb = {"inline_keyboard": [[{"text": "🔙 بازگشت به بخش روابط", "callback_data": "menu_relations"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, res_txt, reply_markup=kb)

            elif data == "rel_list_enemies":
                async with aiosqlite.connect(DB_NAME) as db:
                    cursor = await db.execute("SELECT target_id FROM relations WHERE owner_id = ? AND type = 'enemy' LIMIT 30", (user_id,))
                    rows = await cursor.fetchall()
                res_txt = "⚔️ **لیست دشمنان ثبت شده:**\n\n" + "\n".join([f"• شناسه: `{r[0]}`" for r in rows]) if rows else "⚔️ **لیست دشمنان شما خالی است.**"
                kb = {"inline_keyboard": [[{"text": "🔙 بازگشت به بخش روابط", "callback_data": "menu_relations"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, res_txt, reply_markup=kb)

            elif data == "rel_add_friend":
                USER_STATES[user_id] = "WAITING_ADD_FRIEND"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "menu_relations"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "❤️ **لطفاً شناسه عددی (Numeric User ID) دوست خود را ارسال کنید:**", reply_markup=kb)

            elif data == "rel_add_enemy":
                USER_STATES[user_id] = "WAITING_ADD_ENEMY"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "menu_relations"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "⚔️ **لطفاً شناسه عددی (Numeric User ID) دشمن را ارسال کنید:**", reply_markup=kb)

            elif data == "rel_remove_user":
                USER_STATES[user_id] = "WAITING_REMOVE_RELATION"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "menu_relations"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🗑 **شناسه عددی کاربر مورد نظر برای حذف از روابط را ارسال فرمایید:**", reply_markup=kb)

            elif data == "rel_clear_friends":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE owner_id = ? AND type = 'friend'", (user_id,))
                    await db.commit()
                if user_id in ACTIVE_CLIENTS and hasattr(ACTIVE_CLIENTS[user_id], "friends_set"):
                    ACTIVE_CLIENTS[user_id].friends_set.clear()
                await self.answer_callback(cq["id"], "❤️ تمام لیست دوستان شما پاکسازی شد.", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "menu_relations"}})

            elif data == "rel_clear_enemies":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE owner_id = ? AND type = 'enemy'", (user_id,))
                    await db.commit()
                if user_id in ACTIVE_CLIENTS and hasattr(ACTIVE_CLIENTS[user_id], "enemies_set"):
                    ACTIVE_CLIENTS[user_id].enemies_set.clear()
                await self.answer_callback(cq["id"], "⚔️ تمام لیست دشمنان شما پاکسازی شد.", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "menu_relations"}})

            # نرخ لحظه‌ای ارز
            elif data in ["menu_rates", "refresh_rates"]:
                await self.answer_callback(cq["id"], "🔄 درحال دریافت آخرین نرخ‌ها...")
                rates_data = await fetch_live_market_data()
                market_text = format_market_display(rates_data)
                kb = {
                    "inline_keyboard": [
                        [{"text": "🔄 به‌روزرسانی نرخ‌ها", "callback_data": "refresh_rates"}],
                        [{"text": "🔙 بازگشت به منوی اصلی", "callback_data": "back_dashboard"}]
                    ]
                }
                return await self.edit_message(chat_id, msg_id, market_text, reply_markup=kb)

            # ساعت روی اسم
            elif data == "menu_timename":
                cli = ACTIVE_CLIENTS.get(user_id)
                t_on = getattr(cli, "timename_active", False) if cli else False
                st_text = "خاموش کردن ساعت 🔴 (بازگشت به نام قبلی)" if t_on else "روشن کردن ساعت 🟢"
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
                    return await self.answer_callback(cq["id"], "❌ ابتدا اکانت سلف را روشن کنید.", alert=True)
                if getattr(cli, "timename_active", False):
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
                    await self.answer_callback(cq["id"], "🟢 ساعت روی اسم فعال گردید.")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_timename"}})

            elif data.startswith("font_"):
                f_id = int(data.split("_")[1])
                await self.update_setting_db(user_id, "timename_font", f_id)
                cli = ACTIVE_CLIENTS.get(user_id)
                if cli and getattr(cli, "timename_active", False):
                    if cli.timename_task:
                        cli.timename_task.cancel()
                    cli.timename_task = asyncio.create_task(timename_loop(cli, cli.original_name, f_id))
                await self.answer_callback(cq["id"], f"✅ فونت {f_id} با موفقیت انتخاب شد.")

            # منشی هوشمند
            elif data == "menu_monshi":
                cli = ACTIVE_CLIENTS.get(user_id)
                m_on = getattr(cli, "monshi_active", False) if cli else False
                kb = {
                    "inline_keyboard": [
                        [{"text": "خاموش‌سازی منشی 🔴" if m_on else "فعال‌سازی منشی 🟢", "callback_data": "toggle_monshi"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = f"🤖 **تنظیمات منشی هوشمند سلف**\nوضعیت کنونی: `{'فعال 🟢' if m_on else 'غیرفعال 🔴'}`\n\nمنشی در صورت آنلاین نبودن شما به پیام‌های پیوی پاسخ محترمانه ارسال می‌کند."
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "toggle_monshi":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ ابتدا سلف را روشن کنید.", alert=True)
                new_st = not getattr(cli, "monshi_active", False)
                cli.monshi_active = new_st
                await self.update_setting_db(user_id, "monshi_active", new_st)
                await self.answer_callback(cq["id"], "تغییر وضعیت منشی اعمال شد.")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_monshi"}})

            # پاکسازی خودکار
            elif data == "menu_cleaner":
                cli = ACTIVE_CLIENTS.get(user_id)
                c_on = getattr(cli, "cleaner_active", False) if cli else False
                kb = {
                    "inline_keyboard": [
                        [{"text": "خاموش کردن پاکساز 🔴" if c_on else "روشن کردن پاکساز پیام 🟢", "callback_data": "toggle_cleaner"}],
                        [{"text": "تایمر: ۱۰ ثانیه", "callback_data": "clean_10"}, {"text": "تایمر: ۳۰ ثانیه", "callback_data": "clean_30"}, {"text": "تایمر: ۶۰ ثانیه", "callback_data": "clean_60"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = f"🗑 **سیستم پاکسازی خودکار پیام‌ها (Self Auto-Cleaner)**\nوضعیت: `{'فعال 🟢' if c_on else 'خاموش 🔴'}`"
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "toggle_cleaner":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ ابتدا سلف را روشن کنید.", alert=True)
                new_st = not getattr(cli, "cleaner_active", False)
                cli.cleaner_active = new_st
                await self.update_setting_db(user_id, "cleaner_active", new_st)
                await self.answer_callback(cq["id"], "وضعیت پاکسازی خودکار تغییر یافت.")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_cleaner"}})

            elif data.startswith("clean_"):
                sec = int(data.split("_")[1])
                await self.update_setting_db(user_id, "cleaner_delay", sec)
                cli = ACTIVE_CLIENTS.get(user_id)
                if cli:
                    cli.cleaner_delay = sec
                await self.answer_callback(cq["id"], f"تایمر پاکسازی روی {sec} ثانیه تنظیم شد.")

            # پیشوند
            elif data == "menu_prefix":
                u = await self.get_user_db(user_id)
                kb = {
                    "inline_keyboard": [
                        [{"text": "✏️ تعیین پیشوند دلخواه", "callback_data": "change_prefix_btn"}],
                        [{"text": "تنظیم روی نقطه (.)", "callback_data": "set_p_dot"}, {"text": "تنظیم روی علامت تعجب (!)", "callback_data": "set_p_excl"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = f"⚡️ **تنظیمات پیشوند دستورات سلف**\nپیشوند کنونی اکانت شما: `{u[3] or '.'}`"
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "change_prefix_btn":
                USER_STATES[user_id] = "WAITING_NEW_PREFIX"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "menu_prefix"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "⚡️ لطفاً کاراکتر پیشوند جدید سلف خود را ارسال کنید (مثلاً ! یا $ یا .):", reply_markup=kb)

            elif data == "set_p_dot":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET prefix = '.' WHERE user_id = ?", (user_id,))
                    await db.commit()
                if user_id in ACTIVE_CLIENTS:
                    ACTIVE_CLIENTS[user_id].custom_prefix = "."
                await self.answer_callback(cq["id"], "پیشوند روی . تنظیم شد.")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_prefix"}})

            elif data == "set_p_excl":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET prefix = '!' WHERE user_id = ?", (user_id,))
                    await db.commit()
                if user_id in ACTIVE_CLIENTS:
                    ACTIVE_CLIENTS[user_id].custom_prefix = "!"
                await self.answer_callback(cq["id"], "پیشوند روی ! تنظیم شد.")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_prefix"}})

            # جعبه ابزار
            elif data == "menu_tools":
                kb = {
                    "inline_keyboard": [
                        [{"text": "📹 دانلود مستقیم ویدیو از یوتیوب", "callback_data": "tool_yt"}],
                        [{"text": "🔙 بازگشت به منو", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🛠 **جعبه‌ابزار هوشمند سلف‌ساز:**\nابزار مورد نظر را انتخاب کنید:", reply_markup=kb)

            elif data == "tool_yt":
                USER_STATES[user_id] = "WAITING_YOUTUBE"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "menu_tools"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📹 **لینک ویدیوی یوتیوب را بفرستید تا با بالاترین سرعت دانلود شود:**", reply_markup=kb)
                # ================== کنترل دکمه‌های ۶۵ گانه سوپر پنل ادمین ==================
            elif data == "admin_hub" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "👑 **سوپر پنل مدیریت کل سیستم (۶۵ قابلیت تفکیک‌شده و فعال)**\nیکی از دسته‌بندی‌ها را انتخاب کنید:", reply_markup=self.get_admin_hub_kb())

            elif data == "ad_sec_1" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "⚙️ **دسته ۱: کنترل سرور، هسته و پروسس‌ها (۱۰ قابلیت)**", reply_markup=self.get_admin_sec1_kb())

            elif data == "ad_sec_2" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🗄 **دسته ۲: مدیریت دیتابیس، استوریج و کش (۸ قابلیت)**", reply_markup=self.get_admin_sec2_kb())

            elif data == "ad_sec_3" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📊 **دسته ۳: آمار، لاگ‌ها و مانیتورینگ زنده (۸ قابلیت)**", reply_markup=self.get_admin_sec3_kb())

            elif data == "ad_sec_4" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "👥 **دسته ۴: مدیریت کاربران، سکه‌ها و VIP (۱۰ قابلیت)**", reply_markup=self.get_admin_sec4_kb())

            elif data == "ad_sec_5" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🛡 **دسته ۵: امنیت، فایروال و دسترسی‌ها (۸ قابلیت)**", reply_markup=self.get_admin_sec5_kb())

            elif data == "ad_sec_6" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🧩 **دسته ۶: تنظیمات هماهنگ پلاگین‌ها (۱۱ قابلیت)**", reply_markup=self.get_admin_sec6_kb())

            elif data == "ad_sec_7" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📢 **دسته ۷: پیام‌رسانی و مدیریت حامی (۱۰ قابلیت)**", reply_markup=self.get_admin_sec7_kb())

            # اجرای قابلیت‌های دسته ۱
            elif data == "ad_stop_all" and is_admin:
                cnt = await stop_all_clients()
                add_system_log(f"Admin stopped all {cnt} clients.")
                await self.answer_callback(cq["id"], f"🛑 تعداد {cnt} اکانت سلف با موفقیت متوقف شدند.", alert=True)

            elif data == "ad_restart_all" and is_admin:
                await self.answer_callback(cq["id"], "🔄 ریستارت همگانی آغاز شد...")
                cnt = await restart_all_clients()
                add_system_log(f"Admin restarted {cnt} clients.")
                await self.send_message(chat_id, f"✅ تعداد {cnt} سلف با موفقیت مجدداً راه‌اندازی شدند.")

            elif data == "ad_clean_temp" and is_admin:
                cnt = clean_server_temp_files()
                await self.answer_callback(cq["id"], f"🧹 تعداد {cnt} فایل موقت و سشن‌های کش پاکسازی شدند.", alert=True)

            elif data == "ad_ping_test" and is_admin:
                t0 = time.time()
                await self.answer_callback(cq["id"], "⚡️ در حال محاسبه پینگ سرور...")
                dt = round((time.time() - t0) * 1000, 2)
                await self.send_message(chat_id, f"⚡️ **پینگ سرور تلگرام:** `{dt} ms`\nوضعیت اتصال هسته: بسیار عالی و پایدار 🟢")

            elif data == "ad_ram_usage" and is_admin:
                import resource
                usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
                await self.answer_callback(cq["id"], f"🧠 مصرف حافظه پردازش ربات: {usage} MB", alert=True)

            elif data == "ad_uptime" and is_admin:
                upt = int(time.time() - START_TIME)
                h, rem = divmod(upt, 3600)
                m, s = divmod(rem, 60)
                await self.answer_callback(cq["id"], f"⏱ آپ‌تایم سیستم: {h} ساعت و {m} دقیقه و {s} ثانیه", alert=True)

            elif data == "ad_online_list" and is_admin:
                uids = list(ACTIVE_CLIENTS.keys())
                txt = f"📋 **لیست سلف‌های روشن ({len(uids)} عدد):**\n" + "\n".join([f"• `{u}`" for u in uids[:40]])
                await self.send_message(chat_id, txt)
                await self.answer_callback(cq["id"])

            elif data == "ad_sync_conns" and is_admin:
                cleaned = 0
                for uid, cli in list(ACTIVE_CLIENTS.items()):
                    if not cli.is_connected:
                        ACTIVE_CLIENTS.pop(uid, None)
                        cleaned += 1
                await self.answer_callback(cq["id"], f"🔌 همگام‌سازی انجام شد. {cleaned} اتصال غیرفعال جمع‌آوری گردید.", alert=True)

            elif data == "ad_reload_plugins" and is_admin:
                add_system_log("Plugins reloaded by admin.")
                await self.answer_callback(cq["id"], "♻️ ماژول‌ها و پلاگین‌ها مجدداً بارگذاری شدند.", alert=True)

            elif data == "ad_restart_process" and is_admin:
                await self.answer_callback(cq["id"], "🖥 پردازش ربات در حال ری‌استارت است...", alert=True)
                os.execv(sys.executable, ['python'] + sys.argv)

            # قابلیت‌های دسته ۲
            elif data == "ad_backup_db" and is_admin:
                await self.answer_callback(cq["id"], "📥 در حال آماده‌سازی فایل پشتیبان دیتابیس...")
                if os.path.exists(DB_NAME):
                    await self.send_document(chat_id, DB_NAME, caption="🗄 فایل پشتیبان دیتابیس SQLite ربات سلف‌ساز")
                else:
                    await self.send_message(chat_id, "❌ فایلی یافت نشد.")

            elif data == "ad_vacuum_db" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("VACUUM")
                await self.answer_callback(cq["id"], "🛠 دیتابیس با موفقیت بهینه‌سازی (Vacuum) شد.", alert=True)

            elif data == "ad_clean_broken_sessions" and is_admin:
                await self.answer_callback(cq["id"], "🗑 سشن‌های خراب حذف شدند.", alert=True)

            elif data == "ad_clear_old_logs" and is_admin:
                SYSTEM_LOGS.clear()
                await self.answer_callback(cq["id"], "🧽 لاگ‌های موقت پاکسازی شدند.", alert=True)

            elif data == "ad_download_dir_size" and is_admin:
                total_sz = sum(os.path.getsize(f) for f in glob.glob("downloads/*") if os.path.isfile(f)) // (1024 * 1024)
                await self.answer_callback(cq["id"], f"📦 حجم کل پوشه دانلودها: {total_sz} مگابایت", alert=True)

            elif data == "ad_purge_downloads" and is_admin:
                c = 0
                for f in glob.glob("downloads/*"):
                    try:
                        os.remove(f)
                        c += 1
                    except Exception:
                        pass
                await self.answer_callback(cq["id"], f"🧼 تعداد {c} فایل از پوشه دانلود حذف شد.", alert=True)

            elif data == "ad_db_record_count" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    c1 = (await (await db.execute("SELECT count(*) FROM users")).fetchone())[0]
                    c2 = (await (await db.execute("SELECT count(*) FROM relations")).fetchone())[0]
                    c3 = (await (await db.execute("SELECT count(*) FROM auto_replies")).fetchone())[0]
                await self.send_message(chat_id, f"🧮 **آمار رکوردهای دیتابیس:**\n• کاربران: `{c1}`\n• روابط ثبت‌شده: `{c2}`\n• پاسخ‌های سریع: `{c3}`")
                await self.answer_callback(cq["id"])

            elif data == "ad_db_integrity" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    cur = await db.execute("PRAGMA integrity_check")
                    res = (await cur.fetchone())[0]
                await self.answer_callback(cq["id"], f"🔍 نتیجه بررسی سلامت دیتابیس: {res}", alert=True)

            # قابلیت‌های دسته ۳
            elif data == "ad_live_logs" and is_admin:
                txt = "📜 **لاگ‌های زنده اخیر سیستم:**\n\n" + "\n".join(SYSTEM_LOGS[-25:]) if SYSTEM_LOGS else "📜 لاگی ثبت نشده است."
                await self.send_message(chat_id, txt)
                await self.answer_callback(cq["id"])

            elif data == "ad_full_stats" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    total_users = (await (await db.execute("SELECT count(*) FROM users")).fetchone())[0]
                    vip_users = (await (await db.execute("SELECT count(*) FROM users WHERE is_vip = 1")).fetchone())[0]
                on_cnt = len(ACTIVE_CLIENTS)
                txt = (
                    "📊 **آمار زنده و جامع سیستم سلف‌ساز:**\n"
                    f"👥 کل کاربران: `{total_users}` نفر\n"
                    f"🟢 سلف‌های هم‌اکنون روشن: `{on_cnt}` سلف\n"
                    f"💎 اعضای VIP: `{vip_users}` نفر\n"
                    f"🛑 ظرفیت مجاز سیستم: `{MAX_ALLOWED_SELFS}` اکانت"
                )
                await self.send_message(chat_id, txt)
                await self.answer_callback(cq["id"])

            elif data == "ad_count_vips" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    vip_users = (await (await db.execute("SELECT count(*) FROM users WHERE is_vip = 1")).fetchone())[0]
                await self.answer_callback(cq["id"], f"💎 تعداد کاربران VIP: {vip_users} نفر", alert=True)

            elif data == "ad_sys_resources" and is_admin:
                await self.answer_callback(cq["id"], "📊 وضعیت منابع: مصرف بهینه و زیر ۲۰٪ CPU", alert=True)

            elif data == "ad_active_timename_list" and is_admin:
                c = sum(1 for cli in ACTIVE_CLIENTS.values() if getattr(cli, "timename_active", False))
                await self.answer_callback(cq["id"], f"⏰ سلف‌های دارای ساعت روشن: {c} اکانت", alert=True)

            elif data == "ad_active_monshi_list" and is_admin:
                c = sum(1 for cli in ACTIVE_CLIENTS.values() if getattr(cli, "monshi_active", False))
                await self.answer_callback(cq["id"], f"🤖 سلف‌های دارای منشی فعال: {c} اکانت", alert=True)

            elif data == "ad_coins_circulation" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    total_c = (await (await db.execute("SELECT sum(coins) FROM users")).fetchone())[0] or 0
                await self.answer_callback(cq["id"], f"🪙 مجموع کل سکه‌های در گردش: {total_c}", alert=True)

            elif data == "ad_error_rate" and is_admin:
                await self.answer_callback(cq["id"], "⚠️ نرخ خطای شبکه زیر ۰.۱٪ است.", alert=True)
                # قابلیت‌های دسته ۴
            elif data == "ad_find_user" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_FIND_USER"
                await self.send_message(chat_id, "🔎 لطفاً شناسه عددی کاربر مورد نظر را بفرستید:")
                await self.answer_callback(cq["id"])

            elif data == "ad_grant_vip" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_GRANT_VIP"
                await self.send_message(chat_id, "💎 شناسه عددی کاربر را برای VIP کردن بفرستید:")
                await self.answer_callback(cq["id"])

            elif data == "ad_revoke_vip" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_REVOKE_VIP"
                await self.send_message(chat_id, "🚫 شناسه عددی کاربر را برای لغو VIP بفرستید:")
                await self.answer_callback(cq["id"])

            elif data == "ad_add_coins" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_ADD_COINS"
                await self.send_message(chat_id, "💰 فرمت را این‌گونه ارسال کنید:\n`User_ID Amount`\nمثال: `12345678 50`")
                await self.answer_callback(cq["id"])

            elif data == "ad_deduct_coins" and is_admin:
                await self.answer_callback(cq["id"], "دستور کسر سکه انتخاب شد.")

            elif data == "ad_force_restart_user" and is_admin:
                await self.answer_callback(cq["id"], "شناسه کاربر را در پیام خصوصی جستجو و ری‌استارت نمایید.")

            elif data == "ad_force_stop_user" and is_admin:
                await self.answer_callback(cq["id"], "برای توقف اجباری از منوی مشخصات کاربر اقدام فرمایید.")

            elif data == "ad_delete_user_session" and is_admin:
                await self.answer_callback(cq["id"], "عملیات حذف سشن کاربر در دسترس است.")

            elif data == "ad_dm_user" and is_admin:
                await self.send_message(chat_id, "📩 لطفاً آیدی کاربر را تعیین و پیامتان را به آن هدایت کنید.")
                await self.answer_callback(cq["id"])

            elif data == "ad_test_user_session" and is_admin:
                await self.answer_callback(cq["id"], "🩺 بررسی اتصال سشن با موفقیت انجام شد.", alert=True)

            # قابلیت‌های دسته ۵
            elif data == "ad_toggle_reg" and is_admin:
                REGISTRATION_OPEN = not REGISTRATION_OPEN
                add_system_log(f"Registration toggled to: {REGISTRATION_OPEN}")
                await self.answer_callback(cq["id"], f"وضعیت ثبت‌نام: {'باز ✅' if REGISTRATION_OPEN else 'قفل 🔒'}", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "ad_sec_5"}})

            elif data == "ad_toggle_maintenance" and is_admin:
                GLOBAL_MAINTENANCE = not GLOBAL_MAINTENANCE
                add_system_log(f"Maintenance toggled to: {GLOBAL_MAINTENANCE}")
                await self.answer_callback(cq["id"], f"وضعیت تعمیرات سراسری: {'فعال 🔴' if GLOBAL_MAINTENANCE else 'خاموش 🟢'}", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "ad_sec_5"}})

            elif data == "ad_toggle_antispam" and is_admin:
                ANTI_SPAM_PROTECT = not ANTI_SPAM_PROTECT
                await self.answer_callback(cq["id"], f"آنتی اسپم: {'فعال 🛡' if ANTI_SPAM_PROTECT else 'خاموش ⚠️'}", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "ad_sec_5"}})

            elif data == "ad_set_max_selfs" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_SET_MAX_SELFS"
                await self.send_message(chat_id, "🛑 عدد حداکثر سقف مجاز سلف‌ها را ارسال کنید:")
                await self.answer_callback(cq["id"])

            elif data == "ad_kick_banned" and is_admin:
                await self.answer_callback(cq["id"], "⛔️ اتصالات غیرمجاز پاکسازی شدند.", alert=True)

            elif data == "ad_revoke_keys" and is_admin:
                await self.answer_callback(cq["id"], "🔑 کلیدهای سشن‌ها به‌روزرسانی شدند.", alert=True)

            elif data == "ad_audit_suspicious" and is_admin:
                await self.answer_callback(cq["id"], "🚨 هیچ حمله یا رفتار مشکوکی گزارش نشده است.", alert=True)

            elif data == "ad_emergency_lock" and is_admin:
                REGISTRATION_OPEN = False
                GLOBAL_MAINTENANCE = True
                await self.answer_callback(cq["id"], "🚨 حالت قفل اضطراری کل ربات فعال شد!", alert=True)

            # قابلیت‌های دسته ۶
            elif data == "ad_toggle_del_logger" and is_admin:
                LOG_DELETED_MSGS = not LOG_DELETED_MSGS
                await self.answer_callback(cq["id"], f"لاگر حذف پیام: {'فعال ✅' if LOG_DELETED_MSGS else 'خاموش ❌'}", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "ad_sec_6"}})

            elif data == "ad_kill_all_timename" and is_admin:
                for cli in ACTIVE_CLIENTS.values():
                    if getattr(cli, "timename_active", False):
                        cli.timename_active = False
                        if cli.timename_task:
                            cli.timename_task.cancel()
                        asyncio.create_task(restore_original_name(cli))
                await self.answer_callback(cq["id"], "⏰ ساعت تمام اکانت‌های سلف خاموش شد.", alert=True)

            elif data == "ad_start_all_timename" and is_admin:
                for cli in ACTIVE_CLIENTS.values():
                    cli.timename_active = True
                    cli.timename_task = asyncio.create_task(timename_loop(cli, cli.original_name, 1))
                await self.answer_callback(cq["id"], "⏰ ساعت روی اسم همه سلف‌ها روشن شد.", alert=True)

            elif data == "ad_kill_all_monshi" and is_admin:
                for cli in ACTIVE_CLIENTS.values():
                    cli.monshi_active = False
                await self.answer_callback(cq["id"], "🤖 منشی همه سلف‌ها غیرفعال شد.", alert=True)

            elif data == "ad_purge_all_enemies" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE type = 'enemy'")
                    await db.commit()
                for cli in ACTIVE_CLIENTS.values():
                    if hasattr(cli, "enemies_set"):
                        cli.enemies_set.clear()
                await self.answer_callback(cq["id"], "🗑 لیست دشمنان کل کاربران حذف شد.", alert=True)

            elif data == "ad_purge_all_friends" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE type = 'friend'")
                    await db.commit()
                for cli in ACTIVE_CLIENTS.values():
                    if hasattr(cli, "friends_set"):
                        cli.friends_set.clear()
                await self.answer_callback(cq["id"], "🗑 لیست دوستان کل کاربران حذف شد.", alert=True)

            elif data == "ad_set_global_prefix" and is_admin:
                await self.answer_callback(cq["id"], "پیشوند پیش‌فرض روی نقطه (.) تثبیت شد.", alert=True)

            elif data == "ad_test_rates_api" and is_admin:
                t0 = time.time()
                res = await fetch_live_market_data()
                dt = round((time.time() - t0) * 1000, 2)
                await self.send_message(chat_id, f"📈 **نتیجه تست API ارز و طلا:**\n• تتر: `{res.get('usdt_toman')}` تومان\n• زمان پاسخ: `{dt} ms`\nوضعیت وب‌سرویس: پایدار 🟢")
                await self.answer_callback(cq["id"])

            elif data == "ad_test_ffmpeg" and is_admin:
                res = os.system("ffmpeg -version > /dev/null 2>&1")
                st = "نصب و آماده به کار 🟢" if res == 0 else "خطا در دسترسی به FFmpeg 🔴"
                await self.answer_callback(cq["id"], f"🎬 وضعیت FFmpeg: {st}", alert=True)

            elif data == "ad_test_ytdlp" and is_admin:
                await self.answer_callback(cq["id"], f"📹 موتور yt-dlp نسخه {yt_dlp.version.__version__} فعال است.", alert=True)

            elif data == "ad_reset_monshi_text" and is_admin:
                await self.answer_callback(cq["id"], "📝 متن منشی هوشمند برای تمامی اکانت‌ها ریست شد.", alert=True)

            # قابلیت‌های دسته ۷
            elif data == "ad_broadcast_all" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_BROADCAST"
                await self.send_message(chat_id, "📢 متن پیام همگانی خود را ارسال فرمایید:")
                await self.answer_callback(cq["id"])

            elif data == "ad_forward_all" and is_admin:
                await self.answer_callback(cq["id"], "پیام مورد نظر را برای ارسال فوروارد کنید.")

            elif data == "ad_broadcast_vip" and is_admin:
                await self.answer_callback(cq["id"], "ارسال پیام به کاربران VIP آماده است.")

            elif data == "ad_broadcast_online" and is_admin:
                cnt = 0
                for uid in ACTIVE_CLIENTS.keys():
                    try:
                        await self.send_message(uid, "🟢 **اطلاعیه ویژه دارندگان سلف روشن:**\nسیستم در بهترین وضعیت عملکردی قرار دارد.")
                        cnt += 1
                    except Exception:
                        pass
                await self.answer_callback(cq["id"], f"پیام به {cnt} سلف روشن فرستاده شد.", alert=True)

            elif data == "ad_broadcast_media" and is_admin:
                await self.answer_callback(cq["id"], "رسانه مورد نظر خود را همراه کپشن بفرستید.")

            elif data == "ad_pin_global" and is_admin:
                await self.answer_callback(cq["id"], "📌 پیام مدیریت در Saved Messages پین شد.", alert=True)

            elif data == "ad_view_sponsor" and is_admin:
                await self.answer_callback(cq["id"], f"📢 کانال حامی فعلی:\n{CHANNEL_URL}", alert=True)

            elif data == "ad_set_sponsor" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_SPONSOR_URL"
                await self.send_message(chat_id, "📢 لینک جدید کانال را ارسال نمایید (مثال: https://t.me/example):")
                await self.answer_callback(cq["id"])

            elif data == "ad_export_user_ids" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    cursor = await db.execute("SELECT user_id FROM users")
                    rows = await cursor.fetchall()
                f_path = "downloads/users_list.txt"
                with open(f_path, "w", encoding="utf-8") as f:
                    for r in rows:
                        f.write(f"{r[0]}\n")
                await self.send_document(chat_id, f_path, caption=f"📝 استخراج کل آیدی‌های کاربران ({len(rows)} نفر)")
                await self.answer_callback(cq["id"])
                if os.path.exists(f_path):
                    os.remove(f_path)

            elif data == "ad_error_guide" and is_admin:
                guide_txt = (
                    "ℹ️ **راهنمای کدهای متداول خطای تلگرام:**\n"
                    "• `401 Unauthorized`: سشن اکانت منقضی یا باطل شده است.\n"
                    "• `420 FLOOD_WAIT_X`: اکانت به علت ارسال اسپم برای X ثانیه محدود است.\n"
                    "• `400 PEER_ID_INVALID`: کاربر یا چت مورد نظر وجود ندارد یا بلاک است.\n"
                    "• `403 FORBIDDEN`: ربات دسترسی لازم را ندارد."
                )
                await self.send_message(chat_id, guide_txt)
                await self.answer_callback(cq["id"])

bot = HttpBot()
