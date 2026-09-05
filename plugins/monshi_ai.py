# -*- coding: utf-8 -*-
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from core.filters import self_cmd
from config import AI_API_KEY, AI_BASE_URL

MONSHI = {"enabled": False, "answered": set()}

@Client.on_message(self_cmd(["منشی"]))
async def monshi_toggle(client: Client, message: Message):
    if "روشن" in message.command_args:
        MONSHI["enabled"] = True
        await message.edit_text("🤖 منشی هوشمند روشن شد.")
    elif "خاموش" in message.command_args:
        MONSHI["enabled"] = False
        MONSHI["answered"].clear()
        await message.edit_text("🛑 منشی خاموش شد.")

@Client.on_message(filters.private & filters.incoming & ~filters.bot)
async def monshi_responder(client: Client, message: Message):
    if not MONSHI["enabled"] or message.from_user.id in MONSHI["answered"]:
        return
    try:
        async with aiohttp.ClientSession() as s:
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "شما منشی رسمی من هستید. بفرمایید فعلا آنلاین نیستم و بعدا پیامشان خوانده می‌شود."},
                    {"role": "user", "content": message.text or "سلام"}
                ]
            }
            async with s.post(f"{AI_BASE_URL}/chat/completions", json=payload, headers={"Authorization": f"Bearer {AI_API_KEY}"}) as r:
                if r.status == 200:
                    res = (await r.json())["choices"][0]["message"]["content"]
                    await message.reply_text(f"🤖 **[منشی هوشمند]**\n\n{res}")
                    MONSHI["answered"].add(message.from_user.id)
                    return
    except Exception:
        pass
    await message.reply_text("در حال حاضر آفلاین هستم. در اولین فرصت پاسخ می‌دهم. 🙏")
    MONSHI["answered"].add(message.from_user.id)
