# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import aiosqlite
import json
from config import BOT_TOKEN, DB_NAME
from core.manager import start_single_client, stop_single_client, ACTIVE_CLIENTS, timename_loop
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

    def get_main_dashboard_kb(self, is_online):
        status_btn = "🟢 وضعیت سلف: روشن (خاموش کردن)" if is_online else "🔴 وضعیت سلف: خاموش (روشن کردن)"
        toggle_cb = "btn_turn_off" if is_online else "btn_turn_on"
        return {
            "inline_keyboard": [
                [{"text": status_btn, "callback_data": toggle_cb}],
                [{"text": "🔄 راه‌اندازی مجدد سلف", "callback_data": "btn_restart"}, {"text": "📈 نرخ لحظه‌ای ارز و طلا", "callback_data": "menu_rates"}],
                [{"text": "⏰ ساعت روی اسم", "callback_data": "menu_timename"}, {"text": "🤖 منشی هوشمند", "callback_data": "menu_monshi"}],
                [{"text": "🗑 پاکسازی خودکار پیام‌ها", "callback_data": "menu_cleaner"}, {"text": "🛡 لیست دوستان و دشمنان", "callback_data": "menu_relations"}],
                [{"text": "⚡️ تغییر پیشوند (.)", "callback_data": "menu_prefix"}, {"text": "🛠 جعبه ابزارها", "callback_data": "menu_tools"}],
                [{"text": "🛑 خروج و پاک کردن اکانت", "callback_data": "btn_delete_account"}, {"text": "📢 کانال پشتیبانی", "url": CHANNEL_URL}]
            ]
        }

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
        # ----------------- پردازش پیام‌ها -----------------
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg.get("from", {}).get("id", chat_id)
            text = msg.get("text", "").strip()

            if text == "/start":
                USER_STATES.pop(user_id, None)
                u = await self.get_user_db(user_id)
                if u:
                    is_online = user_id in ACTIVE_CLIENTS
                    p_text = (
                        "👑 **داشبورد مدیریت یکپارچه سلف‌بات**\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🆔 شناسه شما: `{user_id}`\n"
                        f"⚡️ وضعیت اتصال: {'فعال و روشن 🟢' if is_online else 'خاموش 🔴'}\n"
                        f"💰 اعتبار: `{u[1]}` سکه | پلن: {'VIP 💎' if u[2] else 'عادی'}\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        "👇 همه‌چیز کاملاً دکمه‌ای است؛ بخش دلخواه را انتخاب کنید:"
                    )
                    return await self.send_message(chat_id, p_text, reply_markup=self.get_main_dashboard_kb(is_online))
                else:
                    kb = {
                        "inline_keyboard": [
                            [{"text": "🔑 اتصال اکانت (ارسال سشن)", "callback_data": "btn_submit_session"}],
                            [{"text": "📢 کانال اطلاع‌رسانی", "url": CHANNEL_URL}]
                        ]
                    }
                    return await self.send_message(chat_id, "👋 **به سیستم مدیریت سلف‌ساز خوش آمدید!**\n\nجهت راه‌اندازی و اتصال سلف خود روی دکمه زیر کلیک کنید:", reply_markup=kb)

            # ارسال رشته سشن تنها در مرحله ثبت اولیه اکانت
            if USER_STATES.get(user_id) == "WAITING_SESSION":
                if len(text) > 40:
                    await self.send_message(chat_id, "⏳ در حال اتصال آنی سلف به سرور...")
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT OR REPLACE INTO users (user_id, session_string, coins, prefix, prefix_enabled, settings) VALUES (?, ?, 100, '.', 1, '{}')", (user_id, text))
                        await db.commit()

                    started, err = await start_single_client(user_id, text)
                    USER_STATES.pop(user_id, None)

                    if started:
                        await self.send_message(chat_id, "🎉 **سلف شما با موفقیت روشن شد!** اکنون همه کارها را با دکمه‌ها کنترل کنید:", reply_markup=self.get_main_dashboard_kb(True))
                    else:
                        await self.send_message(chat_id, f"❌ خطا در روشن شدن:\n`{err}`")
                else:
                    await self.send_message(chat_id, "❌ استرینگ سشن ارسالی نامعتبر است.")

        # ----------------- دکمه‌ها و کلیک‌ها -----------------
        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            user_id = cq.get("from", {}).get("id", chat_id)
            msg_id = cq["message"]["message_id"]
            data = cq.get("data")

            if data == "btn_submit_session":
                USER_STATES[user_id] = "WAITING_SESSION"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "back_home"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📱 استرینگ سشن (String Session) اکانت خود را در چت بفرستید:", reply_markup=kb)

            # ۱. دکمه‌های روشن / خاموش و ریستارت
            elif data == "btn_turn_off":
                await stop_single_client(user_id)
                await self.answer_callback(cq["id"], "🛑 سلف خاموش شد.")
                return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (خاموش 🔴)**", reply_markup=self.get_main_dashboard_kb(False))

            elif data == "btn_turn_on":
                u = await self.get_user_db(user_id)
                if u:
                    ok, err = await start_single_client(user_id, u[0])
                    if ok:
                        await self.answer_callback(cq["id"], "🟢 سلف روشن شد!")
                        return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (روشن 🟢)**", reply_markup=self.get_main_dashboard_kb(True))
                    else:
                        await self.answer_callback(cq["id"], f"خطا در روشن شدن:\n{err}", alert=True)

            elif data == "btn_restart":
                u = await self.get_user_db(user_id)
                if u:
                    await stop_single_client(user_id)
                    await asyncio.sleep(1)
                    await start_single_client(user_id, u[0])
                    await self.answer_callback(cq["id"], "🔄 سلف ریستارت شد!", alert=True)
                    return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (روشن 🟢)**", reply_markup=self.get_main_dashboard_kb(True))

            elif data == "btn_delete_account":
                await stop_single_client(user_id)
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                    await db.execute("DELETE FROM relations WHERE owner_id = ?", (user_id,))
                    await db.commit()
                await self.answer_callback(cq["id"], "اکانت و سلف شما پاک شد.", alert=True)
                kb = {"inline_keyboard": [[{"text": "🔑 اتصال مجدد", "callback_data": "btn_submit_session"}]]}
                return await self.edit_message(chat_id, msg_id, "🛑 سلف شما متوقف و حذف شد.", reply_markup=kb)

            # ۲. استعلام زنده و واقعی نرخ ارز و کریپتو (با دکمه رفرش)
            elif data == "menu_rates" or data == "refresh_rates":
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

            # ۳. ساعت روی اسم با دکمه و انتخاب فونت
            elif data == "menu_timename":
                cli = ACTIVE_CLIENTS.get(user_id)
                t_on = getattr(cli, "timename_active", False) if cli else False
                st_text = "خاموش کردن ساعت 🔴" if t_on else "روشن کردن ساعت 🟢"
                kb = {
                    "inline_keyboard": [
                        [{"text": st_text, "callback_data": "toggle_timename"}],
                        [{"text": "فونت ۱ (𝟎𝟎:𝟎𝟎)", "callback_data": "font_1"}, {"text": "فونت ۲ (𝟘𝟘:𝟘𝟘)", "callback_data": "font_2"}, {"text": "فونت ۳ (⓪⓪:⓪⓪)", "callback_data": "font_3"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = (
                    "⏰ **بخش ساعت خودکار روی نام اکانت**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"وضعیت فعلی: `{'روشن 🟢' if t_on else 'خاموش 🔴'}`\n\n"
                    "با کلیک روی دکمه زیر ساعت به انتهای اسم شما متصل شده و هر دقیقه آپدیت می‌شود."
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
                    await self.update_setting_db(user_id, "timename_active", False)
                    await self.answer_callback(cq["id"], "🛑 ساعت خاموش شد.")
                else:
                    cli.timename_active = True
                    await self.update_setting_db(user_id, "timename_active", True)
                    cli.timename_task = asyncio.create_task(timename_loop(cli, cli.settings.get("timename_base", "Self"), cli.settings.get("timename_font", 1)))
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
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = (
                    "🤖 **منشی پاسخگوی خودکار پی‌وی**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"وضعیت: `{'فعال و آماده 🟢' if m_on else 'غیرفعال 🔴'}`\n\n"
                    "در صورت روشن بودن، به پیام‌های جدید پی‌وی پاسخ خودکار ارسال خواهد شد."
                )
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "toggle_monshi":
                cli = ACTIVE_CLIENTS.get(user_id)
                if not cli:
                    return await self.answer_callback(cq["id"], "❌ سلف شما خاموش است.", alert=True)
                cli.monshi_active = not getattr(cli, "monshi_active", False)
                await self.update_setting_db(user_id, "monshi_active", cli.monshi_active)
                await self.answer_callback(cq["id"], f"منشی: {'روشن شد 🟢' if cli.monshi_active else 'خاموش شد 🔴'}")
                return await self.handle_update({"callback_query": {**cq, "data": "menu_monshi"}})

            # ۵. پاکسازی خودکار پیام‌ها با انتخاب ثانیه‌ها
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
                txt = (
                    "🗑 **پاکسازی خودکار پیام‌های ارسالی شما**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"وضعیت: `{'روشن 🟢' if c_on else 'خاموش 🔴'}` | تاخیر: `{delay}` ثانیه\n\n"
                    "پیام‌هایی که در پی‌وی بفرستید پس از این تایم خودکار حذف می‌شوند."
                )
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
                await self.answer_callback(cq["id"], f"⏱ تایمر پاکسازی روی {sec} ثانیه ذخیره شد!", alert=True)
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
                        [{"text": f"🗑 پاکسازی کامل دشمنان ({ec})", "callback_data": "clear_enemies"}, {"text": f"🗑 پاکسازی کامل دوستان ({fc})", "callback_data": "clear_friends"}],
                        [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = (
                    "🛡 **داشبورد امنیت و روابط**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚔️ تعداد افراد در لیست دشمن: `{ec}` نفر\n"
                    f"❤️ تعداد افراد در لیست دوست: `{fc}` نفر\n\n"
                    "پیام‌های پاک شده یا ادیت شده توسط دیگران خودکار برای شما در Saved Messages ذخیره و لاگ می‌شوند."
                )
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

            # ۷. دکمه‌های انتخاب پیشوند
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
                return await self.edit_message(chat_id, msg_id, f"⚡️ **تنظیم پیشوند دستورات سلف**\n\nپیشوند فعلی: `{curr_p}`\nیکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=kb)

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
                kb = {"inline_keyboard": [[{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]]}
                await self.answer_callback(cq["id"])
                txt = (
                    "🛠 **جعبه ابزارهای هوشمند سلف**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "• **دانلودر یوتیوب:** ارسال لینک مستقیم ویدیو در چت جهت دریافت فایل\n"
                    "• **ویدیو نوت گرد:** ریپلای روی هر فیلم جهت تبدیل به ویدیوی دایره‌ای\n"
                    "• **سیو محتوای ضد فوروارد:** ریپلای روی فایل در کانال‌های قفل‌دار جهت ذخیره در Saved Messages"
                )
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            # دکمه‌های بازگشت
            elif data == "back_dashboard":
                is_online = user_id in ACTIVE_CLIENTS
                u = await self.get_user_db(user_id)
                await self.answer_callback(cq["id"])
                p_text = (
                    "👑 **داشبورد مدیریت یکپارچه سلف‌بات**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 شناسه شما: `{user_id}`\n"
                    f"⚡️ وضعیت اتصال: {'فعال و روشن 🟢' if is_online else 'خاموش 🔴'}\n"
                    f"💰 اعتبار: `{u[1]}` سکه | پلن: {'VIP 💎' if u[2] else 'عادی'}\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "👇 همه‌چیز کاملاً دکمه‌ای است؛ بخش دلخواه را انتخاب کنید:"
                )
                return await self.edit_message(chat_id, msg_id, p_text, reply_markup=self.get_main_dashboard_kb(is_online))

            elif data == "back_home":
                USER_STATES.pop(user_id, None)
                kb = {"inline_keyboard": [[{"text": "🔑 اتصال اکانت (ارسال سشن)", "callback_data": "btn_submit_session"}]]}
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "👋 لطفاً انتخاب کنید:", reply_markup=kb)

bot = HttpBot()
