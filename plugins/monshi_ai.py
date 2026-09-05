# -*- coding: utf-8 -*-
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from config import AI_API_KEY, AI_BASE_URL

@Client.on_message(filters.private & filters.incoming & ~filters.bot)
async def monshi_responder(client: Client, message: Message):
    if not getattr(client, "monshi_active", False):
        return
    
    if not hasattr(client, "monshi_replied"):
        client.monshi_replied = set()

    if message.from_user.id in client.monshi_replied:
        return

    client.monshi_replied.add(message.from_user.id)
    try:
        if AI_API_KEY:
            async with aiohttp.ClientSession() as s:
                payload = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "شما منشی رسمی من هستید. با ادب اطلاع دهید در حال حاضر در دسترس نیستم."},
                        {"role": "user", "content": message.text or "سلام"}
                    ]
                }
                async with s.post(f"{AI_BASE_URL}/chat/completions", json=payload, headers={"Authorization": f"Bearer {AI_API_KEY}"}, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        res = (await r.json())["choices"][0]["message"]["content"]
                        return await message.reply_text(f"🤖 **[منشی خودکار]**\n\n{res}")
    except Exception:
        pass

    await message.reply_text("سلام؛ در حال حاضر آنلاین نیستم. به محض ورود پیامتان را بررسی خواهم کرد. 🙏")
