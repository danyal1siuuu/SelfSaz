# -*- coding: utf-8 -*-
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import aiohttp
from config import AI_API_KEY, AI_BASE_URL

@Client.on_message(filters.private & ~filters.me & ~filters.bot)
async def monshi_responder(client: Client, message: Message):
    # بررسی فعال بودن منشی
    if not getattr(client, "monshi_active", False):
        return

    if not message.from_user or message.from_user.is_self:
        return

    # سیستم ضداسپم: جلوگیری از ارسال مجدد تا ۵ دقیقه به یک کاربر
    if not hasattr(client, "monshi_replied_users"):
        client.monshi_replied_users = {}

    user_id = message.from_user.id
    now = asyncio.get_event_loop().time()
    last_replied = client.monshi_replied_users.get(user_id, 0)
    if now - last_replied < 300:  # ۵ دقیقه تاخیر برای هر مخاطب
        return

    client.monshi_replied_users[user_id] = now
    
    reply_text = getattr(client, "monshi_custom_text", "") or "سلام و درود؛ در حال حاضر آنلاین نیستم. به محض ورود پیامتان را بررسی خواهم کرد. 🙏"

    # در صورت فعال بودن هوش مصنوعی
    if AI_API_KEY:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as s:
                payload = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "شما منشی رسمی و بسیار محترم من در تلگرام هستید. به پیام کاربر پاسخی کوتاه و محترمانه بدهید و بگویید فعلاً آنلاین نیستم."},
                        {"role": "user", "content": message.text or "سلام"}
                    ]
                }
                async with s.post(f"{AI_BASE_URL}/chat/completions", json=payload, headers={"Authorization": f"Bearer {AI_API_KEY}"}) as r:
                    if r.status == 200:
                        res = (await r.json())["choices"][0]["message"]["content"]
                        reply_text = f"🤖 **[منشی هوشمند]**\n\n{res}"
        except Exception:
            pass

    try:
        await message.reply_text(reply_text)
        print(f"[🤖 منشی] پاسخ خودکار برای کاربر {user_id} ارسال شد.")
    except Exception as e:
        print(f"[!] خطا در ارسال پیام منشی: {e}")
