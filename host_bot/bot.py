# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import aiosqlite
from config import BOT_TOKEN, DB_NAME

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

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

    async def edit_message(self, chat_id, message_id, text):
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{API_URL}/editMessageText", json=payload) as resp:
                    return await resp.json()
        except Exception:
            pass

    async def answer_callback(self, callback_query_id):
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": callback_query_id})
        except Exception:
            pass

    async def start(self):
        self.running = True
        offset = 0
        print("[+] Maker Bot successfully started via HTTP API (No API_ID needed!)")
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
                kb = {
                    "inline_keyboard": [
                        [{"text": "⚡️ ساخت سلف در چند ثانیه", "callback_data": "make"}],
                        [{"text": "📢 کانال رسمی", "url": "https://t.me/Vip_Viro"}]
                    ]
                }
                await self.send_message(
                    chat_id,
                    "👑 **به سامانه سلف‌ساز جامع VipViro خوش آمدید!**\nبرای راه‌اندازی سلف روی دکمه زیر کلیک کنید:",
                    reply_markup=kb
                )
            elif text and not text.startswith("/"):
                if len(text) > 40:
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute(
                            "INSERT OR REPLACE INTO users (user_id, session_string) VALUES (?, ?)",
                            (user_id, text)
                        )
                        await db.commit()
                    await self.send_message(
                        chat_id,
                        "✅ **سلف شما با موفقیت فعال شد!**\nکافیست در Saved Messages اکانت خود دستور `.راهنما` یا `.نرخ ارز` را تست کنید."
                    )
                else:
                    await self.send_message(chat_id, "❌ استرینگ سشن ارسالی نامعتبر است.")

        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            msg_id = cq["message"]["message_id"]
            data = cq.get("data")
            await self.answer_callback(cq["id"])
            if data == "make":
                await self.edit_message(chat_id, msg_id, "📱 لطفاً **String Session** اکانت خود را در این چت ارسال نمایید:")

bot = HttpBot()
