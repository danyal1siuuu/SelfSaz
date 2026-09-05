# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import aiosqlite
import json
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

    async def answer_callback(self, callback_query_id, text=None):
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = True
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

    # ------------------ داشبورد اصلی سلف ------------------
    def get_dashboard_kb(self, is_online):
        status_btn = "🟢 وضعیت: روشن" if is_online else "🔴 وضعیت: خاموش"
        toggle_cb = "turn_off" if is_online else "turn_on"
        return {
            "inline_keyboard": [
                [{"text": status_btn, "callback_data": toggle_cb}, {"text": "🔄 ریستارت سلف", "callback_data": "restart_self"}],
                [{"text": "⏰ زمان، نام و بیو", "callback_data": "p_time"}, {"text": "🛡 مدیریت و ضد خیانت", "callback_data": "p_security"}],
                [{"text": "🤖 منشی و هوش مصنوعی", "callback_data": "p_ai"}, {"text": "🛠 ابزارها و دانلودرها", "callback_data": "p_tools"}],
                [{"text": "📢 همگانی و تبلیغات", "callback_data": "p_broadcast"}, {"text": "🗑 پاکسازی خودکار", "callback_data": "p_cleaner"}],
                [{"text": "⚡️ تنظیم پیشوند (.)", "callback_data": "p_prefix"}, {"text": "🎮 سرگرمی و کریپتو", "callback_data": "p_fun"}],
                [{"text": "🛑 خروج و حذف سلف", "callback_data": "delete_self"}, {"text": "📢 کانال ما", "url": CHANNEL_URL}]
            ]
        }

    async def start(self):
        self.running = True
        offset = 0
        print("[+] HTTP Bot Control Panel Started.")
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
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg.get("from", {}).get("id", chat_id)
            text = msg.get("text", "").strip()

            if text == "/start":
                user_data = await self.is_registered(user_id)
                if user_data:
                    # کاربر ثبت‌نام کرده است -> نمایش پنل مدیریت
                    is_online = user_id in ACTIVE_CLIENTS
                    panel_text = (
                        "👑 **پنل مدیریت اختصاصی سلف‌بات شما**\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🆔 شناسه کاربری: `{user_id}`\n"
                        f"⚡️ وضعیت اتصال: {'فعال و آنلاین 🟢' if is_online else 'غیرفعال 🔴'}\n"
                        f"💰 اعتبار سکه: `{user_data[1]}` سکه\n"
                        f"💎 وضعیت اکانت: {'کاربر ویژه (VIP) 🌟' if user_data[2] else 'کاربر عادی'}\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        "👇 برای مدیریت و تنظیم امکانات سلف، دکمه‌های زیر را لمس کنید:"
                    )
                    return await self.send_message(chat_id, panel_text, reply_markup=self.get_dashboard_kb(is_online))
                else:
                    # کاربر جدید است -> هدایت به اتصال سشن
                    kb = {
                        "inline_keyboard": [
                            [{"text": "🔑 اتصال و راه‌اندازی سلف", "callback_data": "submit_session"}],
                            [{"text": "📖 راهنمای دریافت سشن", "callback_data": "help_session"}],
                            [{"text": "📢 کانال رسمی", "url": CHANNEL_URL}]
                        ]
                    }
                    welcome = (
                        "👋 **به سامانه هوشمند و یکپارچه سلف‌ساز خوش آمدید!**\n\n"
                        "برای اتصال اکانت خود به سلف و استفاده از ده‌ها پلاگین خفن، روی دکمه **اتصال و راه‌اندازی** کلیک کنید:"
                    )
                    return await self.send_message(chat_id, welcome, reply_markup=kb)

            # دریافت استرینگ سشن ارسالی
            if USER_STATES.get(user_id) == "WAITING_SESSION":
                if len(text) > 40:
                    wait_msg = await self.send_message(chat_id, "⏳ در حال بررسی سشن و فعال‌سازی آنی سلف...")
                    
                    # ذخیره در دیتابیس
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT OR REPLACE INTO users (user_id, session_string, coins) VALUES (?, ?, 100)", (user_id, text))
                        await db.commit()

                    # استارت زنده در رم بدون ریستارت سرور!
                    started = await start_single_client(user_id, text)
                    USER_STATES.pop(user_id, None)

                    if started:
                        msg_ok = (
                            "🎉 **سلف شما در همان لحظه با موفقیت روشن شد!**\n\n"
                            "دیگر هیچ نیازی به ریستارت سرور نیست. هم‌اکنون می‌توانید از طریق پنل زیر سلف خود را مدیریت کنید."
                        )
                        await self.send_message(chat_id, msg_ok, reply_markup=self.get_dashboard_kb(True))
                    else:
                        await self.send_message(chat_id, "⚠️ سشن ذخیره شد اما در اتصال مشکلی رخ داد. لطفاً مطمئن شوید سشن معتبر است.")
                else:
                    await self.send_message(chat_id, "❌ استرینگ سشن ارسالی نامعتبر است.")

        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            user_id = cq.get("from", {}).get("id", chat_id)
            msg_id = cq["message"]["message_id"]
            data = cq.get("data")

            # --- بخش اتصال سشن ---
            if data == "submit_session":
                USER_STATES[user_id] = "WAITING_SESSION"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف", "callback_data": "back_home"}]]}
                prompt = (
                    "📱 **ارسال استرینگ سشن:**\n\n"
                    "لطفاً کد **String Session** اکانت خود را به این چت بفرستید تا سلف شما در همان لحظه روشن شود:"
                )
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, prompt, reply_markup=kb)

            elif data == "help_session":
                kb = {"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "back_home"}]]}
                text_help = (
                    "📖 **راهنمای سریع دریافت سشن:**\n\n"
                    "کافیست در ترموکس گوشی خود دستور ساخت سشن را اجرا کنید، شماره و کد تلگرام را بزنید و متن خروجی را اینجا بفرستید."
                )
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, text_help, reply_markup=kb)

            # --- دکمه‌های کنترل سلف (روشن/خاموش/ریستارت) ---
            if data == "turn_off":
                await stop_single_client(user_id)
                await self.answer_callback(cq["id"], "🛑 سلف شما خاموش شد.")
                return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (خاموش 🔴)**", reply_markup=self.get_dashboard_kb(False))

            elif data == "turn_on":
                user_data = await self.is_registered(user_id)
                if user_data:
                    await start_single_client(user_id, user_data[0])
                    await self.answer_callback(cq["id"], "🟢 سلف شما روشن شد!")
                    return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت سلف‌بات (روشن 🟢)**", reply_markup=self.get_dashboard_kb(True))

            elif data == "restart_self":
                user_data = await self.is_registered(user_id)
                if user_data:
                    await stop_single_client(user_id)
                    await asyncio.sleep(1)
                    await start_single_client(user_id, user_data[0])
                    await self.answer_callback(cq["id"], "🔄 سلف شما با موفقیت ریستارت شد!")

            # --- منوی زیرمجموعه‌ها ---
            elif data == "p_time":
                kb = {
                    "inline_keyboard": [
                        [{"text": "🕒 ساعت روی اسم (روشن)", "callback_data": "act_time_name_on"}, {"text": "🛑 ساعت اسم (خاموش)", "callback_data": "act_time_name_off"}],
                        [{"text": "📝 ساعت روی بیو (روشن)", "callback_data": "act_time_bio_on"}, {"text": "🛑 ساعت بیو (خاموش)", "callback_data": "act_time_bio_off"}],
                        [{"text": "🎨 فونت ساعت (۱ تا ۲۱)", "callback_data": "act_font_list"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "⏰ **تنظیمات زمان، نام و بیوگرافی:**\nیکی از گزینه‌ها را انتخاب کنید:", reply_markup=kb)

            elif data == "p_security":
                kb = {
                    "inline_keyboard": [
                        [{"text": "🛡 مدیریت دشمنان", "callback_data": "act_enemy_mgr"}, {"text": "❤️ مدیریت دوستان", "callback_data": "act_friend_mgr"}],
                        [{"text": "🔒 ضد خیانت ادمین (Zed)", "callback_data": "act_zed"}, {"text": "🚫 ضد ادیت و حذف پیام", "callback_data": "act_antiedit"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🛡 **مدیریت امنیت، ضد خیانت و روابط:**", reply_markup=kb)

            elif data == "p_ai":
                kb = {
                    "inline_keyboard": [
                        [{"text": "🤖 منشی هوشمند (روشن/خاموش)", "callback_data": "act_monshi_toggle"}],
                        [{"text": "💼 بیزینس مود (ساعات کاری)", "callback_data": "act_biz_mode"}],
                        [{"text": "💬 چت با هوش مصنوعی (.ai)", "callback_data": "act_ai_info"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🤖 **هوش مصنوعی و منشی اختصاصی:**", reply_markup=kb)

            elif data == "p_tools":
                kb = {
                    "inline_keyboard": [
                        [{"text": "📥 دانلودر یوتیوب و موزیک", "callback_data": "info_yt"}, {"text": "📸 دانلودر اینستاگرام", "callback_data": "info_insta"}],
                        [{"text": "🎥 تبدیل به ویدیو گرد", "callback_data": "info_round"}, {"text": "🖼 حذف پس‌زمینه عکس", "callback_data": "info_bg"}],
                        [{"text": "🎵 تشخیص موزیک (شزم)", "callback_data": "info_shazam"}, {"text": "📁 سیو پیام ضد فوروارد", "callback_data": "info_save"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🛠 **ابزارها و دانلودرهای چندرسانه‌ای:**", reply_markup=kb)

            elif data == "p_cleaner":
                kb = {
                    "inline_keyboard": [
                        [{"text": "🗑 حذف خودکار پیام‌ها (روشن)", "callback_data": "act_clean_on"}, {"text": "🛑 حذف خودکار (خاموش)", "callback_data": "act_clean_off"}],
                        [{"text": "⏱ تنظیم تاخیر (ثانیه)", "callback_data": "act_clean_time"}],
                        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "🗑 **پاک‌سازی خودکار و زمان‌بندی شده چت‌ها:**", reply_markup=kb)

            elif data == "p_prefix":
                # سوئیچ روشن/خاموش کردن پیشوند نقطه (.)
                cli = ACTIVE_CLIENTS.get(user_id)
                if cli:
                    cli.prefix_enabled = not getattr(cli, "prefix_enabled", True)
                    st = "فعال (.)" if cli.prefix_enabled else "غیرفعال (بدون نقطه)"
                    await self.answer_callback(cq["id"], f"پیشوند دستورات: {st}")
                else:
                    await self.answer_callback(cq["id"], "سلف شما خاموش است.")

            elif data == "delete_self":
                await stop_single_client(user_id)
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                    await db.commit()
                await self.answer_callback(cq["id"], "سلف شما حذف شد.")
                return await self.edit_message(chat_id, msg_id, "🛑 سلف شما حذف و اتصال قطع شد. برای اتصال مجدد /start را بزنید.")

            elif data == "back_dashboard":
                is_online = user_id in ACTIVE_CLIENTS
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "👑 **پنل مدیریت اختصاصی سلف‌بات:**", reply_markup=self.get_dashboard_kb(is_online))

            elif data == "back_home":
                USER_STATES.pop(user_id, None)
                kb = {
                    "inline_keyboard": [
                        [{"text": "🔑 اتصال و راه‌اندازی سلف", "callback_data": "submit_session"}],
                        [{"text": "📖 راهنمای دریافت سشن", "callback_data": "help_session"}]
                    ]
                }
                await self.answer_callback(cq["id"])
                return await self.edit_message(chat_id, msg_id, "👋 منوی اصلی:", reply_markup=kb)

            else:
                await self.answer_callback(cq["id"], "این قابلیت با فرامین چت نیز مستقیماً هماهنگ است.")

bot = HttpBot()
