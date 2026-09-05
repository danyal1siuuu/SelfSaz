# -*- coding: utf-8 -*-
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import aiohttp
from config import AI_API_KEY, AI_BASE_URL

# ثبت در گروه مستقل ۲ تا هیچ پلاگین دیگری مانع اجرای منشی نشود
@Client.on_message(filters.private & ~filters.me, group=2)
async def monshi_responder(client: Client, message: Message):
    # بررسی فعال بودن منشی روی اکانت سلف
    if not getattr(client, "monshi_active", False):
        return

    # چشم‌پوشی از ربات‌ها و پیام‌های ارسالی خود اکانت
    if not message.from_user or message.from_user.is_self or message.from_user.is_bot:
        return

    # چشم‌پوشی از دوستان ویژه (دوستان معاف از منشی هستند)
    if hasattr(client, "friends_set") and message.from_user.id in client.friends_set:
        return

    # سیستم ضداسپم: جلوگیری از تکرار پیام به یک کاربر در کمتر از ۴ دقیقه
    if not hasattr(client, "monshi_replied_users"):
        client.monshi_replied_users = {}

    user_id = message.from_user.id
    now = asyncio.get_event_loop().time()
    last_replied = client.monshi_replied_users.get(user_id, 0)
    if now - last_replied < 240:
        return

    client.monshi_replied_users[user_id] = now
    reply_text = getattr(client, "monshi_custom_text", "") or "سلام؛ در حال حاضر آنلاین نیستم. به محض ورود پیامتان را بررسی خواهم کرد. 🙏"

    # در صورت تعریف بودن کلید هوش مصنوعی
    if AI_API_KEY:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as s:
                payload = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "شما منشی محترم من هستید. پاسخی بسیار کوتاه و با ادب بدهید که آنلاین نیستم."},
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
        print(f"[🤖 منشی سلف] به مخاطب {user_id} پاسخ داده شد.")
    except Exception as e:
        print(f"[!] خطا در ارسال پاسخ منشی: {e}")
