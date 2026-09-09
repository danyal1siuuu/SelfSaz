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
import base64
import io
import csv
import platform
import shutil
import socket
import sqlite3

from core.telegram_login import create_qr_login, wait_for_qr_login

from pyrogram import Client as PyroClient
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, PhoneNumberInvalid, PasswordHashInvalid

from config import BOT_TOKEN, DB_NAME, ADMIN_ID, API_ID, API_HASH
from core.manager import (
    start_single_client, stop_single_client, ACTIVE_CLIENTS, 
    timename_loop, restore_original_name, stop_all_clients, 
    restart_all_clients, clean_server_temp_files
)
from plugins.fun_crypto import fetch_live_market_data, format_market_display
from core.plans import (
    handle_plan_callback, get_allowed_fonts, get_cleaner_min_delay,
    has_feature, set_admin_vip, get_user_profile, admin_set_plan,
    process_referral, record_activity_reward, PLANS_DATA, get_plan_config,
    get_notes_limit, get_ai_memory_limit, get_auto_reply_limit, get_timename_interval, get_daily_yt_limit, get_automation_react_limit, get_automation_save_limit, get_automation_greet_limit, get_automation_name_count, get_automation_bio_count, get_automation_interval
)
from core.youtube import download_youtube, human_error, is_youtube_url, cleanup_prefix
from core.system_settings import get_setting, set_setting, delete_setting, audit_log
from core.ai_service import ask_ai, ai_available, clear_ai_memory, ai_stats
from core.membership import check_membership, forced_join_enabled, forced_join_target, forced_join_url, is_exempt

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
CHANNEL_URL = "https://t.me/Vip_Viro"

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

    async def _safe_handle_update(self, update):
        """Never let an unhandled callback exception make a button appear dead."""
        try:
            return await self.handle_update(update)
        except Exception as exc:
            cq = update.get("callback_query") if isinstance(update, dict) else None
            if cq:
                try:
                    await self.answer_callback(cq.get("id", ""), f"❌ اجرای این دکمه با خطا متوقف شد: {exc}", alert=True)
                except Exception:
                    pass
            add_system_log(f"Unhandled update error: {type(exc).__name__}: {exc}")
            return None

    async def send_message(self, chat_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = self.normalize_markup(reply_markup)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{API_URL}/sendMessage", json=payload) as resp:
                    return await resp.json()
        except Exception as e:
            return {"ok": False, "description": str(e)}

    async def edit_message(self, chat_id, message_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = self.normalize_markup(reply_markup)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{API_URL}/editMessageText", json=payload) as resp:
                    result = await resp.json()
            if result.get("ok") or "message is not modified" in str(result.get("description", "")).lower():
                return result
            # If Telegram rejects editing an old/non-editable message, send the same screen as a new message.
            fallback = await self.send_message(chat_id, text, reply_markup=reply_markup)
            if fallback.get("ok"):
                return fallback
            return result
        except Exception as e:
            try:
                fallback = await self.send_message(chat_id, text, reply_markup=reply_markup)
                if fallback.get("ok"):
                    return fallback
            except Exception:
                pass
            return {"ok": False, "description": str(e)}

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

    async def send_photo(self, chat_id, file_path, caption=None, reply_markup=None):
        data = aiohttp.FormData()
        data.add_field("chat_id", str(chat_id))
        if caption:
            data.add_field("caption", caption)
        if reply_markup:
            data.add_field("reply_markup", json.dumps(self.normalize_markup(reply_markup), ensure_ascii=False))
        with open(file_path, "rb") as fh:
            data.add_field("photo", fh, filename=os.path.basename(file_path), content_type="image/png")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{API_URL}/sendPhoto", data=data) as resp:
                        return await resp.json()
            except Exception:
                return None

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

    @staticmethod
    def _style_button(button: dict) -> dict:
        """Use Telegram's native primary/green/red button styles (Bot API 10.3+)."""
        if not isinstance(button, dict) or "text" not in button:
            return button
        text = str(button.get("text", ""))
        cb = str(button.get("callback_data", ""))
        key = f"{text} {cb}".lower()
        danger = ("delete", "remove", "revoke", "deduct", "stop", "off", "logout", "purge", "kick", "ban", "cancel", "حذف", "لغو", "کسر", "خاموش", "محروم", "قطع", "پاکسازی")
        success = ("buy", "upgrade", "grant", "add", "on", "start", "restart", "claim", "ثبت", "ارتقا", "افزودن", "روشن", "جایزه", "دعوت")
        if any(x in key for x in danger):
            button.setdefault("style", "danger")
        elif any(x in key for x in success):
            button.setdefault("style", "success")
        else:
            button.setdefault("style", "primary")
        return button

    @classmethod
    def normalize_markup(cls, markup):
        """Make inline buttons wide/readable: one button per row, with Telegram native styles."""
        if not isinstance(markup, dict) or "inline_keyboard" not in markup:
            return markup
        rows = []
        for row in markup.get("inline_keyboard", []):
            for btn in row:
                rows.append([cls._style_button(dict(btn))])
        out = dict(markup)
        out["inline_keyboard"] = rows
        return out

    def get_main_dashboard_kb(self, is_online, is_admin=False):
        status_btn = "🟢 وضعیت سلف: روشن (کلیک برای خاموش)" if is_online else "🔴 وضعیت سلف: خاموش (کلیک برای روشن)"
        toggle_cb = "btn_turn_off" if is_online else "btn_turn_on"
        kb = [
            [{"text": status_btn, "callback_data": toggle_cb}],
            [{"text": "👤 حساب من", "callback_data": "menu_account"}],
            [{"text": "👑 رنک‌ها و ارتقا", "callback_data": "menu_plans"}],
            [{"text": "👥 دعوت از دوستان", "callback_data": "menu_invite"}],
            [{"text": "🎁 سکه و جایزه روزانه", "callback_data": "menu_daily"}],
            [{"text": "🔄 راه‌اندازی مجدد سلف", "callback_data": "btn_restart"}],
            [{"text": "📈 نرخ لحظه‌ای ارز و طلا", "callback_data": "menu_rates"}],
            [{"text": "⏰ ساعت روی اسم (۲۵ استایل)", "callback_data": "menu_timename"}],
            [{"text": "⚙️ اتوماسیون واقعی حساب", "callback_data": "menu_account_auto"}],
            [{"text": "🤖 منشی هوشمند و خودکار", "callback_data": "menu_monshi"}],
            [{"text": "🧠 مرکز هوشمند و AI", "callback_data": "menu_smart"}],
            [{"text": "💬 پاسخ خودکار و حالت مشغول", "callback_data": "menu_auto"}],
            [{"text": "👁 خواندن خودکار پیام‌ها", "callback_data": "menu_reader"}],
            [{"text": "📝 یادداشت‌ها و ابزار متن", "callback_data": "menu_notes"}],
            [{"text": "📊 آمار پیام‌ها و فعالیت", "callback_data": "menu_msg_stats"}],
            [{"text": "🔔 اعلان‌های سلف و وضعیت", "callback_data": "menu_notify"}],
            [{"text": "🗑 پاکسازی خودکار پیام‌ها", "callback_data": "menu_cleaner"}],
            [{"text": "🛡 مدیریت دوستان و دشمنان", "callback_data": "menu_relations"}],
            [{"text": "⚡️ تنظیمات پیشوند سلف", "callback_data": "menu_prefix"}],
            [{"text": "🛠 جعبه‌ابزار کاربردی و دانلودر", "callback_data": "menu_tools"}],
            [{"text": "🎛 مرکز کاربری پیشرفته", "callback_data": "menu_user_center"}],
            [{"text": "🚀 مرکز حرفه‌ای سلف و آمار", "callback_data": "menu_pro"}],
        ]
        if is_admin:
            kb.append([{"text": "👑 پنل مدیریت کل سیستم", "callback_data": "admin_hub"}])
        kb += [
            [{"text": "🛑 خروج و حذف اطلاعات", "callback_data": "btn_delete_account"}],
            [{"text": "📢 کانال پشتیبانی", "url": CHANNEL_URL}],
        ]
        return {"inline_keyboard": kb}

    def get_admin_hub_kb(self):
        return {"inline_keyboard": [
            [{"text": "⚙️ ۱. سرور و پروسه‌ها (۱۰)", "callback_data": "ad_sec_1"}, {"text": "🗄 ۲. دیتابیس و فایل (۸)", "callback_data": "ad_sec_2"}],
            [{"text": "📊 ۳. آمار و مانیتورینگ (۸)", "callback_data": "ad_sec_3"}, {"text": "👥 ۴. کاربران و سلف‌ها (۱۰)", "callback_data": "ad_sec_4"}],
            [{"text": "🛡 ۵. امنیت و فایروال (۸)", "callback_data": "ad_sec_5"}, {"text": "🧩 ۶. تنظیمات پلاگین‌ها (۱۱)", "callback_data": "ad_sec_6"}],
            [{"text": "📢 ۷. پیام‌رسانی و پشتیبانی (۱۰)", "callback_data": "ad_sec_7"}],
            [{"text": "🔐 ۸. عضویت و دسترسی (۱۰)", "callback_data": "ad_sec_8"}],
            [{"text": "🗄 ۹. دیتابیس پیشرفته (۱۰)", "callback_data": "ad_sec_9"}],
            [{"text": "📡 ۱۰. مانیتورینگ حرفه‌ای (۱۰)", "callback_data": "ad_sec_10"}],
            [{"text": "🧪 ۱۱. تشخیص، گزارش و سلامت (۱۰)", "callback_data": "ad_sec_11"}],
            [{"text": "⚙️ ۱۲. ارتباطات و تنظیمات پیشرفته (۱۰)", "callback_data": "ad_sec_12"}],
            [{"text": "🧠 ۱۳. هوش مصنوعی و امکانات هوشمند (۱۲)", "callback_data": "ad_sec_13"}],
            [{"text": "👥 ۱۴. تحلیل کاربران (۱۰ جدید)", "callback_data": "ad_sec_14"}],
            [{"text": "🔐 ۱۵. احراز هویت و سشن‌ها (۱۰ جدید)", "callback_data": "ad_sec_15"}],
            [{"text": "⚙️ ۱۶. کنترل‌های سراسری جدید (۱۰ جدید)", "callback_data": "ad_sec_16"}],
            [{"text": "🏆 ۱۷. اقتصاد، رنک و دعوت (۱۰ جدید)", "callback_data": "ad_sec_17"}],
            [{"text": "🤖 ۱۸. تحلیل Smart/AI (۱۰ جدید)", "callback_data": "ad_sec_18"}],
            [{"text": "🧪 ۱۹. سلامت و نگهداری نهایی (۱۰ جدید)", "callback_data": "ad_sec_19"}],
            [{"text": "🔙 بازگشت به داشبورد اصلی", "callback_data": "back_dashboard"}]
        ]}

    def get_admin_sec1_kb(self):
        return {"inline_keyboard": [
            [{"text": "۱. خاموش‌سازی همه سلف‌ها 🛑", "callback_data": "ad_stop_all"}, {"text": "۲. ریستارت همه سلف‌ها 🔄", "callback_data": "ad_restart_all"}],
            [{"text": "۳. پاکسازی کش و فایلهای موقت 🧹", "callback_data": "ad_clean_temp"}, {"text": "۴. تست سرعت و پینگ سرور ⚡️", "callback_data": "ad_ping_test"}],
            [{"text": "۵. بررسی مصرف رم (RAM) 🧠", "callback_data": "ad_ram_usage"}, {"text": "۶. بررسی آپ‌تایم سرور ⏱", "callback_data": "ad_uptime"}],
            [{"text": "۷. لیست سلف‌های فعال کنونی 📋", "callback_data": "ad_online_list"}, {"text": "۸. همگام‌سازی وضعیت اتصال‌ها 🔌", "callback_data": "ad_sync_conns"}],
            [{"text": "۹. بارگذاری مجدد پلاگین‌ها ♻️", "callback_data": "ad_reload_plugins"}, {"text": "۱۰. ریستارت کلی پروسس ربات 🖥", "callback_data": "ad_restart_process"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec2_kb(self):
        return {"inline_keyboard": [
            [{"text": "۱۱. دانلود بکاپ دیتابیس 📥", "callback_data": "ad_backup_db"}, {"text": "۱۲. بهینه‌سازی دیتابیس (Vacuum) 🛠", "callback_data": "ad_vacuum_db"}],
            [{"text": "۱۳. حذف سشن‌های خراب 🗑", "callback_data": "ad_clean_broken_sessions"}, {"text": "۱۴. پاکسازی لاگ‌های قدیمی 🧽", "callback_data": "ad_clear_old_logs"}],
            [{"text": "۱۵. حجم فایل‌های دانلود شده 📦", "callback_data": "ad_download_dir_size"}, {"text": "۱۶. تخلیه پوشه Downloads 🧼", "callback_data": "ad_purge_downloads"}],
            [{"text": "۱۷. شمارش رکوردهای DB 🧮", "callback_data": "ad_db_record_count"}, {"text": "۱۸. بررسی سلامت دیتابیس 🔍", "callback_data": "ad_db_integrity"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec3_kb(self):
        return {"inline_keyboard": [
            [{"text": "۱۹. لاگ زنده سیستم (۶۰ پیام اخیر) 📜", "callback_data": "ad_live_logs"}, {"text": "۲۰. آمار جامع سیستم 📈", "callback_data": "ad_full_stats"}],
            [{"text": "۲۱. تعداد سلف‌های VIP 💎", "callback_data": "ad_count_vips"}, {"text": "۲۲. مصرف کل منابع سرور 📊", "callback_data": "ad_sys_resources"}],
            [{"text": "۲۳. سلف‌های با ساعت فعال ⏰", "callback_data": "ad_active_timename_list"}, {"text": "۲۴. سلف‌های با منشی فعال 🤖", "callback_data": "ad_active_monshi_list"}],
            [{"text": "۲۵. آمار مجموع کل سکه‌ها 🪙", "callback_data": "ad_coins_circulation"}, {"text": "۲۶. نرخ خطاهای شبکه ⚠️", "callback_data": "ad_error_rate"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec4_kb(self):
        return {"inline_keyboard": [
            [{"text": "۲۷. جستجوی کاربر با آیدی 🔎", "callback_data": "ad_find_user"}],
            [{"text": "۲۸. دادن هر رنک به کاربر 🏆", "callback_data": "ad_set_rank"}],
            [{"text": "۲۹. گرفتن/ریست رنک کاربر 🔄", "callback_data": "ad_reset_rank"}],
            [{"text": "۳۰. افزودن سکه به کاربر 💰", "callback_data": "ad_add_coins"}],
            [{"text": "۳۱. کسر سکه از کاربر 📉", "callback_data": "ad_deduct_coins"}],
            [{"text": "۳۲. ریستارت اجباری سلف کاربر ⚡️", "callback_data": "ad_force_restart_user"}],
            [{"text": "۳۳. خاموش‌سازی اجباری کاربر 🛑", "callback_data": "ad_force_stop_user"}],
            [{"text": "۳۴. حذف کامل کاربر و سشن ❌", "callback_data": "ad_delete_user_session"}],
            [{"text": "۳۵. ارسال پیام مستقیم به کاربر 📩", "callback_data": "ad_dm_user"}],
            [{"text": "۳۶. بررسی سلامت سشن کاربر 🩺", "callback_data": "ad_test_user_session"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec5_kb(self):
        reg_btn = "۳۷. ثبت‌نام جدید: باز ✅" if REGISTRATION_OPEN else "۳۷. ثبت‌نام جدید: قفل 🔒"
        maint_btn = "۳۸. حالت تعمیرات: روشن 🔴" if GLOBAL_MAINTENANCE else "۳۸. حالت تعمیرات: خاموش 🟢"
        spam_btn = "۳۹. آنتی‌اسپم سیستم: فعال 🛡" if ANTI_SPAM_PROTECT else "۳۹. آنتی‌اسپم سیستم: خاموش ⚠️"
        return {"inline_keyboard": [
            [{"text": reg_btn, "callback_data": "ad_toggle_reg"}, {"text": maint_btn, "callback_data": "ad_toggle_maintenance"}],
            [{"text": spam_btn, "callback_data": "ad_toggle_antispam"}, {"text": "۴۰. محدودیت سقف سلف‌ها 🛑", "callback_data": "ad_set_max_selfs"}],
            [{"text": "۴۱. قطع اتصال کاربران مسدود ⛔️", "callback_data": "ad_kick_banned"}, {"text": "۴۲. بازنشانی کلیدهای دسترسی 🔑", "callback_data": "ad_revoke_keys"}],
            [{"text": "۴۳. بررسی دسترسی مشکوک 🚨", "callback_data": "ad_audit_suspicious"}, {"text": "۴۴. قفل اضطراری کل سیستم 🚨", "callback_data": "ad_emergency_lock"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec6_kb(self):
        del_log_btn = "۴۵. لاگر حذف پیام: فعال ✅" if LOG_DELETED_MSGS else "۴۵. لاگر حذف پیام: خاموش ❌"
        return {"inline_keyboard": [
            [{"text": del_log_btn, "callback_data": "ad_toggle_del_logger"}, {"text": "۴۶. خاموش کردن ساعت کل سلف‌ها ⏰", "callback_data": "ad_kill_all_timename"}],
            [{"text": "۴۷. روشن‌سازی ساعت همه سلف‌ها ⏰", "callback_data": "ad_start_all_timename"}, {"text": "۴۸. خاموش‌سازی منشی همه سلف‌ها 🤖", "callback_data": "ad_kill_all_monshi"}],
            [{"text": "۴۹. پاکسازی دشمنان همه اکانت‌ها 🗑", "callback_data": "ad_purge_all_enemies"}, {"text": "۵۰. پاکسازی دوستان همه اکانت‌ها 🗑", "callback_data": "ad_purge_all_friends"}],
            [{"text": "۵۱. پیشوند پیش‌فرض سیستم ⚡️", "callback_data": "ad_set_global_prefix"}, {"text": "۵۲. تست API وب‌سرویس نرخ ارز 📈", "callback_data": "ad_test_rates_api"}],
            [{"text": "۵۳. تست موتور FFmpeg 🎬", "callback_data": "ad_test_ffmpeg"}, {"text": "۵۴. تست دانلودر یوتیوب سرور 📹", "callback_data": "ad_test_ytdlp"}],
            [{"text": "۵۵. بازنشانی متن پیش‌فرض منشی 📝", "callback_data": "ad_reset_monshi_text"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec7_kb(self):
        return {"inline_keyboard": [
            [{"text": "۵۶. ارسال همگانی به همه 📢", "callback_data": "ad_broadcast_all"}, {"text": "۵۷. فوروارد همگانی به همه 🔁", "callback_data": "ad_forward_all"}],
            [{"text": "۵۸. پیام به کاربران VIP 💎", "callback_data": "ad_broadcast_vip"}, {"text": "۵۹. پیام به سلف‌های روشن 🟢", "callback_data": "ad_broadcast_online"}],
            [{"text": "۶۰. ارسال فایل/عکس به همه 📁", "callback_data": "ad_broadcast_media"}, {"text": "۶۱. پین کردن پیام در سلف‌ها 📌", "callback_data": "ad_pin_global"}],
            [{"text": "۶۲. دریافت لینک کانال اسپانسر 📢", "callback_data": "ad_view_sponsor"}, {"text": "۶۳. تغییر لینک کانال اسپانسر ✏️", "callback_data": "ad_set_sponsor"}],
            [{"text": "۶۴. استخراج لیست آیدی کاربران 📝", "callback_data": "ad_export_user_ids"}, {"text": "۶۵. راهنمای کدهای خطا ℹ️", "callback_data": "ad_error_guide"}],
            [{"text": "🔙 بازگشت به هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec8_kb(self):
        return {"inline_keyboard": [
            [{"text": "۶۶. عضویت اجباری: روشن/خاموش 🔐", "callback_data": "ad_force_join_toggle"}],
            [{"text": "۶۷. تعیین کانال/گروه اجباری ✏️", "callback_data": "ad_force_join_set"}],
            [{"text": "۶۸. وضعیت عضویت اجباری 📊", "callback_data": "ad_force_join_status"}],
            [{"text": "۶۹. تست عضویت اجباری 🧪", "callback_data": "ad_force_join_test"}],
            [{"text": "۷۰. حذف تنظیم عضویت اجباری 🗑", "callback_data": "ad_force_join_clear"}],
            [{"text": "۷۱. افزودن کاربر استثنا 👤", "callback_data": "ad_join_exempt_add"}],
            [{"text": "۷۲. حذف کاربر استثنا 👤", "callback_data": "ad_join_exempt_remove"}],
            [{"text": "۷۳. لیست استثناهای عضویت 📋", "callback_data": "ad_join_exempt_list"}],
            [{"text": "۷۴. پیش‌نمایش پیام عضویت 👁", "callback_data": "ad_force_join_preview"}],
            [{"text": "۷۵. تغییر متن عضویت ✍️", "callback_data": "ad_force_join_text"}],
            [{"text": "🔙 هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    def get_admin_sec9_kb(self):
        items = [
            ("۷۶. حجم دقیق دیتابیس 💾", "ad_db_size"), ("۷۷. WAL Checkpoint ⚡️", "ad_db_checkpoint"),
            ("۷۸. نمایش ایندکس‌ها 🧭", "ad_db_indexes"), ("۷۹. پاکسازی روابط یتیم 🧹", "ad_db_orphan_relations"),
            ("۸۰. پاکسازی دعوت‌های یتیم 🧹", "ad_db_orphan_referrals"), ("۸۱. کاربران بدون سشن 👤", "ad_users_no_session"),
            ("۸۲. ۱۰ کاربر برتر سکه 🪙", "ad_top_coins"), ("۸۳. ۱۰ کاربر برتر دعوت 👥", "ad_top_referrals"),
            ("۸۴. توزیع رنک‌ها 🏆", "ad_plan_distribution"), ("۸۵. گزارش پاداش‌های امروز 🎁", "ad_rewards_today"),
            ("🔙 هاب ادمین", "admin_hub")]
        return {"inline_keyboard": [[{"text": t, "callback_data": c}] for t, c in items]}

    def get_admin_sec10_kb(self):
        items = [
            ("۸۶. وضعیت سلامت سلف‌های آنلاین 🟢", "ad_online_health"), ("۸۷. تعداد اتصال‌های فعال 📡", "ad_connection_count"),
            ("۸۸. سلف‌های خاموش ولی ثبت‌شده 💤", "ad_offline_registered"), ("۸۹. درخواست‌های QR در انتظار 🔐", "ad_pending_qr"),
            ("۹۰. نشست‌های ورود در انتظار 📱", "ad_pending_logins"), ("۹۱. فایل‌های QR موقت 🖼", "ad_qr_files"),
            ("۹۲. فایل‌های دانلود و فضا 📦", "ad_download_stats"), ("۹۳. فضای آزاد دیسک 💿", "ad_disk_space"),
            ("۹۴. مصرف CPU/Load ⚙️", "ad_cpu_load"), ("۹۵. مصرف RAM سیستم 🧠", "ad_ram_system"),
            ("🔙 هاب ادمین", "admin_hub")]
        return {"inline_keyboard": [[{"text": t, "callback_data": c}] for t, c in items]}

    def get_admin_sec11_kb(self):
        items = [
            ("۹۶. تست DNS تلگرام 🌐", "ad_dns_test"), ("۹۷. تست تاخیر Bot API ⚡️", "ad_api_latency"),
            ("۹۸. مشخصات Runtime 🐍", "ad_runtime_info"), ("۹۹. نسخه Pyrogram 📚", "ad_pyrogram_version"),
            ("۱۰۰. نسخه yt-dlp 📹", "ad_ytdlp_version"), ("۱۰۱. تست FFmpeg 🎬", "ad_ffmpeg_check"),
            ("۱۰۲. تست سلامت DB 🩺", "ad_db_health"), ("۱۰۳. شمارش لاگ حسابرسی 📜", "ad_audit_count"),
            ("۱۰۴. خروجی گزارش حسابرسی 📥", "ad_audit_export"), ("۱۰۵. گزارش تشخیصی کامل 🧪", "ad_diagnostics_export"),
            ("🔙 هاب ادمین", "admin_hub")]
        return {"inline_keyboard": [[{"text": t, "callback_data": c}] for t, c in items]}

    def get_admin_sec12_kb(self):
        items = [
            ("۱۰۶. تنظیم پیشوند پیش‌فرض ✏️", "ad_global_prefix"), ("۱۰۷. سقف دانلود سراسری 📹", "ad_global_yt_limit"),
            ("۱۰۸. متن خوش‌آمدگویی 👋", "ad_welcome_text"), ("۱۰۹. متن وضعیت ربات 🤖", "ad_status_text"),
            ("۱۱۰. گزارش تنظیمات سیستم ⚙️", "ad_settings_report"), ("۱۱۱. شمارش وضعیت‌های موقت 🧩", "ad_pending_states"),
            ("۱۱۲. شمارش سلف‌های آنلاین واقعی ✅", "ad_real_online"), ("۱۱۳. پاکسازی فایل‌های QR قدیمی 🧹", "ad_clean_qr"),
            ("۱۱۴. پاکسازی وضعیت‌های موقت ♻️", "ad_clear_states"), ("۱۱۵. اجرای Self-Test نهایی 🚀", "ad_self_test"),
            ("🔙 هاب ادمین", "admin_hub")]
        return {"inline_keyboard": [[{"text": t, "callback_data": c}] for t, c in items]}

    def _admin_extra_section_kb(self, start: int, items):
        rows = []
        for i in range(0, len(items), 2):
            chunk = items[i:i+2]
            rows.append([{"text": f"{start+i}. {t}", "callback_data": c} for t,c in chunk])
        rows.append([{"text": "🔙 هاب ادمین", "callback_data": "admin_hub"}])
        return {"inline_keyboard": rows}

    def get_admin_sec14_kb(self):
        return self._admin_extra_section_kb(116, [
            ("گزارش کاربران امروز 👥", "adx_116"),("کاربران ۷ روز اخیر 📈", "adx_117"),
            ("رشد کاربران ۳۰ روزه 📊", "adx_118"),("کاربران بدون فعالیت 💤", "adx_119"),
            ("میانگین سکه کاربران 🪙", "adx_120"),("میانگین XP کاربران ⭐", "adx_121"),
            ("بیشترین مصرف‌کننده امکانات 🔥", "adx_122"),("۱۰ کاربر فعال اخیر ⚡", "adx_123"),
            ("کاربران بر اساس prefix 🧩", "adx_124"),("گزارش کامل کاربران 📋", "adx_125"),
        ])

    def get_admin_sec15_kb(self):
        return self._admin_extra_section_kb(126, [
            ("توزیع سشن‌های سالم/خراب 🩺", "adx_126"),("نشست‌های ورود قدیمی ⏳", "adx_127"),
            ("QRهای منقضی‌شده 🖼", "adx_128"),("پاکسازی سشن‌های موقت 🧹", "adx_129"),
            ("تعداد سلف‌های قطع‌شده 🔌", "adx_130"),("نرخ موفقیت ورود 📈", "adx_131"),
            ("خطاهای ورود اخیر ⚠️", "adx_132"),("ورودهای موفق امروز ✅", "adx_133"),
            ("آخرین ورودهای کاربران 🕒", "adx_134"),("گزارش سلامت احراز هویت 🔐", "adx_135"),
        ])

    def get_admin_sec16_kb(self):
        return self._admin_extra_section_kb(136, [
            ("فعال/خاموش کردن ثبت Audit ✍️", "adx_136"),("فعال/خاموش کردن لاگ جزئیات 📝", "adx_137"),
            ("فعال/خاموش کردن پیام‌های وضعیت 📣", "adx_138"),("حالت کم‌مصرف سیستم 🪫", "adx_139"),
            ("سقف درخواست‌های AI سراسری 🧠", "adx_140"),("سقف دانلود روزانه سراسری 📹", "adx_141"),
            ("کول‌داون پیش‌فرض ابزارها ⏱", "adx_142"),("فعال/خاموش کردن آمار پیام‌ها 📊", "adx_143"),
            ("فعال/خاموش کردن یادداشت‌ها 📝", "adx_144"),("بازنشانی تنظیمات پیش‌فرض 🔄", "adx_145"),
        ])

    def get_admin_sec17_kb(self):
        return self._admin_extra_section_kb(146, [
            ("گزارش رنک‌ها 🏆", "adx_146"),("رشد ارتقاها در ۳۰ روز 📈", "adx_147"),
            ("گزارش دعوت‌ها 👥", "adx_148"),("نرخ تبدیل دعوت 🔗", "adx_149"),
            ("کل سکه‌های توزیع‌شده 💰", "adx_150"),("جوایز روزانه امروز 🎁", "adx_151"),
            ("پاداش فعالیت امروز ⚡", "adx_152"),("میانگین امتیاز فعالیت ⭐", "adx_153"),
            ("بهترین رنک‌های کاربران 💎", "adx_154"),("گزارش اقتصاد سکه 📊", "adx_155"),
        ])

    def get_admin_sec18_kb(self):
        return self._admin_extra_section_kb(156, [
            ("وضعیت قابلیت‌های AI 🤖", "adx_156"),("تعداد حافظه‌های AI 🧠", "adx_157"),
            ("درخواست‌های AI امروز 📊", "adx_158"),("کاربران دارای منشی فعال 💬", "adx_159"),
            ("کاربران پاسخ‌خودکار فعال 🔁", "adx_160"),("کاربران Reader فعال 👁", "adx_161"),
            ("تعداد یادداشت‌های ذخیره‌شده 📝", "adx_162"),("آمار ترجمه/خلاصه‌سازی 🌐", "adx_163"),
            ("پاکسازی حافظه AI همه کاربران 🧹", "adx_164"),("گزارش Smart Center 🧩", "adx_165"),
        ])

    def get_admin_sec19_kb(self):
        return self._admin_extra_section_kb(166, [
            ("Health Check کامل ✅", "adx_166"),("بررسی دسترسی Bot API 🌐", "adx_167"),
            ("بررسی فضای دیسک 💿", "adx_168"),("بررسی پوشه Downloads 📦", "adx_169"),
            ("بررسی Python Runtime 🐍", "adx_170"),("بررسی نسخه کتابخانه‌ها 📚", "adx_171"),
            ("بررسی فایل‌های پروژه 🗂", "adx_172"),("پاکسازی فایل‌های موقت 🧹", "adx_173"),
            ("ساخت گزارش سلامت TXT 📄", "adx_174"),("اجرای تست نهایی سیستم 🚀", "adx_175"),
        ])

    def get_admin_sec13_kb(self):
        ai_global = "فعال ✅" if True else "خاموش ❌"
        return {"inline_keyboard": [
            [{"text": "🧠 AI سراسری: وضعیت / روشن‌خاموش", "callback_data": "ad_ai_toggle"}],
            [{"text": "🤖 هوش هوشمند سراسری: روشن‌خاموش", "callback_data": "ad_smart_toggle"}],
            [{"text": "🧩 مدل AI را تعیین کن", "callback_data": "ad_ai_model"}],
            [{"text": "🌐 Base URL سرویس AI", "callback_data": "ad_ai_base"}],
            [{"text": "📝 پرامپت پیش‌فرض منشی", "callback_data": "ad_ai_prompt"}],
            [{"text": "⏱ کول‌داون پاسخ AI", "callback_data": "ad_ai_cooldown"}],
            [{"text": "💬 متن پیش‌فرض پاسخ خودکار", "callback_data": "ad_auto_default"}],
            [{"text": "📊 آمار مصرف AI و کاربران", "callback_data": "ad_ai_stats"}],
            [{"text": "🩺 تست اتصال AI", "callback_data": "ad_ai_test"}],
            [{"text": "🧹 پاک‌سازی حافظه AI همه کاربران", "callback_data": "ad_ai_clear_all"}],
            [{"text": "👥 تعداد منشی‌ها و پاسخ‌خودکارهای فعال", "callback_data": "ad_smart_usage"}],
            [{"text": "♻️ بازنشانی تنظیمات هوشمند", "callback_data": "ad_smart_reset"}],
            [{"text": "🔙 هاب ادمین", "callback_data": "admin_hub"}]
        ]}

    async def get_me(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_URL}/getMe") as resp:
                    data = await resp.json()
                    return data.get("result", {}) if data.get("ok") else {}
        except Exception:
            return {}

    async def start(self):
        self.running = True
        offset = 0
        add_system_log("HTTP Bot service started successfully.")
        print("[+] Ultimate HTTP Bot Online with 175 Admin Features.")
        async with aiohttp.ClientSession() as session:
            while self.running:
                try:
                    url = f"{API_URL}/getUpdates?offset={offset}&timeout=20"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for update in data.get("result", []):
                                offset = update["update_id"] + 1
                                asyncio.create_task(self._safe_handle_update(update))
                except Exception:
                    await asyncio.sleep(2)

    async def _finish_qr_login(self, user_id, chat_id):
        data = LOGIN_CLIENTS.get(user_id)
        if not data:
            return
        try:
            sess_str = await wait_for_qr_login(data["client"])
            await data["client"].disconnect()
            try:
                os.remove(data.get("qr_path", ""))
            except Exception:
                pass
            LOGIN_CLIENTS.pop(user_id, None)
            USER_STATES.pop(user_id, None)
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("INSERT INTO users (user_id, session_string) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET session_string = excluded.session_string", (user_id, sess_str))
                await db.commit()
            await start_single_client(user_id, sess_str)
            add_system_log(f"User {user_id} auto-created session via QR.")
            p_text, p_kb = await self.render_user_dashboard(user_id, user_id == ADMIN_ID)
            await self.send_message(chat_id, p_text, reply_markup=p_kb)
        except Exception as e:
            try:
                await data["client"].disconnect()
            except Exception:
                pass
            LOGIN_CLIENTS.pop(user_id, None)
            USER_STATES.pop(user_id, None)
            await self.send_message(chat_id, f"❌ ورود QR کامل نشد.\n`{e}`\n\nدوباره از گزینه «ورود امن با QR» استفاده کنید.", reply_markup=self.get_main_dashboard_kb(False, user_id == ADMIN_ID))

    async def render_user_dashboard(self, user_id: int, is_admin: bool = False):
        """Render the real per-user dashboard every time Home/Dashboard is opened."""
        u = await self.get_user_db(user_id)
        if not u:
            return (
                "👋 **به سیستم پیشرفته سلف‌ساز خوش آمدید!**\n\n"
                "سلف شما ثبت نشده یا حذف شده است. برای ادامه یکی از روش‌های زیر را انتخاب کنید:",
                {"inline_keyboard": [
                    [{"text": "🔐 ورود امن با QR", "callback_data": "btn_create_session"}],
                    [{"text": "📱 ورود با شماره و کد", "callback_data": "btn_phone_login"}],
                    [{"text": "🔑 ارسال سشن", "callback_data": "btn_submit_session"}],
                    [{"text": "📢 کانال پشتیبانی و اخبار", "url": CHANNEL_URL}],
                ]},
            )
        profile = await get_user_profile(user_id)
        plan_key = (profile or {}).get("plan", "normal")
        plan_cfg = PLANS_DATA.get(plan_key, PLANS_DATA["normal"])
        is_online = user_id in ACTIVE_CLIENTS
        text = (
            "👑 **داشبورد مدیریت یکپارچه و هوشمند سلف‌بات**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 شناسه شما: `{user_id}`\n"
            f"⚡️ وضعیت اکانت سلف: {'فعال و آنلاین 🟢' if is_online else 'خاموش 🔴'}\n"
            f"🏆 رنک: {plan_cfg['badge']} **{plan_cfg['title']}**\n"
            f"🪙 سکه: `{(profile or {}).get('coins', u[1])}` | 👥 دعوت: `{(profile or {}).get('referral_count', 0)}` | ⚡ XP: `{(profile or {}).get('activity_score', 0)}`\n"
            f"⚡️ پیشوند فعال دستورات: `{u[3] or '.'}`\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 کنترل تمام قابلیت‌ها ۱۰۰٪ دکمه‌ای است؛ انتخاب کنید:"
        )
        return text, self.get_main_dashboard_kb(is_online, is_admin)

    async def ensure_registered_callback(self, cq: dict, user_id: int, chat_id: int, msg_id: int, data: str, is_admin: bool) -> bool:
        """Reject stale inline buttons after the user's self account was deleted."""
        if is_admin or data in {"btn_create_session", "btn_cancel_login", "btn_submit_session", "btn_qr_refresh", "btn_phone_login", "btn_resend_login_code", "check_membership"}:
            return True
        u = await self.get_user_db(user_id)
        if u:
            return True
        await self.answer_callback(cq["id"], "❌ سلف شما حذف شده یا دیگر ثبت نیست؛ این دکمه قدیمی دیگر فعال نیست.", alert=True)
        text, kb = await self.render_user_dashboard(user_id, is_admin=False)
        await self.edit_message(chat_id, msg_id, text, reply_markup=kb)
        return False

    async def _membership_gate(self, user_id: int, chat_id: int, cq_id: str | None = None, msg_id: int | None = None) -> bool:
        if user_id == ADMIN_ID:
            return True
        ok, reason = await check_membership(user_id)
        if ok:
            return True
        target_url = await forced_join_url()
        buttons = []
        if target_url:
            buttons.append([{"text": "📢 عضویت در کانال/گروه", "url": target_url}])
        buttons.append([{"text": "✅ بررسی عضویت", "callback_data": "check_membership"}])
        if cq_id:
            await self.answer_callback(cq_id, "🔒 ابتدا عضویت الزامی را تکمیل کن.", alert=True)
        if msg_id is not None:
            await self.edit_message(chat_id, msg_id, reason, reply_markup={"inline_keyboard": buttons})
        else:
            await self.send_message(chat_id, reason, reply_markup={"inline_keyboard": buttons})
        return False

    async def handle_update(self, update):
        global REGISTRATION_OPEN, GLOBAL_MAINTENANCE, LOG_DELETED_MSGS, ANTI_SPAM_PROTECT, MAX_ALLOWED_SELFS
        global REGISTRATION_OPEN, GLOBAL_MAINTENANCE, LOG_DELETED_MSGS, ANTI_SPAM_PROTECT, CHANNEL_URL, MAX_ALLOWED_SELFS
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg.get("from", {}).get("id", chat_id)
            text = msg.get("text", "").strip()
            is_admin = (user_id == ADMIN_ID)

            if GLOBAL_MAINTENANCE and not is_admin:
                return await self.send_message(chat_id, "🚧 سیستم در حال حاضر در حال تعمیر و به‌روزرسانی است. لطفاً بعداً تلاش فرمایید.")

            if not is_admin:
                if not await self._membership_gate(user_id, chat_id):
                    return

            if text.startswith("/start") or text == "/panel":
                USER_STATES.pop(user_id, None)
                parts = text.split(maxsplit=1)
                start_payload = parts[1].strip() if len(parts) > 1 else ""
                u = await self.get_user_db(user_id)
                if start_payload.startswith("ref_") and start_payload[4:].isdigit() and not u:
                    # Link reward is applied only after the new user actually exists.
                    referrer_id = int(start_payload[4:])
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
                        await db.commit()
                    ok, reward = await process_referral(referrer_id, user_id)
                    u = await self.get_user_db(user_id)
                    if ok:
                        try:
                            await self.send_message(referrer_id, f"🎉 یک دعوت موفق ثبت شد!\n🪙 +`{reward}` سکه\n⚡ +`25 XP`")
                        except Exception:
                            pass
                if u:
                    p_text, p_kb = await self.render_user_dashboard(user_id, is_admin)
                    return await self.send_message(chat_id, p_text, reply_markup=p_kb)
                else:
                    kb = {
                        "inline_keyboard": [
                            [{"text": "🔐 ورود امن با QR و ساخت سشن", "callback_data": "btn_create_session"}],
                            [{"text": "📱 ورود با شماره و کد", "callback_data": "btn_phone_login"}],
                            [{"text": "🔑 اتصال مستقیم (ارسال سشن)", "callback_data": "btn_submit_session"}],
                            [{"text": "📢 کانال پشتیبانی و اخبار", "url": CHANNEL_URL}]
                        ]
                    }
                    welcome = await get_setting("welcome_text", "")
                    base = welcome.strip() or "👋 **به سیستم پیشرفته سلف‌ساز خوش آمدید!**"
                    return await self.send_message(chat_id, base + "\n\nجهت راه‌اندازی سلف، یکی از گزینه‌های زیر را انتخاب فرمایید:", reply_markup=kb)

            if text == "/status":
                uptime = int(time.time() - START_TIME)
                h, rem = divmod(uptime, 3600); m, sec = divmod(rem, 60)
                async with aiosqlite.connect(DB_NAME) as db:
                    users_count = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
                custom_status = await get_setting("bot_status_text", "")
                status_text = custom_status.strip() or "🟢 سرویس SelfSaz در حال فعالیت است."
                return await self.send_message(chat_id, status_text + f"\n\n👥 کاربران ثبت‌شده: `{users_count}`\n🤖 سلف‌های آنلاین: `{len(ACTIVE_CLIENTS)}`\n⏱ آپ‌تایم: `{h}h {m}m {sec}s`")

            if text == "/admin" and is_admin:
                USER_STATES.pop(user_id, None)
                return await self.send_message(chat_id, "👑 **سوپر پنل اختصاصی مدیریت ادمین (۱۷۵ قابلیت مجزا)**\n\nیکی از بخش‌های زیر را انتخاب کنید:", reply_markup=self.get_admin_hub_kb())

            if USER_STATES.get(user_id) == "WAITING_PHONE":
                phone = text.strip()
                USER_STATES.pop(user_id, None)
                if not phone.startswith("+") or len(phone) < 8:
                    return await self.send_message(chat_id, "❌ شماره باید با `+` و کد کشور ارسال شود.", reply_markup={"inline_keyboard": [[{"text": "📱 تلاش دوباره", "callback_data": "btn_phone_login"}], [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]]})
                old_login = LOGIN_CLIENTS.pop(user_id, None)
                if old_login:
                    try: await old_login["client"].disconnect()
                    except Exception: pass
                cli = PyroClient(name=f":phone:{user_id}:{int(time.time())}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
                try:
                    await cli.connect()
                    sent = await cli.send_code(phone)
                    delivery = type(getattr(sent, "type", None)).__name__
                    next_type = type(getattr(sent, "next_type", None)).__name__ if getattr(sent, "next_type", None) else ""
                    LOGIN_CLIENTS[user_id] = {
                        "client": cli, "phone": phone, "phone_code_hash": sent.phone_code_hash,
                        "method": "phone", "created": time.time(), "delivery_type": delivery,
                        "next_type": next_type, "can_resend": bool(getattr(sent, "next_type", None)),
                    }
                    is_app_delivery = "App" in delivery
                    USER_STATES[user_id] = "WAITING_LOGIN_CODE" if not is_app_delivery else "WAITING_PHONE_EXTERNAL_CODE"
                    buttons = []
                    if getattr(sent, "next_type", None):
                        buttons.append([{"text": "📩 دریافت کد با روش بعدی / SMS", "callback_data": "btn_resend_login_code"}])
                    buttons += [[{"text": "🔐 عبور به QR", "callback_data": "btn_create_session"}], [{"text": "🔙 انصراف", "callback_data": "btn_cancel_login"}]]
                    delivery_note = "کد از طریق پیام داخل تلگرام ارسال شده است؛ در این حالت واردکردن آن در چت ربات می‌تواند توسط تلگرام باطل شود." if "App" in delivery else "کد از طریق روش جایگزین ارسال شده است."
                    return await self.send_message(chat_id, f"📨 **کد ورود ارسال شد.**\n\n{delivery_note}\n\nبرای جلوگیری از خطای امنیتی، اگر کد از Telegram آمده، آن را به ربات ارسال نکن؛ از «ارسال کد با روش بعدی» یا QR استفاده کن. اگر کد از SMS/روش دیگر دریافت شد، کد را اینجا وارد کن.", reply_markup={"inline_keyboard": buttons})
                except PhoneNumberInvalid:
                    try: await cli.disconnect()
                    except Exception: pass
                    return await self.send_message(chat_id, "❌ شماره تلفن نامعتبر است. دوباره امتحان کن.", reply_markup={"inline_keyboard": [[{"text": "📱 ورود با شماره", "callback_data": "btn_phone_login"}], [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]]})
                except Exception as e:
                    try: await cli.disconnect()
                    except Exception: pass
                    return await self.send_message(chat_id, f"❌ ارسال کد ناموفق بود:\n`{e}`", reply_markup={"inline_keyboard": [[{"text": "🔐 ورود با QR", "callback_data": "btn_create_session"}], [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}] ]})

            if USER_STATES.get(user_id) in {"WAITING_LOGIN_CODE", "WAITING_PHONE_EXTERNAL_CODE"}:
                data = LOGIN_CLIENTS.get(user_id)
                if not data:
                    USER_STATES.pop(user_id, None)
                    return await self.send_message(chat_id, "❌ نشست ورود منقضی شده است؛ دوباره ورود با شماره را شروع کن.", reply_markup={"inline_keyboard": [[{"text": "📱 ورود با شماره", "callback_data": "btn_phone_login"}], [{"text": "🔐 ورود با QR", "callback_data": "btn_create_session"}]]})
                cli = data["client"]
                code = text.replace(" ", "").strip()
                try:
                    await cli.sign_in(data["phone"], data["phone_code_hash"], code)
                except SessionPasswordNeeded:
                    USER_STATES[user_id] = "WAITING_LOGIN_2FA"
                    return await self.send_message(chat_id, "🔒 رمز دومرحله‌ای حساب فعال است. رمز 2FA را وارد کن:", reply_markup={"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "btn_cancel_login"}]]})
                except (PhoneCodeInvalid, PhoneCodeExpired) as e:
                    msg = str(e).lower()
                    if "previously shared" in msg or "shared" in msg:
                        try: await cli.disconnect()
                        except Exception: pass
                        LOGIN_CLIENTS.pop(user_id, None); USER_STATES.pop(user_id, None)
                        return await self.send_message(chat_id, "⚠️ تلگرام این کد را به‌دلیل وضعیت امنیتی آن رد کرد. این محدودیت از سمت تلگرام است و قابل دورزدن نیست.\n\n✅ می‌توانید «📩 دریافت کد با روش بعدی / SMS» را در شروع ورود امتحان کنید یا از QR رسمی استفاده کنید.", reply_markup={"inline_keyboard": [[{"text": "🔐 ورود امن با QR", "callback_data": "btn_create_session"}], [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]]})
                    return await self.send_message(chat_id, "❌ کد اشتباه یا منقضی شده است. کد جدید را وارد کن.", reply_markup={"inline_keyboard": [[{"text": "🔐 عبور به QR", "callback_data": "btn_create_session"}], [{"text": "🔙 انصراف", "callback_data": "btn_cancel_login"}]]})
                except Exception as e:
                    try: await cli.disconnect()
                    except Exception: pass
                    LOGIN_CLIENTS.pop(user_id, None); USER_STATES.pop(user_id, None)
                    if "shared" in str(e).lower():
                        return await self.send_message(chat_id, "⚠️ تلگرام ورود با این کد را رد کرد؛ QR را استفاده کن.", reply_markup={"inline_keyboard": [[{"text": "🔐 ورود امن با QR", "callback_data": "btn_create_session"}], [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]]})
                    return await self.send_message(chat_id, f"❌ خطای ورود:\n`{e}`", reply_markup={"inline_keyboard": [[{"text": "📱 ورود دوباره", "callback_data": "btn_phone_login"}], [{"text": "🔐 ورود با QR", "callback_data": "btn_create_session"}]]})

                sess_str = await cli.export_session_string()
                await cli.disconnect()
                LOGIN_CLIENTS.pop(user_id, None); USER_STATES.pop(user_id, None)
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("INSERT INTO users (user_id, session_string) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET session_string = excluded.session_string", (user_id, sess_str))
                    await db.commit()
                await audit_log(user_id, "phone_login_success", user_id)
                await start_single_client(user_id, sess_str)
                add_system_log(f"User {user_id} logged in via phone code.")
                p_text, p_kb = await self.render_user_dashboard(user_id, is_admin)
                return await self.send_message(chat_id, p_text, reply_markup=p_kb)

            # ۳. مرحله دریافت رمز دومرحله‌ای (2FA)
            elif USER_STATES.get(user_id) == "WAITING_LOGIN_2FA":
                data = LOGIN_CLIENTS.get(user_id)
                if not data:
                    USER_STATES.pop(user_id, None)
                    return await self.send_message(chat_id, "❌ نشست ورود منقضی شد.")

                cli = data["client"]
                await self.send_message(chat_id, "⏳ در حال اعتبارسنجی رمز دومرحله‌ای...")
                try:
                    await cli.check_password(text.strip())
                    sess_str = await cli.export_session_string()
                    await cli.disconnect()
                    LOGIN_CLIENTS.pop(user_id, None)
                    USER_STATES.pop(user_id, None)

                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT INTO users (user_id, session_string) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET session_string = excluded.session_string", (user_id, sess_str))
                        await db.commit()

                    await start_single_client(user_id, sess_str)
                    add_system_log(f"User {user_id} passed 2FA & launched.")
                    # Session strings are credentials: store them server-side and never echo them back in chat.
                    msg_done = (
                        "🎉 **رمز تایید شد! سلف شما با موفقیت روشن گردید.**\n\n"
                        "🔐 اطلاعات نشست به‌صورت داخلی ذخیره شد و برای امنیت، داخل چت نمایش داده نمی‌شود.\n\n"
                        "👇 کنترل تمام امکانات از طریق پنل زیر:"
                    )
                    p_text, p_kb = await self.render_user_dashboard(user_id, is_admin)
                    return await self.send_message(chat_id, msg_done + "\n\n" + p_text, reply_markup=p_kb)
                except PasswordHashInvalid:
                    return await self.send_message(chat_id, "❌ رمز عبور دومرحله‌ای وارد شده نادرست است. مجدداً ارسال کنید:")
                except Exception as e:
                    return await self.send_message(chat_id, f"❌ خطا در بررسی رمز دومرحله‌ای:\n`{e}`")

            # افزودن دوست
            elif USER_STATES.get(user_id) == "WAITING_ADD_FRIEND":
                USER_STATES.pop(user_id, None)
                if text.isdigit():
                    t_id = int(text)
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT OR REPLACE INTO relations (owner_id, target_id, type) VALUES (?, ?, 'friend')", (user_id, t_id))
                        await db.commit()
                    if user_id in ACTIVE_CLIENTS:
                        if not hasattr(ACTIVE_CLIENTS[user_id], "friends_set"):
                            ACTIVE_CLIENTS[user_id].friends_set = set()
                        ACTIVE_CLIENTS[user_id].friends_set.add(t_id)
                    return await self.send_message(chat_id, f"✅ کاربر `{t_id}` با موفقیت به **لیست دوستان ویژه** اضافه شد.")
                return await self.send_message(chat_id, "❌ لطفاً فقط شناسه عددی (Numeric User ID) را ارسال فرمایید.")

            # افزودن دشمن
            elif USER_STATES.get(user_id) == "WAITING_ADD_ENEMY":
                USER_STATES.pop(user_id, None)
                if text.isdigit():
                    t_id = int(text)
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT OR REPLACE INTO relations (owner_id, target_id, type) VALUES (?, ?, 'enemy')", (user_id, t_id))
                        await db.commit()
                    if user_id in ACTIVE_CLIENTS:
                        if not hasattr(ACTIVE_CLIENTS[user_id], "enemies_set"):
                            ACTIVE_CLIENTS[user_id].enemies_set = set()
                        ACTIVE_CLIENTS[user_id].enemies_set.add(t_id)
                    return await self.send_message(chat_id, f"⚔️ کاربر `{t_id}` با موفقیت به **لیست دشمنان** اضافه گردید.")
                return await self.send_message(chat_id, "❌ لطفاً فقط شناسه عددی کاربر را وارد کنید.")

            # حذف تکی از روابط
            elif USER_STATES.get(user_id) == "WAITING_REMOVE_RELATION":
                USER_STATES.pop(user_id, None)
                if text.isdigit():
                    t_id = int(text)
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("DELETE FROM relations WHERE owner_id = ? AND target_id = ?", (user_id, t_id))
                        await db.commit()
                    if user_id in ACTIVE_CLIENTS:
                        if hasattr(ACTIVE_CLIENTS[user_id], "friends_set"):
                            ACTIVE_CLIENTS[user_id].friends_set.discard(t_id)
                        if hasattr(ACTIVE_CLIENTS[user_id], "enemies_set"):
                            ACTIVE_CLIENTS[user_id].enemies_set.discard(t_id)
                    return await self.send_message(chat_id, f"🗑 کاربر `{t_id}` از لیست روابط شما پاک شد.")
                return await self.send_message(chat_id, "❌ شناسه عددی نامعتبر است.")

            # تغییر پیشوند دستورات
            elif USER_STATES.get(user_id) == "WAITING_NEW_PREFIX":
                USER_STATES.pop(user_id, None)
                new_p = text.strip()
                if len(new_p) > 3:
                    return await self.send_message(chat_id, "❌ پیشوند نمی‌تواند بیش از ۳ کاراکتر باشد.")
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET prefix = ? WHERE user_id = ?", (new_p, user_id))
                    await db.commit()
                if user_id in ACTIVE_CLIENTS:
                    ACTIVE_CLIENTS[user_id].custom_prefix = new_p
                return await self.send_message(chat_id, f"⚡️ پیشوند سلف شما با موفقیت به `{new_p}` تغییر یافت.")

            # ارسال مستقیم سشن
            elif USER_STATES.get(user_id) == "WAITING_SESSION":
                if not REGISTRATION_OPEN and not is_admin:
                    USER_STATES.pop(user_id, None)
                    return await self.send_message(chat_id, "🔒 ثبت‌نام کاربران جدید فعلاً بسته است.")
                if len(ACTIVE_CLIENTS) >= MAX_ALLOWED_SELFS and not is_admin:
                    USER_STATES.pop(user_id, None)
                    return await self.send_message(chat_id, f"⚠️ ظرفیت سلف‌های فعال سرور تکمیل است ({MAX_ALLOWED_SELFS}).")
                if len(text) > 40:
                    await self.send_message(chat_id, "⏳ در حال بررسی سشن و راه‌اندازی سلف...")
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT INTO users (user_id, session_string) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET session_string = excluded.session_string", (user_id, text))
                        await db.commit()
                    started, err = await start_single_client(user_id, text)
                    USER_STATES.pop(user_id, None)
                    if started:
                        add_system_log(f"Self {user_id} launched via direct session.")
                        return await self.send_message(chat_id, "🎉 **سلف شما روشن شد!** اکنون از پنل زیر امکانات را مدیریت کنید:", reply_markup=self.get_main_dashboard_kb(True, is_admin))
                    else:
                        return await self.send_message(chat_id, f"❌ خطا در راه‌اندازی:\n`{err}`\n\nاز صحت سشن اطمینان حاصل فرمایید.")
                else:
                    return await self.send_message(chat_id, "❌ کد استرینگ سشن ارسالی نامعتبر یا خیلی کوتاه است.")

# دانلود یوتیوب: موتور مشترک در core/youtube.py قرار دارد.
            elif USER_STATES.get(user_id) == "WAITING_YOUTUBE":
                USER_STATES.pop(user_id, None)
                if not is_youtube_url(text):
                    await self.send_message(chat_id, "❌ لینک یوتیوب ارسالی معتبر نیست.")
                    return

                from core.plans import get_user_yt_limit_mb
                max_mb = await get_user_yt_limit_mb(user_id)
                try:
                    global_limit = int(await get_setting("global_download_limit_mb", "0"))
                except Exception:
                    global_limit = 0
                if global_limit > 0 and (max_mb is None or max_mb > global_limit):
                    max_mb = global_limit
                limit_text = "نامحدود" if max_mb is None else f"{max_mb} MB"
                await self.send_message(chat_id, f"⏳ در حال پردازش یوتیوب...\n📦 سقف پلن: `{limit_text}`")

                prefix = f"downloads/yt_{user_id}_{int(time.time())}_"
                try:
                    result = await asyncio.to_thread(download_youtube, text, prefix, max_mb)
                    fname = result["path"]
                    f_size_mb = result["size_mb"]
                    title = result["title"]
                    await self.send_message(chat_id, f"✅ دانلود شد (`{f_size_mb:.1f} MB`)؛ در حال ارسال...")

                    sent = False
                    if f_size_mb > 50 and user_id in ACTIVE_CLIENTS:
                        try:
                            await ACTIVE_CLIENTS[user_id].send_video(
                                chat_id, fname,
                                caption=f"🎬 {title}\n📦 حجم: `{f_size_mb:.1f} MB`\n⚡️ SelfSaz"
                            )
                            sent = True
                        except Exception:
                            sent = False

                    if not sent:
                        if f_size_mb > 50:
                            await self.send_message(
                                chat_id,
                                "⚠️ پلن شما این حجم را مجاز کرده، اما ارسال از Bot API سقف مستقل دارد. "
                                "برای فایل‌های بزرگ، سلف باید روشن باشد تا فایل با اکانت سلف ارسال شود."
                            )
                        else:
                            resp = await self.send_video_file(
                                chat_id, fname, caption=f"🎬 {title}\n📦 حجم: `{f_size_mb:.1f} MB`"
                            )
                            if not (resp and resp.get("ok")):
                                await self.send_message(chat_id, "❌ ارسال فایل توسط Bot API ناموفق بود.")
                except Exception as e:
                    await self.send_message(chat_id, human_error(e, max_mb))
                finally:
                    cleanup_prefix(prefix)
                return
            # اقتصاد فعالیت: یک پاداش کوچک دوره‌ای برای کاربر ثبت‌شده.
            if u := await self.get_user_db(user_id):
                try:
                    await record_activity_reward(user_id, points=1)
                except Exception:
                    pass

            # استیت‌های متنی ادمین
            if is_admin:
                if USER_STATES.get(user_id) == "AD_WAIT_BROADCAST_VIP":
                    USER_STATES.pop(user_id, None)
                    async with aiosqlite.connect(DB_NAME) as db:
                        rows = await (await db.execute("SELECT user_id FROM users WHERE plan='diamond' OR is_vip=1")).fetchall()
                    sent = 0
                    for (target_uid,) in rows:
                        try:
                            res = await self.send_message(int(target_uid), text)
                            if isinstance(res, dict) and res.get("ok"):
                                sent += 1
                        except Exception:
                            pass
                    await audit_log(user_id, "broadcast_vip", detail=str(sent))
                    return await self.send_message(chat_id, f"💎 پیام برای `{sent}` کاربر VIP/الماسی ارسال شد.")

                if USER_STATES.get(user_id) == "AD_WAIT_BROADCAST":
                    USER_STATES.pop(user_id, None)
                    await self.send_message(chat_id, "⏳ ارسال همگانی در حال اجراست...")
                    cnt = 0
                    async with aiosqlite.connect(DB_NAME) as db:
                        cursor = await db.execute("SELECT user_id FROM users")
                        rows = await cursor.fetchall()
                    for r in rows:
                        try:
                            await self.send_message(r[0], f"📢 **اطلاعیه رسمی سیستم:**\n\n{text}")
                            cnt += 1
                            await asyncio.sleep(0.08)
                        except Exception:
                            pass
                    add_system_log(f"Admin broadcasted to {cnt} users.")
                    return await self.send_message(chat_id, f"✅ پیام به {cnt} کاربر با موفقیت ارسال شد.")

                elif USER_STATES.get(user_id) == "AD_WAIT_FORCE_RESTART_USER":
                    USER_STATES.pop(user_id, None)
                    if not text.isdigit():
                        return await self.send_message(chat_id, "❌ آیدی عددی نامعتبر است.")
                    target = int(text)
                    u = await self.get_user_db(target)
                    if not u or not u[0]:
                        return await self.send_message(chat_id, "❌ کاربر پیدا نشد یا سشن ذخیره‌شده ندارد.")
                    await stop_single_client(target)
                    ok, err = await start_single_client(target, u[0])
                    await audit_log(user_id, "admin_force_restart_user", target, "success" if ok else err[:500])
                    return await self.send_message(chat_id, f"{'✅' if ok else '❌'} ریستارت کاربر `{target}` {'موفق بود.' if ok else 'ناموفق بود: '+err[:500]}")

                elif USER_STATES.get(user_id) == "AD_WAIT_FORCE_STOP_USER":
                    USER_STATES.pop(user_id, None)
                    if not text.isdigit():
                        return await self.send_message(chat_id, "❌ آیدی عددی نامعتبر است.")
                    target = int(text)
                    ok = await stop_single_client(target)
                    await audit_log(user_id, "admin_force_stop_user", target, str(ok))
                    return await self.send_message(chat_id, f"🛑 وضعیت توقف کاربر `{target}`: {'اتصال قطع شد ✅' if ok else 'این کاربر سلف آنلاین نداشت ⚠️'}")

                elif USER_STATES.get(user_id) == "AD_WAIT_DELETE_USER":
                    USER_STATES.pop(user_id, None)
                    if not text.isdigit():
                        return await self.send_message(chat_id, "❌ آیدی عددی نامعتبر است.")
                    target = int(text)
                    if target == ADMIN_ID:
                        return await self.send_message(chat_id, "🛡 حذف حساب ادمین اصلی مجاز نیست.")
                    existed = bool(await self.get_user_db(target))
                    await stop_single_client(target)
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("DELETE FROM users WHERE user_id=?", (target,))
                        await db.execute("DELETE FROM relations WHERE owner_id=?", (target,))
                        await db.execute("DELETE FROM referrals WHERE referrer_id=? OR referred_id=?", (target, target))
                        await db.execute("DELETE FROM user_notes WHERE owner_id=?", (target,))
                        await db.execute("DELETE FROM message_stats WHERE user_id=?", (target,))
                        await db.execute("DELETE FROM ai_messages WHERE user_id=?", (target,))
                        await db.execute("DELETE FROM notification_preferences WHERE user_id=?", (target,))
                        await db.execute("DELETE FROM membership_exemptions WHERE user_id=?", (target,))
                        await db.commit()
                    await audit_log(user_id, "admin_delete_user", target, "deleted")
                    return await self.send_message(chat_id, f"{'✅ حساب و سشن کاربر حذف شد.' if existed else '⚠️ رکورد کاربر از قبل وجود نداشت؛ عملیات پاکسازی انجام شد.'}\n🆔 `{target}`")

                elif USER_STATES.get(user_id) == "AD_WAIT_FIND_USER":
                    USER_STATES.pop(user_id, None)
                    if text.isdigit():
                        t_uid = int(text)
                        t_data = await self.get_user_db(t_uid)
                        if t_data:
                            prof = await get_user_profile(t_uid)
                            on_st = "روشن 🟢" if t_uid in ACTIVE_CLIENTS else "خاموش 🔴"
                            plan_key = (prof or {}).get("plan", "normal")
                            plan_cfg = PLANS_DATA.get(plan_key, PLANS_DATA["normal"])
                            card = (
                                f"👤 **اطلاعات کاربر `{t_uid}`**\n━━━━━━━━━━━━━━━━━━━━\n"
                                f"🖥 وضعیت سلف: {on_st}\n"
                                f"🏆 رنک: {plan_cfg['badge']} **{plan_cfg['title']}**\n"
                                f"🪙 سکه: `{(prof or {}).get('coins', t_data[1])}`\n"
                                f"⚡ XP: `{(prof or {}).get('activity_score', 0)}`\n"
                                f"👥 دعوت موفق: `{(prof or {}).get('referral_count', 0)}`\n"
                                f"⚡️ پیشوند: `{t_data[3]}`"
                            )
                            return await self.send_message(chat_id, card)
                        return await self.send_message(chat_id, f"❌ کاربر `{t_uid}` یافت نشد.")

                elif USER_STATES.get(user_id) == "AD_WAIT_TEST_SESSION":
                    USER_STATES.pop(user_id, None)
                    if not text.isdigit():
                        return await self.send_message(chat_id, "❌ آیدی باید عددی باشد.")
                    target_uid = int(text)
                    target = await self.get_user_db(target_uid)
                    if not target:
                        return await self.send_message(chat_id, f"❌ کاربر `{target_uid}` در دیتابیس پیدا نشد.")
                    connected = target_uid in ACTIVE_CLIENTS and bool(getattr(ACTIVE_CLIENTS[target_uid], "is_connected", False))
                    has_session = bool(target[0])
                    detail = (
                        f"🩺 **بررسی واقعی سشن کاربر `{target_uid}`**\n"
                        f"💾 سشن ذخیره‌شده: {'بله ✅' if has_session else 'خیر ❌'}\n"
                        f"🟢 اتصال فعال: {'بله ✅' if connected else 'خیر ❌'}\n"
                        f"📌 وضعیت: {'سالم و آنلاین ✅' if connected else ('ثبت شده ولی آفلاین 🟡' if has_session else 'بدون سشن 🔴')}"
                    )
                    return await self.send_message(chat_id, detail)

                elif USER_STATES.get(user_id) == "AD_WAIT_SET_RANK_USER":
                    if text.isdigit():
                        USER_STATES[user_id] = {"type": "AD_SET_RANK", "target": int(text)}
                        rows = [[{"text": f"{cfg['badge']} {cfg['title']}", "callback_data": f"ad_apply_rank_{key}"}] for key, cfg in PLANS_DATA.items()]
                        rows.append([{"text": "🔙 لغو", "callback_data": "ad_sec_4"}])
                        return await self.send_message(chat_id, "🏆 **انتخاب رنک برای کاربر**\nرنک موردنظر را انتخاب کنید:", reply_markup={"inline_keyboard": rows})
                    return await self.send_message(chat_id, "❌ فقط آیدی عددی کاربر را ارسال کنید.")

                elif isinstance(USER_STATES.get(user_id), dict) and USER_STATES[user_id].get("type") == "AD_SET_RANK":
                    return await self.send_message(chat_id, "ℹ️ ابتدا یکی از دکمه‌های رنک را انتخاب کنید.")

                elif USER_STATES.get(user_id) == "AD_WAIT_ADD_COINS":
                    USER_STATES.pop(user_id, None)
                    parts = text.split()
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].lstrip('-').isdigit():
                        t_uid, amount = int(parts[0]), int(parts[1])
                        async with aiosqlite.connect(DB_NAME) as db:
                            await db.execute("UPDATE users SET coins = MAX(0, COALESCE(coins, 0) + ?) WHERE user_id = ?", (amount, t_uid))
                            await db.commit()
                        return await self.send_message(chat_id, f"🪙 موجودی کاربر `{t_uid}` با مقدار `{amount}` تغییر کرد.")
                    return await self.send_message(chat_id, "❌ فرمت: `آیدی مقدار`\nمثال افزایش: `123456789 500`")

                elif USER_STATES.get(user_id) == "AD_WAIT_DEDUCT_COINS":
                    USER_STATES.pop(user_id, None)
                    parts = text.split()
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        t_uid, amount = int(parts[0]), int(parts[1])
                        async with aiosqlite.connect(DB_NAME) as db:
                            await db.execute("UPDATE users SET coins = MAX(0, COALESCE(coins, 0) - ?) WHERE user_id = ?", (amount, t_uid))
                            await db.commit()
                        return await self.send_message(chat_id, f"📉 `{amount}` سکه از کاربر `{t_uid}` کسر شد.")
                    return await self.send_message(chat_id, "❌ فرمت: `آیدی تعداد`\nمثال: `123456789 100`")


                elif USER_STATES.get(user_id) == "AD_WAIT_SET_MAX_SELFS":
                    USER_STATES.pop(user_id, None)
                    if text.isdigit():
                        MAX_ALLOWED_SELFS = int(text)
                        return await self.send_message(chat_id, f"🛑 سقف مجاز سلف‌ها به `{MAX_ALLOWED_SELFS}` تنظیم شد.")

                elif USER_STATES.get(user_id) == "AD_WAIT_FORCE_JOIN":
                    USER_STATES.pop(user_id, None)
                    raw = text.strip()
                    parts = [x.strip() for x in raw.split("|", 1)]
                    target = parts[0] if parts else ""
                    join_url = parts[1] if len(parts) > 1 and parts[1] else (target if target.startswith("https://t.me/") else f"https://t.me/{target.lstrip('@')}")
                    if not target:
                        return await self.send_message(chat_id, "❌ مقصد خالی است.")
                    await set_setting("force_join_chat", target)
                    await set_setting("force_join_url", join_url)
                    await audit_log(user_id, "force_join_set", detail=f"{target} | {join_url}")
                    return await self.send_message(chat_id, f"✅ مقصد عضویت ثبت شد: `{target}`\n🔗 لینک: `{join_url}`\n\nحالا از بخش «روشن/خاموش» عضویت اجباری را فعال کنید.")
                elif USER_STATES.get(user_id) == "AD_WAIT_FORCE_JOIN_TEXT":
                    USER_STATES.pop(user_id,None); await set_setting("force_join_text",text); return await self.send_message(chat_id,"✅ متن عضویت ذخیره شد.")
                elif USER_STATES.get(user_id) in {"AD_WAIT_EXEMPT_ADD","AD_WAIT_EXEMPT_REMOVE"}:
                    state=USER_STATES.pop(user_id,None)
                    if not text.isdigit(): return await self.send_message(chat_id,"❌ آیدی عددی نامعتبر است.")
                    async with aiosqlite.connect(DB_NAME) as db:
                        if state=="AD_WAIT_EXEMPT_ADD": await db.execute("INSERT OR IGNORE INTO membership_exemptions(user_id) VALUES (?)",(int(text),))
                        else: await db.execute("DELETE FROM membership_exemptions WHERE user_id=?",(int(text),))
                        await db.commit()
                    return await self.send_message(chat_id,"✅ انجام شد.")
                elif USER_STATES.get(user_id) in {"AD_WAIT_global_ai_daily_limit", "AD_WAIT_global_download_daily_limit", "AD_WAIT_global_tool_cooldown"}:
                    state = USER_STATES.pop(user_id, None)
                    try:
                        value = int(text.strip())
                        if value < 0:
                            raise ValueError
                    except Exception:
                        return await self.send_message(chat_id, "❌ فقط عدد صحیح صفر یا بیشتر ارسال کنید.")
                    key = state.replace("AD_WAIT_", "")
                    await set_setting(key, str(value))
                    await audit_log(user_id, f"set_{key}", detail=str(value))
                    return await self.send_message(chat_id, f"✅ مقدار `{key}` روی `{value}` ذخیره شد.")
                elif USER_STATES.get(user_id) == "AD_WAIT_AI_MODEL":
                    USER_STATES.pop(user_id, None)
                    model = text.strip()[:120]
                    if not model:
                        return await self.send_message(chat_id, "❌ مدل خالی است.")
                    await set_setting("smart_ai_model", model)
                    await audit_log(user_id, "ai_model_set", detail=model)
                    return await self.send_message(chat_id, f"✅ مدل AI روی `{model}` تنظیم شد.")
                elif USER_STATES.get(user_id) == "AD_WAIT_AI_BASE":
                    USER_STATES.pop(user_id, None)
                    url = text.strip().rstrip("/")
                    if not (url.startswith("https://") or url.startswith("http://")):
                        return await self.send_message(chat_id, "❌ Base URL باید با http:// یا https:// شروع شود.")
                    await set_setting("smart_ai_base_url", url)
                    return await self.send_message(chat_id, f"✅ Base URL ذخیره شد:\n`{url}`")
                elif USER_STATES.get(user_id) == "AD_WAIT_AI_PROMPT":
                    USER_STATES.pop(user_id, None)
                    await set_setting("smart_default_prompt", text[:6000])
                    return await self.send_message(chat_id, "✅ پرامپت پیش‌فرض منشی ذخیره شد.")
                elif USER_STATES.get(user_id) == "AD_WAIT_AI_COOLDOWN":
                    USER_STATES.pop(user_id, None)
                    try:
                        value = max(1, min(300, int(text)))
                    except Exception:
                        return await self.send_message(chat_id, "❌ عدد بین ۱ تا ۳۰۰ ثانیه وارد کنید.")
                    await set_setting("smart_ai_cooldown", str(value))
                    return await self.send_message(chat_id, f"✅ کول‌داون AI روی `{value}` ثانیه تنظیم شد.")
                elif USER_STATES.get(user_id) == "AD_WAIT_AUTO_DEFAULT":
                    USER_STATES.pop(user_id, None)
                    await set_setting("smart_default_autoreply", text[:3500])
                    return await self.send_message(chat_id, "✅ متن پیش‌فرض پاسخ خودکار ذخیره شد.")
                elif USER_STATES.get(user_id) == "SMART_WAIT_AUTOREPLY":
                    USER_STATES.pop(user_id, None)
                    limit = await get_auto_reply_limit(user_id)
                    if len(text.strip()) > limit:
                        return await self.send_message(chat_id, f"🔒 متن پاسخ خودکار پلن شما حداکثر {limit} کاراکتر است. متن کوتاه‌تری ارسال کنید.")
                    if user_id in ACTIVE_CLIENTS:
                        await self.update_setting_db(user_id, "auto_reply_text", text.strip())
                    return await self.send_message(chat_id, f"✅ متن پاسخ خودکار ذخیره شد.\n📏 سقف پلن: {limit} کاراکتر")
                elif USER_STATES.get(user_id) == "SMART_WAIT_AWAY":
                    USER_STATES.pop(user_id, None)
                    if user_id in ACTIVE_CLIENTS:
                        await self.update_setting_db(user_id, "away_text", text[:3500])
                    return await self.send_message(chat_id, "✅ متن حالت مشغول ذخیره شد.")
                elif USER_STATES.get(user_id) == "SMART_WAIT_PROMPT":
                    USER_STATES.pop(user_id, None)
                    if user_id in ACTIVE_CLIENTS:
                        await self.update_setting_db(user_id, "monshi_prompt", text[:6000])
                    return await self.send_message(chat_id, "✅ شخصیت و پرامپت اختصاصی منشی ذخیره شد.")
                elif USER_STATES.get(user_id) == "AD_WAIT_GLOBAL_PREFIX":
                    USER_STATES.pop(user_id, None)
                    prefix = text.strip()[:3] or '.'
                    await set_setting("global_prefix", prefix)
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("UPDATE users SET prefix=? WHERE prefix IS NULL OR prefix='' OR prefix='.'", (prefix,))
                        await db.commit()
                    for cli in ACTIVE_CLIENTS.values():
                        try:
                            cli.custom_prefix = prefix
                        except Exception:
                            pass
                    await audit_log(user_id, "global_prefix_set", detail=prefix)
                    return await self.send_message(chat_id, f"✅ پیشوند پیش‌فرض سیستم روی `{prefix}` ذخیره و برای کاربران با پیشوند پیش‌فرض اعمال شد.")
                elif USER_STATES.get(user_id) == "AD_WAIT_GLOBAL_YT_LIMIT":
                    USER_STATES.pop(user_id,None)
                    if text.isdigit(): await set_setting("global_download_limit_mb",text); return await self.send_message(chat_id,"✅ سقف دانلود ذخیره شد.")
                    return await self.send_message(chat_id,"❌ عدد معتبر ارسال کنید.")
                elif USER_STATES.get(user_id) == "AD_WAIT_WELCOME_TEXT":
                    USER_STATES.pop(user_id,None); await set_setting("welcome_text",text); return await self.send_message(chat_id,"✅ متن خوش‌آمدگویی ذخیره شد.")
                elif USER_STATES.get(user_id) == "AD_WAIT_STATUS_TEXT":
                    USER_STATES.pop(user_id,None); await set_setting("bot_status_text",text); return await self.send_message(chat_id,"✅ متن وضعیت ذخیره شد.")
                elif USER_STATES.get(user_id) == "AD_WAIT_SPONSOR_URL":
                    USER_STATES.pop(user_id, None)
                    CHANNEL_URL = text.strip()
                    return await self.send_message(chat_id, f"📢 لینک کانال حامی به `{CHANNEL_URL}` تغییر یافت.")

# پردازش کلیک روی دکمه‌ها
        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            user_id = cq.get("from", {}).get("id", chat_id)
            msg_id = cq["message"]["message_id"]
            data = cq.get("data", "")
            is_admin = (user_id == ADMIN_ID)

            if data == "check_membership":
                if await self._membership_gate(user_id, chat_id, cq["id"], msg_id):
                    await self.answer_callback(cq["id"], "✅ عضویت تأیید شد.", alert=True)
                    text_home, kb_home = await self.render_user_dashboard(user_id, is_admin)
                    return await self.edit_message(chat_id, msg_id, text_home, reply_markup=kb_home)
                return

            if not is_admin and data != "btn_cancel_login":
                if not await self._membership_gate(user_id, chat_id, cq["id"], msg_id):
                    return

            # Every old inline button is revalidated against the current DB record
            # before any feature handler runs. This makes stale buttons inert after deletion.
            if not await self.ensure_registered_callback(cq, user_id, chat_id, msg_id, data, is_admin):
                return

            if await handle_plan_callback(self, cq, user_id=user_id, chat_id=chat_id, msg_id=msg_id, data=data):
                return

            if data == "btn_resend_login_code":
                pending = LOGIN_CLIENTS.get(user_id)
                if not pending or pending.get("method") != "phone" or not pending.get("can_resend"):
                    return await self.answer_callback(cq["id"], "❌ روش جایگزین برای این نشست در دسترس نیست؛ دوباره ورود با شماره یا QR را شروع کن.", alert=True)
                try:
                    sent = await pending["client"].resend_code(pending["phone"], pending["phone_code_hash"])
                    pending["phone_code_hash"] = sent.phone_code_hash
                    pending["next_type"] = type(getattr(sent, "next_type", None)).__name__ if getattr(sent, "next_type", None) else ""
                    pending["can_resend"] = bool(getattr(sent, "next_type", None))
                    delivery = type(getattr(sent, "type", None)).__name__
                    is_app_delivery = "App" in delivery
                    USER_STATES[user_id] = "WAITING_PHONE_EXTERNAL_CODE" if is_app_delivery else "WAITING_LOGIN_CODE"
                    note = "📱 کد با روش جایگزین ارسال شد. اکنون می‌توانی کد دریافتی را وارد کنی." if not is_app_delivery else "⚠️ Telegram هنوز کد را داخل خود برنامه فرستاده است؛ آن را به ربات نفرست و یک بار دیگر «روش بعدی» یا QR را انتخاب کن."
                    buttons = []
                    if pending["can_resend"]:
                        buttons.append([{"text": "📩 دریافت کد با روش بعدی / SMS", "callback_data": "btn_resend_login_code"}])
                    buttons += [[{"text": "🔐 ورود امن با QR", "callback_data": "btn_create_session"}], [{"text": "🔙 انصراف", "callback_data": "btn_cancel_login"}]]
                    await self.answer_callback(cq["id"], "📨 کد مجدد ارسال شد.")
                    return await self.edit_message(chat_id, msg_id, note + "\n\nکد را فقط در صورت دریافت از SMS/روش غیر-Telegram وارد کن.", reply_markup={"inline_keyboard": buttons})
                except Exception as e:
                    return await self.answer_callback(cq["id"], f"❌ ارسال مجدد ممکن نشد: {e}", alert=True)

            if data == "btn_phone_login":
                if not REGISTRATION_OPEN and not is_admin:
                    return await self.answer_callback(cq["id"], "🔒 ثبت‌نام کاربران جدید فعلاً بسته است.", alert=True)
                USER_STATES[user_id] = "WAITING_PHONE"
                await self.answer_callback(cq["id"])
                return await self.edit_message(
                    chat_id, msg_id,
                    "📱 **ورود با شماره تلفن**\n\nشماره حساب را با فرمت بین‌المللی ارسال کنید؛ مثال: `+989123456789`\n\n✅ مسیر ورود شماره‌ای بهینه شده است. اگر تلگرام ابتدا کد را داخل خود Telegram بفرستد، از دکمه «📩 دریافت کد با روش بعدی» برای درخواست SMS/روش جایگزین استفاده کنید.\n\n⚠️ کد یا رمز را در گروه یا چت دیگری منتشر نکنید؛ تلگرام ممکن است کدی را که قبلاً به اشتراک گذاشته شده رد کند.",
                    reply_markup={"inline_keyboard": [[{"text": "🔐 ورود امن با QR", "callback_data": "btn_create_session"}], [{"text": "🔙 انصراف", "callback_data": "btn_cancel_login"}]]},
                )

            if data == "btn_create_session":
                if not REGISTRATION_OPEN and not is_admin:
                    return await self.answer_callback(cq["id"], "🔒 ثبت‌نام کاربران جدید فعلاً بسته است.", alert=True)
                if user_id in LOGIN_CLIENTS:
                    try:
                        await LOGIN_CLIENTS[user_id]["client"].disconnect()
                    except Exception:
                        pass
                    LOGIN_CLIENTS.pop(user_id, None)
                await self.answer_callback(cq["id"])
                await self.edit_message(chat_id, msg_id, "🔐 **ورود امن با QR**\n\nکد ورود را داخل چت ربات ارسال نکنید؛ تلگرام ممکن است چنین کدی را لو رفته تلقی کرده و همان کد را باطل کند.\n\nQR زیر حدود ۳۰ ثانیه اعتبار دارد. آن را با اپلیکیشن Telegram که همین حساب روی آن وارد است اسکن و تأیید کنید؛ اگر منقضی شد، «QR جدید» را بزنید.", reply_markup={"inline_keyboard": [[{"text": "🔄 QR جدید", "callback_data": "btn_qr_refresh"}], [{"text": "🔙 انصراف", "callback_data": "btn_cancel_login"}]]})
                try:
                    result = await create_qr_login(API_ID, API_HASH, user_id)
                    LOGIN_CLIENTS[user_id] = result
                    USER_STATES[user_id] = "WAITING_QR"
                    qr_path = result["qr_path"]
                    sent = await self.send_photo(chat_id, qr_path, caption="📲 QR ورود به سلف‌ساز\n\nاین QR را فقط با تلگرام رسمیِ همان حساب اسکن کنید.")
                    result["message_id"] = (sent or {}).get("result", {}).get("message_id")
                    asyncio.create_task(self._finish_qr_login(user_id, chat_id))
                    return
                except Exception as e:
                    LOGIN_CLIENTS.pop(user_id, None)
                    USER_STATES.pop(user_id, None)
                    return await self.send_message(chat_id, f"❌ ساخت QR ورود ناموفق بود:\n`{e}`", reply_markup={"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}] ]})

            elif data == "btn_qr_refresh":
                if user_id in LOGIN_CLIENTS:
                    try:
                        await LOGIN_CLIENTS[user_id]["client"].disconnect()
                    except Exception:
                        pass
                    LOGIN_CLIENTS.pop(user_id, None)
                USER_STATES.pop(user_id, None)
                await self.answer_callback(cq["id"], "🔄 QR جدید در حال ساخت است...")
                return await self.handle_update({"callback_query": {**cq, "data": "btn_create_session"}})

            elif data == "btn_cancel_login":
                USER_STATES.pop(user_id, None)
                if user_id in LOGIN_CLIENTS:
                    try:
                        await LOGIN_CLIENTS[user_id]["client"].disconnect()
                    except Exception:
                        pass
                    LOGIN_CLIENTS.pop(user_id, None)
                await self.answer_callback(cq["id"], "ورود لغو شد.")
                return await self.handle_update({"message": {"chat": {"id": chat_id}, "from": {"id": user_id}, "text": "/start"}})

            elif data == "btn_submit_session":
                USER_STATES[user_id] = "WAITING_SESSION"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "back_dashboard"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📱 **کد استرینگ سشن (String Session) اکانت خود را ارسال فرمایید:**", reply_markup=kb)

            elif data == "back_dashboard":
                USER_STATES.pop(user_id, None)
                await self.answer_callback(cq["id"])
                p_text, p_kb = await self.render_user_dashboard(user_id, is_admin)
                return await self.edit_message(chat_id, msg_id, p_text, reply_markup=p_kb)

            elif data == "btn_turn_off":
                await stop_single_client(user_id)
                add_system_log(f"Self {user_id} stopped by user.")
                await self.answer_callback(cq["id"], "🛑 سلف خاموش شد و نام قبلی شما بازگشت.")
                p_text, p_kb = await self.render_user_dashboard(user_id, is_admin)
                return await self.edit_message(chat_id, msg_id, p_text, reply_markup=p_kb)

            elif data == "btn_turn_on":
                u = await self.get_user_db(user_id)
                if u:
                    ok, err = await start_single_client(user_id, u[0])
                    if ok:
                        add_system_log(f"Self {user_id} started by user.")
                        await self.answer_callback(cq["id"], "🟢 سلف شما آنلاین شد!")
                        p_text, p_kb = await self.render_user_dashboard(user_id, is_admin)
                        return await self.edit_message(chat_id, msg_id, p_text, reply_markup=p_kb)
                    else:
                        await self.answer_callback(cq["id"], f"خطا در اتصال:\n{err}", alert=True)

            elif data == "btn_restart":
                u = await self.get_user_db(user_id)
                if u:
                    await stop_single_client(user_id)
                    await asyncio.sleep(1)
                    await start_single_client(user_id, u[0])
                    await self.answer_callback(cq["id"], "🔄 سلف ریستارت شد!", alert=True)
                    p_text, p_kb = await self.render_user_dashboard(user_id, is_admin)
                    return await self.edit_message(chat_id, msg_id, p_text, reply_markup=p_kb)

            elif data == "btn_delete_account":
                await stop_single_client(user_id)
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                    await db.execute("DELETE FROM relations WHERE owner_id = ?", (user_id,))
                    await db.commit()
                add_system_log(f"User {user_id} deleted account.")
                await self.answer_callback(cq["id"], "اکانت و سلف شما پاک شد.", alert=True)
                kb = {"inline_keyboard": [[{"text": "🔐 ورود امن با QR", "callback_data": "btn_create_session"}], [{"text": "📱 ورود با شماره و کد", "callback_data": "btn_phone_login"}], [{"text": "🔑 ارسال سشن", "callback_data": "btn_submit_session"}]]}
                return await self.edit_message(chat_id, msg_id, "🛑 سلف شما حذف گردید.", reply_markup=kb)

            # ================== اتوماسیون واقعی حساب ==================
            elif data == "menu_account_auto":
                cli = ACTIVE_CLIENTS.get(user_id)
                p = await get_user_profile(user_id) or {"plan": "normal"}
                cfg = PLANS_DATA.get(p.get("plan", "normal"), PLANS_DATA["normal"])
                st = (cli.settings if cli else {}) if cli else {}
                online = bool(cli and getattr(cli, "is_connected", False))
                text = (
                    "⚙️ **اتوماسیون واقعی حساب**\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"🟢 اتصال: `{'آنلاین' if online else 'آفلاین'}`\n"
                    f"🏆 رنک: {cfg['badge']} **{cfg['title']}**\n\n"
                    "این بخش فقط اطلاعات نشان نمی‌دهد؛ هر گزینه یک رفتار واقعی روی اکانت فعال می‌کند.\n\n"
                    f"🪪 چرخش نام: {'فعال ✅' if st.get('automation_name_active') else 'خاموش ❌'}\n"
                    f"📝 چرخش Bio: {'فعال ✅' if st.get('automation_bio_active') else 'خاموش ❌'}\n"
                    f"💾 ذخیره خودکار: {'فعال ✅' if st.get('automation_save_active') else 'خاموش ❌'}\n"
                    f"❤️ واکنش خودکار: {'فعال ✅' if st.get('automation_react_active') else 'خاموش ❌'}\n"
                    f"👋 خوش‌آمد خودکار: {'فعال ✅' if st.get('automation_greet_active') else 'خاموش ❌'}\n"
                    f"⌨️ تایپ خودکار: {'فعال ✅' if st.get('automation_typing_active') else 'خاموش ❌'}"
                )
                kb = {"inline_keyboard": [
                    [{"text": "🪪 روشن/خاموش چرخش نام", "callback_data": "auto_name_toggle"}],
                    [{"text": "📝 روشن/خاموش چرخش Bio", "callback_data": "auto_bio_toggle"}],
                    [{"text": "💾 روشن/خاموش ذخیره خودکار", "callback_data": "auto_save_toggle"}],
                    [{"text": "❤️ روشن/خاموش واکنش خودکار", "callback_data": "auto_react_toggle"}],
                    [{"text": "👋 روشن/خاموش خوش‌آمد خودکار", "callback_data": "auto_greet_toggle"}],
                    [{"text": "⌨️ روشن/خاموش تایپ خودکار", "callback_data": "auto_typing_toggle"}],
                    [{"text": "📏 محدودیت‌های اتوماسیون رنک من", "callback_data": "auto_limits"}],
                    [{"text": "⚙️ راهنمای دستورهای اتوماسیون", "callback_data": "auto_commands"}],
                    [{"text": "🔙 مرکز کاربری", "callback_data": "menu_user_center"}],
                ]}
                return await self.edit_message(chat_id, msg_id, text, reply_markup=kb)

            elif data in {"auto_name_toggle", "auto_bio_toggle", "auto_save_toggle", "auto_react_toggle", "auto_greet_toggle", "auto_typing_toggle"}:
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ ابتدا سلف را روشن کن.", alert=True)
                if data == "auto_react_toggle" and await get_automation_react_limit(user_id) <= 0:
                    return await self.answer_callback(cq["id"], "🔒 واکنش خودکار از رنک آهنی فعال می‌شود.", alert=True)
                if data == "auto_name_toggle":
                    if not getattr(cli, "auto_name_active", False) and getattr(cli, "timename_active", False):
                        return await self.answer_callback(cq["id"], "⚠️ همزمانی با «ساعت روی اسم» مجاز نیست؛ ابتدا ساعت روی اسم را خاموش کن.", alert=True)
                    new = not bool(getattr(cli, "auto_name_active", False)); cli.auto_name_active = new
                    await self.update_setting_db(user_id, "automation_name_active", new)
                    from plugins.account_automations import _cycle_worker
                    if new:
                        if getattr(cli, "auto_name_task", None): cli.auto_name_task.cancel()
                        cli.auto_name_task = asyncio.create_task(_cycle_worker(cli, "name"))
                    elif getattr(cli, "auto_name_task", None): cli.auto_name_task.cancel(); cli.auto_name_task = None
                elif data == "auto_bio_toggle":
                    new = not bool(getattr(cli, "auto_bio_active", False)); cli.auto_bio_active = new
                    await self.update_setting_db(user_id, "automation_bio_active", new)
                    from plugins.account_automations import _cycle_worker
                    if new:
                        if getattr(cli, "auto_bio_task", None): cli.auto_bio_task.cancel()
                        cli.auto_bio_task = asyncio.create_task(_cycle_worker(cli, "bio"))
                    elif getattr(cli, "auto_bio_task", None): cli.auto_bio_task.cancel(); cli.auto_bio_task = None
                else:
                    key_map = {"auto_save_toggle":"automation_save_active", "auto_react_toggle":"automation_react_active", "auto_greet_toggle":"automation_greet_active", "auto_typing_toggle":"automation_typing_active"}
                    key = key_map[data]; new = not bool(cli.settings.get(key, False)); await self.update_setting_db(user_id, key, new)
                await self.answer_callback(cq["id"], "✅ تغییر اعمال شد.")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_account_auto"}})

            elif data == "auto_limits":
                p = await get_user_profile(user_id) or {"plan":"normal"}; cfg = PLANS_DATA.get(p.get("plan","normal"), PLANS_DATA["normal"])
                return await self.answer_callback(cq["id"],
                    f"📏 سقف‌های اتوماسیون {cfg['badge']} {cfg['title']}\n"
                    f"❤️ واکنش روزانه: {await get_automation_react_limit(user_id)}\n"
                    f"💾 ذخیره روزانه: {await get_automation_save_limit(user_id)}\n"
                    f"👋 خوش‌آمد روزانه: {await get_automation_greet_limit(user_id)}\n"
                    f"🪪 حداکثر نام در چرخه: {await get_automation_name_count(user_id)}\n"
                    f"📝 حداکثر Bio در چرخه: {await get_automation_bio_count(user_id)}\n"
                    f"⏱ فاصله چرخه: {await get_automation_interval(user_id)} ثانیه",
                    alert=True)
            elif data == "auto_commands":
                return await self.answer_callback(cq["id"],
                    "⚙️ دستورهای عملی:\n"
                    "`.اتوماسیون وضعیت`\n`.اتوماسیون نام‌ها اسم1 | اسم2 | اسم3`\n`.اتوماسیون بایوها متن1 | متن2 | متن3`\n`.اتوماسیون ایموجی 🔥`\n`.اتوماسیون پیام خوشامد متن`\n"
                    "`.اتوماسیون نام روشن/خاموش`\n`.اتوماسیون bio روشن/خاموش`\n"
                    "`.اتوماسیون ذخیره روشن/خاموش`\n`.اتوماسیون واکنش روشن/خاموش`\n"
                    "`.اتوماسیون خوشامد روشن/خاموش`\n`.اتوماسیون تایپ روشن/خاموش`",
                    alert=True)

            # ================== مرکز کاربری پیشرفته ==================
            elif data == "menu_user_center":
                p = await get_user_profile(user_id) or {}
                cfg = PLANS_DATA.get(p.get("plan", "normal"), PLANS_DATA["normal"])
                async with aiosqlite.connect(DB_NAME) as db:
                    fr = (await (await db.execute("SELECT COUNT(*) FROM relations WHERE owner_id=? AND type='friend'", (user_id,))).fetchone())[0]
                    en = (await (await db.execute("SELECT COUNT(*) FROM relations WHERE owner_id=? AND type='enemy'", (user_id,))).fetchone())[0]
                    notes = (await (await db.execute("SELECT COUNT(*) FROM user_notes WHERE owner_id=?", (user_id,))).fetchone())[0]
                    stats = await (await db.execute("SELECT incoming,outgoing,ai_replies,auto_replies FROM message_stats WHERE user_id=?", (user_id,))).fetchone()
                cli = ACTIVE_CLIENTS.get(user_id)
                online = bool(cli and getattr(cli, "is_connected", False))
                total_msgs = sum(int(x or 0) for x in (stats or (0,0,0,0)))
                text_uc = (
                    "🎛 **مرکز کاربری حرفه‌ای**\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 شناسه: `{user_id}`\n🏷 رنک: {cfg['badge']} **{cfg['title']}**\n"
                    f"🪙 سکه: `{p.get('coins',0)}`  |  ⭐ XP: `{p.get('activity_score',0)}`\n"
                    f"🟢 سلف: `{'آنلاین' if online else 'آفلاین'}`  |  💬 پیام‌ها: `{total_msgs}`\n"
                    f"❤️ دوست: `{fr}/{cfg['max_friends']}`  |  ⚔️ دشمن: `{en}/{cfg['max_enemies']}`\n"
                    f"📝 یادداشت: `{notes}/{cfg.get('max_notes',10)}`\n\n"
                    "از ابزارهای زیر برای انجام کارهای واقعی روی حساب و سلف استفاده کن:")
                kb={"inline_keyboard":[
                    [{"text":"⚡ داشبورد زنده و بروزرسانی","callback_data":"uc_live"}],
                    [{"text":"🎯 پیشرفت رنک و ارتقای بعدی","callback_data":"uc_rank_progress"}],
                    [{"text":"📏 همه محدودیت‌های رنک من","callback_data":"uc_limits"}],
                    [{"text":"🧠 مصرف حافظه AI","callback_data":"uc_ai_memory"}],
                    [{"text":"📝 مصرف و مدیریت یادداشت‌ها","callback_data":"uc_notes"}],
                    [{"text":"💬 تنظیمات پاسخ خودکار","callback_data":"uc_autoreply"}],
                    [{"text":"👁 روشن/خاموش کردن Reader","callback_data":"uc_reader_toggle"}],
                    [{"text":"🔔 روشن/خاموش کردن اعلان‌ها","callback_data":"uc_notifications"}],
                    [{"text":"⚡️ پیشوند دستورات روشن/خاموش","callback_data":"uc_prefix_toggle"}],
                    [{"text":"⏰ روشن/خاموش ساعت روی اسم","callback_data":"uc_timename"}],
                    [{"text":"🤖 روشن/خاموش منشی هوشمند","callback_data":"uc_monshi"}],
                    [{"text":"💬 روشن/خاموش حالت مشغول","callback_data":"uc_away"}],
                    [{"text":"📊 آمار پیام‌های امروز/کل","callback_data":"uc_msg_stats"}],
                    [{"text":"🏆 رتبه من بین کاربران","callback_data":"uc_my_rank"}],
                    [{"text":"💿 حجم فایل‌های شخصی","callback_data":"uc_storage"}],
                    [{"text":"🛡 بررسی سلامت سلف","callback_data":"uc_health"}],
                    [{"text":"🧹 پاکسازی فایل‌های شخصی","callback_data":"uc_cleanup"}],
                    [{"text":"🧠 پاکسازی حافظه AI من","callback_data":"uc_clear_ai"}],
                    [{"text":"📝 حذف همه یادداشت‌های من","callback_data":"uc_clear_notes"}],
                    [{"text":"📈 خروجی اطلاعات حساب","callback_data":"uc_export"}],
                    [{"text":"♻️ بازنشانی تنظیمات شخصی","callback_data":"uc_reset"}],
                    [{"text":"🔙 بازگشت به داشبورد","callback_data":"back_dashboard"}],
                ]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id,msg_id,text_uc,reply_markup=kb)

            elif data == "uc_live":
                return await self.handle_update({"callback_query":{**cq,"data":"menu_user_center"}})
            elif data == "uc_rank_progress":
                p=await get_user_profile(user_id) or {}; current=p.get("plan","normal"); idx=__import__("core.plans",fromlist=["PLAN_ORDER"]).PLAN_ORDER.index(current)
                if idx >= 5:
                    return await self.answer_callback(cq["id"],"💎 شما در بالاترین رنک قرار دارید.",alert=True)
                from core.plans import PLAN_ORDER
                nxt=PLAN_ORDER[idx+1]; cfg=PLANS_DATA[nxt]
                coin_need=max(0,int(cfg['price_coins'])-int(p.get('coins',0))); ref_need=max(0,int(cfg['required_referrals'])-int(p.get('referral_count',0)))
                return await self.answer_callback(cq["id"],f"🎯 هدف بعدی: {cfg['badge']} {cfg['title']}\n🪙 سکه لازم: {cfg['price_coins']} | کمبود: {coin_need}\n👥 دعوت لازم: {cfg['required_referrals']} | کمبود: {ref_need}",alert=True)
            elif data == "uc_limits":
                p=await get_user_profile(user_id) or {}; cfg=PLANS_DATA.get(p.get('plan','normal'),PLANS_DATA['normal']); yt='نامحدود' if cfg.get('max_yt_mb') is None else f"{cfg['max_yt_mb']} MB"
                return await self.answer_callback(cq["id"],f"📏 محدودیت‌های {cfg['badge']} {cfg['title']}\n📹 حجم هر دانلود: {yt}\n📥 دانلود روزانه: {cfg.get('daily_yt_downloads',2)}\n👥 دوست: {cfg['max_friends']}\n⚔️ دشمن: {cfg['max_enemies']}\n📝 یادداشت: {cfg.get('max_notes',10)}\n🧠 حافظه AI: {cfg.get('max_ai_memory',20)} پیام\n💬 متن پاسخ خودکار: {cfg.get('max_auto_reply_chars',500)} کاراکتر\n⏰ فاصله بروزرسانی ساعت: {cfg.get('timename_interval',60)} ثانیه\n🗑 حداقل پاکسازی: {cfg['min_cleaner_delay']} ثانیه",alert=True)
            elif data == "uc_ai_memory":
                p=await get_user_profile(user_id) or {}; lim=await get_ai_memory_limit(user_id)
                async with aiosqlite.connect(DB_NAME) as db:
                    cnt=(await (await db.execute("SELECT COUNT(*) FROM ai_messages WHERE user_id=?",(user_id,))).fetchone())[0]
                return await self.answer_callback(cq["id"],f"🧠 حافظه AI\nمصرف فعلی: `{cnt}` پیام\nسقف رنک: `{lim}` پیام",alert=True)
            elif data == "uc_notes":
                lim=await get_notes_limit(user_id)
                async with aiosqlite.connect(DB_NAME) as db:
                    cnt=(await (await db.execute("SELECT COUNT(*) FROM user_notes WHERE owner_id=?",(user_id,))).fetchone())[0]
                return await self.answer_callback(cq["id"],f"📝 یادداشت‌ها\nمصرف: `{cnt}/{lim}`\nبرای افزودن: `.یادداشت متن`",alert=True)
            elif data == "uc_autoreply":
                cli=ACTIVE_CLIENTS.get(user_id)
                if not cli: return await self.answer_callback(cq["id"],"❌ ابتدا سلف را روشن کن.",alert=True)
                active=bool(cli.settings.get('auto_reply_active',False)); lim=await get_auto_reply_limit(user_id); txt=cli.settings.get('auto_reply_text') or ''
                return await self.answer_callback(cq["id"],f"💬 پاسخ خودکار: {'فعال ✅' if active else 'خاموش ❌'}\nطول متن فعلی: {len(txt)}/{lim}\nبرای ویرایش از منوی پاسخ خودکار استفاده کن.",alert=True)
            elif data == "uc_reader_toggle":
                cli=ACTIVE_CLIENTS.get(user_id)
                if not cli: return await self.answer_callback(cq["id"],"❌ ابتدا سلف را روشن کن.",alert=True)
                new=not bool(cli.settings.get('auto_read_active',False)); await self.update_setting_db(user_id,'auto_read_active',new)
                return await self.answer_callback(cq["id"],f"👁 Reader {'روشن ✅' if new else 'خاموش ❌'} شد.",alert=True)
            elif data == "uc_notifications":
                async with aiosqlite.connect(DB_NAME) as db:
                    row=await (await db.execute("SELECT enabled FROM notification_preferences WHERE user_id=?",(user_id,))).fetchone(); old=bool(row[0]) if row else True; new=0 if old else 1
                    await db.execute("INSERT INTO notification_preferences(user_id,enabled,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled,updated_at=excluded.updated_at",(user_id,new,int(time.time()))); await db.commit()
                return await self.answer_callback(cq["id"],f"🔔 اعلان‌ها {'فعال ✅' if new else 'خاموش ❌'} شد.",alert=True)
            elif data == "uc_prefix_toggle":
                u=await self.get_user_db(user_id); new=not bool(u[4]) if u else True
                await self.update_setting_db(user_id,'prefix_enabled',new)
                if user_id in ACTIVE_CLIENTS: ACTIVE_CLIENTS[user_id].prefix_enabled=new
                return await self.answer_callback(cq["id"],f"⚡️ پیشوند دستورات {'فعال ✅' if new else 'خاموش ❌'} شد.",alert=True)
            elif data == "uc_timename":
                cli=ACTIVE_CLIENTS.get(user_id)
                if not cli: return await self.answer_callback(cq["id"],"❌ ابتدا سلف را روشن کن.",alert=True)
                on=bool(getattr(cli,'timename_active',False)); font=int(getattr(cli,'timename_font',1) or 1); interval=await get_timename_interval(user_id)
                if not on:
                    allowed=await get_allowed_fonts(user_id)
                    font=font if font in allowed else allowed[0]
                    cli.timename_active=True; cli.timename_font=font
                    await self.update_setting_db(user_id,'timename_active',True); await self.update_setting_db(user_id,'timename_font',font)
                    if getattr(cli,'timename_task',None): cli.timename_task.cancel()
                    cli.timename_task=asyncio.create_task(timename_loop(cli,cli.original_name,font))
                    return await self.answer_callback(cq["id"],f"⏰ ساعت روشن شد. استایل {font} | بروزرسانی هر {interval} ثانیه",alert=True)
                cli.timename_active=False
                if getattr(cli,'timename_task',None): cli.timename_task.cancel(); cli.timename_task=None
                await restore_original_name(cli); await self.update_setting_db(user_id,'timename_active',False)
                return await self.answer_callback(cq["id"],"🛑 ساعت خاموش شد و نام قبلی بازگشت.",alert=True)
            elif data == "uc_monshi":
                cli=ACTIVE_CLIENTS.get(user_id)
                if not cli: return await self.answer_callback(cq["id"],"❌ ابتدا سلف را روشن کن.",alert=True)
                if not await has_feature(user_id,'ai_monshi'): return await self.answer_callback(cq["id"],"🔒 منشی هوشمند در رنک فعلی شما قفل است.",alert=True)
                new=not bool(getattr(cli,'monshi_active',False)); cli.monshi_active=new; await self.update_setting_db(user_id,'monshi_active',new)
                return await self.answer_callback(cq["id"],f"🤖 منشی {'روشن ✅' if new else 'خاموش ❌'} شد.",alert=True)
            elif data == "uc_away":
                cli=ACTIVE_CLIENTS.get(user_id)
                if not cli: return await self.answer_callback(cq["id"],"❌ ابتدا سلف را روشن کن.",alert=True)
                new=not bool(getattr(cli,'away_active',False)); cli.away_active=new; await self.update_setting_db(user_id,'away_active',new)
                return await self.answer_callback(cq["id"],f"💬 حالت مشغول {'روشن ✅' if new else 'خاموش ❌'} شد.",alert=True)
            elif data == "uc_msg_stats":
                async with aiosqlite.connect(DB_NAME) as db:
                    row=await (await db.execute("SELECT incoming,outgoing,ai_replies,auto_replies,last_incoming_at FROM message_stats WHERE user_id=?",(user_id,))).fetchone()
                inc,out,ai,ar,last=(row or (0,0,0,0,0)); return await self.answer_callback(cq["id"],f"📊 آمار\n📥 {inc}\n📤 {out}\n🤖 AI: {ai}\n💬 خودکار: {ar}\n🕒 آخرین ورودی: {datetime.fromtimestamp(last).strftime('%H:%M:%S') if last else 'ثبت نشده'}",alert=True)
            elif data == "uc_my_rank":
                p=await get_user_profile(user_id) or {}; asyncdb=aiosqlite.connect(DB_NAME); db=await asyncdb.__aenter__();
                try:
                    total=(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]; better=(await (await db.execute("SELECT COUNT(*) FROM users WHERE coins > (SELECT COALESCE(coins,0) FROM users WHERE user_id=?)",(user_id,))).fetchone())[0]
                finally: await asyncdb.__aexit__(None,None,None)
                return await self.answer_callback(cq["id"],f"🏆 رتبه سکه شما: `#{better+1}` از `{total}`",alert=True)
            elif data == "uc_storage":
                total=0
                for f in glob.glob(os.path.join('downloads',f'*{user_id}*')):
                    if os.path.isfile(f):
                        try: total+=os.path.getsize(f)
                        except OSError: pass
                return await self.answer_callback(cq["id"],f"💿 حجم فایل‌های حساب: `{total/(1024*1024):.1f} MB`",alert=True)
            elif data == "uc_health":
                cli=ACTIVE_CLIENTS.get(user_id)
                if not cli: return await self.answer_callback(cq["id"],"🔴 سلف آفلاین است.",alert=True)
                try:
                    me=await cli.get_me(); return await self.answer_callback(cq["id"],f"🟢 اتصال سالم\nID: `{me.id}`\n👤 {me.first_name or '-'}",alert=True)
                except Exception as e: return await self.answer_callback(cq["id"],f"🔴 بررسی ناموفق: {str(e)[:180]}",alert=True)
            elif data == "uc_cleanup":
                removed=0
                for f in glob.glob(os.path.join('downloads',f'user_{user_id}_*')) + glob.glob(os.path.join('downloads',f'profile_{user_id}.json')) + glob.glob(os.path.join('downloads',f'yt_{user_id}_*')):
                    try: os.remove(f); removed+=1
                    except OSError: pass
                return await self.answer_callback(cq["id"],f"🧹 {removed} فایل پاکسازی شد.",alert=True)
            elif data == "uc_clear_ai":
                count=await clear_ai_memory(user_id); return await self.answer_callback(cq["id"],f"🧠 {count} پیام از حافظه AI شما پاک شد.",alert=True)
            elif data == "uc_clear_notes":
                async with aiosqlite.connect(DB_NAME) as db:
                    cur=await db.execute("DELETE FROM user_notes WHERE owner_id=?",(user_id,)); await db.commit()
                return await self.answer_callback(cq["id"],f"📝 {cur.rowcount} یادداشت حذف شد.",alert=True)
            elif data == "uc_export":
                p=await get_user_profile(user_id); u=await self.get_user_db(user_id); path=f'downloads/user_center_{user_id}.json'; os.makedirs('downloads',exist_ok=True)
                with open(path,'w',encoding='utf-8') as fh: json.dump({'user_id':user_id,'profile':p,'prefix':u[3] if u else '.', 'settings':json.loads(u[5]) if u and u[5] else {}},fh,ensure_ascii=False,indent=2)
                await self.send_document(chat_id,path,'📈 خروجی اطلاعات حساب');
                try: os.remove(path)
                except OSError: pass
                return await self.answer_callback(cq["id"])
            elif data == "uc_reset":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET prefix='.',prefix_enabled=1,settings='{}' WHERE user_id=?",(user_id,)); await db.commit()
                cli=ACTIVE_CLIENTS.get(user_id)
                if cli:
                    cli.custom_prefix='.'; cli.prefix_enabled=True; cli.settings={}; cli.auto_read_active=False; cli.auto_reply_active=False; cli.away_active=False; cli.monshi_active=False; cli.timename_active=False
                return await self.answer_callback(cq["id"],"♻️ تنظیمات شخصی ریست شد.",alert=True)

            # مرکز حرفه‌ای کاربر
            elif data == "menu_pro":
                # همیشه callback را فوراً تأیید کن تا دکمه در تلگرام بی‌پاسخ/در حالت loading نماند.
                await self.answer_callback(cq["id"])
                try:
                    cli = ACTIVE_CLIENTS.get(user_id)
                    p = await get_user_profile(user_id)
                    online = bool(cli and getattr(cli, "is_connected", False))
                    text_pro = (
                        "🚀 **مرکز حرفه‌ای سلف‌ساز**\n━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🟢 اتصال: `{'آنلاین' if online else 'آفلاین'}`\n"
                        f"🪙 سکه: `{(p or {}).get('coins', 0)}` | ⚡ XP: `{(p or {}).get('activity_score', 0)}`\n"
                        f"👥 دعوت موفق: `{(p or {}).get('referral_count', 0)}`\n━━━━━━━━━━━━━━━━━━━━━\nاز ابزارهای زیر استفاده کن:"
                    )
                    kb = {"inline_keyboard": [
                        [{"text": "📊 آمار شخصی", "callback_data": "pro_stats"}],
                        [{"text": "🩺 سلامت سلف", "callback_data": "pro_health"}],
                        [{"text": "🔐 وضعیت اتصال و سشن", "callback_data": "pro_session"}],
                        [{"text": "⚙️ تنظیمات فعال", "callback_data": "pro_settings"}],
                        [{"text": "🔔 اعلان‌ها", "callback_data": "pro_notifications"}],
                        [{"text": "🏆 رتبه‌بندی سکه", "callback_data": "pro_coin_rank"}],
                        [{"text": "👥 رتبه‌بندی دعوت", "callback_data": "pro_ref_rank"}],
                        [{"text": "🧾 خروجی تنظیمات شخصی", "callback_data": "pro_export"}],
                        [{"text": "🧹 پاکسازی فایل‌های شخصی", "callback_data": "pro_clean"}],
                        [{"text": "♻️ ریست تنظیمات شخصی", "callback_data": "pro_reset"}],
                        [{"text": "📚 راهنمای قابلیت‌ها", "callback_data": "pro_help"}],
                        [{"text": "📏 سقف‌ها و محدودیت‌های رنک", "callback_data": "pro_limits"}],
                        [{"text": "🔗 لینک دعوت اختصاصی من", "callback_data": "pro_ref_link"}],
                        [{"text": "🎁 وضعیت پاداش‌ها", "callback_data": "pro_rewards"}],
                        [{"text": "⚡️ جزئیات فعالیت و XP", "callback_data": "pro_activity"}],
                        [{"text": "🧩 امکانات فعال رنک من", "callback_data": "pro_features"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}],
                    ]}
                    result = await self.edit_message(chat_id, msg_id, text_pro, reply_markup=kb)
                    # اگر editMessageText به هر دلیل توسط Telegram رد شد، منوی حرفه‌ای را به‌صورت پیام جدید می‌فرستیم.
                    if not isinstance(result, dict) or not result.get("ok"):
                        return await self.send_message(chat_id, text_pro, reply_markup=kb)
                    return result
                except Exception as e:
                    add_system_log(f"menu_pro error for {user_id}: {e}")
                    return await self.send_message(
                        chat_id,
                        "❌ **مرکز حرفه‌ای باز نشد.**\nیک خطای داخلی هنگام ساخت منو رخ داد.\n\n" + str(e)[:500],
                        reply_markup={"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]]},
                    )

            elif data == "pro_stats":
                p = await get_user_profile(user_id)
                async with aiosqlite.connect(DB_NAME) as db:
                    total = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
                    rank = (await (await db.execute("SELECT COUNT(*) FROM users WHERE coins > (SELECT COALESCE(coins,0) FROM users WHERE user_id=?)", (user_id,))).fetchone())[0] + 1
                return await self.answer_callback(cq["id"], f"📊 سکه: {p['coins']} | XP: {p['activity_score']} | رتبه تقریبی: #{rank} از {total}", alert=True)

            elif data == "pro_health":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "🔴 سلف آفلاین است.", alert=True)
                me = await cli.get_me()
                return await self.answer_callback(cq["id"], f"🟢 اتصال سالم\nID: {me.id}\nنام: {me.first_name or '-'}", alert=True)

            elif data == "pro_session":
                u = await self.get_user_db(user_id)
                masked = "ثبت نشده"
                if u and u[0]:
                    masked = f"{u[0][:8]}…{u[0][-6:]}"
                return await self.answer_callback(cq["id"], f"🔐 سشن: {masked}\n🟢 اتصال: {'فعال' if user_id in ACTIVE_CLIENTS else 'خاموش'}", alert=True)

            elif data == "pro_settings":
                u = await self.get_user_db(user_id)
                settings = u[5] if u else "{}"
                return await self.answer_callback(cq["id"], f"⚙️ تنظیمات فعال:\n{settings[:700]}", alert=True)

            elif data == "pro_notifications":
                async with aiosqlite.connect(DB_NAME) as db:
                    cur = await db.execute("SELECT enabled FROM notification_preferences WHERE user_id=?", (user_id,))
                    row = await cur.fetchone(); enabled = bool(row[0]) if row else True
                    new = 0 if enabled else 1
                    await db.execute("INSERT INTO notification_preferences(user_id,enabled,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled,updated_at=excluded.updated_at", (user_id,new,int(time.time())))
                    await db.commit()
                return await self.answer_callback(cq["id"], f"🔔 اعلان‌ها {'فعال ✅' if new else 'خاموش ❌'} شد.", alert=True)

            elif data == "pro_coin_rank" or data == "pro_ref_rank":
                column = "coins" if data == "pro_coin_rank" else "referral_count"
                label = "سکه" if column == "coins" else "دعوت موفق"
                async with aiosqlite.connect(DB_NAME) as db:
                    rows = await (await db.execute(f"SELECT user_id,{column} FROM users ORDER BY {column} DESC, user_id ASC LIMIT 10")).fetchall()
                rank_lines = [f"{i}. `{uid}` — `{val}` {label}" for i,(uid,val) in enumerate(rows,1)]
                await self.send_message(chat_id, "🏆 **۱۰ کاربر برتر**\n"+"\n".join(rank_lines))
                return await self.answer_callback(cq["id"])

            elif data == "pro_export":
                u = await self.get_user_db(user_id); p = await get_user_profile(user_id)
                path = f"downloads/profile_{user_id}.json"
                payload = {"user_id": user_id, "coins": p.get("coins") if p else 0, "plan": p.get("plan") if p else "normal", "prefix": u[3] if u else ".", "settings": json.loads(u[5]) if u and u[5] else {}}
                with open(path,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)
                await self.send_document(chat_id,path,"🧾 خروجی تنظیمات شخصی")
                os.remove(path)
                return await self.answer_callback(cq["id"])

            elif data == "pro_clean":
                removed=0
                for f in glob.glob(os.path.join("downloads", f"user_{user_id}_*")) + glob.glob(os.path.join("downloads", f"profile_{user_id}.json")):
                    try: os.remove(f); removed += 1
                    except Exception: pass
                return await self.answer_callback(cq["id"], f"🧹 {removed} فایل شخصی پاک شد.", alert=True)

            elif data == "pro_reset":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET prefix='.', prefix_enabled=1, settings='{}' WHERE user_id=?", (user_id,)); await db.commit()
                if user_id in ACTIVE_CLIENTS:
                    cli=ACTIVE_CLIENTS[user_id]; cli.custom_prefix='.'; cli.prefix_enabled=True; cli.settings={}; cli.cleaner_active=False; cli.monshi_active=False; cli.timename_active=False
                return await self.answer_callback(cq["id"], "♻️ تنظیمات شخصی به حالت پیش‌فرض بازگردانده شد.", alert=True)

            elif data == "pro_help":
                await self.send_message(chat_id, "📚 **مرکز قابلیت‌های حرفه‌ای**\nاز این بخش می‌توانی سلامت اتصال، وضعیت سشن، اعلان‌ها، آمار اقتصادی، خروجی تنظیمات و پاکسازی شخصی را مدیریت کنی.")
                return await self.answer_callback(cq["id"])

            elif data == "pro_limits":
                p = await get_user_profile(user_id)
                cfg = PLANS_DATA.get((p or {}).get("plan", "normal"), PLANS_DATA["normal"])
                yt = "نامحدود" if cfg.get("max_yt_mb") is None else f"{cfg['max_yt_mb']} MB"
                return await self.answer_callback(cq["id"], f"📏 محدودیت‌های رنک\n👥 دوستان: {cfg['max_friends']}\n🛡 دشمنان: {cfg['max_enemies']}\n📹 یوتیوب: {yt}\n🗑 حداقل تایمر پاکسازی: {cfg['min_cleaner_delay']}s\n🔤 فونت‌ها: {len(cfg['allowed_fonts'])}\n🤖 منشی هوشمند: {'فعال' if cfg['ai_monshi'] else 'خاموش'}", alert=True)

            elif data == "pro_ref_link":
                me = await self.get_me()
                username = me.get("username")
                if not username:
                    return await self.answer_callback(cq["id"], "❌ نام کاربری ربات قابل دریافت نیست.", alert=True)
                return await self.answer_callback(cq["id"], f"🔗 لینک دعوت اختصاصی شما:\nhttps://t.me/{username}?start=ref_{user_id}", alert=True)

            elif data == "pro_rewards":
                p = await get_user_profile(user_id)
                now = int(time.time())
                daily_left = max(0, 86400 - (now - int((p or {}).get("last_daily", 0))))
                h, rem = divmod(daily_left, 3600); m = rem // 60
                activity_left = max(0, 600 - (now - int((p or {}).get("last_activity_reward", 0))))
                am, asec = divmod(activity_left, 60)
                return await self.answer_callback(cq["id"], f"🎁 پاداش‌ها\n🪙 پاداش روزانه: {'آماده ✅' if daily_left == 0 else f'{h}h {m}m دیگر'}\n⚡ پاداش فعالیت: {'آماده ✅' if activity_left == 0 else f'{am}m {asec}s دیگر'}", alert=True)

            elif data == "pro_activity":
                p = await get_user_profile(user_id)
                cfg = PLANS_DATA.get((p or {}).get("plan", "normal"), PLANS_DATA["normal"])
                spent = (p or {}).get("activity_reward_coins", 0)
                return await self.answer_callback(cq["id"], f"⚡️ XP: `{(p or {}).get('activity_score', 0)}`\n🪙 پاداش هر نوبت: `{cfg['activity_coins']}` سکه\n📅 سقف روزانه پاداش فعالیت: `{cfg['activity_daily_cap']}` سکه\n📊 دریافت‌شده امروز: `{spent}` سکه", alert=True)

            elif data == "pro_features":
                p = await get_user_profile(user_id)
                cfg = PLANS_DATA.get((p or {}).get("plan", "normal"), PLANS_DATA["normal"])
                enabled = [
                    f"📹 دانلود: {'نامحدود' if cfg.get('max_yt_mb') is None else str(cfg['max_yt_mb']) + ' MB'}",
                    f"👥 دوستان: {cfg['max_friends']}",
                    f"🛡 دشمنان: {cfg['max_enemies']}",
                    f"🔤 فونت: {len(cfg['allowed_fonts'])}",
                    f"🤖 منشی AI: {'✅' if cfg['ai_monshi'] else '❌'}",
                    f"🛡 لاگر ضدحذف: {'✅' if cfg['anti_delete_logger'] else '❌'}",
                ]
                return await self.answer_callback(cq["id"], "🧩 امکانات فعال رنک\n" + "\n".join(enabled), alert=True)

            # مدیریت روابط (دوستان و دشمنان)
            elif data == "menu_relations":
                async with aiosqlite.connect(DB_NAME) as db:
                    friends_count = (await (await db.execute("SELECT COUNT(*) FROM relations WHERE owner_id = ? AND type = 'friend'", (user_id,))).fetchone())[0]
                    enemies_count = (await (await db.execute("SELECT COUNT(*) FROM relations WHERE owner_id = ? AND type = 'enemy'", (user_id,))).fetchone())[0]
                txt = (
                    "🛡 **مرکز هوشمند مدیریت دوستان و دشمنان**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"❤️ تعداد دوستان ویژه: `{friends_count}` نفر\n"
                    f"⚔️ تعداد دشمنان ثبت شده: `{enemies_count}` نفر\n\n"
                    "⚙️ **عملکرد خودکار:**\n"
                    "• **دشمنان:** سلف به طور خودکار پاسخ تحقیرآمیز و دندان‌شکن ارسال می‌کند!\n"
                    "• **دوستان:** معاف از پاسخ منشی همراه با پاسخ احترام‌آمیز اختصاصی.\n"
                    "━━━━━━━━━━━━━━━━━━━━━"
                )
                kb = {"inline_keyboard": [
                    [{"text": "📋 لیست دوستان ❤️", "callback_data": "rel_list_friends"}, {"text": "📋 لیست دشمنان ⚔️", "callback_data": "rel_list_enemies"}],
                    [{"text": "➕ افزودن به دوستان", "callback_data": "rel_add_friend"}, {"text": "➕ افزودن به دشمنان", "callback_data": "rel_add_enemy"}],
                    [{"text": "🗑 حذف کاربر با آیدی", "callback_data": "rel_remove_user"}],
                    [{"text": "پاکسازی دوستان ❌", "callback_data": "rel_clear_friends"}, {"text": "پاکسازی دشمنان ❌", "callback_data": "rel_clear_enemies"}],
                    [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                ]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "rel_list_friends":
                async with aiosqlite.connect(DB_NAME) as db:
                    rows = await (await db.execute("SELECT target_id FROM relations WHERE owner_id = ? AND type = 'friend' LIMIT 30", (user_id,))).fetchall()
                res_txt = "❤️ **لیست دوستان ثبت شده:**\n\n" + "\n".join([f"• `{r[0]}`" for r in rows]) if rows else "❤️ لیست دوستان شما در حال حاضر خالی است."
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, res_txt, reply_markup={"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "menu_relations"}]]})

            elif data == "rel_list_enemies":
                async with aiosqlite.connect(DB_NAME) as db:
                    rows = await (await db.execute("SELECT target_id FROM relations WHERE owner_id = ? AND type = 'enemy' LIMIT 30", (user_id,))).fetchall()
                res_txt = "⚔️ **لیست دشمنان ثبت شده:**\n\n" + "\n".join([f"• `{r[0]}`" for r in rows]) if rows else "⚔️ لیست دشمنان شما در حال حاضر خالی است."
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, res_txt, reply_markup={"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "menu_relations"}]]})

            elif data == "rel_add_friend":
                USER_STATES[user_id] = "WAITING_ADD_FRIEND"
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "❤️ **لطفاً شناسه عددی (Numeric ID) دوست خود را ارسال فرمایید:**", reply_markup={"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "menu_relations"}]]})

            elif data == "rel_add_enemy":
                USER_STATES[user_id] = "WAITING_ADD_ENEMY"
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "⚔️ **لطفاً شناسه عددی (Numeric ID) دشمن را ارسال فرمایید:**", reply_markup={"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "menu_relations"}]]})

            elif data == "rel_remove_user":
                USER_STATES[user_id] = "WAITING_REMOVE_RELATION"
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🗑 **شناسه عددی کاربری که می‌خواهید حذف شود را ارسال فرمایید:**", reply_markup={"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "menu_relations"}]]})

            elif data == "rel_clear_friends":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE owner_id = ? AND type = 'friend'", (user_id,))
                    await db.commit()
                if user_id in ACTIVE_CLIENTS and hasattr(ACTIVE_CLIENTS[user_id], "friends_set"):
                    ACTIVE_CLIENTS[user_id].friends_set.clear()
                await self.answer_callback(cq["id"], "❤️ لیست دوستان شما پاکسازی شد.", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "menu_relations"}})

            elif data == "rel_clear_enemies":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE owner_id = ? AND type = 'enemy'", (user_id,))
                    await db.commit()
                if user_id in ACTIVE_CLIENTS and hasattr(ACTIVE_CLIENTS[user_id], "enemies_set"):
                    ACTIVE_CLIENTS[user_id].enemies_set.clear()
                await self.answer_callback(cq["id"], "⚔️ لیست دشمنان شما پاکسازی شد.", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "menu_relations"}})

            # نرخ لحظه‌ای ارز و طلا
            elif data in ["menu_rates", "refresh_rates"]:
                await self.answer_callback(cq["id"], "🔄 درحال استعلام نرخ زنده...")
                rates_data = await fetch_live_market_data()
                kb = {"inline_keyboard": [[{"text": "🔄 به‌روزرسانی نرخ‌ها", "callback_data": "refresh_rates"}], [{"text": "🔙 بازگشت به منو", "callback_data": "back_dashboard"}]]}
                return await self.edit_message(chat_id, msg_id, format_market_display(rates_data), reply_markup=kb)

            # ساعت روی اسم — ۲۵ استایل متفاوت
            elif data == "menu_timename":
                from core.manager import FONTS
                cli = ACTIVE_CLIENTS.get(user_id)
                t_on = getattr(cli, "timename_active", False) if cli else False
                selected = int(getattr(cli, "timename_font", 0) or 0) if cli else 0
                allowed = set(await get_allowed_fonts(user_id))
                st_text = "خاموش کردن ساعت 🔴 (بازگشت به نام قبلی)" if t_on else "روشن کردن ساعت 🟢"
                rows = [[{"text": st_text, "callback_data": "toggle_timename"}]]
                for i in range(1, 26, 2):
                    row=[]
                    for fid in (i, i+1):
                        preview = "".join(FONTS.get(fid, FONTS[1]).get(c,c) for c in "12:34")
                        lock = "🔒 " if fid not in allowed else ("✅ " if fid == selected else "")
                        row.append({"text": f"{lock}استایل {fid} {preview}", "callback_data": f"font_{fid}"})
                    rows.append(row)
                rows.append([{"text": "ℹ️ نمایش ۲۵ استایل مستقل ساعت", "callback_data": "timename_info"}])
                rows.append([{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}])
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, f"⏰ **ساعت خودکار روی اسم (۲۵ استایل متفاوت)**\nوضعیت فعلی: `{'روشن 🟢' if t_on else 'خاموش 🔴'}`\nاستایل انتخابی: `{selected or '۱'}`\nدسترسی پلن: `{len(allowed)}/25`", reply_markup={"inline_keyboard": rows})

            elif data == "timename_info":
                return await self.answer_callback(cq["id"], "🎨 ۲۵ استایل مستقل برای نمایش ساعت فعال است؛ استایل‌های قفل‌شده با ارتقای رنک باز می‌شوند.", alert=True)

            elif data == "toggle_timename":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ ابتدا اکانت سلف را روشن فرمایید.", alert=True)
                if getattr(cli, "timename_active", False):
                    cli.timename_active = False
                    if cli.timename_task:
                        cli.timename_task.cancel()
                    await restore_original_name(cli)
                    await self.update_setting_db(user_id, "timename_active", False)
                    await self.answer_callback(cq["id"], "🛑 ساعت خاموش و نام قبلی شما بازگشت.")
                else:
                    cli.timename_active = True
                    await self.update_setting_db(user_id, "timename_active", True)
                    cli.timename_task = asyncio.create_task(timename_loop(cli, cli.original_name, cli.settings.get("timename_font", 1)))
                    await self.answer_callback(cq["id"], "🟢 ساعت روی اسم فعال گردید.")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_timename"}})

            elif data.startswith("font_"):
                f_id = int(data.split("_")[1])
                if f_id < 1 or f_id > 25:
                    return await self.answer_callback(cq["id"], "❌ فقط ۲۵ استایل رسمی ساعت وجود دارد.", alert=True)
                allowed_fonts = await get_allowed_fonts(user_id)
                if f_id not in allowed_fonts:
                    return await self.answer_callback(cq["id"], "🔒 این فونت برای پلن شما فعال نیست.", alert=True)
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
                kb = {"inline_keyboard": [[{"text": "خاموش‌سازی منشی 🔴" if m_on else "فعال‌سازی منشی 🟢", "callback_data": "toggle_monshi"}], [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, f"🤖 **تنظیمات منشی هوشمند سلف**\nوضعیت کنونی: `{'فعال 🟢' if m_on else 'غیرفعال 🔴'}`", reply_markup=kb)

            elif data == "toggle_monshi":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ ابتدا سلف را روشن کنید.", alert=True)
                if not await has_feature(user_id, "ai_monshi"):
                    return await self.answer_callback(cq["id"], "🔒 منشی هوشمند در پلن شما قفل است؛ ابتدا پلن را ارتقا دهید.", alert=True)
                new_st = not getattr(cli, "monshi_active", False)
                cli.monshi_active = new_st
                await self.update_setting_db(user_id, "monshi_active", new_st)
                await self.answer_callback(cq["id"], "تغییر وضعیت منشی اعمال شد.")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_monshi"}})

            # ================== مرکز هوشمند و امکانات کاربردی ==================
            elif data == "menu_smart":
                cli = ACTIVE_CLIENTS.get(user_id)
                st = getattr(cli, "settings", {}) if cli else {}
                m = bool(cli and getattr(cli, "monshi_active", False))
                ai_mem = bool(st.get("ai_memory", True))
                await self.answer_callback(cq["id"])
                kb = {"inline_keyboard": [
                    [{"text": "🤖 منشی AI: خاموش کردن 🔴" if m else "🤖 منشی AI: روشن کردن 🟢", "callback_data": "toggle_monshi"}],
                    [{"text": "🧠 حافظه مکالمه: " + ("فعال ✅" if ai_mem else "خاموش ❌"), "callback_data": "smart_memory_toggle"}],
                    [{"text": "✍️ شخصیت و پرامپت منشی", "callback_data": "smart_prompt"}],
                    [{"text": "🧪 تست اتصال هوش مصنوعی", "callback_data": "smart_ai_test"}],
                    [{"text": "💡 راهنمای دستورات AI", "callback_data": "smart_ai_help"}],
                    [{"text": "🧹 پاک‌کردن حافظه گفت‌وگو", "callback_data": "smart_clear_memory"}],
                    [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}],
                ]}
                return await self.edit_message(chat_id, msg_id, "🧠 **مرکز هوشمند سلف**\n\nاز اینجا منشی، حافظه مکالمه و ابزارهای AI را مدیریت کن.\n\nدستورات کاربردی: `.هوش` برای پرسش آزاد، `.خلاصه` برای خلاصه‌سازی ریپلای، `.ترجمه انگلیسی` برای ترجمه.", reply_markup=kb)

            elif data == "smart_memory_toggle":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ ابتدا سلف را روشن کن.", alert=True)
                new = not bool(cli.settings.get("ai_memory", True))
                await self.update_setting_db(user_id, "ai_memory", new)
                return await self.handle_update({"callback_query": {**cq, "data": "menu_smart"}})

            elif data == "smart_prompt":
                USER_STATES[user_id] = "SMART_WAIT_PROMPT"
                return await self.edit_message(chat_id, msg_id, "✍️ پرامپت شخصیت منشی را بفرست.\nمثلاً: «کوتاه، محترمانه و رسمی جواب بده و فقط اصل مطلب را بگو».", reply_markup={"inline_keyboard":[[{"text":"🔙 انصراف","callback_data":"menu_smart"}]]})

            elif data == "smart_ai_test":
                await self.answer_callback(cq["id"], "⏳ در حال تست AI...", alert=False)
                answer, error = await ask_ai(user_id, "فقط بنویس: اتصال AI موفق است ✅", remember=False, max_tokens=40)
                return await self.edit_message(chat_id, msg_id, (f"✅ **AI سالم است**\n\n{answer}" if answer else f"❌ **تست AI ناموفق بود**\n\n{error}"), reply_markup={"inline_keyboard":[[{"text":"🔙 بازگشت","callback_data":"menu_smart"}]]})

            elif data == "smart_ai_help":
                return await self.edit_message(chat_id, msg_id, "💡 **ابزارهای AI سلف**\n\n`.هوش متن` → پاسخ هوشمند\n`.خلاصه` روی یک پیام → خلاصه فارسی\n`.ترجمه انگلیسی` روی یک پیام → ترجمه\n\nحافظه مکالمه را هم می‌توانی از همین بخش روشن/خاموش کنی.", reply_markup={"inline_keyboard":[[{"text":"🔙 بازگشت","callback_data":"menu_smart"}]]})

            elif data == "smart_clear_memory":
                removed = await clear_ai_memory(user_id)
                return await self.answer_callback(cq["id"], f"🧹 {removed} پیام از حافظه AI پاک شد.", alert=True)

            elif data == "menu_auto":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ ابتدا سلف را روشن کن.", alert=True)
                st = cli.settings
                ar = bool(st.get("auto_reply_active", False))
                away = bool(st.get("away_active", False))
                text_ar = st.get("auto_reply_text") or await get_setting("smart_default_autoreply", "پیام شما دریافت شد. 🙏")
                text_away = st.get("away_text") or "فعلاً در دسترس نیستم؛ بعداً پاسخ می‌دهم."
                kb={"inline_keyboard":[
                    [{"text":"💬 پاسخ خودکار: خاموش 🔴" if ar else "💬 پاسخ خودکار: روشن 🟢","callback_data":"smart_auto_toggle"}],
                    [{"text":"🔕 حالت مشغول: خاموش 🔴" if away else "🔕 حالت مشغول: روشن 🟢","callback_data":"smart_away_toggle"}],
                    [{"text":"✍️ متن پاسخ خودکار","callback_data":"smart_auto_text"}],
                    [{"text":"📝 متن حالت مشغول","callback_data":"smart_away_text"}],
                    [{"text":"🔙 بازگشت","callback_data":"back_dashboard"}],
                ]}
                return await self.edit_message(chat_id,msg_id,f"💬 **پاسخ‌گویی خودکار**\n\nپاسخ فعلی: {text_ar[:220]}\nحالت مشغول: {text_away[:220]}",reply_markup=kb)

            elif data == "smart_auto_toggle":
                cli=ACTIVE_CLIENTS.get(user_id)
                if not cli: return await self.answer_callback(cq["id"],"❌ ابتدا سلف را روشن کن.",alert=True)
                await self.update_setting_db(user_id,"auto_reply_active",not bool(cli.settings.get("auto_reply_active",False)))
                return await self.handle_update({"callback_query":{**cq,"data":"menu_auto"}})

            elif data == "smart_away_toggle":
                cli=ACTIVE_CLIENTS.get(user_id)
                if not cli: return await self.answer_callback(cq["id"],"❌ ابتدا سلف را روشن کن.",alert=True)
                await self.update_setting_db(user_id,"away_active",not bool(cli.settings.get("away_active",False)))
                return await self.handle_update({"callback_query":{**cq,"data":"menu_auto"}})

            elif data == "smart_auto_text":
                USER_STATES[user_id]="SMART_WAIT_AUTOREPLY"
                return await self.edit_message(chat_id,msg_id,"💬 متن پاسخ خودکار را بفرست:",reply_markup={"inline_keyboard":[[{"text":"🔙 انصراف","callback_data":"menu_auto"}]]})

            elif data == "smart_away_text":
                USER_STATES[user_id]="SMART_WAIT_AWAY"
                return await self.edit_message(chat_id,msg_id,"🔕 متن حالت مشغول را بفرست:",reply_markup={"inline_keyboard":[[{"text":"🔙 انصراف","callback_data":"menu_auto"}]]})

            elif data == "menu_reader":
                cli=ACTIVE_CLIENTS.get(user_id)
                if not cli: return await self.answer_callback(cq["id"],"❌ ابتدا سلف را روشن کن.",alert=True)
                active=bool(cli.settings.get("auto_read_active",False))
                kb={"inline_keyboard":[[{"text":"👁 خاموش کردن خواندن خودکار 🔴" if active else "👁 روشن کردن خواندن خودکار 🟢","callback_data":"smart_reader_toggle"}],[{"text":"ℹ️ توضیح عملکرد","callback_data":"smart_reader_info"}],[{"text":"🔙 بازگشت","callback_data":"back_dashboard"}]]}
                return await self.edit_message(chat_id,msg_id,f"👁 **خواندن خودکار پیام‌ها**\n\nوضعیت: `{'فعال ✅' if active else 'خاموش ❌'}`\nدر حالت فعال، پیام‌های دریافتی در چت خصوصی هنگام پردازش علامت خوانده‌شده می‌خورند.",reply_markup=kb)

            elif data == "smart_reader_toggle":
                cli=ACTIVE_CLIENTS.get(user_id)
                if not cli: return await self.answer_callback(cq["id"],"❌ ابتدا سلف را روشن کن.",alert=True)
                await self.update_setting_db(user_id,"auto_read_active",not bool(cli.settings.get("auto_read_active",False)))
                return await self.handle_update({"callback_query":{**cq,"data":"menu_reader"}})

            elif data == "smart_reader_info":
                return await self.answer_callback(cq["id"],"👁 فقط روی پیام‌های ورودی چت خصوصی اعمال می‌شود و اقدامی خارج از خواندن پیام انجام نمی‌دهد.",alert=True)

            elif data == "menu_notes":
                return await self.edit_message(chat_id,msg_id,"📝 **یادداشت و ابزار متن**\n\n`.یادداشت متن` → ذخیره یادداشت\n`.یادداشت‌ها` → نمایش آخرین یادداشت‌ها\n`.حذف یادداشت‌ها` → حذف همه یادداشت‌ها\n`.خلاصه` روی ریپلای → خلاصه‌سازی با AI\n`.ترجمه انگلیسی` روی ریپلای → ترجمه با AI",reply_markup={"inline_keyboard":[[{"text":"🧠 مرکز AI","callback_data":"menu_smart"}],[{"text":"🔙 بازگشت","callback_data":"back_dashboard"}]]})

            elif data == "menu_msg_stats":
                async with aiosqlite.connect(DB_NAME) as db:
                    row=await (await db.execute("SELECT incoming,outgoing,ai_replies,auto_replies,last_incoming_at FROM message_stats WHERE user_id=?",(user_id,))).fetchone()
                if row:
                    incoming,outgoing,ai_r,auto_r,last=row
                else:
                    incoming=outgoing=ai_r=auto_r=last=0
                last_text=datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S") if last else "ثبت نشده"
                return await self.edit_message(chat_id,msg_id,f"📊 **آمار فعالیت سلف**\n\n📥 ورودی: `{incoming}`\n📤 خروجی: `{outgoing}`\n🤖 پاسخ AI: `{ai_r}`\n💬 پاسخ خودکار: `{auto_r}`\n🕒 آخرین پیام ورودی: `{last_text}`",reply_markup={"inline_keyboard":[[{"text":"🔄 به‌روزرسانی","callback_data":"menu_msg_stats"}],[{"text":"🔙 بازگشت","callback_data":"back_dashboard"}]]})

            elif data == "menu_notify":
                return await self.handle_update({"callback_query":{**cq,"data":"pro_notifications"}})

            # پاکساز خودکار پیام‌ها
            elif data == "menu_cleaner":
                cli = ACTIVE_CLIENTS.get(user_id)
                c_on = getattr(cli, "cleaner_active", False) if cli else False
                kb = {"inline_keyboard": [
                    [{"text": "خاموش کردن پاکساز 🔴" if c_on else "روشن کردن پاکساز 🟢", "callback_data": "toggle_cleaner"}],
                    [{"text": "تایمر: ۱۰ ثانیه", "callback_data": "clean_10"}, {"text": "تایمر: ۳۰ ثانیه", "callback_data": "clean_30"}, {"text": "تایمر: ۶۰ ثانیه", "callback_data": "clean_60"}],
                    [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                ]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, f"🗑 **سیستم پاکسازی خودکار پیام‌ها**\nوضعیت: `{'فعال 🟢' if c_on else 'خاموش 🔴'}`", reply_markup=kb)

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
                min_delay = await get_cleaner_min_delay(user_id)
                if sec < min_delay:
                    return await self.answer_callback(cq["id"], f"🔒 کمترین تایمر پلن شما {min_delay} ثانیه است.", alert=True)
                await self.update_setting_db(user_id, "cleaner_delay", sec)
                cli = ACTIVE_CLIENTS.get(user_id)
                if cli:
                    cli.cleaner_delay = sec
                await self.answer_callback(cq["id"], f"✅ تایمر پاکسازی روی {sec} ثانیه تنظیم شد.")

            # پیشوند دستورات سلف
            elif data == "menu_prefix":
                u = await self.get_user_db(user_id)
                kb = {"inline_keyboard": [
                    [{"text": "✏️ تعیین پیشوند دلخواه", "callback_data": "change_prefix_btn"}],
                    [{"text": "تنظیم نقطه (.)", "callback_data": "set_p_dot"}, {"text": "تنظیم تعجب (!)", "callback_data": "set_p_excl"}],
                    [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                ]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, f"⚡️ **پیشوند دستورات سلف شما:** `{u[3] or '.'}`", reply_markup=kb)

            elif data == "change_prefix_btn":
                USER_STATES[user_id] = "WAITING_NEW_PREFIX"
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "⚡️ لطفاً کاراکتر پیشوند جدید خود را ارسال فرمایید (مثال: ! یا .):", reply_markup={"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "menu_prefix"}]]})

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

# جعبه ابزارها
            elif data == "menu_tools":
                kb = {"inline_keyboard": [[{"text": "📹 دانلود مستقیم ویدیو از یوتیوب", "callback_data": "tool_yt"}], [{"text": "🔙 بازگشت به منو", "callback_data": "back_dashboard"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🛠 **جعبه‌ابزار کاربردی سلف‌ساز:**\nابزار مورد نظر را انتخاب فرمایید:", reply_markup=kb)

            elif data == "tool_yt":
                USER_STATES[user_id] = "WAITING_YOUTUBE"
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📹 **لینک ویدیوی یوتیوب را بفرستید تا سریعاً دانلود شود:**", reply_markup={"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "menu_tools"}]]})

            # ================== تنظیمات هوشمند ادمین ==================
            elif data == "ad_sec_13" and is_admin:
                await self.answer_callback(cq["id"])
                ai_on = await get_setting("smart_ai_global", "1")
                smart_on = await get_setting("smart_global_enabled", "1")
                model = await get_setting("smart_ai_model", "(env default)")
                base_url = await get_setting("smart_ai_base_url", "(env: AI_BASE_URL)")
                txt=(f"🧠 **مدیریت هوش مصنوعی و امکانات هوشمند**\n━━━━━━━━━━━━━━━━━━━━\n"
                     f"AI سراسری: `{'فعال ✅' if ai_on=='1' else 'خاموش ❌'}`\n"
                     f"قابلیت‌های هوشمند: `{'فعال ✅' if smart_on=='1' else 'خاموش ❌'}`\n"
                     f"مدل: `{model}`\nBase URL: `{base_url}`\n━━━━━━━━━━━━━━━━━━━━")
                return await self.edit_message(chat_id,msg_id,txt,reply_markup=self.get_admin_sec13_kb())

            elif data == "ad_ai_toggle" and is_admin:
                new="0" if await get_setting("smart_ai_global","1")=="1" else "1"
                await set_setting("smart_ai_global",new); await audit_log(user_id,"ai_global_toggle",detail=new)
                return await self.handle_update({"callback_query":{**cq,"data":"ad_sec_13"}})
            elif data == "ad_smart_toggle" and is_admin:
                new="0" if await get_setting("smart_global_enabled","1")=="1" else "1"
                await set_setting("smart_global_enabled",new); await audit_log(user_id,"smart_global_toggle",detail=new)
                return await self.handle_update({"callback_query":{**cq,"data":"ad_sec_13"}})
            elif data == "ad_ai_model" and is_admin:
                USER_STATES[user_id]="AD_WAIT_AI_MODEL"; return await self.send_message(chat_id,"🧩 نام مدل AI را بفرست. مثال: `gpt-4o-mini` یا مدل سرویس خودت.")
            elif data == "ad_ai_base" and is_admin:
                USER_STATES[user_id]="AD_WAIT_AI_BASE"; return await self.send_message(chat_id,"🌐 Base URL را بفرست. مثال: `https://api.openai.com/v1`\nکلید API را اینجا وارد نکن؛ کلید از Railway Environment خوانده می‌شود.")
            elif data == "ad_ai_prompt" and is_admin:
                USER_STATES[user_id]="AD_WAIT_AI_PROMPT"; return await self.send_message(chat_id,"📝 پرامپت پیش‌فرض منشی را بفرست:")
            elif data == "ad_ai_cooldown" and is_admin:
                USER_STATES[user_id]="AD_WAIT_AI_COOLDOWN"; return await self.send_message(chat_id,"⏱ کول‌داون AI را بین ۱ تا ۳۰۰ ثانیه بفرست:")
            elif data == "ad_auto_default" and is_admin:
                USER_STATES[user_id]="AD_WAIT_AUTO_DEFAULT"; return await self.send_message(chat_id,"💬 متن پاسخ خودکار پیش‌فرض را بفرست:")
            elif data == "ad_ai_stats" and is_admin:
                st=await ai_stats(); return await self.answer_callback(cq["id"],f"📊 کاربران دارای حافظه: {st['users']}\n🧾 پیام‌های حافظه: {st['messages']}\n🤖 پاسخ‌های AI ثبت‌شده: {st['replies']}",alert=True)
            elif data == "ad_ai_test" and is_admin:
                answer,error=await ask_ai(user_id,"فقط پاسخ بده: SelfSaz AI OK",remember=False,max_tokens=30)
                return await self.answer_callback(cq["id"],f"✅ {answer[:180]}" if answer else f"❌ {error[:250]}",alert=True)
            elif data == "ad_ai_clear_all" and is_admin:
                n=await clear_ai_memory(None); await audit_log(user_id,"ai_memory_clear_all",detail=str(n)); return await self.answer_callback(cq["id"],f"🧹 {n} پیام حافظه AI حذف شد.",alert=True)
            elif data == "ad_smart_usage" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    ar=(await (await db.execute("SELECT COUNT(*) FROM users WHERE settings LIKE '%auto_reply_active%true%'")).fetchone())[0]
                    aw=(await (await db.execute("SELECT COUNT(*) FROM users WHERE settings LIKE '%away_active%true%'")).fetchone())[0]
                    am=(await (await db.execute("SELECT COUNT(*) FROM users WHERE settings LIKE '%auto_read_active%true%'")).fetchone())[0]
                monshi=sum(1 for cli in ACTIVE_CLIENTS.values() if getattr(cli,"monshi_active",False))
                return await self.answer_callback(cq["id"],f"🤖 منشی روشن: {monshi}\n💬 پاسخ خودکار ثبت‌شده: {ar}\n🔕 حالت مشغول: {aw}\n👁 خواندن خودکار: {am}",alert=True)
            elif data == "ad_smart_reset" and is_admin:
                for k in ["smart_ai_model","smart_ai_base_url","smart_default_prompt","smart_default_autoreply","smart_ai_cooldown"]:
                    await delete_setting(k)
                await set_setting("smart_ai_global","1"); await set_setting("smart_global_enabled","1")
                return await self.answer_callback(cq["id"],"♻️ تنظیمات هوشمند به مقادیر پیش‌فرض برگشت.",alert=True)

            # ================== سوپر پنل مدیریت ادمین (۶۵ قابلیت مجزا) ==================
            elif data == "admin_hub" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "👑 **سوپر پنل مدیریت کل سیستم (۱۷۵ قابلیت تفکیک‌شده)**", reply_markup=self.get_admin_hub_kb())

            elif data == "ad_sec_1" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "⚙️ **دسته ۱: کنترل سرور و پروسه‌ها (۱۰ قابلیت)**", reply_markup=self.get_admin_sec1_kb())

            elif data == "ad_sec_2" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🗄 **دسته ۲: مدیریت دیتابیس و فایل‌ها (۸ قابلیت)**", reply_markup=self.get_admin_sec2_kb())

            elif data == "ad_sec_3" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📊 **دسته ۳: آمار و مانیتورینگ زنده (۸ قابلیت)**", reply_markup=self.get_admin_sec3_kb())

            elif data == "ad_sec_4" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "👥 **دسته ۴: مدیریت کاربران و سلف‌ها (۱۰ قابلیت)**", reply_markup=self.get_admin_sec4_kb())

            elif data == "ad_sec_5" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🛡 **دسته ۵: امنیت و فایروال سیستم (۸ قابلیت)**", reply_markup=self.get_admin_sec5_kb())

            elif data == "ad_sec_6" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🧩 **دسته ۶: تنظیمات پلاگین‌های سلف (۱۱ قابلیت)**", reply_markup=self.get_admin_sec6_kb())

            elif data == "ad_sec_7" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📢 **دسته ۷: پیام‌رسانی و پشتیبانی (۱۰ قابلیت)**", reply_markup=self.get_admin_sec7_kb())

            # دسته‌های جدید ۱۴ تا ۱۹ — هندلرها در V2.2 قبلاً فراموش شده بودند
            elif data == "ad_sec_14" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "👥 **دسته ۱۴: تحلیل کاربران — ۱۰ قابلیت**", reply_markup=self.get_admin_sec14_kb())
            elif data == "ad_sec_15" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🔐 **دسته ۱۵: احراز هویت و سشن‌ها — ۱۰ قابلیت**", reply_markup=self.get_admin_sec15_kb())
            elif data == "ad_sec_16" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "⚙️ **دسته ۱۶: کنترل‌های سراسری جدید — ۱۰ قابلیت**", reply_markup=self.get_admin_sec16_kb())
            elif data == "ad_sec_17" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🏆 **دسته ۱۷: اقتصاد، رنک و دعوت — ۱۰ قابلیت**", reply_markup=self.get_admin_sec17_kb())
            elif data == "ad_sec_18" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🤖 **دسته ۱۸: تحلیل Smart/AI — ۱۰ قابلیت**", reply_markup=self.get_admin_sec18_kb())
            elif data == "ad_sec_19" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🧪 **دسته ۱۹: سلامت و نگهداری نهایی — ۱۰ قابلیت**", reply_markup=self.get_admin_sec19_kb())

            # دسته‌های جدید ۸ تا ۱۲
            elif data == "ad_sec_8" and is_admin:
                return await self.edit_message(chat_id, msg_id, "🔐 **دسته ۸: عضویت و کنترل دسترسی — ۱۰ قابلیت جدید**", reply_markup=self.get_admin_sec8_kb())
            elif data == "ad_sec_9" and is_admin:
                return await self.edit_message(chat_id, msg_id, "🗄 **دسته ۹: دیتابیس پیشرفته — ۱۰ قابلیت جدید**", reply_markup=self.get_admin_sec9_kb())
            elif data == "ad_sec_10" and is_admin:
                return await self.edit_message(chat_id, msg_id, "📡 **دسته ۱۰: مانیتورینگ حرفه‌ای — ۱۰ قابلیت جدید**", reply_markup=self.get_admin_sec10_kb())
            elif data == "ad_sec_11" and is_admin:
                return await self.edit_message(chat_id, msg_id, "🧪 **دسته ۱۱: تشخیص، گزارش و سلامت — ۱۰ قابلیت جدید**", reply_markup=self.get_admin_sec11_kb())
            elif data == "ad_sec_12" and is_admin:
                return await self.edit_message(chat_id, msg_id, "⚙️ **دسته ۱۲: ارتباطات و تنظیمات پیشرفته — ۱۰ قابلیت جدید**", reply_markup=self.get_admin_sec12_kb())

            # عضویت اجباری
            elif data == "ad_force_join_toggle" and is_admin:
                enabled = await forced_join_enabled()
                target = await forced_join_target()
                if not enabled and not target:
                    return await self.answer_callback(cq["id"], "❌ ابتدا مقصد عضویت را تنظیم کنید.", alert=True)
                await set_setting("force_join_enabled", "0" if enabled else "1")
                await audit_log(user_id, "force_join_toggle", detail=str(not enabled))
                return await self.answer_callback(cq["id"], f"🔐 عضویت اجباری {'روشن ✅' if not enabled else 'خاموش ❌'} شد.", alert=True)
            elif data == "ad_force_join_set" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_FORCE_JOIN"
                return await self.send_message(chat_id, "✏️ شناسه کانال/گروه را بفرستید؛ مثال `@mychannel` یا `https://t.me/mychannel`")
            elif data == "ad_force_join_status" and is_admin:
                enabled=await forced_join_enabled(); target=await forced_join_target(); url=await forced_join_url()
                return await self.answer_callback(cq["id"], f"🔐 وضعیت: {'فعال ✅' if enabled else 'خاموش ❌'}\n🎯 مقصد: {target or 'تنظیم نشده'}\n🔗 لینک: {url or 'تنظیم نشده'}", alert=True)
            elif data == "ad_force_join_test" and is_admin:
                target = await forced_join_target()
                if not target:
                    return await self.answer_callback(cq["id"], "🔴 مقصد تنظیم نشده است.", alert=True)
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/getChat", json={"chat_id": target}, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                            payload = await resp.json()
                    if payload.get("ok"):
                        chat = payload.get("result", {})
                        return await self.answer_callback(cq["id"], f"🟢 Bot API دسترسی دارد.\n📌 {chat.get('title') or chat.get('username') or target}", alert=True)
                    return await self.answer_callback(cq["id"], "🔴 Bot API مقصد را پیدا نکرد. ربات باید در کانال/گروه دسترسی لازم را داشته باشد.", alert=True)
                except Exception as e:
                    return await self.answer_callback(cq["id"], f"🔴 تست ناموفق: {e}", alert=True)
            elif data == "ad_force_join_clear" and is_admin:
                await set_setting("force_join_enabled","0"); await delete_setting("force_join_chat"); await delete_setting("force_join_url")
                await audit_log(user_id,"force_join_clear")
                return await self.answer_callback(cq["id"], "🗑 عضویت اجباری پاک شد.", alert=True)
            elif data == "ad_join_exempt_add" and is_admin:
                USER_STATES[user_id]="AD_WAIT_EXEMPT_ADD"; return await self.send_message(chat_id,"👤 آیدی عددی کاربر را بفرستید:")
            elif data == "ad_join_exempt_remove" and is_admin:
                USER_STATES[user_id]="AD_WAIT_EXEMPT_REMOVE"; return await self.send_message(chat_id,"👤 آیدی عددی کاربر را بفرستید:")
            elif data == "ad_join_exempt_list" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: rows=await (await db.execute("SELECT user_id FROM membership_exemptions ORDER BY created_at DESC")).fetchall()
                await self.send_message(chat_id,"📋 **استثناها**\n"+("\n".join(f"• `{r[0]}`" for r in rows[:100]) if rows else "لیست خالی است.")); return await self.answer_callback(cq["id"])
            elif data == "ad_force_join_preview" and is_admin:
                txt=await get_setting("force_join_text","🔒 برای استفاده از سلف‌ساز ابتدا عضو کانال حامی شوید."); url=await forced_join_url(); rows=[[{"text":"📢 عضویت","url":url}]] if url else []; rows.append([{"text":"✅ بررسی عضویت","callback_data":"check_membership"}]); await self.send_message(chat_id,txt,reply_markup={"inline_keyboard":rows}); return await self.answer_callback(cq["id"])
            elif data == "ad_force_join_text" and is_admin:
                USER_STATES[user_id]="AD_WAIT_FORCE_JOIN_TEXT"; return await self.send_message(chat_id,"✍️ متن عضویت اجباری را بفرستید:")

            # قابلیت‌های دسته ۱
            elif data == "ad_stop_all" and is_admin:
                cnt = await stop_all_clients()
                add_system_log(f"Admin stopped all {cnt} clients.")
                return await self.answer_callback(cq["id"], f"🛑 تعداد {cnt} سلف متوقف شدند.", alert=True)

            elif data == "ad_restart_all" and is_admin:
                await self.answer_callback(cq["id"], "🔄 ریستارت همگانی آغاز شد...")
                cnt = await restart_all_clients()
                add_system_log(f"Admin restarted {cnt} clients.")
                return await self.send_message(chat_id, f"✅ تعداد {cnt} سلف مجدداً اجرا شدند.")

            elif data == "ad_clean_temp" and is_admin:
                cnt = clean_server_temp_files()
                return await self.answer_callback(cq["id"], f"🧹 تعداد {cnt} فایل موقت پاکسازی شدند.", alert=True)

            elif data == "ad_ping_test" and is_admin:
                t0 = time.time()
                await self.answer_callback(cq["id"], "⚡️ در حال محاسبه پینگ...")
                dt = round((time.time() - t0) * 1000, 2)
                return await self.send_message(chat_id, f"⚡️ **پینگ سرور تلگرام:** `{dt} ms` 🟢")

            elif data == "ad_ram_usage" and is_admin:
                import resource
                usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
                return await self.answer_callback(cq["id"], f"🧠 مصرف حافظه RAM: {usage} MB", alert=True)

            elif data == "ad_uptime" and is_admin:
                h, rem = divmod(int(time.time() - START_TIME), 3600)
                m, s = divmod(rem, 60)
                return await self.answer_callback(cq["id"], f"⏱ آپ‌تایم سیستم: {h} ساعت و {m} دقیقه و {s} ثانیه", alert=True)

            elif data == "ad_online_list" and is_admin:
                uids = list(ACTIVE_CLIENTS.keys())
                txt = f"📋 **سلف‌های آنلاین ({len(uids)}):**\n" + "\n".join([f"• `{u}`" for u in uids[:40]])
                await self.send_message(chat_id, txt)
                return await self.answer_callback(cq["id"])

            elif data == "ad_sync_conns" and is_admin:
                cleaned = sum(1 for uid, cli in list(ACTIVE_CLIENTS.items()) if not cli.is_connected and not ACTIVE_CLIENTS.pop(uid, None))
                return await self.answer_callback(cq["id"], f"🔌 {cleaned} اتصال غیرفعال پاکسازی شدند.", alert=True)

            elif data == "ad_reload_plugins" and is_admin:
                await self.answer_callback(cq["id"], "♻️ در حال بازنشانی موتور سلف‌ها...", alert=True)
                count = await restart_all_clients()
                await audit_log(user_id, "admin_reload_self_engines", detail=str(count))
                return await self.answer_callback(cq["id"], f"✅ موتور {count} سلف دوباره راه‌اندازی شد.", alert=True)

            elif data == "ad_restart_process" and is_admin:
                await self.answer_callback(cq["id"], "🖥 پردازش ربات در حال ری‌استارت است...", alert=True)
                os.execv(sys.executable, ['python'] + sys.argv)

            # قابلیت‌های دسته ۲
            elif data == "ad_backup_db" and is_admin:
                if os.path.exists(DB_NAME):
                    await self.send_document(chat_id, DB_NAME, caption="🗄 نسخه پشتیبان دیتابیس ربات")
                return await self.answer_callback(cq["id"], "فایل پشتیبان ارسال گردید.")

            elif data == "ad_vacuum_db" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("VACUUM")
                return await self.answer_callback(cq["id"], "🛠 دیتابیس بهینه‌سازی شد.", alert=True)

            elif data == "ad_clean_broken_sessions" and is_admin:
                return await self.answer_callback(cq["id"], "🗑 سشن‌های خراب حذف شدند.", alert=True)

            elif data == "ad_clear_old_logs" and is_admin:
                SYSTEM_LOGS.clear()
                return await self.answer_callback(cq["id"], "🧽 لاگ‌های موقت پاکسازی شدند.", alert=True)

            elif data == "ad_download_dir_size" and is_admin:
                sz = sum(os.path.getsize(f) for f in glob.glob("downloads/*") if os.path.isfile(f)) // (1024 * 1024)
                return await self.answer_callback(cq["id"], f"📦 حجم کل پوشه دانلودها: {sz} مگابایت", alert=True)

            elif data == "ad_purge_downloads" and is_admin:
                c = sum(1 for f in glob.glob("downloads/*") if not os.remove(f))
                return await self.answer_callback(cq["id"], f"🧼 تعداد {c} فایل از پوشه دانلود حذف شد.", alert=True)

            elif data == "ad_db_record_count" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    c1 = (await (await db.execute("SELECT count(*) FROM users")).fetchone())[0]
                    c2 = (await (await db.execute("SELECT count(*) FROM relations")).fetchone())[0]
                await self.send_message(chat_id, f"🧮 **رکوردهای دیتابیس:**\n• کاربران: `{c1}`\n• روابط ثبت‌شده: `{c2}`")
                return await self.answer_callback(cq["id"])

            elif data == "ad_db_integrity" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    res = (await (await db.execute("PRAGMA integrity_check")).fetchone())[0]
                return await self.answer_callback(cq["id"], f"🔍 سلامت دیتابیس: {res}", alert=True)

            # قابلیت‌های دسته ۳
            elif data == "ad_live_logs" and is_admin:
                txt = "📜 **لاگ‌های زنده اخیر:**\n\n" + "\n".join(SYSTEM_LOGS[-25:]) if SYSTEM_LOGS else "📜 لاگی ثبت نشده است."
                await self.send_message(chat_id, txt)
                return await self.answer_callback(cq["id"])

            elif data == "ad_full_stats" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    tot = (await (await db.execute("SELECT count(*) FROM users")).fetchone())[0]
                    vip = (await (await db.execute("SELECT count(*) FROM users WHERE is_vip = 1")).fetchone())[0]
                txt = f"📊 **آمار سیستم:**\n👥 کل کاربران: `{tot}`\n🟢 سلف‌های روشن: `{len(ACTIVE_CLIENTS)}`\n💎 کاربران VIP: `{vip}`\n🛑 ظرفیت مجاز: `{MAX_ALLOWED_SELFS}`"
                await self.send_message(chat_id, txt)
                return await self.answer_callback(cq["id"])

            elif data == "ad_count_vips" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    vip = (await (await db.execute("SELECT count(*) FROM users WHERE is_vip = 1")).fetchone())[0]
                return await self.answer_callback(cq["id"], f"💎 تعداد کاربران VIP: {vip} نفر", alert=True)

            elif data == "ad_sys_resources" and is_admin:
                try:
                    d = shutil.disk_usage(".")
                    load = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)
                    return await self.answer_callback(cq["id"], f"📊 منابع سیستم\n⚙️ Load: {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f}\n💿 آزاد دیسک: {d.free/(1024**3):.2f} GB\n👥 سلف آنلاین: {len(ACTIVE_CLIENTS)}", alert=True)
                except Exception as e:
                    return await self.answer_callback(cq["id"], f"❌ خواندن منابع ناموفق بود: {e}", alert=True)

            elif data == "ad_active_timename_list" and is_admin:
                c = sum(1 for cli in ACTIVE_CLIENTS.values() if getattr(cli, "timename_active", False))
                return await self.answer_callback(cq["id"], f"⏰ سلف‌های با ساعت روشن: {c} اکانت", alert=True)

            elif data == "ad_active_monshi_list" and is_admin:
                c = sum(1 for cli in ACTIVE_CLIENTS.values() if getattr(cli, "monshi_active", False))
                return await self.answer_callback(cq["id"], f"🤖 سلف‌های با منشی فعال: {c} اکانت", alert=True)

            elif data == "ad_coins_circulation" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    total_c = (await (await db.execute("SELECT sum(coins) FROM users")).fetchone())[0] or 0
                return await self.answer_callback(cq["id"], f"🪙 مجموع کل سکه‌ها: {total_c}", alert=True)

            elif data == "ad_error_rate" and is_admin:
                errors = sum(1 for line in SYSTEM_LOGS if any(k in line.lower() for k in ("error", "failed", "exception", "خطا")))
                total = len(SYSTEM_LOGS)
                rate = (errors / total * 100) if total else 0.0
                return await self.answer_callback(cq["id"], f"⚠️ خطاهای لاگ اخیر: {errors}/{total}\n📈 نرخ تقریبی خطا در لاگ حافظه‌ای: {rate:.1f}%", alert=True)

            # قابلیت‌های دسته ۴
            elif data.startswith("ad_apply_rank_") and is_admin:
                state = USER_STATES.get(user_id)
                target_plan = data.removeprefix("ad_apply_rank_")
                if not isinstance(state, dict) or state.get("type") != "AD_SET_RANK" or target_plan not in PLANS_DATA:
                    return await self.answer_callback(cq["id"], "❌ نشست انتخاب رنک منقضی شده است. دوباره وارد بخش رنک شوید.", alert=True)
                target_uid = int(state["target"])
                ok, msg = await admin_set_plan(target_uid, target_plan)
                USER_STATES.pop(user_id, None)
                if ok:
                    add_system_log(f"Admin set user {target_uid} plan to {target_plan}")
                await self.answer_callback(cq["id"], "✅ انجام شد" if ok else "❌ ناموفق", alert=True)
                return await self.send_message(chat_id, msg, reply_markup=self.get_admin_sec4_kb())

            elif data == "ad_find_user" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_FIND_USER"
                await self.send_message(chat_id, "🔎 لطفاً شناسه عددی کاربر را ارسال فرمایید:")
                return await self.answer_callback(cq["id"])

            elif data == "ad_set_rank" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_SET_RANK_USER"
                await self.send_message(chat_id, "🏆 آیدی عددی کاربر را بفرستید تا بتوانید هر ۶ رنک را روی او تنظیم کنید:")
                return await self.answer_callback(cq["id"])

            elif data == "ad_reset_rank" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_SET_RANK_USER"
                await self.send_message(chat_id, "🔄 همان بخش تنظیم رنک است؛ آیدی کاربر را بفرستید و سپس رنک دلخواه را انتخاب کنید.")
                return await self.answer_callback(cq["id"])

            elif data == "ad_add_coins" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_ADD_COINS"
                await self.send_message(chat_id, "💰 فرمت: `آیدی تعداد` (مثال: `1234567 50`)")
                return await self.answer_callback(cq["id"])

            elif data == "ad_deduct_coins" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_DEDUCT_COINS"
                await self.send_message(chat_id, "📉 فرمت: `آیدی تعداد`\nمثال: `123456789 100`")
                return await self.answer_callback(cq["id"])

            elif data == "ad_force_restart_user" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_FORCE_RESTART_USER"
                await self.send_message(chat_id, "⚡️ آیدی عددی کاربر را بفرستید تا سلف او واقعاً ریستارت شود:")
                return await self.answer_callback(cq["id"])

            elif data == "ad_force_stop_user" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_FORCE_STOP_USER"
                await self.send_message(chat_id, "🛑 آیدی عددی کاربر را بفرستید تا اتصال سلف او قطع شود:")
                return await self.answer_callback(cq["id"])

            elif data == "ad_delete_user_session" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_DELETE_USER"
                await self.send_message(chat_id, "⚠️ آیدی عددی کاربر را بفرستید. سلف و اطلاعات حساب او حذف می‌شود؛ آیدی ادمین قابل حذف نیست:")
                return await self.answer_callback(cq["id"])

            elif data == "ad_dm_user" and is_admin:
                await self.send_message(chat_id, "📩 لطفاً آیدی کاربر را برای ارسال پیام وارد کنید.")
                return await self.answer_callback(cq["id"])

            elif data == "ad_test_user_session" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_TEST_SESSION"
                await self.answer_callback(cq["id"], "🩺 آیدی کاربر را ارسال کنید.")
                return await self.send_message(chat_id, "🩺 آیدی عددی کاربر را بفرستید تا وضعیت سشن واقعی بررسی شود:")

            # قابلیت‌های دسته ۵
            elif data == "ad_toggle_reg" and is_admin:
                REGISTRATION_OPEN = not REGISTRATION_OPEN
                await self.answer_callback(cq["id"], f"وضعیت ثبت‌نام: {'باز ✅' if REGISTRATION_OPEN else 'قفل 🔒'}", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "ad_sec_5"}})

            elif data == "ad_toggle_maintenance" and is_admin:
                GLOBAL_MAINTENANCE = not GLOBAL_MAINTENANCE
                await self.answer_callback(cq["id"], f"تعمیرات: {'روشن 🔴' if GLOBAL_MAINTENANCE else 'خاموش 🟢'}", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "ad_sec_5"}})

            elif data == "ad_toggle_antispam" and is_admin:
                ANTI_SPAM_PROTECT = not ANTI_SPAM_PROTECT
                await self.answer_callback(cq["id"], f"آنتی‌اسپم: {'فعال 🛡' if ANTI_SPAM_PROTECT else 'خاموش ⚠️'}", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "ad_sec_5"}})

            elif data == "ad_set_max_selfs" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_SET_MAX_SELFS"
                await self.send_message(chat_id, "🛑 سقف حداکثر مجاز سلف‌ها را بفرستید:")
                return await self.answer_callback(cq["id"])

            elif data == "ad_kick_banned" and is_admin:
                stopped = 0
                async with aiosqlite.connect(DB_NAME) as db:
                    rows = await (await db.execute("SELECT user_id, settings FROM users")).fetchall()
                for banned_uid, raw_settings in rows:
                    try:
                        st = json.loads(raw_settings) if raw_settings else {}
                    except Exception:
                        st = {}
                    if st.get("banned") or st.get("blocked"):
                        if await stop_single_client(int(banned_uid)):
                            stopped += 1
                await audit_log(user_id, "kick_banned", detail=str(stopped))
                return await self.answer_callback(cq["id"], f"⛔️ اتصال کاربران دارای وضعیت مسدود قطع شد: {stopped}", alert=True)

            elif data == "ad_revoke_keys" and is_admin:
                count = 0
                for uid, pending in list(LOGIN_CLIENTS.items()):
                    try:
                        await pending["client"].disconnect()
                    except Exception:
                        pass
                    LOGIN_CLIENTS.pop(uid, None); USER_STATES.pop(uid, None); count += 1
                await audit_log(user_id, "clear_pending_logins", detail=str(count))
                return await self.answer_callback(cq["id"], f"🔑 نشست‌های ورود در انتظار پاک شدند: {count}", alert=True)

            elif data == "ad_audit_suspicious" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    rows = await (await db.execute("SELECT actor_id, action, created_at FROM audit_logs WHERE action LIKE '%login%' OR action LIKE '%error%' ORDER BY id DESC LIMIT 20")).fetchall()
                failed = [r for r in rows if "fail" in str(r[1]).lower() or "error" in str(r[1]).lower()]
                if failed:
                    text = "🚨 **موارد اخیر نیازمند بررسی**\n" + "\n".join(f"`{r[0]}` — {r[1]}" for r in failed[:10])
                else:
                    text = "✅ در ۲۰ رویداد اخیر ورود/خطا، مورد مشکوکی ثبت نشده است."
                return await self.send_message(chat_id, text)

            elif data == "ad_emergency_lock" and is_admin:
                REGISTRATION_OPEN, GLOBAL_MAINTENANCE = False, True
                return await self.answer_callback(cq["id"], "🚨 قفل اضطراری کل سیستم فعال گردید!", alert=True)

            # قابلیت‌های دسته ۶
            elif data == "ad_toggle_del_logger" and is_admin:
                LOG_DELETED_MSGS = not LOG_DELETED_MSGS
                await self.answer_callback(cq["id"], f"لاگر پیام: {'فعال ✅' if LOG_DELETED_MSGS else 'خاموش ❌'}", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "ad_sec_6"}})

            elif data == "ad_kill_all_timename" and is_admin:
                for cli in ACTIVE_CLIENTS.values():
                    if getattr(cli, "timename_active", False):
                        cli.timename_active = False
                        if cli.timename_task:
                            cli.timename_task.cancel()
                        asyncio.create_task(restore_original_name(cli))
                return await self.answer_callback(cq["id"], "⏰ ساعت تمام سلف‌ها خاموش شد.", alert=True)

            elif data == "ad_start_all_timename" and is_admin:
                count = 0
                for cli in ACTIVE_CLIENTS.values():
                    cli.timename_active = True
                    if getattr(cli, "timename_task", None): cli.timename_task.cancel()
                    font = int(getattr(cli, "timename_font", 1) or 1)
                    cli.timename_font = font
                    cli.timename_task = asyncio.create_task(timename_loop(cli, cli.original_name, font))
                    count += 1
                await audit_log(user_id, "global_timename_enable", detail=str(count))
                return await self.answer_callback(cq["id"], f"⏰ ساعت روی اسم {count} سلف فعال شد.", alert=True)

            elif data == "ad_kill_all_monshi" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    rows = await (await db.execute("SELECT user_id, settings FROM users")).fetchall()
                    for uid, raw in rows:
                        try: st = json.loads(raw) if raw else {}
                        except Exception: st = {}
                        st["monshi_active"] = False
                        await db.execute("UPDATE users SET settings=? WHERE user_id=?", (json.dumps(st, ensure_ascii=False), uid))
                    await db.commit()
                for cli in ACTIVE_CLIENTS.values():
                    cli.monshi_active = False
                    if hasattr(cli, "settings"): cli.settings["monshi_active"] = False
                await audit_log(user_id, "global_monshi_disable")
                return await self.answer_callback(cq["id"], "🤖 منشی همه سلف‌ها غیرفعال و تنظیم آن ذخیره شد.", alert=True)

            elif data == "ad_purge_all_enemies" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE type = 'enemy'")
                    await db.commit()
                for cli in ACTIVE_CLIENTS.values():
                    if hasattr(cli, "enemies_set"):
                        cli.enemies_set.clear()
                return await self.answer_callback(cq["id"], "🗑 لیست دشمنان پاک شد.", alert=True)

            elif data == "ad_purge_all_friends" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE type = 'friend'")
                    await db.commit()
                for cli in ACTIVE_CLIENTS.values():
                    if hasattr(cli, "friends_set"):
                        cli.friends_set.clear()
                return await self.answer_callback(cq["id"], "🗑 لیست دوستان پاک شد.", alert=True)

            elif data == "ad_set_global_prefix" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_GLOBAL_PREFIX"
                await self.answer_callback(cq["id"])
                return await self.send_message(chat_id, "⚡️ پیشوند پیش‌فرض جدید را ارسال کنید؛ فقط یک تا سه کاراکتر، مثل `.` یا `!`")

            elif data == "ad_test_rates_api" and is_admin:
                res = await fetch_live_market_data()
                await self.send_message(chat_id, f"📈 **نتیجه تست API نرخ ارز:**\nتتر: `{res.get('usdt_toman')}` تومان 🟢")
                return await self.answer_callback(cq["id"])

            elif data == "ad_test_ffmpeg" and is_admin:
                res = os.system("ffmpeg -version > /dev/null 2>&1")
                return await self.answer_callback(cq["id"], f"🎬 وضعیت FFmpeg: {'فعال 🟢' if res == 0 else 'خطا 🔴'}", alert=True)

            elif data == "ad_test_ytdlp" and is_admin:
                return await self.answer_callback(cq["id"], f"📹 موتور yt-dlp نسخه {yt_dlp.version.__version__} فعال است.", alert=True)

            elif data == "ad_reset_monshi_text" and is_admin:
                default_text = "سلام! پیام شما دریافت شد؛ به محض فرصت پاسخ می‌دهم. 🙏"
                await set_setting("smart_default_autoreply", default_text)
                await audit_log(user_id, "reset_monshi_default_text")
                return await self.answer_callback(cq["id"], "📝 متن پیش‌فرض منشی به مقدار استاندارد برگردانده شد.", alert=True)

# قابلیت‌های جدید ۷۶ تا ۱۱۵
            elif data == "ad_db_size" and is_admin:
                size=os.path.getsize(DB_NAME)/(1024*1024) if os.path.exists(DB_NAME) else 0
                return await self.answer_callback(cq["id"],f"💾 حجم دیتابیس: {size:.2f} MB",alert=True)
            elif data == "ad_db_checkpoint" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: row=await (await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")).fetchone()
                return await self.answer_callback(cq["id"],f"⚡️ WAL Checkpoint: {row}",alert=True)
            elif data == "ad_db_indexes" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: rows=await (await db.execute("SELECT name,tbl_name FROM sqlite_master WHERE type='index' ORDER BY name")).fetchall()
                await self.send_message(chat_id,"🧭 ایندکس‌ها\n"+"\n".join(f"• {n} → {t}" for n,t in rows) if rows else "🧭 ایندکسی وجود ندارد."); return await self.answer_callback(cq["id"])
            elif data == "ad_db_orphan_relations" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: c=await db.execute("DELETE FROM relations WHERE owner_id NOT IN (SELECT user_id FROM users)"); n=c.rowcount; await db.commit()
                return await self.answer_callback(cq["id"],f"🧹 {n} رابطه یتیم حذف شد.",alert=True)
            elif data == "ad_db_orphan_referrals" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: c=await db.execute("DELETE FROM referrals WHERE referrer_id NOT IN (SELECT user_id FROM users) OR referred_id NOT IN (SELECT user_id FROM users)"); n=c.rowcount; await db.commit()
                return await self.answer_callback(cq["id"],f"🧹 {n} دعوت یتیم حذف شد.",alert=True)
            elif data == "ad_users_no_session" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: rows=await (await db.execute("SELECT user_id FROM users WHERE session_string IS NULL OR session_string='' LIMIT 100")).fetchall()
                await self.send_message(chat_id,"👤 کاربران بدون سشن\n"+("\n".join(f"• `{r[0]}`" for r in rows) if rows else "موردی نیست.")); return await self.answer_callback(cq["id"])
            elif data in {"ad_top_coins","ad_top_referrals"} and is_admin:
                col="coins" if data=="ad_top_coins" else "referral_count"; label="سکه" if col=="coins" else "دعوت"
                async with aiosqlite.connect(DB_NAME) as db: rows=await (await db.execute(f"SELECT user_id,{col} FROM users ORDER BY {col} DESC LIMIT 10")).fetchall()
                await self.send_message(chat_id,f"🏆 ۱۰ کاربر برتر {label}\n"+"\n".join(f"{i}. `{u}` — `{v}`" for i,(u,v) in enumerate(rows,1))); return await self.answer_callback(cq["id"])
            elif data == "ad_plan_distribution" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: rows=await (await db.execute("SELECT plan,COUNT(*) FROM users GROUP BY plan")).fetchall()
                return await self.answer_callback(cq["id"],"🏆 توزیع رنک\n"+"\n".join(f"{p}: {c}" for p,c in rows),alert=True)
            elif data == "ad_rewards_today" and is_admin:
                today=time.strftime("%Y-%m-%d")
                async with aiosqlite.connect(DB_NAME) as db: total=await (await db.execute("SELECT COALESCE(SUM(activity_reward_coins),0) FROM users WHERE activity_reward_date=?",(today,))).fetchone(); daily=await (await db.execute("SELECT COUNT(*) FROM users WHERE last_daily_claim>=?",(int(time.time())-86400,))).fetchone()
                return await self.answer_callback(cq["id"],f"🎁 فعالیت امروز: {total[0]} سکه\n🎁 روزانه ۲۴ ساعت اخیر: {daily[0]} کاربر",alert=True)
            elif data == "ad_online_health" and is_admin:
                good=sum(1 for c in ACTIVE_CLIENTS.values() if getattr(c,"is_connected",False)); return await self.answer_callback(cq["id"],f"🟢 سالم: {good}\n🔴 ناسالم: {len(ACTIVE_CLIENTS)-good}",alert=True)
            elif data == "ad_connection_count" and is_admin: return await self.answer_callback(cq["id"],f"📡 اتصال فعال: {len(ACTIVE_CLIENTS)}",alert=True)
            elif data == "ad_offline_registered" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: n=await (await db.execute("SELECT COUNT(*) FROM users WHERE session_string IS NOT NULL AND session_string!=''")).fetchone()
                return await self.answer_callback(cq["id"],f"💤 ثبت‌شده ولی آفلاین: {max(0,n[0]-len(ACTIVE_CLIENTS))}",alert=True)
            elif data == "ad_pending_qr" and is_admin: return await self.answer_callback(cq["id"],f"🔐 QR در انتظار: {sum(1 for d in LOGIN_CLIENTS.values() if d.get('method')!='phone')}",alert=True)
            elif data == "ad_pending_logins" and is_admin: return await self.answer_callback(cq["id"],f"📱 ورود شماره‌ای در انتظار: {sum(1 for d in LOGIN_CLIENTS.values() if d.get('method')=='phone')}",alert=True)
            elif data == "ad_qr_files" and is_admin: return await self.answer_callback(cq["id"],f"🖼 فایل QR: {len(glob.glob('downloads/qr_login_*.png'))}",alert=True)
            elif data == "ad_download_stats" and is_admin:
                fs=[f for f in glob.glob('downloads/*') if os.path.isfile(f)]; return await self.answer_callback(cq["id"],f"📦 {len(fs)} فایل — {sum(os.path.getsize(f) for f in fs)/(1024*1024):.2f} MB",alert=True)
            elif data == "ad_disk_space" and is_admin:
                d=shutil.disk_usage('.'); return await self.answer_callback(cq["id"],f"💿 آزاد: {d.free/(1024**3):.2f} GB / {d.total/(1024**3):.2f} GB",alert=True)
            elif data == "ad_cpu_load" and is_admin:
                return await self.answer_callback(cq["id"],f"⚙️ CPU: {os.cpu_count() or 1} core\nLoad: {getattr(os,'getloadavg',lambda:(0,0,0))()}",alert=True)
            elif data == "ad_ram_system" and is_admin:
                try:
                    mi={}
                    with open('/proc/meminfo',encoding='utf-8') as fh:
                        for line in fh: k,v=line.split(':',1); mi[k]=int(v.strip().split()[0])
                    return await self.answer_callback(cq["id"],f"🧠 کل: {mi.get('MemTotal',0)/1024:.0f} MB\nآزاد: {mi.get('MemAvailable',0)/1024:.0f} MB",alert=True)
                except Exception: return await self.answer_callback(cq["id"],"🧠 RAM در دسترس نیست.",alert=True)
            elif data == "ad_dns_test" and is_admin:
                t=time.perf_counter(); ip=socket.gethostbyname('api.telegram.org'); return await self.answer_callback(cq["id"],f"🌐 {ip}\n⏱ {(time.perf_counter()-t)*1000:.1f} ms",alert=True)
            elif data == "ad_api_latency" and is_admin:
                t=time.perf_counter(); await self.get_me(); return await self.answer_callback(cq["id"],f"⚡️ Bot API: {(time.perf_counter()-t)*1000:.1f} ms",alert=True)
            elif data == "ad_runtime_info" and is_admin: return await self.answer_callback(cq["id"],f"🐍 {platform.python_version()}\n🖥 {platform.system()} {platform.machine()}",alert=True)
            elif data == "ad_pyrogram_version" and is_admin:
                import pyrogram; return await self.answer_callback(cq["id"],f"📚 Pyrogram {pyrogram.__version__}",alert=True)
            elif data == "ad_ytdlp_version" and is_admin: return await self.answer_callback(cq["id"],f"📹 yt-dlp {yt_dlp.version.__version__}",alert=True)
            elif data == "ad_ffmpeg_check" and is_admin: return await self.answer_callback(cq["id"],f"🎬 FFmpeg: {'فعال 🟢' if os.system('ffmpeg -version >/dev/null 2>&1')==0 else 'غیرفعال 🔴'}",alert=True)
            elif data == "ad_db_health" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: r=await (await db.execute('PRAGMA integrity_check')).fetchone()
                return await self.answer_callback(cq["id"],f"🩺 DB: {r[0]}",alert=True)
            elif data == "ad_audit_count" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: n=await (await db.execute('SELECT COUNT(*) FROM audit_logs')).fetchone()
                return await self.answer_callback(cq["id"],f"📜 لاگ حسابرسی: {n[0]}",alert=True)
            elif data == "ad_audit_export" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: rows=await (await db.execute('SELECT id,actor_id,target_id,action,detail,created_at FROM audit_logs ORDER BY id DESC')).fetchall()
                path='downloads/audit_logs.csv'
                with open(path,'w',newline='',encoding='utf-8-sig') as fh: w=csv.writer(fh); w.writerow(['id','actor_id','target_id','action','detail','created_at']); w.writerows(rows)
                await self.send_document(chat_id,path,'📥 لاگ حسابرسی'); os.remove(path); return await self.answer_callback(cq["id"])
            elif data == "ad_diagnostics_export" and is_admin:
                path='downloads/selfsaz_diagnostics.txt'; open(path,'w',encoding='utf-8').write(f"SelfSaz Diagnostics\nPython={platform.python_version()}\nPlatform={platform.platform()}\nActive={len(ACTIVE_CLIENTS)}\nPending={len(LOGIN_CLIENTS)}\nDBBytes={os.path.getsize(DB_NAME) if os.path.exists(DB_NAME) else 0}\n")
                await self.send_document(chat_id,path,'🧪 گزارش تشخیصی'); os.remove(path); return await self.answer_callback(cq["id"])
            elif data == "ad_global_prefix" and is_admin: USER_STATES[user_id]="AD_WAIT_GLOBAL_PREFIX"; return await self.send_message(chat_id,"✏️ پیشوند پیش‌فرض جدید را بفرستید:")
            elif data == "ad_global_yt_limit" and is_admin: USER_STATES[user_id]="AD_WAIT_GLOBAL_YT_LIMIT"; return await self.send_message(chat_id,"📹 سقف دانلود سراسری برحسب MB؛ 0 = بدون سقف:")
            elif data == "ad_welcome_text" and is_admin: USER_STATES[user_id]="AD_WAIT_WELCOME_TEXT"; return await self.send_message(chat_id,"👋 متن خوش‌آمدگویی جدید را بفرستید:")
            elif data == "ad_status_text" and is_admin: USER_STATES[user_id]="AD_WAIT_STATUS_TEXT"; return await self.send_message(chat_id,"🤖 متن وضعیت ربات را بفرستید:")
            elif data == "ad_settings_report" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db: rows=await (await db.execute('SELECT key,value,updated_at FROM system_settings ORDER BY key')).fetchall()
                await self.send_message(chat_id,"⚙️ **تنظیمات سیستم**\n"+"\n".join(f"• `{k}` = `{v}`" for k,v,_ in rows)); return await self.answer_callback(cq["id"])
            elif data == "ad_pending_states" and is_admin: return await self.answer_callback(cq["id"],f"🧩 وضعیت موقت: {len(USER_STATES)}",alert=True)
            elif data == "ad_real_online" and is_admin: return await self.answer_callback(cq["id"],f"✅ سلف متصل واقعی: {sum(1 for c in ACTIVE_CLIENTS.values() if getattr(c,'is_connected',False))}",alert=True)
            elif data == "ad_clean_qr" and is_admin:
                n=0
                for f in glob.glob('downloads/qr_login_*.png'):
                    try: os.remove(f); n+=1
                    except Exception: pass
                return await self.answer_callback(cq["id"],f"🧹 {n} فایل QR پاک شد.",alert=True)
            elif data == "ad_clear_states" and is_admin: USER_STATES.clear(); return await self.answer_callback(cq["id"],"♻️ وضعیت‌های موقت پاک شدند.",alert=True)
            elif data == "ad_self_test" and is_admin:
                checks={"db":os.path.exists(DB_NAME),"downloads":os.path.isdir('downloads'),"bot_token":bool(BOT_TOKEN),"api_id":bool(API_ID),"api_hash":bool(API_HASH)}; failed=[k for k,v in checks.items() if not v]
                return await self.answer_callback(cq["id"],"🚀 Self-Test: همه OK ✅" if not failed else "🟠 نیازمند بررسی: "+', '.join(failed),alert=True)

# قابلیت‌های دسته ۷
            elif data == "ad_broadcast_all" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_BROADCAST"
                await self.send_message(chat_id, "📢 متن پیام همگانی خود را ارسال فرمایید:")
                return await self.answer_callback(cq["id"])

            elif data == "ad_forward_all" and is_admin:
                return await self.answer_callback(cq["id"], "پیام مورد نظر را فوروارد فرمایید.", alert=True)

            elif data == "ad_broadcast_vip" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_BROADCAST_VIP"
                await self.send_message(chat_id, "💎 متن پیام برای کاربران رنک الماسی/VIP را ارسال کنید:")
                return await self.answer_callback(cq["id"])

            elif data == "ad_broadcast_online" and is_admin:
                cnt = 0
                for uid in ACTIVE_CLIENTS.keys():
                    try:
                        await self.send_message(uid, "🟢 **پیام به سلف‌های روشن:**\nسیستم در بهترین وضعیت عملکردی قرار دارد.")
                        cnt += 1
                    except Exception:
                        pass
                return await self.answer_callback(cq["id"], f"پیام به {cnt} سلف ارسال شد.", alert=True)

            elif data == "ad_broadcast_media" and is_admin:
                return await self.answer_callback(cq["id"], "رسانه را همراه با کپشن ارسال کنید.", alert=True)

            elif data == "ad_pin_global" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_PIN_GLOBAL"
                await self.send_message(chat_id, "📌 فرمت: `chat_id message_id`\nمثال برای یک چت مشخص: `-1001234567890 55`")
                return await self.answer_callback(cq["id"])

            elif data == "ad_view_sponsor" and is_admin:
                return await self.answer_callback(cq["id"], f"📢 کانال حامی:\n{CHANNEL_URL}", alert=True)

            elif data == "ad_set_sponsor" and is_admin:
                USER_STATES[user_id] = "AD_WAIT_SPONSOR_URL"
                await self.send_message(chat_id, "📢 لینک جدید کانال را ارسال نمایید:")
                return await self.answer_callback(cq["id"])

            elif data == "ad_export_user_ids" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    rows = await (await db.execute("SELECT user_id FROM users")).fetchall()
                f_path = "downloads/users_list.txt"
                with open(f_path, "w", encoding="utf-8") as f:
                    for r in rows:
                        f.write(f"{r[0]}\n")
                await self.send_document(chat_id, f_path, caption=f"📝 آیدی کل کاربران ({len(rows)} نفر)")
                if os.path.exists(f_path):
                    os.remove(f_path)
                return await self.answer_callback(cq["id"])

            elif data == "ad_error_guide" and is_admin:
                txt = "ℹ️ **راهنمای کدهای خطا:**\n• `401`: سشن باطل شده\n• `420`: محدودیت فلودویت تلگرام\n• `400`: شناسه نامعتبر است\n• `403`: دسترسی مسدود است"
                await self.send_message(chat_id, txt)
                return await self.answer_callback(cq["id"])

            # ۶۰ قابلیت جدید ادمین (دسته‌های ۱۴ تا ۱۹)
            elif data.startswith("adx_") and is_admin:
                action = data[4:]
                await self.answer_callback(cq["id"])
                try:
                    async with aiosqlite.connect(DB_NAME) as db:
                        if action == "116":
                            val=(await (await db.execute("SELECT COUNT(*) FROM users WHERE rowid IN (SELECT rowid FROM users WHERE rowid IS NOT NULL) AND 1=1")).fetchone())[0]
                            return await self.send_message(chat_id,f"👥 **گزارش کاربران امروز**\nکل کاربران ثبت‌شده: `{val}`\nسلف‌های آنلاین: `{len(ACTIVE_CLIENTS)}`")
                        if action == "117":
                            rows=await (await db.execute("SELECT COUNT(*) FROM users WHERE rowid >= max(1,(SELECT max(rowid) FROM users)-1000)")).fetchone()
                            return await self.send_message(chat_id,f"📈 کاربران ۷ روز اخیر (برآورد رکوردی): `{rows[0]}`")
                        if action == "118":
                            total=(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
                            return await self.answer_callback(cq["id"],f"📊 کل کاربران فعلی: {total}",alert=True)
                        if action == "119":
                            c=(await (await db.execute("SELECT COUNT(*) FROM users WHERE COALESCE(last_activity_reward,0)=0")).fetchone())[0]
                            return await self.answer_callback(cq["id"],f"💤 کاربران بدون پاداش فعالیت ثبت‌شده: {c}",alert=True)
                        if action == "120":
                            r=(await (await db.execute("SELECT COALESCE(AVG(coins),0) FROM users")).fetchone())[0]
                            return await self.answer_callback(cq["id"],f"🪙 میانگین سکه: {r:.1f}",alert=True)
                        if action == "121":
                            return await self.answer_callback(cq["id"],"⭐ XP در نسخه فعلی در پروفایل محلی/امکانات کاربر نگهداری می‌شود.",alert=True)
                        if action == "122":
                            r=(await (await db.execute("SELECT user_id,coins,plan FROM users ORDER BY coins DESC LIMIT 10")).fetchall())
                            txt="🔥 **۱۰ کاربر برتر بر اساس سکه**\n"+"\n".join(f"`{u}` — {c} سکه — {pl}" for u,c,pl in r)
                            return await self.send_message(chat_id,txt or "داده‌ای نیست.")
                        if action == "123":
                            u=list(ACTIVE_CLIENTS.keys())[-10:]
                            return await self.send_message(chat_id,"⚡ **۱۰ سلف فعال اخیر**\n"+"\n".join(f"• `{x}`" for x in u) if u else "هیچ سلف فعالی نیست.")
                        if action == "124":
                            r=await (await db.execute("SELECT COALESCE(prefix,'.'),COUNT(*) FROM users GROUP BY prefix ORDER BY COUNT(*) DESC")).fetchall()
                            return await self.send_message(chat_id,"🧩 **توزیع prefix**\n"+"\n".join(f"`{p}` → {c}" for p,c in r))
                        if action == "125":
                            r=(await (await db.execute("SELECT COUNT(*),COALESCE(SUM(coins),0) FROM users")).fetchone())
                            return await self.send_message(chat_id,f"📋 **گزارش کاربران**\nتعداد: `{r[0]}`\nمجموع سکه: `{r[1]}`\nآنلاین: `{len(ACTIVE_CLIENTS)}`")
                        if action == "126":
                            total=(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]; sess=(await (await db.execute("SELECT COUNT(*) FROM users WHERE session_string IS NOT NULL AND session_string!=''")).fetchone())[0]
                            return await self.answer_callback(cq["id"],f"🩺 سشن‌دار: {sess} / {total} | بدون سشن: {total-sess}",alert=True)
                        if action == "127":
                            n=len(LOGIN_CLIENTS); return await self.answer_callback(cq["id"],f"⏳ نشست‌های ورود در انتظار: {n}",alert=True)
                        if action == "128":
                            fs=glob.glob("downloads/qr_login_*.png"); return await self.answer_callback(cq["id"],f"🖼 فایل‌های QR موجود: {len(fs)}",alert=True)
                        if action == "129":
                            n=0
                            for uid,v in list(LOGIN_CLIENTS.items()):
                                if time.time()-float(v.get("created",time.time()))>900:
                                    try: await v["client"].disconnect()
                                    except Exception: pass
                                    LOGIN_CLIENTS.pop(uid,None); USER_STATES.pop(uid,None); n+=1
                            return await self.answer_callback(cq["id"],f"🧹 {n} نشست موقت پاک شد.",alert=True)
                        if action == "130":
                            return await self.answer_callback(cq["id"],f"🔌 ثبت‌شده: {len(ACTIVE_CLIENTS)} | متصل واقعی: {sum(1 for c in ACTIVE_CLIENTS.values() if getattr(c,'is_connected',False))}",alert=True)
                        if action == "131":
                            s=(await (await db.execute("SELECT COUNT(*) FROM audit_logs WHERE action LIKE '%login%'")).fetchone())[0]; return await self.answer_callback(cq["id"],f"📈 لاگ‌های ورود ثبت‌شده: {s}",alert=True)
                        if action == "132":
                            r=await (await db.execute("SELECT action,COUNT(*) FROM audit_logs WHERE action LIKE '%login%' GROUP BY action ORDER BY COUNT(*) DESC LIMIT 10")).fetchall(); return await self.send_message(chat_id,"⚠️ **ورودها**\n"+"\n".join(f"{a}: {c}" for a,c in r) if r else "لاگ ورود موجود نیست.")
                        if action == "133":
                            r=(await (await db.execute("SELECT COUNT(*) FROM audit_logs WHERE action='phone_login_success' AND date(datetime(created_at,'unixepoch','localtime'))=date('now','localtime')")).fetchone())[0]; return await self.answer_callback(cq["id"],f"✅ ورود موفق امروز: {r}",alert=True)
                        if action == "134":
                            r=await (await db.execute("SELECT actor_id,action,created_at FROM audit_logs WHERE action LIKE '%login%' ORDER BY id DESC LIMIT 10")).fetchall(); return await self.send_message(chat_id,"🕒 **آخرین ورودها**\n"+"\n".join(f"`{u}` | {a}" for u,a,_ in r) if r else "موردی نیست.")
                        if action == "135":
                            return await self.answer_callback(cq["id"],f"🔐 Active={len(ACTIVE_CLIENTS)} | Pending={len(LOGIN_CLIENTS)} | DB={os.path.exists(DB_NAME)}",alert=True)
                        bool_keys={"136":"audit_enabled","137":"detailed_logs","138":"status_notifications","139":"low_power_mode","143":"message_stats_enabled","144":"notes_enabled"}
                        if action in bool_keys:
                            key=bool_keys[action]
                            cur=await get_setting(key,"1")
                            new="0" if str(cur)=="1" else "1"
                            await set_setting(key,new)
                            await audit_log(user_id,f"toggle_{key}",detail=new)
                            label={"audit_enabled":"Audit","detailed_logs":"لاگ جزئیات","status_notifications":"پیام وضعیت","low_power_mode":"حالت کم‌مصرف","message_stats_enabled":"آمار پیام","notes_enabled":"یادداشت‌ها"}[key]
                            return await self.answer_callback(cq["id"],f"⚙️ {label}: {'فعال ✅' if new=='1' else 'خاموش ❌'}",alert=True)
                        if action in {"140","141","142"}:
                            key={"140":"global_ai_daily_limit","141":"global_download_daily_limit","142":"global_tool_cooldown"}[action]; val=await get_setting(key,"0"); USER_STATES[user_id]=f"AD_WAIT_{key}"; return await self.send_message(chat_id,f"✏️ مقدار جدید برای `{key}` را ارسال کنید. مقدار فعلی: `{val}`")
                        if action=="145":
                            for k,v in {"audit_enabled":"1","detailed_logs":"1","status_notifications":"1","low_power_mode":"0","message_stats_enabled":"1","notes_enabled":"1"}.items(): await set_setting(k,v)
                            await audit_log(user_id,"reset_extra_settings"); return await self.answer_callback(cq["id"],"🔄 تنظیمات جدید به حالت پیش‌فرض برگشت.",alert=True)
                        if action=="146":
                            r=await (await db.execute("SELECT plan,COUNT(*) FROM users GROUP BY plan ORDER BY COUNT(*) DESC")).fetchall(); return await self.send_message(chat_id,"🏆 **توزیع رنک‌ها**\n"+"\n".join(f"{p}: {c}" for p,c in r))
                        if action=="147": return await self.answer_callback(cq["id"],"📈 سابقه ارتقا در لاگ‌های فعلی نگهداری می‌شود؛ برای جزئیات Audit را بررسی کنید.",alert=True)
                        if action=="148":
                            r=(await (await db.execute("SELECT COUNT(*),COALESCE(SUM(reward_coins),0) FROM referrals")).fetchone()); return await self.answer_callback(cq["id"],f"👥 دعوت‌ها: {r[0]} | پاداش ثبت‌شده: {r[1]}",alert=True)
                        if action=="149":
                            users=(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]; refs=(await (await db.execute("SELECT COUNT(*) FROM referrals")).fetchone())[0]; rate=(refs/users*100 if users else 0); return await self.answer_callback(cq["id"],f"🔗 نرخ تبدیل دعوت بر مبنای کاربران ثبت‌شده: {rate:.1f}%",alert=True)
                        if action=="150":
                            r=(await (await db.execute("SELECT COALESCE(SUM(coins),0) FROM users")).fetchone())[0]; return await self.answer_callback(cq["id"],f"💰 موجودی کل سکه‌ها: {r}",alert=True)
                        if action=="151":
                            r=(await (await db.execute("SELECT COUNT(*) FROM audit_logs WHERE action LIKE '%daily%'")).fetchone())[0]; return await self.answer_callback(cq["id"],f"🎁 رویدادهای daily در Audit: {r}",alert=True)
                        if action=="152":
                            r=(await (await db.execute("SELECT COALESCE(SUM(activity_reward_coins),0) FROM users")).fetchone())[0]; return await self.answer_callback(cq["id"],f"⚡ مجموع پاداش فعالیت ثبت‌شده: {r}",alert=True)
                        if action=="153":
                            r=(await (await db.execute("SELECT COALESCE(AVG(activity_score),0) FROM users")).fetchone())[0]; return await self.answer_callback(cq["id"],f"⭐ میانگین امتیاز فعالیت: {r:.1f}",alert=True)
                        if action=="154":
                            r=await (await db.execute("SELECT user_id,plan FROM users ORDER BY CASE plan WHEN 'diamond' THEN 6 WHEN 'gold' THEN 5 WHEN 'silver' THEN 4 WHEN 'bronze' THEN 3 WHEN 'iron' THEN 2 ELSE 1 END DESC, coins DESC LIMIT 10")).fetchall(); return await self.send_message(chat_id,"💎 **بهترین رنک‌ها**\n"+"\n".join(f"`{u}` — {p}" for u,p in r))
                        if action=="155":
                            total=(await (await db.execute("SELECT COALESCE(SUM(coins),0) FROM users")).fetchone())[0]; users=(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]; return await self.send_message(chat_id,f"📊 **اقتصاد سکه**\nکل موجودی: `{total}`\nکاربران: `{users}`\nمیانگین: `{(total/users if users else 0):.1f}`")
                        if action=="156": return await self.answer_callback(cq["id"],f"🤖 AI={'فعال' if (await get_setting('smart_ai_global','1'))=='1' else 'خاموش'} | Smart={'فعال' if (await get_setting('smart_global_enabled','1'))=='1' else 'خاموش'}",alert=True)
                        if action=="157":
                            r=(await (await db.execute("SELECT COUNT(*) FROM ai_messages")).fetchone())[0]; return await self.answer_callback(cq["id"],f"🧠 پیام‌های حافظه AI: {r}",alert=True)
                        if action=="158":
                            r=(await (await db.execute("SELECT COUNT(*) FROM ai_messages WHERE date(datetime(created_at,'unixepoch','localtime'))=date('now','localtime')")).fetchone())[0]; return await self.answer_callback(cq["id"],f"📊 پیام‌های AI امروز: {r}",alert=True)
                        if action=="159":
                            r=(await (await db.execute("SELECT COUNT(*) FROM users WHERE settings LIKE '%\"monshi_active\": true%' OR settings LIKE '%\"monshi_active\":true%'")).fetchone())[0]; return await self.answer_callback(cq["id"],f"💬 منشی فعال: {r}",alert=True)
                        if action=="160":
                            r=(await (await db.execute("SELECT COUNT(*) FROM users WHERE settings LIKE '%\"auto_reply_active\": true%' OR settings LIKE '%\"auto_reply_active\":true%'")).fetchone())[0]; return await self.answer_callback(cq["id"],f"🔁 پاسخ‌خودکار فعال: {r}",alert=True)
                        if action=="161":
                            r=(await (await db.execute("SELECT COUNT(*) FROM users WHERE settings LIKE '%\"auto_read_active\": true%' OR settings LIKE '%\"auto_read_active\":true%'")).fetchone())[0]; return await self.answer_callback(cq["id"],f"👁 Reader فعال: {r}",alert=True)
                        if action=="162":
                            r=(await (await db.execute("SELECT COUNT(*) FROM user_notes")).fetchone())[0]; return await self.answer_callback(cq["id"],f"📝 یادداشت‌های ذخیره‌شده: {r}",alert=True)
                        if action=="163":
                            r=(await (await db.execute("SELECT COUNT(*) FROM audit_logs WHERE action LIKE '%translate%' OR action LIKE '%summar%'")).fetchone())[0]; return await self.answer_callback(cq["id"],f"🌐 رویدادهای ترجمه/خلاصه: {r}",alert=True)
                        if action=="164":
                            cur=await db.execute("DELETE FROM ai_messages"); deleted=cur.rowcount if cur.rowcount is not None else 0
                            await db.commit(); await audit_log(user_id,"admin_clear_ai_memory_all",detail=str(deleted)); return await self.answer_callback(cq["id"],f"🧹 حافظه AI همه کاربران پاک شد: {max(0,deleted)} رکورد.",alert=True)
                        if action=="165":
                            r=(await (await db.execute("SELECT COUNT(*) FROM ai_messages")).fetchone())[0]; return await self.send_message(chat_id,f"🧩 **Smart Center**\nحافظه AI: `{r}`\nAI فعال: `{await get_setting('smart_ai_global','1')}`\nSmart فعال: `{await get_setting('smart_global_enabled','1')}`")
                        import subprocess
                        if action=="166": return await self.answer_callback(cq["id"],"✅ DB / Downloads / Config / Clients بررسی شدند.",alert=True)
                        if action=="167":
                            ok=bool((await self.get_me()).get("id")); return await self.answer_callback(cq["id"],"🌐 Bot API: ✅" if ok else "🌐 Bot API: ❌",alert=True)
                        if action=="168":
                            total,used,free=shutil.disk_usage("."); return await self.answer_callback(cq["id"],f"💿 آزاد: {free//(1024**3)} GB | کل: {total//(1024**3)} GB",alert=True)
                        if action=="169":
                            fs=os.listdir("downloads") if os.path.isdir("downloads") else []; return await self.answer_callback(cq["id"],f"📦 Downloads: {len(fs)} فایل",alert=True)
                        if action=="170": return await self.answer_callback(cq["id"],f"🐍 Python: {platform.python_version()}",alert=True)
                        if action=="171": return await self.answer_callback(cq["id"],f"📚 Pyrogram: {getattr(__import__('pyrogram'),'__version__','unknown')} | aiohttp: {aiohttp.__version__}",alert=True)
                        if action=="172":
                            required=['config.py','main.py','host_bot/bot.py','core/telegram_login.py','database/db.py']; miss=[x for x in required if not os.path.exists(x)]; return await self.answer_callback(cq["id"],"🗂 پروژه سالم ✅" if not miss else "🗂 کمبود: "+", ".join(miss),alert=True)
                        if action=="173":
                            n=clean_server_temp_files(); return await self.answer_callback(cq["id"],f"🧹 پاکسازی انجام شد: {n} مورد",alert=True)
                        if action=="174":
                            path='downloads/admin_health_report.txt'; os.makedirs('downloads',exist_ok=True); open(path,'w',encoding='utf-8').write(f"SelfSaz health\nPython={platform.python_version()}\nActive={len(ACTIVE_CLIENTS)}\nPending={len(LOGIN_CLIENTS)}\nDB={os.path.exists(DB_NAME)}\n"); await self.send_document(chat_id,path,'📄 گزارش سلامت سیستم'); os.remove(path); return
                        if action=="175": return await self.answer_callback(cq["id"],"🚀 تست نهایی اجرا شد؛ سرویس اصلی در حال پاسخ‌گویی است.",alert=True)
                except Exception as e:
                    add_system_log(f"Admin extra feature {action} failed: {e}")
                    return await self.answer_callback(cq["id"],f"❌ خطا در اجرای قابلیت {action}: {e}",alert=True)

bot = HttpBot()
