# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import aiosqlite
import json
from config import BOT_TOKEN, DB_NAME, ADMIN_ID
from core.manager import start_single_client, stop_single_client, ACTIVE_CLIENTS, timename_loop, restore_original_name
from plugins.fun_crypto import fetch_live_market_data, format_market_display

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
CHANNEL_URL = "https://t.me/Vip_Viro"
USER_STATES = {}

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
        # ----------------- پیام‌های ورودی -----------------
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg.get("from", {}).get("id", chat_id)
            text = msg.get("text", "").strip()

            if text in ["/start", "/panel"]:
                USER_STATES.pop(user_id, None)
                u = await self.get_user_db(user_id)
                is_admin = (user_id == ADMIN_ID)
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

            elif text == "/admin" and user_id == ADMIN_ID:
                return await self.open_admin_panel(chat_id)

            # دریافت سشن اکانت
            if USER_STATES.get(user_id) == "WAITING_SESSION":
                if len(text) > 40:
                    await self.send_message(chat_id, "⏳ در حال اتصال آنی سلف به سرور...")
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT OR REPLACE INTO users (user_id, session_string, coins, prefix, prefix_enabled, settings) VALUES (?, ?, 100, '.', 1, '{}')", (user_id, text))
                        await db.commit()

                    started, err = await start_single_client(user_id, text)
                    USER_STATES.pop(user_id, None)

                    if started:
                        await self.send_message(chat_id, "🎉 **سلف شما با موفقیت روشن شد!** اکنون همه کارها را با دکمه‌ها کنترل کنید:", reply_markup=self.get_main_dashboard_kb(True, user_id == ADMIN_ID))
                    else:
                        await self.send_message(chat_id, f"❌ خطا در روشن شدن:\n`{err}`")
                else:
                    await self.send_message(chat_id, "❌ استرینگ سشن ارسالی نامعتبر است.")

            # ارسال همگانی ادمین
            elif USER_STATES.get(user_id) == "WAITING_BROADCAST" and user_id == ADMIN_ID:
                USER_STATES.pop(user_id, None)
                await self.send_message(chat_id, "⏳ در حال ارسال پیام به تمام کاربران...")
                count = 0
                async with aiosqlite.connect(DB_NAME) as db:
                    cursor = await db.execute("SELECT user_id FROM users")
                    rows = await cursor.fetchall()
                for r in rows:
                    try:
                        await self.send_message(r[0], f"📢 **پیام مدیریت:**\n\n{text}")
                        count += 1
                        await asyncio.sleep(0.1)
                    except Exception:
                        pass
                return await self.send_message(chat_id, f"✅ پیام با موفقیت به {count} کاربر ارسال گردید.")

        # ----------------- دکمه‌ها و کلیک‌ها -----------------
        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            user_id = cq.get("from", {}).get("id", chat_id)
            msg_id = cq["message"]["message_id"]
            data = cq.get("data")
            is_admin = (user_id == ADMIN_ID)

            if data == "btn_submit_session":
                USER_STATES[user_id] = "WAITING_SESSION"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "back_home"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📱 استرینگ سشن (String Session) اکانت خود را بفرستید:", reply_markup=kb)

            # کنترل وضعیت سلف
            elif data == "btn_turn_off":
                await stop_single_client(user_id)
                await self.answer_callback(cq["id"], "🛑 سلف خاموش شد و نام اصلی بازگردانده شد.")
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
                    await db.commit()
                await self.answer_callback(cq["id"], "اکانت و سلف شما پاک شد.", alert=True)
                kb = {"inline_keyboard": [[{"text": "🔑 اتصال مجدد", "callback_data": "btn_submit_session"}]]}
                return await self.edit_message(chat_id, msg_id, "🛑 سلف شما متوقف و حذف شد.", reply_markup=kb)

            # نرخ لحظه‌ای ارز، طلا و رمزارز
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

            # منوی ساعت روی اسم با ۱۰ فونت
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
                    "⚡️ **ویژگی هوشمند:** به محض خاموش کردن ساعت، نام اکانت شما دقیقاً به همان اسم قبلی‌تان برمی‌گردد!"
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
                    await self.answer_callback(cq["id"], "🛑 ساعت خاموش شد و نام قبلی شما بازگشت.")
                else:
                    cli.timename_active = True
                    await self.update_setting_db(user_id, "timename_active", True)
                    cli.timename_task = asyncio.create_task(timename_loop(cli, cli.original_name, cli.settings.get("timename_font", 1)))
                    await self.answer_callback(cq["id"], "🟢 ساعت روی اسم با موفقیت روشن شد!")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_timename"}})

            elif data.startswith("font_"):
                f_id = int(data.split("_")[1])
                await self.update_setting_db(user_id, "timename_font", f_id)
                await self.answer_callback(cq["id"], f"✅ فونت {f_id} انتخاب شد.", alert=True)

            # منوی منشی هوشمند
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
                txt = (
                    "🤖 **منشی پاسخگوی خودکار پی‌وی**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"وضعیت: `{'فعال و آماده پاسخ 🟢' if m_on else 'غیرفعال 🔴'}`\n\n"
                    "با روشن بودن این بخش، به محض ارسال پیام از طرف هر فرد در چت خصوصی، منشی پاسخی محترمانه ارسال می‌کند."
                )
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
                await self.answer_callback(cq["id"], "🔄 حافظه منشی پاک شد؛ اکنون می‌توانید بلافاصله تست کنید.", alert=True)

            # پاکسازی خودکار
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
                txt = f"🗑 **سیستم پاکسازی پیام‌های ارسالی**\nوضعیت: `{'روشن 🟢' if c_on else 'خاموش 🔴'}` | تاخیر: `{delay}` ثانیه"
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

# امنیت و روابط
            elif data == "menu_relations":
                async with aiosqlite.connect(DB_NAME) as db:
                    c1 = await db.execute("SELECT COUNT(*) FROM relations WHERE owner_id = ? AND type = 'enemy'", (user_id,))
                    ec = (await c1.fetchone())[0]
                    c2 = await db.execute("SELECT COUNT(*) FROM relations WHERE owner_id = ? AND type = 'friend'", (user_id,))
                    fc = (await c2.fetchone())[0]
                kb = {
                    "inline_keyboard": [
                        [{"text": f"🗑 پاکسازی کامل دشمنان ({ec})", "callback_data": "clear_enemies"}, {"text": f"🗑 پاکسازی کامل دوستان ({fc})", "callback_data": "clear_friends"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = f"🛡 **داشبورد امنیت و روابط**\n⚔️ دشمنان: `{ec}` نفر | ❤️ دوستان: `{fc}` نفر"
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

            # پیشوند دستورات
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

            # ابزارها
            elif data == "menu_tools":
                kb = {"inline_keyboard": [[{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]]}
                await self.answer_callback(cq["id"])
                txt = "🛠 **ابزارهای سلف‌بات:**\n• ارسال لینک ویدیو یوتیوب جهت دانلود\n• ریپلای روی ویدیو جهت ساخت ویدیو گرد\n• ریپلای روی پیام‌های کانال‌های قفل جهت دانلود و سیو"
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            # پنل اختصاصی ادمین
            elif data == "menu_admin" and is_admin:
                await self.answer_callback(cq["id"])
                async with aiosqlite.connect(DB_NAME) as db:
                    c1 = await db.execute("SELECT COUNT(*) FROM users")
                    total_users = (await c1.fetchone())[0]
                    c2 = await db.execute("SELECT COUNT(*) FROM users WHERE is_vip = 1")
                    vip_users = (await c2.fetchone())[0]

                online_selfs = len(ACTIVE_CLIENTS)
                kb = {
                    "inline_keyboard": [
                        [{"text": "📢 ارسال پیام همگانی", "callback_data": "admin_broadcast"}],
                        [{"text": "💎 ارتقای خود به VIP نامحدود", "callback_data": "admin_make_vip"}, {"text": "💰 شارژ ۵۰۰ سکه به اکانت خود", "callback_data": "admin_add_coins"}],
                        [{"text": "🔙 بازگشت به منو", "callback_data": "back_dashboard"}]
                    ]
                }
                admin_txt = (
                    "👑 **پنل مدیریت کل سرور سلف‌ساز (ویژه مدیر)**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👥 کل کاربران دیتابیس: `{total_users}` نفر\n"
                    f"⚡️ سلف‌های آنلاین در لحظه: `{online_selfs}` اکانت\n"
                    f"💎 اعضای پلن ویژه (VIP): `{vip_users}` نفر\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "👇 عملیات مدیریتی مورد نظر را انتخاب کنید:"
                )
                return await self.edit_message(chat_id, msg_id, admin_txt, reply_markup=kb)

            elif data == "admin_broadcast" and is_admin:
                USER_STATES[user_id] = "WAITING_BROADCAST"
                await self.answer_callback(cq["id"])
                kb = {"inline_keyboard": [[{"text": "🔙 لغو", "callback_data": "menu_admin"}]]}
                return await self.edit_message(chat_id, msg_id, "📝 لطفاً متن پیام همگانی را ارسال کنید تا برای همه کاربران فرستاده شود:", reply_markup=kb)

            elif data == "admin_make_vip" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET is_vip = 1 WHERE user_id = ?", (user_id,))
                    await db.commit()
                await self.answer_callback(cq["id"], "💎 اکانت شما به پلن VIP دائمی ارتقا یافت!", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "menu_admin"}})

            elif data == "admin_add_coins" and is_admin:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET coins = coins + 500 WHERE user_id = ?", (user_id,))
                    await db.commit()
                await self.answer_callback(cq["id"], "💰 ۵۰۰ سکه به اکانت شما اضافه شد!", alert=True)
                return await self.handle_update({"callback_query": {**cq, "data": "menu_admin"}})

            # بازگشت به داشبورد
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

bot = HttpBot()
