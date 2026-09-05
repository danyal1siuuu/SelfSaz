# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import aiosqlite
import re
from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    PhoneNumberInvalid,
    FloodWait,
    PasswordHashInvalid
)
from config import BOT_TOKEN, DB_NAME, API_ID, API_HASH

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 👈 لینک کانال خود را اینجا بگذارید (اگر کانال ندارید، بگذارید https://t.me)
CHANNEL_URL = "https://t.me/Vip_Viro"

USER_STATES = {}
USER_AUTH_DATA = {}

SESSION_HELP_TEXT = """
🔐 **راهنمای جامع ساخت سلف و ورود امن**

━━━━━━━━━━━━━━━━━━━━━
❓ **استرینگ سشن چیست؟**
یک کلید رمزنگاری‌شده استاندارد است که به ربات سلف‌ساز اجازه می‌دهد بدون نیاز به افشای رمز اصلی شما، قابلیت‌های پیشرفته (ساعت متحرک، ضدادیت، دانلودرها و...) را روی اکانتتان فعال کند.

━━━━━━━━━━━━━━━━━━━━━
🚀 **مراحل راه‌اندازی (۱۰۰٪ داخل همین ربات):**

1️⃣ روی دکمه **«⚡️ ورود خودکار با شماره تلفن»** در منوی اصلی بزنید.

2️⃣ شماره تلفن خود را با پیش‌شماره کشور بفرستید (مثلاً: `+989123456789`).

3️⃣ کد ۵ رقمی که تلگرام برایتان ارسال می‌کند را وارد کنید.

4️⃣ در صورتی که اکانت شما تایید دو مرحله‌ای (2FA) دارد، رمز عبورتان را وارد کنید.

5️⃣ کار تمام است! سلف‌بات شما فوراً فعال شده و یک نسخه از کد سشن نیز جهت بکاپ به شما تحویل داده می‌شود.

━━━━━━━━━━━━━━━━━━━━━
🛡 **امنیت و حریم خصوصی:**
• تمامی سشن‌ها به صورت رمزگذاری‌شده روی سرور امن نگهداری می‌شوند.
• هر زمان تمایل داشته باشید، می‌توانید از بخش:
`Settings > Devices (دستگاه‌های فعال)`
در تلگرام خود با یک کلیک دسترسی سلف‌ساز را قطع کنید.
"""

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

    async def delete_message(self, chat_id, message_id):
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(f"{API_URL}/deleteMessage", json={"chat_id": chat_id, "message_id": message_id})
        except Exception:
            pass

    async def answer_callback(self, callback_query_id):
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": callback_query_id})
        except Exception:
            pass

    async def cleanup_user(self, user_id):
        if user_id in USER_AUTH_DATA:
            try:
                client = USER_AUTH_DATA[user_id].get("client")
                if client and client.is_connected:
                    await client.disconnect()
            except Exception:
                pass
            del USER_AUTH_DATA[user_id]
        USER_STATES.pop(user_id, None)

    async def start(self):
        self.running = True
        offset = 0
        print("[+] Maker Bot successfully online with In-House Session Generator!")
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
        # ----------------- پردازش پیام‌های متنی -----------------
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg.get("from", {}).get("id", chat_id)
            text = msg.get("text", "").strip()
            msg_id = msg["message_id"]

            if text == "/start":
                await self.cleanup_user(user_id)
                kb = {
                    "inline_keyboard": [
                        [{"text": "⚡️ ورود خودکار با شماره تلفن (سریع)", "callback_data": "auth_direct"}],
                        [{"text": "🔑 ورود دستی با استرینگ سشن", "callback_data": "auth_manual"}],
                        [{"text": "📖 راهنما و امنیت سلف", "callback_data": "help_session"}],
                        [{"text": "📢 کانال پشتیبانی", "url": CHANNEL_URL}]
                    ]
                }
                welcome = (
                    "👑 **به سامانه هوشمند و اختصاصی سلف‌ساز خوش آمدید!**\n\n"
                    "با این سیستم می‌توانید بدون نیاز به هیچ برنامه یا ربات دیگر، اکانت خود را مستقیماً به امکانات پیشرفته مجهز کنید.\n\n"
                    "👇 لطفاً یکی از گزینه‌های زیر را انتخاب نمایید:"
                )
                return await self.send_message(chat_id, welcome, reply_markup=kb)

            # ۱. دریافت شماره تلفن
            if USER_STATES.get(user_id) == "WAITING_PHONE":
                clean_phone = re.sub(r"[^\d+]", "", text)
                if not clean_phone.startswith("+") or len(clean_phone) < 10:
                    kb = {"inline_keyboard": [[{"text": "🔙 انصراف و بازگشت", "callback_data": "cancel_auth"}]]}
                    return await self.send_message(
                        chat_id,
                        "❌ **فرمت شماره اشتباه است!**\nشماره باید همراه با کد کشور باشد.\nمثال: `+989123456789`",
                        reply_markup=kb
                    )

                wait_msg = await self.send_message(chat_id, "⏳ در حال ارسال کد تایید به تلگرام شما...")
                temp_client = Client(f"temp_{user_id}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
                
                try:
                    await temp_client.connect()
                    code_info = await temp_client.send_code(clean_phone)
                    USER_AUTH_DATA[user_id] = {
                        "client": temp_client,
                        "phone": clean_phone,
                        "phone_code_hash": code_info.phone_code_hash
                    }
                    USER_STATES[user_id] = "WAITING_CODE"

                    kb = {"inline_keyboard": [[{"text": "🔙 لغو فرایند", "callback_data": "cancel_auth"}]]}
                    prompt = (
                        f"📩 **کد تایید به تلگرام شماره `{clean_phone}` ارسال شد!**\n\n"
                        "⚠️ **نکته امنیتی بسیار مهم:**\n"
                        "برای اینکه تلگرام پیام شما را بلاک نکند، کد را به صورت **فاصله‌دار** ارسال کنید.\n"
                        "مثال: اگر کد دریافتی شما `54321` است، بفرستید: `5 4 3 2 1`"
                    )
                    return await self.send_message(chat_id, prompt, reply_markup=kb)

                except FloodWait as e:
                    await self.cleanup_user(user_id)
                    return await self.send_message(chat_id, f"⚠️ تلگرام به دلیل تلاش‌های مکرر شما را محدود کرده است. لطفاً `{e.value}` ثانیه صبر کنید.")
                except PhoneNumberInvalid:
                    await self.cleanup_user(user_id)
                    return await self.send_message(chat_id, "❌ شماره وارد شده نامعتبر یا در تلگرام ثبت نشده است.")
                except Exception as e:
                    await self.cleanup_user(user_id)
                    return await self.send_message(chat_id, f"❌ خطا در ارسال کد:\n`{str(e)}`")

            # ۲. دریافت کد تایید ارسالی
            elif USER_STATES.get(user_id) == "WAITING_CODE":
                clean_code = re.sub(r"\D", "", text)
                if len(clean_code) < 5:
                    return await self.send_message(chat_id, "❌ لطفاً کد ۵ رقمی را به درستی وارد کنید.")

                auth = USER_AUTH_DATA.get(user_id)
                if not auth:
                    await self.cleanup_user(user_id)
                    return await self.send_message(chat_id, "⚠️ نشست منقضی شد. لطفاً دوباره از /start شروع کنید.")

                temp_client = auth["client"]
                try:
                    await temp_client.sign_in(auth["phone"], auth["phone_code_hash"], clean_code)
                    session_str = await temp_client.export_session_string()
                    await temp_client.disconnect()

                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT OR REPLACE INTO users (user_id, session_string) VALUES (?, ?)", (user_id, session_str))
                        await db.commit()

                    await self.cleanup_user(user_id)
                    success_text = (
                        "🎉 **سلف اختصاصی شما با موفقیت ساخته و متصل شد!**\n\n"
                        "🔐 **استرینگ سشن اکانت شما (جهت ذخیره):**\n"
                        f"`{session_str}`\n\n"
                        "💡 **شروع به کار:**\n"
                        "وارد Saved Messages اکانت خود شوید و دستورات زیر را تست کنید:\n"
                        "• `.راهنما` — لیست فرامین و امکانات\n"
                        "• `.نرخ ارز` — قیمت لحظه‌ای دلار و طلا\n"
                        "• `.زمان اسم روشن` — ساعت متحرک روی نام شما"
                    )
                    return await self.send_message(chat_id, success_text)

                except SessionPasswordNeeded:
                    USER_STATES[user_id] = "WAITING_PASSWORD"
                    kb = {"inline_keyboard": [[{"text": "🔙 لغو فرایند", "callback_data": "cancel_auth"}]]}
                    return await self.send_message(
                        chat_id,
                        "🔐 **تایید دو مرحله‌ای (2FA) فعال است!**\n\n"
                        "اکانت شما دارای گذرواژه ابری است. لطفاً رمز عبور اکانت تلگرام خود را بفرستید:\n"
                        "*(پیام حاوی رمز عبور بلافاصله پس از پردازش جهت امنیت پاک خواهد شد)*",
                        reply_markup=kb
                    )
                except (PhoneCodeInvalid, PhoneCodeExpired):
                    return await self.send_message(chat_id, "❌ کد وارد شده اشتباه یا منقضی شده است. مجدداً ارسال کنید:")
                except Exception as e:
                    await self.cleanup_user(user_id)
                    return await self.send_message(chat_id, f"❌ خطا در احراز هویت:\n`{str(e)}`")

            # ۳. دریافت رمز تایید دو مرحله‌ای
            elif USER_STATES.get(user_id) == "WAITING_PASSWORD":
                password = text
                await self.delete_message(chat_id, msg_id)

                auth = USER_AUTH_DATA.get(user_id)
                if not auth:
                    await self.cleanup_user(user_id)
                    return await self.send_message(chat_id, "⚠️ نشست منقضی شد. لطفاً از /start دوباره اقدام کنید.")

                temp_client = auth["client"]
                try:
                    await temp_client.check_password(password)
                    session_str = await temp_client.export_session_string()
                    await temp_client.disconnect()

                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT OR REPLACE INTO users (user_id, session_string) VALUES (?, ?)", (user_id, session_str))
                        await db.commit()

                    await self.cleanup_user(user_id)
                    success_text = (
                        "🎉 **هویت شما با موفقیت تایید و سلف فعال شد!**\n\n"
                        "🔐 **کد سشن اختصاصی شما:**\n"
                        f"`{session_str}`\n\n"
                        "📌 از این لحظه سلف روی اکانت شما روشن است. دستور `.راهنما` را در Saved Messages تست کنید."
                    )
                    return await self.send_message(chat_id, success_text)

                except PasswordHashInvalid:
                    return await self.send_message(chat_id, "❌ رمز عبور وارد شده اشتباه است! دوباره رمز را ارسال کنید:")
                except Exception as e:
                    await self.cleanup_user(user_id)
                    return await self.send_message(chat_id, f"❌ خطا در ورود دو مرحله‌ای:\n`{str(e)}`")

            # ۴. دریافت دستی سشن
            elif USER_STATES.get(user_id) == "WAITING_MANUAL_SESSION":
                if len(text) > 40:
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute("INSERT OR REPLACE INTO users (user_id, session_string) VALUES (?, ?)", (user_id, text))
                        await db.commit()
                    await self.cleanup_user(user_id)
                    return await self.send_message(chat_id, "✅ **سلف شما با موفقیت متصل شد!**\nدستور `.راهنما` را در چت‌های خود تست کنید.")
                else:
                    return await self.send_message(chat_id, "❌ استرینگ سشن ارسالی نامعتبر است.")

        # ----------------- پردازش دکمه‌های شیشه‌ای -----------------
        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            user_id = cq.get("from", {}).get("id", chat_id)
            msg_id = cq["message"]["message_id"]
            data = cq.get("data")
            await self.answer_callback(cq["id"])

            if data == "auth_direct":
                USER_STATES[user_id] = "WAITING_PHONE"
                kb = {"inline_keyboard": [[{"text": "🔙 انصراف و بازگشت", "callback_data": "cancel_auth"}]]}
                prompt = (
                    "📱 **ورود مستقیم با شماره تلفن:**\n\n"
                    "لطفاً شماره موبایل اکانت تلگرام خود را به همراه کد کشور بفرستید:\n\n"
                    "📌 مثال برای شماره ایران:\n"
                    "`+989123456789`"
                )
                await self.edit_message(chat_id, msg_id, prompt, reply_markup=kb)

            elif data == "auth_manual":
                USER_STATES[user_id] = "WAITING_MANUAL_SESSION"
                kb = {
                    "inline_keyboard": [
                        [{"text": "📖 راهنمای سشن", "callback_data": "help_session"}],
                        [{"text": "🔙 انصراف و بازگشت", "callback_data": "cancel_auth"}]
                    ]
                }
                prompt = (
                    "🔑 **ورود دستی با استرینگ سشن:**\n\n"
                    "اگر از قبل کد String Session اکانت خود را دارید، آن را در قالب یک پیام به همین چت ارسال نمایید:"
                )
                await self.edit_message(chat_id, msg_id, prompt, reply_markup=kb)

            elif data == "help_session":
                kb = {
                    "inline_keyboard": [
                        [{"text": "⚡️ شروع ساخت سلف با شماره", "callback_data": "auth_direct"}],
                        [{"text": "🔙 بازگشت به منوی اصلی", "callback_data": "cancel_auth"}]
                    ]
                }
                await self.edit_message(chat_id, msg_id, SESSION_HELP_TEXT, reply_markup=kb)

            elif data == "cancel_auth":
                await self.cleanup_user(user_id)
                kb = {
                    "inline_keyboard": [
                        [{"text": "⚡️ ورود خودکار با شماره تلفن (سریع)", "callback_data": "auth_direct"}],
                        [{"text": "🔑 ورود دستی با استرینگ سشن", "callback_data": "auth_manual"}],
                        [{"text": "📖 راهنما و امنیت سلف", "callback_data": "help_session"}],
                        [{"text": "📢 کانال پشتیبانی", "url": CHANNEL_URL}]
                    ]
                }
                await self.edit_message(chat_id, msg_id, "👑 **منوی اصلی سلف‌ساز:**\nیکی از گزینه‌های زیر را انتخاب نمایید:", reply_markup=kb)

bot = HttpBot()
