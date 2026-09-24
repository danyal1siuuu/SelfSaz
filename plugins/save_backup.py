# -*- coding: utf-8 -*-
import os
import aiosqlite
from pyrogram import Client, filters
from pyrogram.types import Message
from core.filters import self_cmd
from config import DB_NAME

@Client.on_message(self_cmd(["save", "سیو", "ذخیره"]))
async def save_restricted(client: Client, message: Message):
    if not message.reply_to_message:
        return await message.edit_text("❌ روی محتوای ضد فوروارد ریپلای کنید.")
    rep = message.reply_to_message
    await message.edit_text("⏳ در حال دانلود و دور زدن محدودیت کپی...")
    try:
        dl_path = await rep.download()
        cap = rep.caption or "📥 ذخیره شده توسط سلف‌ساز"
        if rep.photo:
            await client.send_photo("me", dl_path, caption=cap)
        elif rep.video:
            await client.send_video("me", dl_path, caption=cap)
        elif rep.voice:
            await client.send_voice("me", dl_path, caption=cap)
        elif rep.audio:
            await client.send_audio("me", dl_path, caption=cap)
        elif rep.document:
            await client.send_document("me", dl_path, caption=cap)
        if dl_path and os.path.exists(dl_path):
            os.remove(dl_path)
        await message.edit_text("✅ با موفقیت در Saved Messages ذخیره شد!")
    except Exception as e:
        await message.edit_text(f"❌ خطا در استخراج مدیا: {e}")

@Client.on_message(self_cmd(["دسترسی"]))
async def set_quick_access(client: Client, message: Message):
    args = message.command_args.split(maxsplit=1)
    if not args or not message.reply_to_message:
        return await message.edit_text("❌ دستور را به این شکل بفرستید (ریپلای روی متن):\n`.دسترسی کلمه`")
    trigger = args[0]
    content = message.reply_to_message.text or message.reply_to_message.caption or ""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO auto_replies (owner_id, trigger, response) VALUES (?, ?, ?)", (client.me.id, trigger, content))
        await db.commit()
    await message.edit_text(f"⚡️ دسترسی سریع برای کلید `{trigger}` تنظیم شد.")

@Client.on_message(filters.me & filters.text)
async def execute_quick_access(client: Client, message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT response FROM auto_replies WHERE owner_id = ? AND trigger = ?", (client.me.id, message.text.strip()))
        row = await cursor.fetchone()
    if row:
        await message.edit_text(row[0])
