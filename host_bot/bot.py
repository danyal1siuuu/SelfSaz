# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import aiosqlite
from config import BOT_TOKEN, DB_NAME
from core.manager import start_single_client, stop_single_client, ACTIVE_CLIENTS

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
CHANNEL_URL = "https://t.me/YourChannelUsername"

USER_STATES = {}

class HttpBot:
    def __init__(self):
        self.running = False

    async def send_message(self, chat_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{API_URL}/sendMessage", json=payload) as resp:
                    return await resp.json()
        except Exception:
            pass

    async def edit_message(self, chat_id, message_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown"}
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

    async def is_registered(self, user_id):
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("SELECT session_string, coins, is_vip, prefix FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            return row if row else None

    # ------------------ کیبورد داشبورد اصلی ------------------
    def get_dashboard_kb(self, is_online):
        status_btn = "🟢 وضعیت: روشن" if is_online else "🔴 وضعیت: خاموش"
        toggle_cb = "turn_off" if is_online else "turn_on"
        return {
            "inline_keyboard": [
                [{"text": status_btn, "callback_data": toggle_cb}, {"text": "🔄 ریستارت سلف", "callback_data": "restart_self"}],
                [{"text": "⏰ زمان، نام و بیو", "callback_data": "p_time"}, {"text": "🛡 امنیت و دشمنان", "callback_data": "p_security"}],
                [{"text": "🤖 منشی و هوش مصنوعی", "callback_data": "p_ai"}, {"text": "🛠 ابزارها و دانلودرها", "callback_data": "p_tools"}],
                [{"text": "📢 همگانی و تبلیغات", "callback_data": "p_broadcast"}, {"text": "🗑 پاکسازی پیام‌ها", "callback_data": "p_cleaner"}],
                [{"text": "⚡️ تغییر پیشوند (.)", "callback_data": "p_prefix"}, {"text": "🎮 بازی و کریپتو", "callback_data": "p_fun"}],
                [{"text": "🛑 خروج و حذف سلف", "callback_data": "delete_self"}, {"text": "📢 کانال ما", "url": CHANNEL_URL}]
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
        # ----------------- پیام‌های متنی -----------------
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg.get("from", {}).get("id", chat_id)
            text = msg.get("text", "").strip()

            if text == "/start":
                user_data = await self.is_registered(user_id)
                if user_data:
                    is_online = user_id in ACTIVE_CLIENTS
                    panel_text = (
                        "👑 **پنل مدیریت اختصاصی سلف‌بات شما**\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🆔 شناسه کاربری: `{user_id}`\n"
                        f"⚡️ وضعیت اتصال: {'فعال و آنلاین 🟢' if is_online else 'غیرفعال 🔴'}\n"
                        f"💰 موجودی: `{user_data[1]}` سکه | پلن: {'ویژه (VIP) 💎' if user_data[2] else 'عادی'}\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        "👇 برای کنترل هر بخش از دکمه‌های زیر استفاده کنید:"
                    )
                    return await self.send_message(chat_id, panel_text, reply_markup=self.get_dashboard_kb(is_online))
                else:
                    kb = {
                        "inline_keyboard": [
                            [{"text": "🔑 اتصال و فعال‌سازی سلف", "callback_data": "submit_session"}],
                            [{"text": "📖 راهنمای دریافت سشن", "callback_data": "help_session"}],
                            [{"text": "📢 کانال پشتیبانی", "url": CHANNEL_URL}]
                        ]
                    }
                    welcome = (
                        "👋 **به سامانه هوشمند و پیشرفته سلف‌ساز خوش آمدید!**\n\n"
                        "برای اتصال اکانت خود به سلف و استفاده از تمام قابلیت‌ها، روی دکمه زیر کلیک کنید:"
                    )
                    return await self.send_message(chat_id, welcome, reply_markup=kb)

            # بررسی دریافت سشن ارسالی
            if USER_STATES.get(user_id) == "WAITING_SESSION":
                if len(text) > 40:
                    wait_msg = await self.send_message(chat_id, "⏳ در حال اتصال آنی سلف...")
                    
                    # ذخیره مطمئن در دیتابیس
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT OR REPLACE INTO users (user_id, session_string, coins) VALUES (?, ?, 100)", (user_id, text))
                        await db.commit()

                    # استارت لحظه‌ای در رم
                    started, err = await start_single_client(user_id, text)
                    USER_STATES.pop(user_id, None)

                    if started:
                        msg_ok = (
                            "🎉 **سلف شما در همان لحظه با موفقیت روشن شد!**\n\n"
                            "اکنون می‌توانید از پنل زیر امکانات را خاموش و روشن کنید یا مستقیماً در اکانت خود دستورات را تست نمایید."
                        )
                        await self.send_message(chat_id, msg_ok, reply_markup=self.get_dashboard_kb(True))
                    else:
                        await self.send_message(chat_id, f"❌ خطا در اتصال به تلگرام:\n`{err}`\n\nلطفاً مطمئن شوید سشن صحیح است.")
                else:
                    await self.send_message(chat_id, "❌ استرینگ سشن ارسالی نامعتبر است.")

        # ----------------- دکمه‌های شیشه‌ای -----------------
        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            user_id = cq.get("from", {}).get("id", chat_id)
            msg_id = cq["message"]["message_id"]
            data = cq.get("data")

            # ۱. دکمه‌های ورود و سشن
            if data == "submit_session":
                USER_STATES[user_id] = "WAITING_SESSION"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "back_home"}]]}
                prompt = "📱 **ارسال استرینگ سشن:**\n\nکد String Session را در این چت بفرستید تا سلف فوراً روشن شود:"
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, prompt, reply_markup=kb)

            elif data == "help_session":
                kb = {"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "back_home"}]]}
                text_help = "📖 دستور ساخت سشن در ترموکس:\n`python -c \"...\"`\nسپس شماره و کد را بزنید و متن دریافتی را بفرستید."
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, text_help, reply_markup=kb)

            # ۲. کنترل وضعیت سلف
            elif data == "turn_off":
                await stop_single_client(user_id)
                await self.answer_callback(cq["id"], "🛑 سلف خاموش شد.")
                return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (خاموش 🔴)**", reply_markup=self.get_dashboard_kb(False))

            elif data == "turn_on":
                user_data = await self.is_registered(user_id)
                if user_data:
                    started, err = await start_single_client(user_id, user_data[0])
                    if started:
                        await self.answer_callback(cq["id"], "🟢 سلف روشن شد!")
                        return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (روشن 🟢)**", reply_markup=self.get_dashboard_kb(True))
                    else:
                        await self.answer_callback(cq["id"], f"خطا در روشن شدن: {err}", alert=True)

            elif data == "restart_self":
                user_data = await self.is_registered(user_id)
                if user_data:
                    await stop_single_client(user_id)
                    await asyncio.sleep(1)
                    await start_single_client(user_id, user_data[0])
                    await self.answer_callback(cq["id"], "🔄 سلف ریستارت و به‌روزرسانی شد!", alert=True)

            elif data == "delete_self":
                # قطع ارتباط در رم
                await stop_single_client(user_id)
                # پاک کردن کامل از دیتابیس
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                    await db.commit()
                await self.answer_callback(cq["id"], "سلف شما با موفقیت حذف شد.", alert=True)
                kb = {"inline_keyboard": [[{"text": "🔑 اتصال مجدد سلف", "callback_data": "submit_session"}]]}
                return await self.edit_message(chat_id, msg_id, "🛑 **سلف شما به طور کامل حذف شد.** برای اتصال مجدد کلیک کنید:", reply_markup=kb)

            # ۳. منوی ساعت و نام (p_time)
            elif data == "p_time":
                kb = {
                    "inline_keyboard": [
                        [{"text": "🕒 ساعت روی اسم (دستور: .زمان اسم روشن)", "callback_data": "info_time_name"}],
                        [{"text": "📝 ساعت روی بیوگرافی (دستور: .بیو زمان)", "callback_data": "info_time_bio"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = "⏰ **بخش زمان و پروفایل:**\nساعت سلف با ۲۱ فونت مختلف و هماهنگ با ثانیه کار می‌کند."
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            # ۴. منوی امنیت و دشمنان (p_security)
            elif data == "p_security":
                kb = {
                    "inline_keyboard": [
                        [{"text": "🗑 پاکسازی کامل لیست دشمنان", "callback_data": "clear_enemies_action"}],
                        [{"text": "🗑 پاکسازی کامل لیست دوستان", "callback_data": "clear_friends_action"}],
                        [{"text": "🔒 راهنمای قفل‌های گروه (لینک، فوروارد)", "callback_data": "info_locks"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = (
                    "🛡 **مدیریت امنیت و دشمنان:**\n\n"
                    "• برای افزودن دشمن در چت: ریپلای و ارسال `.افزودن دشمن`\n"
                    "• برای افزودن دوست در چت: ریپلای و ارسال `.افزودن دوست`\n"
                    "• پیام‌های حذفی و ادیت شده دیگران خودکار برای شما لاگ می‌شوند."
                )
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            elif data == "clear_enemies_action":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE owner_id = ? AND type = 'enemy'", (user_id,))
                    await db.commit()
                await self.answer_callback(cq["id"], "🗑 تمامی کاربران از لیست دشمنان شما حذف شدند!", alert=True)

            elif data == "clear_friends_action":
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM relations WHERE owner_id = ? AND type = 'friend'", (user_id,))
                    await db.commit()
                await self.answer_callback(cq["id"], "🗑 تمامی کاربران از لیست دوستان شما حذف شدند!", alert=True)

            # ۵. منوی هوش مصنوعی و منشی (p_ai)
            elif data == "p_ai":
                kb = {
                    "inline_keyboard": [
                        [{"text": "🤖 راهنمای منشی خودکار (.منشی روشن)", "callback_data": "info_monshi"}],
                        [{"text": "💬 چت با هوش مصنوعی (.ai سوال شما)", "callback_data": "info_ai"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                txt = "🤖 **تنظیمات هوش مصنوعی و منشی:**\nدر زمان آفلاین بودن، منشی به صورت هوشمند و محترمانه پاسخ چت‌های شما را می‌دهد."
                return await self.edit_message(chat_id, msg_id, txt, reply_markup=kb)

            # ۶. منوی ابزارها و دانلودرها (p_tools)
            elif data == "p_tools":
                kb = {
                    "inline_keyboard": [
                        [{"text": "🎥 ویدیو گرد: ریپلای و ارسال .تلسکوپ", "callback_data": "info_dummy"}],
                        [{"text": "📥 یوتیوب: .یوتوب + لینک", "callback_data": "info_dummy"}],
                        [{"text": "💾 سیو پیام فوروارد قفل: ریپلای و .سیو", "callback_data": "info_dummy"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🛠 **راهنمای سریع دانلودرها و ابزارها:**", reply_markup=kb)

            # ۷. منوی پاکسازی پیام‌ها (p_cleaner)
            elif data == "p_cleaner":
                kb = {
                    "inline_keyboard": [
                        [{"text": "⏱ روشن کردن: .حذف کن روشن", "callback_data": "info_dummy"}],
                        [{"text": "🛑 خاموش کردن: .حذف کن خاموش", "callback_data": "info_dummy"}],
                        [{"text": "⚙️ تغییر زمان: .حذف کن تنظیم 30", "callback_data": "info_dummy"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🗑 **پاک‌سازی خودکار پیام‌ها:**\nبا فعال کردن این بخش، پیام‌های ارسالی شما پس از زمان مشخص شده خودکار پاک می‌شوند.", reply_markup=kb)

            # ۸. منوی همگانی و تبلیغات (p_broadcast)
            elif data == "p_broadcast":
                kb = {
                    "inline_keyboard": [
                        [{"text": "📢 تنظیم بنر: ریپلای و .پیام فرستنده", "callback_data": "info_dummy"}],
                        [{"text": "🚀 ارسال به آنلاین‌ها: .فرستنده", "callback_data": "info_dummy"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "📢 **سیستم تبچی و ارسال هوشمند به اعضای آنلاین:**", reply_markup=kb)

            # ۹. منوی بازی و سرگرمی (p_fun)
            elif data == "p_fun":
                kb = {
                    "inline_keyboard": [
                        [{"text": "📊 نرخ ارز: .نرخ ارز", "callback_data": "info_dummy"}],
                        [{"text": "🐱 میو خودکار: .میو روشن", "callback_data": "info_dummy"}],
                        [{"text": "📍 لوکیشن فیک: .لوکیشن جعلی تهران", "callback_data": "info_dummy"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🎮 **امکانات سرگرمی، مالی و بازی:**", reply_markup=kb)

            # ۱۰. تغییر پیشوند دستورات (نقطه .)
            elif data == "p_prefix":
                cli = ACTIVE_CLIENTS.get(user_id)
                if cli:
                    cli.prefix_enabled = not getattr(cli, "prefix_enabled", True)
                    st = "فعال (.)" if cli.prefix_enabled else "غیرفعال (بدون نقطه)"
                    await self.answer_callback(cq["id"], f"پیشوند دستورات: {st}", alert=True)
                else:
                    await self.answer_callback(cq["id"], "سلف شما خاموش است؛ ابتدا آن را روشن کنید.", alert=True)

            # برگشت‌ها
            elif data == "back_dashboard":
                is_online = user_id in ACTIVE_CLIENTS
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت اختصاصی سلف‌بات:**", reply_markup=self.get_dashboard_kb(is_online))

            elif data == "back_home":
                USER_STATES.pop(user_id, None)
                kb = {
                    "inline_keyboard": [
                        [{"text": "🔑 اتصال و فعال‌سازی سلف", "callback_data": "submit_session"}],
                        [{"text": "📖 راهنمای دریافت سشن", "callback_data": "help_session"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "👋 منوی اصلی:", reply_markup=kb)

            else:
                await self.answer_callback(cq["id"])

bot = HttpBot()
