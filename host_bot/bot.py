# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import aiosqlite
import json
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
            [{"text": "⚡️ تغییر پیشوند (.)", "callback_data": "menu_prefix"}, {"text": "🛠 جعبه ابزارها", "callback_data": "menu_tools"}]
        ]
        if is_admin:
            kb.append([{"text": "👑 پنل ویژه مدیریت ادمین", "callback_data": "menu_admin"}])
        kb.append([{"text": "🛑 خروج و پاک کردن اکانت", "callback_data": "btn_delete_account"}, {"text": "📢 کانال پشتیبانی", "url": CHANNEL_URL}])
        return {"inline_keyboard": kb}

    async def start(self):
        self.running = True
        offset = 0
        print("[+] HTTP Bot Control Dashboard Online.")
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

            # دستور اختصاصی ادمین
            if text == "/admin" and is_admin:
                return await self.show_admin_panel(chat_id)

            # دریافت سشن اولیه
            if USER_STATES.get(user_id) == "WAITING_SESSION":
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

            # دریافت متن پیام همگانی ادمین
            elif USER_STATES.get(user_id) == "WAITING_BROADCAST" and is_admin:
                USER_STATES.pop(user_id, None)
                await self.send_message(chat_id, "⏳ در حال ارسال پیام همگانی...")
                count = 0
                async with aiosqlite.connect(DB_NAME) as db:
                    cursor = await db.execute("SELECT user_id FROM users")
                    rows = await cursor.fetchall()
                for r in rows:
                    try:
                        await self.send_message(r[0], f"📢 **اطلاعیه مدیریت:**\n\n{text}")
                        count += 1
                        await asyncio.sleep(0.08)
                    except Exception:
                        pass
                return await self.send_message(chat_id, f"✅ پیام به {count} کاربر با موفقیت ارسال شد.")

            # دریافت آیدی کاربر برای مدیریت توسط ادمین
            elif USER_STATES.get(user_id) == "WAITING_TARGET_USER" and is_admin:
                USER_STATES.pop(user_id, None)
                if text.isdigit():
                    t_uid = int(text)
                    target_data = await self.get_user_db(t_uid)
                    if target_data:
                        TARGET_USER_ADMIN[user_id] = t_uid
                        return await self.show_target_user_card(chat_id, t_uid, target_data)
                    else:
                        return await self.send_message(chat_id, f"❌ کاربری با شناسه عددی `{t_uid}` در دیتابیس یافت نشد.")
                else:
                    return await self.send_message(chat_id, "❌ شناسه عددی نامعتبر است.")

        # ----------------- دکمه‌ها و رویدادهای شیشه‌ای -----------------
        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            user_id = cq.get("from", {}).get("id", chat_id)
            msg_id = cq["message"]["message_id"]
            data = cq.get("data")
            is_admin = (user_id == ADMIN_ID)

            # دکمه‌های عمومی که بدون ثبت‌نام هم مجاز هستند
            allowed_unregistered = ["btn_submit_session", "back_home"]

            # بررسی ادمین بودن
            is_admin_action = is_admin and (data.startswith("admin_") or data in ["menu_admin"])

            # 🛡 لایه محافظتی: قطع دسترسی تمام دکمه‌ها در چت‌های قبلی پس از حذف سلف
            if not is_admin_action and data not in allowed_unregistered:
                u_check = await self.get_user_db(user_id)
                if not u_check:
                    await self.answer_callback(cq["id"], "❌ سلف شما حذف شده است و دیگر این دکمه‌ها فعال نیستند!", alert=True)
                    kb_reconnect = {
                        "inline_keyboard": [
                            [{"text": "🔑 اتصال مجدد سلف (ارسال سشن)", "callback_data": "btn_submit_session"}],
                            [{"text": "📢 کانال پشتیبانی", "url": CHANNEL_URL}]
                        ]
                    }
                    return await self.edit_message(chat_id, msg_id, "🛑 **سلف شما قبلاً حذف شده است.**\nدکمه‌های این پیام منقضی شده‌اند. برای راه‌اندازی روی دکمه زیر بزنید:", reply_markup=kb_reconnect)

            # ارسال سشن
            if data == "btn_submit_session":
                USER_STATES[user_id] = "WAITING_SESSION"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "back_home"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📱 کد استرینگ سشن (String Session) اکانت خود را در چت بفرستید:", reply_markup=kb)

            # ۱. دکمه‌های وضعیت سلف
            elif data == "btn_turn_off":
                await stop_single_client(user_id)
                await self.answer_callback(cq["id"], "🛑 سلف خاموش شد و نام اصلی بازگشت.")
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
                await self.answer_callback(cq["id"], "اکانت و سلف شما با موفقیت حذف شد.", alert=True)
                kb = {"inline_keyboard": [[{"text": "🔑 اتصال مجدد سلف", "callback_data": "btn_submit_session"}]]}
                return await self.edit_message(chat_id, msg_id, "🛑 **سلف شما به طور کامل متوقف و حذف شد.**\nتمامی دکمه‌های پیام‌های قبلی شما باطل شدند.", reply_markup=kb)

            # ۲. نرخ لحظه‌ای ارز، طلا، سکه و کریپتو
            elif data in ["menu_rates", "refresh_rates"]:
                await self.answer_callback(cq["id"], "🔄 درحال استعلام مظنه زنده بازار...")
                rates_data = await fetch_live_market_data()
                market_text = format_market_display(rates_data)
                kb = {
                    "inline_keyboard": [
                        [{"text": "🔄 به‌روزرسانی لحظه‌ای نرخ‌ها", "callback_data": "refresh_rates"}],
                        [{"text": "🔙 بازگشت به منوی اصلی", "callback_data": "back_dashboard"}]
                    ]
                }
                return await self.edit_message(chat_id, msg_id, market_text, reply_markup=kb)

            # ۳. ساعت روی اسم با ۱۰ فونت
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
                txt = (
                    "⏰ **بخش ساعت خودکار روی نام اکانت (۱۰ فونت)**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"وضعیت فعلی: `{'روشن 🟢' if t_on else 'خاموش 🔴'}`\n\n"
                    "⚡️ با خاموش کردن ساعت، نام شما بلافاصله به اسم اصلی‌تان بازمی‌گردد."
                )
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "toggle_timename":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ سلف شما خاموش است؛ ابتدا آن را روشن کنید.", alert=True)
                if cli.timename_active:
                    cli.timename_active = False
                    if cli.timename_task:
                        cli.timename_task.cancel()
                    await restore_original_name(cli)
                    await self.update_setting_db(user_id, "timename_active", False)
                    await self.answer_callback(cq["id"], "🛑 ساعت خاموش شد و نام قبلی بازگشت.")
                else:
                    cli.timename_active = True
                    await self.update_setting_db(user_id, "timename_active", True)
                    cli.timename_task = asyncio.create_task(timename_loop(cli, cli.original_name, cli.settings.get("timename_font", 1)))
                    await self.answer_callback(cq["id"], "🟢 ساعت روی اسم روشن شد!")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_timename"}})

            elif data.startswith("font_"):
                f_id = int(data.split("_")[1])
                await self.update_setting_db(user_id, "timename_font", f_id)
                await self.answer_callback(cq["id"], f"✅ فونت {f_id} فعال شد.", alert=True)

            # ۴. منشی هوشمند
            elif data == "menu_monshi":
                cli = ACTIVE_CLIENTS.get(user_id)
                m_on = getattr(cli, "monshi_active", False) if cli else False
                st_text = "خاموش کردن منشی 🔴" if m_on else "روشن کردن منشی 🟢"
                kb = {
                    "inline_keyboard": [
                        [{"text": st_text, "callback_data": "toggle_monshi"}],
                        [{"text": "🔄 ریست کردن حافظه منشی (تست مجدد)", "callback_data": "reset_monshi"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = f"🤖 **منشی پاسخگوی خودکار پی‌وی**\n\nوضعیت: `{'فعال و آماده 🟢' if m_on else 'غیرفعال 🔴'}`"
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "toggle_monshi":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ ابتدا سلف را روشن کنید.", alert=True)
                cli.monshi_active = not getattr(cli, "monshi_active", False)
                await self.update_setting_db(user_id, "monshi_active", cli.monshi_active)
                await self.answer_callback(cq["id"], f"منشی: {'روشن شد 🟢' if cli.monshi_active else 'خاموش شد 🔴'}")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_monshi"}})

            elif data == "reset_monshi":
                cli = ACTIVE_CLIENTS.get(user_id)
                if cli and hasattr(cli, "monshi_replied_users"):
                    cli.monshi_replied_users.clear()
                await self.answer_callback(cq["id"], "🔄 حافظه منشی خالی شد. پیام تست بفرستید!", alert=True)

# ۵. پاکسازی پیام‌ها
            elif data == "menu_cleaner":
                cli = ACTIVE_CLIENTS.get(user_id)
                c_on = getattr(cli, "cleaner_active", False) if cli else False
                delay = getattr(cli, "cleaner_delay", 20) if cli else 20
                st_text = "خاموش کردن پاکسازی 🔴" if c_on else "روشن کردن پاکسازی 🟢"
                kb = {
                    "inline_keyboard": [
                        [{"text": st_text, "callback_data": "toggle_cleaner"}],
                        [{"text": "⏱ ۱۰ ثانیه", "callback_data": "sec_10"}, {"text": "⏱ ۳۰ ثانیه", "callback_data": "sec_30"}, {"text": "⏱ ۶۰ ثانیه", "callback_data": "sec_60"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = f"🗑 **پاکسازی خودکار پیام‌ها**\nوضعیت: `{'روشن 🟢' if c_on else 'خاموش 🔴'}` | تایمر: `{delay}` ثانیه"
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "toggle_cleaner":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ ابتدا سلف را روشن کنید.", alert=True)
                cli.cleaner_active = not getattr(cli, "cleaner_active", False)
                await self.update_setting_db(user_id, "cleaner_active", cli.cleaner_active)
                await self.answer_callback(cq["id"], f"پاکسازی خودکار: {'فعال شد 🟢' if cli.cleaner_active else 'خاموش شد 🔴'}")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_cleaner"}})

            elif data.startswith("sec_"):
                sec = int(data.split("_")[1])
                await self.update_setting_db(user_id, "cleaner_delay", sec)
                await self.answer_callback(cq["id"], f"⏱ تایمر روی {sec} ثانیه ذخیره شد!", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "menu_cleaner"}})

            # ۶. امنیت و دوستان و دشمنان
            elif data == "menu_relations":
                async with aiosqlite.connect(DB_NAME) as db:
                    c1 = await db.execute("SELECT COUNT(*) FROM relations WHERE owner_id = ? AND type = 'enemy'", (user_id,))
                    ec = (await c1.fetchone())[0]
                    c2 = await db.execute("SELECT COUNT(*) FROM relations WHERE owner_id = ? AND type = 'friend'", (user_id,))
                    fc = (await c2.fetchone())[0]
                kb = {
                    "inline_keyboard": [
                        [{"text": f"🗑 پاکسازی دشمنان ({ec})", "callback_data": "clear_enemies"}, {"text": f"🗑 پاکسازی دوستان ({fc})", "callback_data": "clear_friends"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = f"🛡 **داشبورد امنیت و روابط**\n⚔️ دشمنان فعال: `{ec}` نفر | ❤️ دوستان ویژه: `{fc}` نفر"
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "clear_enemies":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE owner_id = ? AND type = 'enemy'", (user_id,))
                    await db.commit()
                await self.answer_callback(cq["id"], "🗑 لیست دشمنان خالی شد.", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "menu_relations"}})

            elif data == "clear_friends":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE owner_id = ? AND type = 'friend'", (user_id,))
                    await db.commit()
                await self.answer_callback(cq["id"], "🗑 لیست دوستان خالی شد.", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "menu_relations"}})

            # ۷. پیشوند دستورات
            elif data == "menu_prefix":
                u = await self.get_user_db(user_id)
                curr_p = u[3] if u else "."
                kb = {
                    "inline_keyboard": [
                        [{"text": "نقطه (.)", "callback_data": "set_dot"}, {"text": "اسلش (/)", "callback_data": "set_slash"}, {"text": "تعجب (!)", "callback_data": "set_excl"}],
                        [{"text": "بدون علامت (متن خام)", "callback_data": "set_none"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, f"⚡️ پیشوند فعلی: `{curr_p}`\nیکی را انتخاب کنید:", reply_markup=kb)

            elif data in ["set_dot", "set_slash", "set_excl", "set_none"]:
                mapping = {"set_dot": ".", "set_slash": "/", "set_excl": "!", "set_none": ""}
                new_p = mapping[data]
                is_on = 0 if data == "set_none" else 1
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET prefix = ?, prefix_enabled = ? WHERE user_id = ?", (new_p, is_on, user_id))
                    await db.commit()
                if user_id in ACTIVE_CLIENTS:
                    ACTIVE_CLIENTS[user_id].custom_prefix = new_p
                    ACTIVE_CLIENTS[user_id].prefix_enabled = bool(is_on)
                await self.answer_callback(cq["id"], "✅ پیشوند سلف تغییر یافت.", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "menu_prefix"}})

            # ۸. جعبه ابزارها
            elif data == "menu_tools":
                kb = {"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]]}
                await self.answer_callback(cq["id"])
                txt = "🛠 **ابزارهای سلف‌بات:**\n• ارسال لینک ویدیو یوتیوب جهت دانلود\n• ریپلای روی ویدیو جهت ساخت ویدیو گرد\n• ریپلای روی پیام‌های کانال‌های قفل جهت دانلود و سیو"
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            # ================== پنل فوق‌حرفه‌ای ادمین ==================
            elif data == "menu_admin" and is_admin:
                await self.answer_callback(cq["id"])
                return await self.show_admin_panel(chat_id, msg_id)

            elif data == "admin_broadcast" and is_admin:
                USER_STATES[user_id] = "WAITING_BROADCAST"
                await self.answer_callback(cq["id"])
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "menu_admin"}]]}
                return await self.edit_message(chat_id, msg_id, "📝 **ارسال همگانی:** پیام خود را تایپ و ارسال کنید تا برای همه کاربران فرستاده شود:", reply_markup=kb)

            elif data == "admin_find_user" and is_admin:
                USER_STATES[user_id] = "WAITING_TARGET_USER"
                await self.answer_callback(cq["id"])
                kb = {"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "menu_admin"}]]}
                return await self.edit_message(chat_id, msg_id, "🔍 **شناسه عددی (User ID)** کاربر مورد نظر را در چت ارسال کنید:", reply_markup=kb)

            elif data == "admin_gift_coins" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET coins = coins + 50")
                    await db.commit()
                await self.answer_callback(cq["id"], "🎁 به تمام کاربران ۵۰ سکه هدیه داده شد!", alert=True)
                return await self.show_admin_panel(chat_id, msg_id)

            elif data == "admin_restart_all" and is_admin:
                await self.answer_callback(cq["id"], "⏳ در حال ریستارت همگانی سلف‌ها...", alert=True)
                restarted = await restart_all_clients()
                await self.send_message(chat_id, f"🔄 **ریستارت همگانی:** تعداد `{restarted}` سلف آنلاین با موفقیت ریستارت شدند.")
                return await self.show_admin_panel(chat_id, msg_id)

            elif data == "admin_stop_all" and is_admin:
                stopped = await stop_all_clients()
                await self.answer_callback(cq["id"], f"🛑 تمامی {stopped} سلف فعال خاموش شدند.", alert=True)
                return await self.show_admin_panel(chat_id, msg_id)

            elif data == "admin_clean_cache" and is_admin:
                d = clean_server_temp_files()
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("VACUUM")
                    await db.commit()
                await self.answer_callback(cq["id"], f"🧹 سرور بهینه‌سازی شد و {d} فایل کش پاک شد.", alert=True)
                return await self.show_admin_panel(chat_id, msg_id)

            # عملیات روی کاربر انتخابی توسط ادمین
            elif data == "admin_toggle_vip" and is_admin:
                t_uid = TARGET_USER_ADMIN.get(user_id)
                if t_uid:
                    u_data = await self.get_user_db(t_uid)
                    new_vip = 0 if u_data[2] else 1
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("UPDATE users SET is_vip = ? WHERE user_id = ?", (new_vip, t_uid))
                        await db.commit()
                    await self.answer_callback(cq["id"], f"وضعیت VIP کاربر به {new_vip} تغییر یافت.", alert=True)
                    target_data = await self.get_user_db(t_uid)
                    return await self.show_target_user_card(chat_id, t_uid, target_data, msg_id)

            elif data == "admin_add_100_coins" and is_admin:
                t_uid = TARGET_USER_ADMIN.get(user_id)
                if t_uid:
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("UPDATE users SET coins = coins + 100 WHERE user_id = ?", (t_uid,))
                        await db.commit()
                    await self.answer_callback(cq["id"], "💰 ۱۰۰ سکه به کاربر اضافه شد.", alert=True)
                    target_data = await self.get_user_db(t_uid)
                    return await self.show_target_user_card(chat_id, t_uid, target_data, msg_id)

            elif data == "admin_force_stop" and is_admin:
                t_uid = TARGET_USER_ADMIN.get(user_id)
                if t_uid:
                    await stop_single_client(t_uid)
                    await self.answer_callback(cq["id"], "🛑 سلف کاربر به صورت اجباری متوقف شد.", alert=True)
                    target_data = await self.get_user_db(t_uid)
                    return await self.show_target_user_card(chat_id, t_uid, target_data, msg_id)

            elif data == "admin_ban_user" and is_admin:
                t_uid = TARGET_USER_ADMIN.get(user_id)
                if t_uid:
                    await stop_single_client(t_uid)
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("DELETE FROM users WHERE user_id = ?", (t_uid,))
                        await db.execute("DELETE FROM relations WHERE owner_id = ?", (t_uid,))
                        await db.commit()
                    TARGET_USER_ADMIN.pop(user_id, None)
                    await self.answer_callback(cq["id"], "🗑 کاربر و سلف وی کلاً از سرور حذف و بن شدند.", alert=True)
                    return await self.show_admin_panel(chat_id, msg_id)

            # بازگشت‌ها
            elif data == "back_dashboard":
                is_online = user_id in ACTIVE_CLIENTS
                u = await self.get_user_db(user_id)
                await self.answer_callback(cq["id"])
                p_text = (
                    "👑 **داشبورد مدیریت یکپارچه سلف‌بات**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 شناسه شما: `{user_id}`\n"
                    f"⚡️ وضعیت اتصال: {'فعال و روشن 🟢' if is_online else 'خاموش 🔴'}\n"
                    f"💰 موجودی: `{u[1]}` سکه | پلن: {'VIP 💎 (نامحدود)' if u[2] else 'عادی 👤'}\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "👇 کنترل تمام قابلیت‌ها ۱۰۰٪ دکمه‌ای است؛ انتخاب کنید:"
                )
                return await self.edit_message(chat_id, msg_id, p_text, reply_markup=self.get_main_dashboard_kb(is_online, is_admin))

            elif data == "back_home":
                USER_STATES.pop(user_id, None)
                kb = {"inline_keyboard": [[{"text": "🔑 اتصال اکانت (ارسال سشن)", "callback_data": "btn_submit_session"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "👋 لطفاً انتخاب کنید:", reply_markup=kb)

    # ------------------ متدهای پنل مدیریت کل ادمین ------------------
    async def show_admin_panel(self, chat_id, msg_id=None):
        async with aiosqlite.connect(DB_NAME) as db:
            c1 = await db.execute("SELECT COUNT(*) FROM users")
            total_users = (await c1.fetchone())[0]
            c2 = await db.execute("SELECT COUNT(*) FROM users WHERE is_vip = 1")
            vip_users = (await c2.fetchone())[0]

        online_selfs = len(ACTIVE_CLIENTS)
        kb = {
            "inline_keyboard": [
                [{"text": "🔍 جستجو و مدیریت کاربر", "callback_data": "admin_find_user"}, {"text": "📢 ارسال پیام همگانی", "callback_data": "admin_broadcast"}],
                [{"text": "🎁 هدیه ۵۰ سکه به همه", "callback_data": "admin_gift_coins"}, {"text": "🔄 ریستارت همگانی سلف‌ها", "callback_data": "admin_restart_all"}],
                [{"text": "🛑 خاموش‌سازی همگانی", "callback_data": "admin_stop_all"}, {"text": "🧹 پاکسازی کش و دیتابیس", "callback_data": "admin_clean_cache"}],
                [{"text": "🔙 بازگشت به منوی کاربری", "callback_data": "back_dashboard"}]
            ]
        }
        admin_txt = (
            "👑 **مرکز کنترل و مدیریت کل سرور (Super Admin)**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 کل کاربران ثبت‌شده: `{total_users}` نفر\n"
            f"⚡️ سلف‌های روشن در لحظه: `{online_selfs}` اکانت\n"
            f"💎 اعضای ویژه (VIP): `{vip_users}` نفر | عادی: `{total_users - vip_users}` نفر\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 عملیات سیستمی مورد نظر را انتخاب کنید:"
        )
        if msg_id:
            return await self.edit_message(chat_id, msg_id, admin_txt, reply_markup=kb)
        return await self.send_message(chat_id, admin_txt, reply_markup=kb)

    async def show_target_user_card(self, chat_id, t_uid, target_data, msg_id=None):
        is_online = t_uid in ACTIVE_CLIENTS
        kb = {
            "inline_keyboard": [
                [{"text": f"💎 تغییر وضعیت VIP (فعلی: {'بله' if target_data[2] else 'خیر'})", "callback_data": "admin_toggle_vip"}],
                [{"text": "➕ افزایش ۱۰۰ سکه", "callback_data": "admin_add_100_coins"}, {"text": "🛑 خاموش کردن سلف", "callback_data": "admin_force_stop"}],
                [{"text": "🗑 حذف و بن کاربر از سیستم", "callback_data": "admin_ban_user"}],
                [{"text": "🔙 بازگشت به پنل ادمین", "callback_data": "menu_admin"}]
            ]
        }
        card = (
            f"👤 **مدیریت کاربر:** `{t_uid}`\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡️ وضعیت اتصال سلف: `{'آنلاین و متصل 🟢' if is_online else 'خاموش 🔴'}`\n"
            f"💰 موجودی سکه: `{target_data[1]}` | پلن: `{'VIP 💎' if target_data[2] else 'عادی'}`\n"
            f"🔘 پیشوند تنظیم شده: `{target_data[3]}`\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 دستور مورد نظر را اعمال کنید:"
        )
        if msg_id:
            return await self.edit_message(chat_id, msg_id, card, reply_markup=kb)
        return await self.send_message(chat_id, card, reply_markup=kb)

bot = HttpBot()
